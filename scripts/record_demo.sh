#!/usr/bin/env bash
set -e

PORT=5174
FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../frontend" && pwd)"
DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../demo" && pwd)"

echo "=== DevTrack AI — Playwright Demo Video Recorder ==="
echo "Frontend Dir: $FRONTEND_DIR"
echo "Target Port:  $PORT"
echo "Output Video: $DEMO_DIR/devtrack_ai_demo.webm"
echo "===================================================="

# Ensure audio files are in frontend/public/demo
mkdir -p "$FRONTEND_DIR/public/demo"
cp "$DEMO_DIR/audio"/* "$FRONTEND_DIR/public/demo/"

# Start clean Vite dev server on dedicated port
echo "Starting Vite on port $PORT..."
cd "$FRONTEND_DIR"
npx vite --port $PORT > /dev/null 2>&1 &
VITE_PID=$!

cleanup() {
  echo "Shutting down Vite server (PID: $VITE_PID)..."
  kill $VITE_PID 2>/dev/null || true
}
trap cleanup EXIT

# Wait for Vite to be ready
echo "Waiting for Vite to be ready on port $PORT..."
for i in {1..20}; do
  if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
    echo "Vite is up and responding!"
    break
  fi
  sleep 0.5
done

# Run Playwright demo recording spec
echo "Launching Playwright Chromium video recorder..."
PLAYWRIGHT_BASE_URL="http://localhost:$PORT" npx playwright test record-demo.spec.ts

echo "Recording completed successfully!"
ls -lh "$DEMO_DIR/devtrack_ai_demo.webm"

