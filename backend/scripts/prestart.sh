#! /usr/bin/env bash

set -e
set -x

# Let the DB start
python app/backend_pre_start.py

# Run migrations
alembic upgrade head

# The agent's working state: LangGraph migrates its own tables, and it cannot
# do so inside the application (D139).
python -m app.prepare_checkpoints

# Create initial data in DB
python app/initial_data.py
