import os
import socket
import threading
import mimetypes
from urllib.parse import unquote
from datetime import datetime
import argparse
import time

import os

def get_file_type(filepath):
    _, file_extension = os.path.splitext(filepath)
    return file_extension.lower()


class HttpServer:
    DEFAULT_FILE = "index.html"
    BAD_REQUEST = "error/400.html"
    FORBIDDEN = "error/403.html"
    FILE_NOT_FOUND = "error/404.html"
    METHOD_NOT_SUPPORTED = "error/501.html"

    connected_clients = set()

    def __init__(self, connect, document_root, protocol, debug = False, timeout=10):
        self.connect = connect
        self.document_root = document_root
        self.protocol = protocol
        self.timeout = timeout
        self.debug = debug

        if connect:
            client_ip = connect.getpeername()[0]
            if client_ip not in self.connected_clients:
                self.connected_clients.add(client_ip)
                print(f"Connection opened: {client_ip}")

    def start(self, port, timeout = 500):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.settimeout(timeout)
                server_socket.bind(('localhost', port))
                server_socket.listen(3)
                print(f"Server started.\nListening for connections on port: {port}\n")
                count = 0

                while True:
                    count += 1
                    client_socket, client_address = server_socket.accept()
                    server = HttpServer(client_socket, self.document_root, self.protocol, self.debug)
                    thread = threading.Thread(target=server.run, name = f"Thread-{count}")
                    thread.start()
                    # multi threading in python: GIL is a mechanism that allows one thread 
                    # to execute python bytecode at a time in a single process. 
        except Exception as e:
            print(f"Socket connection timed out: {e}")
        finally:
            server_socket.close()



    def run(self):
        try:
            with self.connect, \
                 self.connect.makefile('r', buffering=1) as in_file, \
                 self.connect.makefile('wb', buffering=0) as out_file:

                visited_url = in_file.readline()

                request_parts = visited_url.split(' ')
                if len(request_parts) < 2:
                    print("Invalid request")
                    self.bad_request(out_file, visited_url)
                    return

                http_method, file_name = request_parts[0], unquote(request_parts[1])

                if self.debug:
                    print("file_name", file_name)
                if (http_method.upper() != "GET") or (not self.is_file_supported(file_name)):
                    self.bad_request(out_file, http_method)
                    return

                file_path = self.get_file_path(file_name)
                if file_path is None:
                    self.file_not_found(out_file, file_name)
                    return

                if not os.access(file_path, os.R_OK):
                    self.file_forbidden(out_file, file_name)
                    return

                http_version = "HTTP/" + self.protocol
                # Take HTTP version input once
                
                if self.debug:
                    print("Current thread name is {} and file opened {}"\
                          .format(threading.current_thread().name, file_path))
                # Serve the file with the determined HTTP version
                self.serve_file(out_file, file_path, http_version=http_version)

                # Close the connection for HTTP/1.0 after a short delay
                if http_version == "HTTP/1.0":
                    time.sleep(2)
                    print("Connection closed for HTTP/1.0")

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.close_connection()

    def is_file_supported(self, filepath):
        _, file_extension = os.path.splitext(filepath)
        file_type = file_extension.lower()
        supported_types = {'.pdf', '.jpeg', '.jpg', '.png', '.txt', '.gif', '.html', '.mp4', '.json', '', '.js', '.css'}
        return file_type in supported_types

    def get_file_path(self, file_name):
        if file_name == '/':
            file_name = self.DEFAULT_FILE
        else:
            file_name = file_name[1:]

        file_path = os.path.normpath(os.path.join(self.document_root, file_name))

        if os.path.exists(file_path):
            return file_path
        else:
            return None

    def serve_file(self, out_file, file_path, responsecode="200 OK", http_version="HTTP/1.1"):
        try:
            if responsecode != "200 OK":
                error_file = open(file_path, 'rb')
            else:
                error_file = open(file_path, 'rb')

            content_type, _ = mimetypes.guess_type(file_path)

            headers = [
                "{} {}".format(http_version, responsecode),
                "Server: Python HTTP Server",
                "Date: {}".format(self.get_current_date()),
                "Content-type: {}".format(content_type),
                "Content-length: {}".format(os.path.getsize(file_path)),
                "",
                ""
            ]
            out_file.write("\r\n".join(headers).encode('utf-8'))

            # Set timeout only for HTTP/1.0 requests
            if http_version == "HTTP/1.0":
                self.connect.settimeout(self.timeout)

            chunk = error_file.read(4096)
            while chunk:
                out_file.write(chunk)
                chunk = error_file.read(4096)
        except Exception as e:
            print(f"Error serving file: {e}")
        finally:
            error_file.close()

    def bad_request(self, out_file, visited_url):
        print(f"HTTP 400 Error: {visited_url} Bad Request!")
        self.serve_file(out_file, self.BAD_REQUEST, "400 BadRequest")

    def file_not_found(self, out_file, file_name):
        print(f"HTTP 404 Error: {file_name} cannot be found!")
        self.serve_file(out_file, self.FILE_NOT_FOUND, "404 FileNotFound")

    def file_forbidden(self, out_file, file_name):
        print(f"HTTP 403 Error: {file_name} Forbidden (No permission)")
        self.serve_file(out_file, self.FORBIDDEN, "403 Forbidden")

    def method_not_supported(self, out_file, http_method):
        print(f"HTTP 501 Error: {http_method} HTTP method not implemented!")
        self.serve_file(out_file, self.METHOD_NOT_SUPPORTED, "501 NotImplemented")

    def get_current_date(self):
        return datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    def close_connection(self):
        try:
            if self.connect:
                client_ip = self.connect.getpeername()[0]
                self.connect.close()

                if client_ip in self.connected_clients:
                    self.connected_clients.remove(client_ip)
                    print(f"Connection closed: {client_ip}")
        except OSError as e:
            if e.errno != 9:
                print(f"Error closing connection: {e}")


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Web Server program")
        parser.add_argument("-document_root", required=True, help="Path to the document root")
        parser.add_argument("-port", type=int, required=True, help="Port number")
        parser.add_argument("--protocol", type=str, default="1.1", required = False, help="Enter HTTP Version (default: 1.1)")
        parser.add_argument("--debug", type=bool, default=False, required = False, help="For multi threading debugging")
        args = parser.parse_args()

        document_root = args.document_root
        port = args.port
        protocol = args.protocol
        debug = args.debug
        if not (8000 <= port <= 9999):
            raise ValueError("Port number must be between 8000 and 9999")

        if not os.path.exists(document_root):
            raise FileNotFoundError(f"Document root {document_root} does not exist")

        if protocol not in {'1.1', '1.0'}:
            raise ValueError("Protocol should be either 1.1 or 1.0")
        
        server = HttpServer(None, document_root, protocol, debug)
        server.start(port)

    except Exception as e:
        print(f"Error: {e}")
