import socket
import ssl
from pydoc import cli

server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

server_ctx.load_cert_chain(
    certfile="./server/server.crt", keyfile="./server/server.key"
)

server_ctx.load_verify_locations(cafile="./ca/ca.crt")

server_ctx.verify_mode = ssl.CERT_REQUIRED

HOST = "127.0.0.1"
PORT = 8443
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind((HOST, PORT))
    sock.listen()
    s = server_ctx.wrap_socket(sock, server_side=True)
    while True:
        try:
            conn, addr = s.accept()
            with conn:
                certdict = conn.getpeercert()
                client_cn = ""
                for part in certdict["subject"]:
                    for field, value in part:
                        if field == "commonName":
                            client_cn = value
                data = conn.recv(1024)
                conn.sendall(f"hello {client_cn}\n".encode())
                conn.unwrap()
        except ssl.SSLError as e:
            print(f"rejected: {e}")
