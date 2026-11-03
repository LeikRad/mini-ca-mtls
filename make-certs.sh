#!/usr/bin/env bash
# Regenerates every key and cert in this repo: the root CA, the server and
# client certs, and the broken certs used for the failure scenarios.
# Overwrites anything already there.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p ca server client broken

new_key() {
    openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$1"
}

# new_csr <key> <subject> <csr>
new_csr() {
    openssl req -new -key "$1" -subj "$2" -out "$3"
}

# self_sign <csr> <key> <ext> <crt>
self_sign() {
    openssl x509 -req -in "$1" -signkey "$2" -extfile "$3" -days 3650 -out "$4"
}

# sign <csr> <ca-crt> <ca-key> <ext> <crt> [extra x509 flags...]
sign() {
    local csr=$1 ca_crt=$2 ca_key=$3 ext=$4 crt=$5
    shift 5
    if (($# == 0)); then
        set -- -days 365
    fi
    openssl x509 -req -in "$csr" -CA "$ca_crt" -CAkey "$ca_key" \
        -extfile "$ext" -out "$crt" "$@"
}

echo "== root CA"
new_key ca/ca.key
new_csr ca/ca.key "/CN=Mini Root CA" ca/ca.csr
self_sign ca/ca.csr ca/ca.key ext/ca.ext ca/ca.crt

echo "== server"
new_key server/server.key
new_csr server/server.key "/CN=localhost" server/server.csr
sign server/server.csr ca/ca.crt ca/ca.key ext/server.ext server/server.crt

echo "== client"
new_key client/client.key
new_csr client/client.key "/CN=client1" client/client.csr
sign client/client.csr ca/ca.crt ca/ca.key ext/client.ext client/client.crt

echo "== broken: expired client cert"
sign client/client.csr ca/ca.crt ca/ca.key ext/client.ext broken/expired.crt \
    -not_before 20200101000000Z -not_after 20200102000000Z

echo "== broken: evil CA and a client cert it signed"
new_key broken/evil-ca.key
new_csr broken/evil-ca.key "/CN=Evil CA" broken/evil-ca.csr
self_sign broken/evil-ca.csr broken/evil-ca.key ext/ca.ext broken/evil-ca.crt

new_key broken/evil-client.key
new_csr broken/evil-client.key "/CN=client1" broken/evil-client.csr
sign broken/evil-client.csr broken/evil-ca.crt broken/evil-ca.key ext/client.ext broken/evil-client.crt

echo "== checks"
openssl verify -CAfile ca/ca.crt server/server.crt client/client.crt
