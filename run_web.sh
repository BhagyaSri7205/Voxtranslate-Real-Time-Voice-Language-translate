#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d venv ] || { python3 -m venv venv && . venv/bin/activate && pip install -r requirements-web.txt; }
. venv/bin/activate
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env; }
python web/server.py
