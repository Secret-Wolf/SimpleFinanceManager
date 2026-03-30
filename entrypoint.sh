#!/bin/sh
set -e
# Fix data directory ownership if mounted from host (e.g. created by root)
chown -R appuser:appuser /app/data
exec gosu appuser python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
