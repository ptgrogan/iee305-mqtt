#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
umask 077
mkdir -p data certs
if [[ ! -e data/configuration.yaml ]]; then
    cp configuration.example.yaml data/configuration.yaml
fi
if [[ ! -e .env ]]; then
    cp .env.example .env
fi
printf '%s\n' 'Local files prepared; existing configuration was preserved.' \
    'Edit .env, copy the broker CA certificate to certs/ca.crt, then run docker compose up -d.'
