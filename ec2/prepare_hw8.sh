#!/usr/bin/env bash
# Generate a dedicated publisher secret without displaying it or using shell history.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -f runtime/auth/passwd ]] || { echo 'Run the existing setup.sh first.' >&2; exit 1; }
umask 077
mkdir -p runtime/hw8
if [[ ! -s runtime/hw8/password ]]; then
    od -An -N24 -tx1 /dev/urandom | tr -d ' \n' > runtime/hw8/password
    printf '\n' >> runtime/hw8/password
fi
chmod 700 runtime/hw8
chmod 600 runtime/hw8/password
sudo chgrp 1883 runtime/auth/passwd
docker run --rm --user "$(id -u):1883" \
    --mount "type=bind,src=$PWD/runtime/auth,dst=/auth" \
    --mount "type=bind,src=$PWD/runtime/hw8/password,dst=/run/password,readonly" \
    --entrypoint sh eclipse-mosquitto:2.1.2-alpine -ec \
    'mosquitto_passwd -b /auth/passwd hw8-publisher "$(cat /run/password)"'
chmod 640 runtime/auth/passwd
echo 'HW-8 publisher credential is ready; the existing student password is unchanged.'
echo 'Next: docker compose restart mosquitto'
echo 'Then: docker compose --profile hw8 up -d --build hw8-publisher'
