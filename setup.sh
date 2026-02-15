#!/bin/bash
# eywa-mcp setup
# Checks prerequisites, installs package + Node extractors, verifies commands.
# Safe to run multiple times (idempotent).

set -euo pipefail

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  RED='\033[0;31m'
  BOLD='\033[1m'
  RESET='\033[0m'
else
  GREEN='' YELLOW='' RED='' BOLD='' RESET=''
fi

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}!${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BOLD}eywa-mcp setup${RESET}"
echo ""

# --- 1. Check Python 3.10+ ---
echo -e "${BOLD}Checking Python...${RESET}"
if command -v python3 &>/dev/null; then
  if python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    PY_VERSION="$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")"
    ok "Python ${PY_VERSION}"
  else
    PY_VERSION="$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")"
    fail "Python ${PY_VERSION} found, but 3.10+ is required"
    exit 1
  fi
else
  fail "Python 3 is not installed"
  echo ""
  echo "  Install Python 3.10+:"
  echo "    brew install python@3.12"
  echo ""
  exit 1
fi

# --- 2. Check Node.js 18+ ---
echo ""
echo -e "${BOLD}Checking Node.js...${RESET}"
if command -v node &>/dev/null; then
  NODE_MAJOR=$(node -e "console.log(process.versions.node.split('.')[0])")
  NODE_VERSION=$(node --version 2>/dev/null || echo "unknown")
  if [ "$NODE_MAJOR" -ge 18 ]; then
    ok "Node.js ${NODE_VERSION}"
  else
    fail "Node.js ${NODE_VERSION} found, but 18+ is required"
    exit 1
  fi
else
  fail "Node.js is not installed"
  echo ""
  echo "  Install Node.js 18+:"
  echo "    brew install node"
  echo ""
  exit 1
fi

# --- 3. Install Python package ---
echo ""
echo -e "${BOLD}Installing Python package...${RESET}"
cd "${SCRIPT_DIR}"
if ! python3 -m pip --version >/dev/null 2>&1; then
  warn "pip not found for python3; attempting ensurepip"
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
fi
python3 -m pip install -e .
ok "Python package installed (editable)"

# --- 4. Install Node extractor dependencies ---
echo ""
echo -e "${BOLD}Installing Node extractor dependencies...${RESET}"
cd "${SCRIPT_DIR}/eywa/extractors"
npm install --silent 2>/dev/null || npm install
cd "${SCRIPT_DIR}"
ok "Node dependencies installed"

# --- 5. Verify commands ---
echo ""
echo -e "${BOLD}Verifying commands...${RESET}"

if command -v eywa-mcp &>/dev/null; then
  ok "eywa-mcp command available"
else
  warn "eywa-mcp not on PATH (may need shell restart or pip install with --user)"
fi

if command -v eywa &>/dev/null; then
  ok "eywa command available"
else
  warn "eywa not on PATH (may need shell restart or pip install with --user)"
fi

# --- 6. Configuration summary ---
echo ""
echo -e "${BOLD}Configuration...${RESET}"

EYWA_DATA="${EYWA_DATA_DIR:-~/.eywa}"
EYWA_SESSIONS="${EYWA_SESSIONS_DIR:-~/.claude/projects}"

ok "Data dir: ${EYWA_DATA}"
ok "Sessions dir: ${EYWA_SESSIONS}"

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  ok "ANTHROPIC_API_KEY is set (needed for runtime extraction)"
else
  warn "ANTHROPIC_API_KEY not set (eywa extract requires Claude SDK access)"
fi

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  ok "OPENROUTER_API_KEY is set (needed for batch indexing)"
else
  warn "OPENROUTER_API_KEY not set (only needed for eywa-batch)"
fi

# --- Done ---
echo ""
echo -e "${GREEN}${BOLD}Setup complete.${RESET}"
echo ""
echo "  Quick start:"
echo "    eywa get                         # recent sessions"
echo "    eywa get \"mcp routing\"           # keyword search"
echo "    eywa extract                     # extract current session"
echo "    eywa rebuild-index               # rebuild from stored handoffs"
echo ""
echo "  MCP server:"
echo "    eywa-mcp                         # start MCP stdio server"
echo ""
