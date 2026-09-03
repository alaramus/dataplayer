#! /usr/bin/env bash

# prestart.sh plus the development fixtures. Personal storage and PostgreSQL
# both start without anything useful to explore, so seeding is part of bringing
# the development stack up rather than a command to remember. It is deliberately
# not in prestart.sh: the application's own database is not a demonstration.
#
# The scripts are no longer mounted: they ship inside the postgres adapter,
# because a service started automatically is filled with the same two files.

set -e
set -x

bash scripts/prestart.sh

python -m app.seed_database
python -m app.seed_storage
