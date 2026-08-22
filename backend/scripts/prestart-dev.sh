#! /usr/bin/env bash

# prestart.sh plus the development fixtures. A personal directory starts empty,
# and frontend/tests/files.spec.ts expects a known set of samples, so seeding is
# part of bringing the development stack up rather than a command to remember.
# It is deliberately not in prestart.sh: sample files have no place in a
# deployment.

set -e
set -x

bash scripts/prestart.sh

python -m app.seed_storage
