#! /usr/bin/env bash

set -e
set -x

cd backend
FASTAPI_ENV=development uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
mv openapi.json frontend/
bun run --filter frontend generate-client
# Только сгенерированный клиент: линтер его игнорирует, поэтому формат ему
# ставит prettier. По всему src/ его гонять нельзя — prettier и правила
# форматирования ESLint расходятся, и такой прогон переформатировал бы
# половину проекта заодно с генерацией.
bun run --filter frontend format:client
