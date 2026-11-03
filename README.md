# mini-ca-mtls

A small certificate authority and mutual TLS setup built by hand with openssl and Python's `ssl` module. I made it to understand PKI.
Once the intended path worked, I broke it on purpose to see how each failure looks from both sides of the connection.

## What's in here

| Path             | What it is                                                                               |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `ext/ca.ext`     | Root CA profile. Can sign certs (`keyCertSign`), but not other CAs (`pathlen:0`).        |
| `ext/server.ext` | Server profile. `serverAuth`, valid for `localhost` and `127.0.0.1`.                     |
| `ext/client.ext` | Client profile. `clientAuth` only, no hostname.                                          |
| `make-certs.sh`  | Regenerates every key and cert, including the broken ones.                               |
| `server.py`      | mTLS server. Requires a client cert signed by the CA and replies with the client's CN.   |
| `client.py`      | mTLS client. Flags let you swap in broken certs, a different CA or a different hostname. |

Keys and certs are not committed. `make-certs.sh` rebuilds them.

## Run it

Needs openssl 3.4 or newer (for `-not_before` / `-not_after`) and Python 3.

```sh
./make-certs.sh

python3 server.py        # terminal 1
python3 client.py        # terminal 2
hello client1
```

`client.py` options:

```
--cert       client certificate   (default client/client.crt)
--key        client private key   (default client/client.key)
--ca         CA to trust          (default ca/ca.crt)
--hostname   name to expect       (default localhost)
```

## Breaking it

| #   | What's wrong                     | Who rejects | Client sees                                                  | Server sees                              |
| --- | -------------------------------- | ----------- | ------------------------------------------------------------ | ---------------------------------------- |
| 1   | Client cert expired              | server      | alert 45 `certificate expired`, at `recv`                    | `certificate has expired`                |
| 2   | Client cert signed by another CA | server      | alert 48 `unknown ca`, at `recv`                             | `unable to get local issuer certificate` |
| 3   | Client trusts another CA         | client      | `self-signed certificate in certificate chain`, at `connect` | alert 48 `unknown ca`                    |
| 4   | Wrong hostname                   | client      | `Hostname mismatch`, at `connect`                            | alert 42 `bad certificate`               |
| 5   | No client cert                   | server      | alert 116 `certificate required`                             | `peer did not return a certificate`      |

The rule behind all of them: the side that checks a cert is the side that rejects it. The server checks the client's cert, and the client checks the server's cert and hostname. The side doing the check gets the full reason. The other side only gets a TLS alert code.

### 1. Expired client cert

```sh
python3 client.py --cert broken/expired.crt
```

The cert is valid from 2020-01-01 to 2020-01-02. Same key, same CA, only the dates are different.

```
client: ssl.SSLError: [SSL: SSLV3_ALERT_CERTIFICATE_EXPIRED] ssl/tls alert certificate expired
server: rejected / abandoned: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired
```

The client fails at `recv`, after `connect` already returned. In TLS 1.3 the client finishes its half of the handshake before the server has checked the client cert, so the rejection only shows up on the first read. In TLS 1.2 it would have failed inside the handshake.

The `SSLV3_` prefix is just history. Alert 45 was defined in SSL 3.0 and openssl names alerts after the version that introduced them. The connection as TLS 1.3.

### 2. Client cert from an unknown CA

```sh
python3 client.py --cert broken/evil-client.crt --key broken/evil-client.key
```

`make-certs.sh` creates a second CA called `Evil CA` and uses it to sign a client cert with the CN `client1`, the same name as the real client.

```
client: ssl.SSLError: [SSL: TLSV1_ALERT_UNKNOWN_CA] tlsv1 alert unknown ca
server: rejected / abandoned: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

The server reads the issuer name (`CN=Evil CA`), looks for a cert with that subject in its trust store and finds nothing,so it can't build a chain. This is openssl error 20. The signature never even gets checked.

Using the name `client1` doesn't help the attacker. Names are only used to find the issuer. What proves a cert is the signature,and the evil CA's key can't produce a signature that verifies against my CA.

You can see the same thing without a server:

```sh
openssl verify -CAfile broken/evil-ca.crt broken/evil-client.crt   # OK
openssl verify -CAfile ca/ca.crt broken/evil-client.crt            # error 20
```

The cert is fine in the evil CA's world. Whether a cert is valid depends on who is checking it.

### 3. Client trusts the wrong CA

```sh
python3 client.py --ca broken/evil-ca.crt
```

Now the client is the one doing the rejecting.

```
client: ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain
server: rejected / abandoned: [SSL: TLSV1_ALERT_UNKNOWN_CA] tlsv1 alert unknown ca
```

This fails inside `connect`, because the client checks the server's cert during the handshake.

I expected error 20 again, but got error 19. It turns out the Python server sends the root CA along with its own cert. I only gave it `server.crt`, but openssl fills in the chain from the CAs loaded with `load_verify_locations`. You can see it with:

```sh
openssl s_client -connect 127.0.0.1:8443 -cert client/client.crt -key client/client.key -showcerts
```

```
 0 s:CN=localhost       i:CN=Mini Root CA
 1 s:CN=Mini Root CA    i:CN=Mini Root CA
```

So the client could build the full chain up to a root. It just doesn't trust that root. A CA cert that arrives in the handshake is never trusted on its own, otherwise anyone could send their own root along with their cert.
Trust only comes from the local store.

### 4. Wrong hostname

```sh
python3 client.py --hostname example.com
```

```
client: ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'example.com'.
server: rejected / abandoned: [SSL: SSLV3_ALERT_BAD_CERTIFICATE] ssl/tls alert bad certificate
```

The chain, dates and CA are all fine. The client compares the name it asked for (`server_hostname`) with the cert's `subjectAltName` (`DNS:localhost, IP:127.0.0.1`). It still connects to `127.0.0.1`, but the address isn't what gets checked.

`openssl verify` doesn't check hostnames unless you ask:

```sh
openssl verify -CAfile ca/ca.crt server/server.crt                            # OK
openssl verify -CAfile ca/ca.crt -verify_hostname example.com server/server.crt  # error 62: hostname mismatch
```

Without this check, any cert from a CA you trust would be accepted for any server. The chain proves a trusted CA vouched for the key. The hostname check proves the key belongs to the server you meant to reach.

### 5. No client cert

```sh
printf x | openssl s_client -connect 127.0.0.1:8443 -CAfile ca/ca.crt -quiet
```

```
client: tlsv13 alert certificate required ... SSL alert number 116
server: rejected / abandoned: [SSL: PEER_DID_NOT_RETURN_A_CERTIFICATE] peer did not return a certificate
```

`CERT_REQUIRED` in `server.py` (or `-Verify 1` in `openssl s_server`) is what turns plain TLS into mutual TLS.

### Bonus: certs used for the wrong job

```sh
openssl verify -CAfile ca/ca.crt -purpose sslclient client/client.crt   # OK
openssl verify -CAfile ca/ca.crt -purpose sslserver client/client.crt   # error 26: unsuitable certificate purpose
```

`extendedKeyUsage = clientAuth` means the client cert can't be used to pretend to be a server, even though it's signed by the right CA.
