# Eywa MCP Audit Report (2026-02-15)

Scope: audit and update newly added `eywa/cli.py`, `SKILL.md`, `setup.sh`, verify `pyproject.toml` entry points, update `README.md`, and fix issues found during the audit.

## Findings

### `eywa/cli.py`
- Imports: all referenced symbols resolve to existing modules/functions (`eywa.config`, `eywa.detect_session`, `eywa.extract`, `eywa.index`, `eywa.parse`, `eywa.retrieval`, `eywa.session_convert`).
- Argument parsing: subcommands `get`, `extract`, `rebuild-index` are wired correctly; missing subcommand prints help and exits non-zero.
- Extraction pipeline: matches `eywa/server.py::_handle_eywa_extract()` step-for-step:
  - `detect_session()` -> `jsonl_to_markdown()` -> temp markdown file -> `extract_handoff()` -> `save_handoff()` -> `parse_handoff()` -> `handoff_to_index_entry()` -> `update_index()`.
- Issues found:
  - Unhandled exceptions could crash the CLI with a traceback (e.g., missing `extractors/` files, parse/indexing errors).
  - `eywa get` accepted `--days-back <= 0` and `--max <= 0`, producing surprising behavior.

### `SKILL.md`
- Frontmatter: valid YAML frontmatter with `name` and `description`.
- Capability description: consistent with the repo (MCP tools `eywa_get`/`eywa_extract`, CLI `eywa`, index rebuild, session detection strategies, env vars).
- Issue found: claimed a "4-strategy fallback" for auto-detection when no `session_id` is provided, but the actual heuristic chain is 3 strategies (PID tracing, CWD mtime, global mtime). Explicit `session_id` lookup is a separate path with no heuristic fallback.

### `setup.sh`
- Paths: correct (`eywa/extractors`), and safe to re-run.
- Idempotency: `pip install -e .` and `npm install` are re-runnable.
- Issues found:
  - Python version check was incorrect for `python3` versions with major > 3 (e.g. Python 4.x would incorrectly fail).
  - Used `pip` directly (risking wrong interpreter/environment); no fallback if `pip` missing for `python3`.

### `pyproject.toml`
- `project.scripts` includes:
  - `eywa-mcp = "eywa.server:cli"`
  - `eywa = "eywa.cli:main"`
  - `eywa-batch = "eywa.batch_index:main"`
- Entry point wiring matches the codebase (`eywa/server.py` defines `cli()`; `eywa/cli.py` defines `main()`).

## Changes Made

### Robust CLI exit behavior
- Updated `eywa/cli.py`:
  - Clamp `eywa get` arguments to sane ranges: `days_back >= 1`, `1 <= max <= 5`.
  - Wrap `extract` pipeline in `try/except` to ensure clean stderr messages and exit code `1` on failures (mirrors server behavior of returning error text instead of crashing).
  - Wrap `rebuild-index` in `try/except` to return exit code `1` on failure instead of raising.

### Skill doc accuracy
- Updated `SKILL.md`:
  - Correct session detection wording to reflect the real behavior: 3-strategy heuristic fallback when `session_id` is omitted, and explicit lookup only when `session_id` is provided.

### Bootstrap script correctness
- Updated `setup.sh`:
  - Fix Python version check using `sys.version_info >= (3, 10)` rather than major/minor shell comparisons.
  - Use `python3 -m pip install -e .` (more reliable than `pip`).
  - Add a best-effort `python3 -m ensurepip --upgrade` fallback if `pip` is missing for the current `python3`.

### Docs updates (human-facing)
- Updated `README.md` to reflect:
  - New CLI interface: `eywa get`, `eywa extract`, `eywa rebuild-index`.
  - New bootstrap script: `./setup.sh` (recommended install path).
  - The package now serves as both MCP server (`eywa-mcp`) and CLI tool (`eywa`), while keeping existing batch-index (`eywa-batch`) guidance.

### Minor accuracy fix outside the requested 3-file set
- Updated `eywa/server.py` tool description to remove an incorrect claim about the extraction model version and instead describe the actual configured model (`EYWA_CLAUDE_MODEL`, default `sonnet`) and implementation (Claude Agent SDK).

## Verification Performed
- `python3 -m compileall -q eywa` (syntax/import sanity)
- `python3 -c "import eywa.cli, eywa.server"` (import sanity)
- `bash -n setup.sh` (shell syntax)

## Remaining Notes / Risks
- `setup.sh` installs into whatever environment `python3` points to. If the user expects a venv, they should activate it before running the script.
- `eywa extract` still depends on Node + `@anthropic-ai/claude-agent-sdk` runtime configuration (e.g. `ANTHROPIC_API_KEY`), as before; the CLI now fails cleanly if prerequisites are missing.
