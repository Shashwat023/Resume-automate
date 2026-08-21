#!/usr/bin/env bash
# Run the Career-Ops React frontend in development mode.
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
fi
npm install
npm run dev
