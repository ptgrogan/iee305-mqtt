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
echo "Password for $username saved."
# The running broker keeps its loaded passwords until it reloads the file.
# SIGHUP reloads it without disconnecting anyone; already-connected clients stay
# connected until they reconnect, so restart the broker to revoke them too.
if docker compose ps --status running --services 2>/dev/null | grep -qx mosquitto; then
    # Compose reports this as "Killed", but SIGHUP only makes Mosquitto reload.
    docker compose kill -s HUP mosquitto >/dev/null 2>&1
    printf '%s\n' 'The broker reloaded the password file; new logins use the new password.' \
        'To also disconnect clients logged in with the old password: docker compose restart mosquitto'
else
    echo 'The broker is not running; it will use this password when started.'
fi
