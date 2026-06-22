#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
BACKUP_DIR="$DATA_DIR/reset-backups/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

move_if_exists() {
  local path="$1"
  if [ -e "$path" ]; then
    mv "$path" "$BACKUP_DIR/"
  fi
}

move_if_exists "$DATA_DIR/redditwatch.db"
move_if_exists "$DATA_DIR/redditwatch.db-journal"
move_if_exists "$DATA_DIR/redditwatch.db-wal"
move_if_exists "$DATA_DIR/redditwatch.db-shm"
move_if_exists "$DATA_DIR/chroma"

(
  cd "$ROOT_DIR/backend"
  python -c "import asyncio, app.models; from app.database import init_db; asyncio.run(init_db())"
)

echo "Runtime data reset complete."
echo "Backup archived at: $BACKUP_DIR"
