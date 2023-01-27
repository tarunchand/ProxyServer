#!/usr/bin/env python3
# coding=utf-8

import socket
import select
import logging

from threading import Thread

logging.basicConfig(filename='error.log', filemode='w', format='%(levelname)s - %(asctime)s: %(message)s',
                    datefmt='%H:%M:%S', level=logging.ERROR)


class ProxyServer:
    def __init__(self, config):
        self.proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.buffer_size = config.get('BUFFER_SIZE', 1024)
        self.bind_address = config.get('HOST_NAME', '127.0.0.1')
        self.bind_port = config.get('BIND_PORT', 6060)
        self.max_conn = config.get('MAX_CONN', 100)
        self.clients_list = dict()

    def run(self):
        self.proxy.bind((self.bind_address, self.bind_port))
        self.proxy.listen(self.max_conn)
        print("[+] {} - Proxy server is running on port {}".format(self.bind_address, self.bind_port))

        while True:
            client, client_address = self.proxy.accept()
            if not self.clients_list.get(client_address[0], False):
                print("[+] {} Connected".format(client_address[0]))
                self.clients_list[client_address[0]] = client_address[1]
            Thread(target=self.handle_request, args=(client, client_address)).start()

    def handle_request(self, client, client_address):
        try:
            self.handle_request_internal(client, client_address)
        except (IOError, OSError, KeyboardInterrupt, Exception) as ex:
            logging.error(str(ex))

    def handle_request_internal(self, client, client_address):
        buffer_data = client.recv(self.buffer_size)
        head = self.parse_head(buffer_data)
        headers = head["headers"]
        host = headers['host']
        print('\n\n[+] Proxying : ' + str(client_address) + ' ==>> ' + str(host))
        if self.is_http_protocol(host):
            self.handle_http_request(client, head, headers, host)
        else:
            self.handle_non_http_traffic(client, host)

    def handle_http_request(self, client, head, headers, host):
        request = "{}\r\n".format(head["meta"])
        for key, value in headers.items():
            request += "{}: {}\r\n".format(key, value)
        request += "\r\n"
        if "content-length" in headers:
            while len(head["chunk"]) < int(headers["content-length"]):
                head["chunk"] += client.recv(self.buffer_size)

        request = request.encode() + head["chunk"]
        port = 80
        try:
            tmp = head["meta"].split(" ")[1].split("://")[1].split("/")[0]
        except IndexError:
            client.close()
            return
        if tmp.find(":") > -1:
            port = int(tmp.split(":")[1])

        response = self.send_http_request(host, port, request)
        client.sendall(response)
        self.log_req_resp(host, request, response)
        client.close()

    def send_http_request(self, host, port, data):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.connect((socket.gethostbyname(host), port))
        server.sendall(data)
        buffer_data = server.recv(self.buffer_size)
        head = self.parse_head(buffer_data)
        headers = head["headers"]
        response = "{}\r\n".format(head["meta"])
        for key, value in headers.items():
            response += "{}: {}\r\n".format(key, value)
        response += "\r\n"

        if "content-length" in headers:
            while len(head["chunk"]) < int(headers["content-length"]):
                head["chunk"] += server.recv(self.buffer_size)

        response = response.encode() + head["chunk"]
        server.close()
        return response

    def handle_non_http_traffic(self, client, host):
        webserver, port = host.split(':')
        port = int(port)
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.connect((socket.gethostbyname(webserver), port))
        client.sendall(b'HTTP/1.0 200 Connection established\r\n\r\n')
        conns = [client, server]
        done = False
        while not done:
            readers_ready, _, errors = select.select(conns, [], conns)
            if errors:
                break
            if len(readers_ready) == 0:
                break
            for reader in readers_ready:
                data = reader.recv(self.buffer_size)
                if len(data) == 0:
                    done = True
                    break
                if reader is client:
                    out = server
                else:
                    out = client
                if data:
                    out.send(data)
        server.close()
        client.close()

    @staticmethod
    def parse_head(head_request):
        nodes = head_request.split(b"\r\n\r\n")
        heads = nodes[0].split(b"\r\n")
        meta = heads.pop(0).decode("utf-8")
        data = {
            "meta": meta,
            "headers": {},
            "chunk": b""
        }

        if len(nodes) >= 2:
            data["chunk"] = nodes[1]

        for head in heads:
            pieces = head.split(b": ")
            key = pieces.pop(0).decode("utf-8")
            if key.startswith("Connection: "):
                data["headers"][key.lower()] = "close"
            else:
                data["headers"][key.lower()] = b": ".join(pieces).decode("utf-8")
        return data

    @staticmethod
    def is_http_protocol(host):
        host = host.split(':')
        if (len(host) == 1) or (host[1] == 80):
            return True
        return False

    @staticmethod
    def log_req_resp(host, req, resp):
        '''
        delimiter = '\n\n' + '=' * 100 + '\n'
        address_str = '[+] ' + str(host) + '\n'
        print(delimiter + address_str + '[+] Request : \n' + req + '\n' + '[+] Response : \n' + resp + delimiter)
        '''
        req_res = '''
===============================================================================================================

[+] {}

[+] Request : 
{}

[+] Response :
{}

===============================================================================================================
        '''.format(str(host), req, resp)
        print(req_res)


def main():
    config = dict({
        'HOST_NAME': '192.168.1.190',
        'BIND_PORT': 6060,
        'BUFFER_SIZE': 4096,
        'MAX_CONN': 100,
        'CONNECTION_TIMEOUT': 10
    })
    try:
        proxy_server = ProxyServer(config)
        proxy_server.run()
    except socket.error as ex:
        if str(ex).find('Address already in use') != -1:
            print('[!] Address already in use.')
        logging.error(str(ex))
    except (IOError, OSError, KeyboardInterrupt, Exception) as ex:
        logging.error(str(ex))


if __name__ == "__main__":
    main()
