#!/usr/bin/env bash
# Run as ec2-user on Amazon Linux 2023 after installing Docker.
# Uses Docker's manual CLI-plugin installation method, with a pinned checksum.
# https://github.com/docker/compose/releases/tag/v5.6.0
set -euo pipefail
if [[ "$(uname -s)" != Linux ]]; then
    echo 'Run this installer on the Linux EC2 host.' >&2
    exit 1
fi
for command in docker curl sha256sum install mktemp; do
    command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }
done
if docker compose version >/dev/null 2>&1; then
    echo 'Compose is already installed; preserving the existing installation.'
    docker compose version
    exit 0
fi
compose_version=v5.6.0
compose_arch=$(uname -m)
case "$compose_arch" in
    x86_64) compose_sha256=40343e21ca777173e69cff5dbafeb37c6f81f3b0d57d9e597f036e95eb63e76a ;;
    aarch64) compose_sha256=733ec76717ceb59052a9609b9dadfb523b2df8eab57a54212872d10a58078ea2 ;;
    *) echo "Unsupported EC2 architecture: $compose_arch" >&2; exit 1 ;;
esac
compose_download=$(mktemp)
trap 'rm -f -- "$compose_download"' EXIT
curl --fail --location --retry 3 \
    "https://github.com/docker/compose/releases/download/$compose_version/docker-compose-linux-$compose_arch" \
    --output "$compose_download"
printf '%s  %s\n' "$compose_sha256" "$compose_download" | sha256sum --check -
mkdir -p "$HOME/.docker/cli-plugins"
install -m 0755 "$compose_download" "$HOME/.docker/cli-plugins/docker-compose"
docker compose version
