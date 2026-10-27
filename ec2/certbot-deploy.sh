#!/bin/sh
# Certbot deploy hook: copy the current certificate where Mosquitto can read it.
# Runs as root in the certbot container; Mosquitto runs as UID/GID 1883.
set -eu
src=${RENEWED_LINEAGE:?certbot sets RENEWED_LINEAGE}
cp "$src/privkey.pem" /out/.privkey.pem.tmp
chown 0:1883 /out/.privkey.pem.tmp
chmod 640 /out/.privkey.pem.tmp
cp "$src/fullchain.pem" /out/.fullchain.pem.tmp
chmod 644 /out/.fullchain.pem.tmp
# Replace the key first: the broker reloads when fullchain.pem changes.
mv /out/.privkey.pem.tmp /out/privkey.pem
mv /out/.fullchain.pem.tmp /out/fullchain.pem
echo "Installed certificate from $src for Mosquitto."
