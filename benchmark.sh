#!/usr/bin/env bash
# ============================================================================
# FlowCore — Benchmark Tool
# ============================================================================
# Measures:
#   1. Python startup time
#   2. Config load time
#   3. API response time
#   4. Database query time
# ============================================================================
set -euo pipefail

CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}=============================================="
echo "  FlowCore Benchmark"
echo "==============================================${NC}"
echo ""

# ── 1. Python startup ────────────────────────────────────────────────────
echo "Python startup time..."
START=$(python3 -c "import time; print(time.time())")
END=$(python3 -c "import time; print(time.time())")
ELAPSED=$(echo "$END - $START" | bc -l)
echo "  $ELAPSED seconds"

# ── 2. Config load ───────────────────────────────────────────────────────
echo "Config load time..."
CONFIG_TIME=$(python3 -c "
import time
start = time.time()
from config.loader import load_config
cfg = load_config()
elapsed = time.time() - start
print(f'{elapsed:.4f}')
" 2>/dev/null || echo "error")
echo "  ${CONFIG_TIME}s"

# ── 3. Database init ─────────────────────────────────────────────────────
echo "Database init time..."
DB_TIME=$(python3 -c "
import asyncio, time
from config.loader import get_config
from runtime.core import init_database

async def test():
    cfg = get_config()
    start = time.time()
    await init_database(cfg)
    elapsed = time.time() - start
    print(f'{elapsed:.4f}')

asyncio.run(test())
" 2>/dev/null || echo "error")
echo "  ${DB_TIME}s"

# ── 4. API health endpoint ───────────────────────────────────────────────
echo "API health endpoint time..."
# Start API in background, measure, then stop
python3 flowcore.py serve &
API_PID=$!
sleep 2

if kill -0 "$API_PID" 2>/dev/null; then
    API_TIME=$(python3 -c "
import asyncio, time, httpx

async def test():
    start = time.time()
    async with httpx.AsyncClient() as client:
        resp = await client.get('http://127.0.0.1:8000/api/health')
        elapsed = time.time() - start
        print(f'{elapsed:.4f}')

asyncio.run(test())
" 2>/dev/null || echo "error")
    kill "$API_PID" 2>/dev/null || true
    echo "  ${API_TIME}s"
else
    echo "  (API failed to start — skipping)"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}==============================================${NC}"
echo "  Benchmark complete"
echo -e "${CYAN}==============================================${NC}"
