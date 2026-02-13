"""Detect the active Claude Code session JSONL file.

Detection strategy (ordered fallback chain):
1. Explicit session_id -- search all project dirs for matching JSONL (full UUID or 8-char short ID)
2. PID tracing -- MCP server's PPID -> Claude's open file descriptors -> session UUID
3. CWD-scoped mtime -- most recently modified JSONL in derived project dir
4. Global mtime fallback -- freshest JSONL across all project dirs

When explicit session_id is provided, ONLY that strategy is used -- no fallback to heuristics.
This prevents picking the wrong session in multi-session environments.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from .config import SESSIONS_DIR, TASKS_DIR

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHORT_ID_RE = re.compile(r"^[0-9a-f]{8}$")
STALENESS_WINDOW = 30  # seconds


def _project_dirs() -> list[Path]:
    """List project directories, skipping symlinks and sorbent dirs."""
    if not SESSIONS_DIR.is_dir():
        return []
    dirs: list[Path] = []
    for d in SESSIONS_DIR.iterdir():
        if not d.is_dir():
            continue
        if d.is_symlink():
            continue
        if "sorbent" in d.name.lower():
            continue
        dirs.append(d)
    return dirs


def _find_jsonls(directory: Path) -> list[Path]:
    """Find JSONL files in a directory, deduped by inode."""
    seen_inodes: set[int] = set()
    results: list[Path] = []
    for f in directory.glob("*.jsonl"):
        if not f.is_file():
            continue
        inode = f.stat().st_ino
        if inode in seen_inodes:
            continue
        seen_inodes.add(inode)
        results.append(f)
    return results


def _freshest_jsonl(jsonls: list[Path], max_age: float = STALENESS_WINDOW) -> tuple[Path | None, str | None]:
    """Find the most recently modified JSONL within max_age seconds of now.

    Returns (path, None) on unique match, (None, error) on ambiguity or no match.
    """
    if not jsonls:
        return None, "no JSONL files found"

    now = time.time()
    candidates: list[tuple[Path, float]] = []
    for f in jsonls:
        try:
            mtime = f.stat().st_mtime
            age = now - mtime
            if age <= max_age:
                candidates.append((f, mtime))
        except OSError:
            continue

    if not candidates:
        return None, f"no JSONL modified within {max_age}s"

    candidates.sort(key=lambda x: x[1], reverse=True)

    if len(candidates) == 1:
        return candidates[0][0], None

    # Multiple candidates -- only accept if top one is clearly freshest (>2s gap)
    if candidates[0][1] - candidates[1][1] > 2.0:
        return candidates[0][0], None

    return None, f"ambiguous: {len(candidates)} JSONLs modified within {max_age}s (parallel sessions?)"


def _by_explicit_id(session_id: str) -> tuple[Path | None, str | None]:
    """Strategy 1: Search all project dirs for a JSONL matching session_id.

    Accepts both full UUIDs and 8-char short IDs (prefix match).
    """
    # Full UUID -- direct lookup
    if UUID_RE.fullmatch(session_id):
        for d in _project_dirs():
            candidate = d / f"{session_id}.jsonl"
            if candidate.is_file():
                return candidate, None
        return None, f"session {session_id} not found in any project dir"

    # Short ID (8 hex chars) -- prefix match against all JSONLs
    if SHORT_ID_RE.fullmatch(session_id):
        matches: list[Path] = []
        for d in _project_dirs():
            for f in _find_jsonls(d):
                if f.stem.startswith(session_id):
                    matches.append(f)
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"ambiguous short_id {session_id}: matches {len(matches)} sessions"
        return None, f"session {session_id} not found in any project dir"

    return None, f"invalid session_id format: {session_id}"


def _by_pid_tracing() -> tuple[Path | None, str | None]:
    """Strategy 2: Trace PPID -> Claude's open FDs -> session UUID in tasks dir."""
    ppid = os.getppid()
    if ppid <= 1:
        return None, "PPID is init/launchd, cannot trace"

    try:
        result = subprocess.run(
            ["lsof", "-Fn", "-p", str(ppid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, "lsof failed or not available"

    if result.returncode != 0:
        return None, f"lsof returned {result.returncode}"

    tasks_dir_string = str(TASKS_DIR)
    for line in result.stdout.splitlines():
        if not line.startswith("n"):
            continue
        path_str = line[1:]  # strip the 'n' prefix
        if tasks_dir_string not in path_str:
            continue
        match = UUID_RE.search(path_str)
        if match:
            session_id = match.group(0)
            found_path, _ = _by_explicit_id(session_id)
            if found_path:
                return found_path, None
            return None, f"session UUID {session_id} found via PID but no JSONL exists"

    return None, "no tasks FD found in parent process"


def _cwd_project_dir() -> Path | None:
    """Derive Claude project directory from CWD."""
    encoded = str(Path.cwd()).replace("/", "-")
    candidate = SESSIONS_DIR / encoded
    if candidate.is_dir() and not candidate.is_symlink():
        return candidate
    return None


def _by_cwd_mtime() -> tuple[Path | None, str | None]:
    """Strategy 3: CWD-scoped most recent JSONL."""
    project_dir = _cwd_project_dir()
    if not project_dir:
        return None, "could not derive project dir from CWD"

    return _freshest_jsonl(_find_jsonls(project_dir))


def _by_global_mtime() -> tuple[Path | None, str | None]:
    """Strategy 4: Freshest JSONL across all project dirs."""
    all_jsonls: list[Path] = []
    for d in _project_dirs():
        all_jsonls.extend(_find_jsonls(d))
    return _freshest_jsonl(all_jsonls)


def detect_session(explicit_session_id: str | None = None) -> tuple[Path | None, str | None]:
    """Detect the currently active Claude Code session.

    Returns (jsonl_path, None) on success or (None, error_message) on failure.

    When explicit_session_id is provided, ONLY explicit lookup is attempted.
    No fallback to heuristics -- this prevents picking the wrong session
    in multi-session environments (5+ concurrent sessions).

    When no session_id is provided, heuristic chain:
    1. PID tracing via lsof
    2. CWD-scoped mtime
    3. Global mtime fallback
    """
    if explicit_session_id:
        path, err = _by_explicit_id(explicit_session_id)
        if path:
            return path, None
        return None, f"explicit_id: {err}" if err else "explicit_id: unknown error"

    strategies: list[tuple[str, Callable[[], tuple[Path | None, str | None]]]] = [
        ("pid_tracing", _by_pid_tracing),
        ("cwd_mtime", _by_cwd_mtime),
        ("global_mtime", _by_global_mtime),
    ]

    errors: list[str] = []
    for name, fn in strategies:
        path, err = fn()
        if path:
            return path, None
        if err:
            errors.append(f"{name}: {err}")

    return None, "; ".join(errors) if errors else "no detection strategies available"
