#!/usr/bin/env bash
# Obtain the broker's Let's Encrypt certificate and create the MQTT users.
# Safe to re-run: an unexpired certificate and existing passwords are kept.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
broker_host=${1:-}
email=${2:-}
if [[ -z "$broker_host" || ${#broker_host} -gt 253 || ! "$broker_host" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ||
      "$broker_host" =~ ^[0-9.]+$ ]]; then
    echo 'Usage: bash setup.sh BROKER_DNS_NAME [EMAIL] (DNS name only, no URL or port)' >&2
    exit 1
fi
for command in docker sudo; do
    command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done
docker info >/dev/null
docker compose version
docker compose config --quiet
if docker compose ps --status running --services | grep -qx certbot; then
    echo 'Stop the running stack first (docker compose down); setup needs port 80.' >&2
    exit 1
fi
# Let's Encrypt no longer sends expiry email; an address only helps account recovery.
if [[ -n "$email" ]]; then
    account=(--email "$email")
else
    account=(--register-unsafely-without-email)
fi
# Port 80 must be open to the internet for the HTTP-01 challenge.
docker compose run --rm --service-ports --entrypoint certbot certbot \
    certonly --standalone --non-interactive --agree-tos "${account[@]}" \
    --keep-until-expiring --cert-name broker -d "$broker_host"
docker compose run --rm --entrypoint sh -e RENEWED_LINEAGE=/etc/letsencrypt/live/broker \
    certbot /hooks/deploy.sh
umask 077
mkdir -p runtime/auth
sudo chgrp 1883 runtime/auth
chmod 750 runtime/auth
chmod 644 mosquitto.conf acl
if [[ -e runtime/auth/passwd ]]; then
    printf '%s\n' 'runtime/auth/passwd already exists, so the instructor and student passwords' \
        'from the earlier setup are kept. To set a new one: bash password.sh student'
else
    printf '%s\n' 'Choose a distinct instructor password. Avoid single quotes for the local .env example.'
    bash password.sh instructor
    printf '%s\n' 'Choose a different class password for the student account.'
    bash password.sh student
fi
printf '%s\n' 'Setup complete. Start the broker with: docker compose up -d' \
    'Share only the student password, through Canvas; never distribute runtime/.'
