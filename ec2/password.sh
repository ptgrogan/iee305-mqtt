#!/usr/bin/env bash
# Run on the Amazon Linux 2023 EC2 host. Prompting keeps passwords out of shell history.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
username=${1:-}
case "$username" in
    instructor|student) ;;
    *) printf '%s\n' 'Usage: bash password.sh instructor|student' >&2; exit 1 ;;
esac
[[ -d runtime/auth ]] || { echo 'Run setup.sh first.' >&2; exit 1; }
args=()
if [[ ! -e runtime/auth/passwd ]]; then
    args+=(-c)
fi
docker run --rm -it --user "$(id -u):$(id -g)" \
    --mount "type=bind,src=$PWD/runtime/auth,dst=/auth" \
    --entrypoint mosquitto_passwd eclipse-mosquitto:2.1.2-alpine \
    "${args[@]}" /auth/passwd "$username"
# The container's mosquitto user is UID/GID 1883. Preserve the host owner.
sudo chgrp 1883 runtime/auth/passwd
chmod 640 runtime/auth/passwd
printf '%s\n' 'Password saved. If the broker is running, restart it to revoke existing connections:' \
    'docker compose restart mosquitto'
