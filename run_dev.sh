#!/usr/bin/env bash
set -e

cleanup() {
    kill "$API_PID" "$ADMIN_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uvicorn kupas.api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!
uvicorn kupas.admin.main:app --host 0.0.0.0 --port 8001 --reload &
ADMIN_PID=$!

wait
