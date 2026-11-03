import socket
import ssl

client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

client_ctx.load_cert_chain(
    certfile="./client/client.crt", keyfile="./client/client.key"
)

client_ctx.load_verify_locations(cafile="./ca/ca.crt")

HOST = "127.0.0.1"
PORT = 8443

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    s = client_ctx.wrap_socket(sock, server_hostname="localhost")
    s.connect((HOST, PORT))
    s.sendall("hello world".encode())
    rep = s.recv(1024)
    print(rep.decode(), end="")
    s.unwrap()
