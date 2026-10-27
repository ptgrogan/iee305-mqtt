#!/usr/bin/env bash
# Initial setup only: creates a private teaching CA, broker certificate, and users.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
broker_host=${1:-}
if [[ -z "$broker_host" || ${#broker_host} -gt 253 || ! "$broker_host" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
    echo 'Usage: bash setup.sh EC2_PUBLIC_DNS_OR_IPV4 (hostname only, no URL or port)' >&2
    exit 1
fi
for command in docker openssl sudo; do
    command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done
docker info >/dev/null
docker compose version
if [[ -e runtime ]]; then
    echo 'runtime/ already exists. Setup will not replace keys or accounts.' >&2
    echo 'Use password.sh to rotate passwords; see README for certificate renewal.' >&2
    exit 1
fi
san="DNS:$broker_host"
if [[ "$broker_host" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    san="IP:$broker_host"
fi
umask 077
mkdir -p runtime/private runtime/certs runtime/auth
printf '%s\n' "$broker_host" > runtime/broker-host.txt
openssl req -x509 -newkey rsa:3072 -noenc -sha256 -days 365 \
    -keyout runtime/private/ca.key -out runtime/certs/ca.crt \
    -subj '/CN=IEE305 Lecture 20 Teaching CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign'
openssl req -new -newkey rsa:2048 -noenc \
    -keyout runtime/certs/server.key -out runtime/private/server.csr \
    -subj "/CN=$broker_host"
cat > runtime/private/server.ext <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$san
EOF
openssl x509 -req -sha256 -days 90 \
    -in runtime/private/server.csr \
    -CA runtime/certs/ca.crt -CAkey runtime/private/ca.key -CAcreateserial \
    -extfile runtime/private/server.ext -out runtime/certs/server.crt
openssl verify -CAfile runtime/certs/ca.crt runtime/certs/server.crt
sudo chgrp 1883 runtime/auth runtime/certs runtime/certs/*
chmod 750 runtime/auth runtime/certs
chmod 644 runtime/certs/ca.crt runtime/certs/server.crt
chmod 640 runtime/certs/server.key
chmod 644 mosquitto.conf acl
printf '%s\n' 'Choose a distinct instructor password. Avoid single quotes for the local .env example.'
bash password.sh instructor
printf '%s\n' 'Choose a different class password for the student account.'
bash password.sh student
printf '%s\n' 'Setup complete. Start the broker with: docker compose up -d' \
    'Distribute ONLY runtime/certs/ca.crt, the hostname, and the student login to students.'
