#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
umask 077
mkdir -p data
if [[ ! -e data/configuration.yaml ]]; then
    cp configuration.example.yaml data/configuration.yaml
fi
if [[ ! -e .env ]]; then
    cp .env.example .env
fi
printf '%s\n' 'Local files prepared; existing configuration was preserved.' \
    'Edit .env, then run docker compose up -d.'
