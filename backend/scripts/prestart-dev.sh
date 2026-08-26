#! /usr/bin/env bash

# prestart.sh plus the development fixtures. Personal storage and PostgreSQL
# both start without anything useful to explore, so seeding is part of bringing
# the development stack up rather than a command to remember. It is deliberately
# not in prestart.sh: sample data has no place in a deployment.

set -e
set -x

bash scripts/prestart.sh

python -m app.seed_database /app/sql
python -m app.seed_storage
