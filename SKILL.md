---
name: eywa
description: >
  Cross-session memory CLI. Use at session start to retrieve context from past sessions
  (eywa get). Use at session end to persist a handoff document for future sessions
  (eywa extract). Use when the user references past work, asks "what was I working on",
  or when you need continuity from a prior session.
---

# Eywa CLI

Eywa extracts structured handoffs at session end and retrieves relevant past context at session start. It bridges the gap between ephemeral sessions by preserving what happened, what was decided, and what's still open.

## Commands

```bash
eywa get                          # 3 most recent sessions
eywa get "mcp routing"            # keyword search
eywa get "topic" --days-back 30 --max 5

eywa extract                      # auto-detect current session
eywa extract 1b2f6f6b             # 8-char short ID
eywa extract 1b2f6f6b-65a6-...   # full UUID

eywa rebuild-index                # rescan all stored handoffs
```

Output goes to stdout (for piping), errors to stderr. Exit code 0 = success, 1 = failure.

## When to Call

**eywa get:**
- Session start (no query) — load recent context
- When the user asks about past work — keyword query
- When you need to recall decisions or context from prior sessions

**eywa extract:**
- Session end — persist what happened for the next session
- After significant milestones mid-session (optional, re-extracts if session changed)
- User explicitly asks to save context

**eywa rebuild-index:**
- After manually editing or deleting handoff files
- If the index file is corrupt or missing
- After bulk imports via eywa-batch

## Output Format

**eywa get** returns markdown:
```markdown
## Eywa: 2 past sessions

# Headline of first session

## What Happened
- Bullet points of work done

## Insights
- Key decisions and learnings

## Open Threads
- Unfinished work and next steps

---

# Headline of second session
...
```

**eywa extract** returns the handoff filename + full handoff content. Handoffs are stored at `$EYWA_DATA_DIR/handoffs/YYYY/MM/DD/<session_id>.md`.

## Session Detection

When no `session_id` is provided, detection uses a 3-strategy fallback:
1. PID tracing (lsof on parent process)
2. CWD-scoped mtime (freshest JSONL in derived project dir)
3. Global mtime (freshest JSONL across all project dirs)

When a `session_id` is provided, Eywa only performs an explicit lookup (full UUID or 8-char short ID) — no heuristic fallback.

Requires JSONL to be modified within 30 seconds. In ambiguous multi-session environments, pass the session_id explicitly.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `EYWA_DATA_DIR` | `~/.eywa` | Handoffs + index storage |
| `EYWA_SESSIONS_DIR` | `~/.claude/projects` | Session JSONL root |
| `EYWA_TASKS_DIR` | `<sessions parent>/tasks` | PID-based session detection |
| `EYWA_CLAUDE_MODEL` | `sonnet` | Model for extraction |
| `EYWA_TIMEZONE` | `UTC` | Timestamp rendering |

## Anti-Patterns

- **Conversational queries.** Bad: "let's continue working on the MCP server". Good: "mcp server". Clean keywords score better.
- **Extracting trivial sessions.** Sessions with no real work produce empty handoffs. Don't force extraction on empty sessions.
- **Calling extract multiple times in quick succession.** Dedup check skips re-extraction if unchanged, but each call still runs detection and conversion.
- **Ignoring exit codes.** Exit 1 means failure. Check `$?`.
- **Setting max > 5.** Capped server-side. More than 3 is rarely useful — context gets diluted.

## Setup

```bash
./setup.sh    # checks Python 3.10+, Node 18+, installs package + extractors
```
