#!/usr/bin/env bash
# Helper commands for the Test Data Manager (Mac and Linux).
# Usage: bash tdm.sh <command>
set -e
cd "$(dirname "$0")"

case "$1" in
  setup)
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python create_db.py
    echo "Setup done. Start the app with: bash tdm.sh run"
    ;;
  reset)
    .venv/bin/python create_db.py
    echo "Database rebuilt from db/schema.sql and db/seed.sql."
    ;;
  run)
    .venv/bin/uvicorn backend.app:app --reload
    ;;
  test)
    .venv/bin/python -m unittest discover -s tests -v
    ;;
  import-dry)
    .venv/bin/python tools/import_legacy.py data/legacy_sample.csv --vehicle RUP-EV-26 --dry-run
    ;;
  import)
    .venv/bin/python tools/import_legacy.py data/legacy_sample.csv --vehicle RUP-EV-26
    ;;
  *)
    echo "Usage: bash tdm.sh {setup|reset|run|test|import-dry|import}"
    exit 1
    ;;
esac