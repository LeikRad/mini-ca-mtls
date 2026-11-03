import argparse
import socket
import ssl

parser = argparse.ArgumentParser(description="mTLS test client")
parser.add_argument("--cert", default="./client/client.crt", help="client certificate")
parser.add_argument("--key", default="./client/client.key", help="client private key")
parser.add_argument("--ca", default="./ca/ca.crt", help="CA to trust for the server cert")
parser.add_argument("--hostname", default="localhost", help="name to check against the server cert")
args = parser.parse_args()

client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

client_ctx.load_cert_chain(certfile=args.cert, keyfile=args.key)

client_ctx.load_verify_locations(cafile=args.ca)

HOST = "127.0.0.1"
PORT = 8443

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    s = client_ctx.wrap_socket(sock, server_hostname=args.hostname)
    s.connect((HOST, PORT))
    s.sendall("hello world".encode())
    rep = s.recv(1024)
    print(rep.decode(), end="")
    s.unwrap()
