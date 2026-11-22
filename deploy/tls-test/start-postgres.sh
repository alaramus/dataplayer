#!/bin/sh
# A PostgreSQL that speaks only TLS, for the backend suite (D446). On first
# start it makes a CA, a server certificate for pg-tls, redis-tls, localhost
# and 127.0.0.1, and client certificates for the role `certuser` (one key
# plain, one encrypted under `dataplayer`), into /certs, which git ignores.
# redis-tls uses the same server certificate.
set -eu

certs=/certs
if [ ! -f "$certs/ca.crt" ]; then
  mkdir -p "$certs"
  cd "$certs"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 3650 \
    -subj "/CN=DataPlayer test CA" -keyout ca.key -out ca.crt
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -subj "/CN=pg-tls" -keyout server.key -out server.csr
  printf "subjectAltName=DNS:pg-tls,DNS:redis-tls,DNS:localhost,IP:127.0.0.1\n" > server.ext
  openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -days 3650 -extfile server.ext -out server.crt
  openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
    -subj "/CN=certuser" -keyout client.key -out client.csr
  openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -days 3650 -out client.crt
  openssl pkcs8 -topk8 -in client.key -passout pass:dataplayer -out client-encrypted.key
  rm -f ./*.csr server.ext
  # Test material only: readable by the Redis container's user as well.
  chmod 644 ./*.key
fi

# PostgreSQL refuses a key anybody else may read.
install -o postgres -g postgres -m 600 "$certs/server.key" /var/lib/postgresql/server.key
install -o postgres -g postgres -m 644 "$certs/server.crt" /var/lib/postgresql/server.crt
install -o postgres -g postgres -m 644 "$certs/ca.crt" /var/lib/postgresql/ca.crt

cat > /var/lib/postgresql/pg_hba_tls.conf <<'HBA'
local   all       all                  trust
hostssl all       certuser  all        cert
hostssl all       all       all        scram-sha-256
host    all       all       all        reject
HBA
chown postgres:postgres /var/lib/postgresql/pg_hba_tls.conf

mkdir -p /docker-entrypoint-initdb.d
printf "CREATE ROLE certuser LOGIN;\n" > /docker-entrypoint-initdb.d/certuser.sql

exec docker-entrypoint.sh postgres \
  -c ssl=on \
  -c ssl_cert_file=/var/lib/postgresql/server.crt \
  -c ssl_key_file=/var/lib/postgresql/server.key \
  -c ssl_ca_file=/var/lib/postgresql/ca.crt \
  -c hba_file=/var/lib/postgresql/pg_hba_tls.conf
