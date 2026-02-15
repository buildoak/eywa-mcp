"""Eywa CLI -- synchronous entry point for get, extract, and rebuild-index."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from .config import HANDOFFS_DIR, INDEX_PATH, LOG_LEVEL, ensure_data_dirs
from .detect_session import detect_session
from .extract import extract_handoff, save_handoff
from .index import handoff_to_index_entry, rebuild_index, update_index
from .parse import parse_handoff
from .retrieval import EywaRetrieval
from .session_convert import jsonl_to_markdown

logger = logging.getLogger("eywa")


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def cmd_get(args: argparse.Namespace) -> int:
    """Retrieve past session handoffs."""
    try:
        days_back = max(int(args.days_back), 1)
        max_handoffs = min(max(int(args.max), 1), 5)
        retrieval = EywaRetrieval()
        result = retrieval.get_handoffs(
            query=args.query,
            days_back=days_back,
            max_handoffs=max_handoffs,
        )
        print(result)
        return 0
    except FileNotFoundError as exc:
        print(f"Eywa not initialized: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract a handoff from current or specified session."""
    try:
        ensure_data_dirs()

        # 1. Detect session
        jsonl_path, detection_error = detect_session(args.session_id)
        if not jsonl_path:
            print(
                f"Session detection failed: {detection_error or 'unknown'}",
                file=sys.stderr,
            )
            return 1

        short_id = jsonl_path.stem[:8]

        # 2. Dedup check -- skip if JSONL hasn't changed since last handoff
        try:
            retrieval = EywaRetrieval()
            current_entry = retrieval.index.get("handoffs", {}).get(short_id)
            if current_entry:
                date_str = str(current_entry.get("date", ""))
                try:
                    year, month, day = date_str.split("-")
                    handoff_path = HANDOFFS_DIR / year / month / day / f"{short_id}.md"
                    if (
                        handoff_path.exists()
                        and jsonl_path.stat().st_mtime <= handoff_path.stat().st_mtime
                    ):
                        print(f"Handoff already exists for {short_id} (session unchanged)")
                        return 0
                    logger.info("Re-extracting %s: session updated since last handoff", short_id)
                except ValueError:
                    pass
        except FileNotFoundError:
            pass  # First run -- no index yet

        # 3. Convert JSONL to markdown
        markdown = jsonl_to_markdown(jsonl_path)
        if not markdown:
            print(f"Session {short_id} has no extractable content", file=sys.stderr)
            return 1

        # 4. Extract handoff via Node extractor
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(markdown)
                temp_path = Path(tmp.name)

            handoff_content = extract_handoff(temp_path)
            if not handoff_content:
                print(
                    f"Extraction failed for {short_id}. Check Node and Claude SDK setup.",
                    file=sys.stderr,
                )
                return 1

            # 5. Save handoff
            handoff_path = save_handoff(handoff_content, temp_path, HANDOFFS_DIR)
            if not handoff_path:
                print(f"Failed to save handoff for {short_id}", file=sys.stderr)
                return 1
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

        # 6. Update index
        parsed = parse_handoff(handoff_path)
        entry = handoff_to_index_entry(parsed)
        index_session_id = str(parsed.get("session_id", short_id))

        if not update_index(entry, index_session_id, INDEX_PATH):
            print(f"Handoff saved but indexing failed for {index_session_id}", file=sys.stderr)
            return 1

        print(f"Handoff extracted: {handoff_path.name}")
        print()
        print(handoff_content)
        return 0
    except FileNotFoundError as exc:
        print(f"Extraction error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Extraction error: {exc}", file=sys.stderr)
        return 1


def cmd_rebuild_index(args: argparse.Namespace) -> int:
    """Rebuild the handoff index from scratch."""
    del args
    try:
        ensure_data_dirs()
        index = rebuild_index(HANDOFFS_DIR, INDEX_PATH)
        count = index.get("meta", {}).get("handoff_count", 0)
        print(f"Index rebuilt: {count} handoffs indexed")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(prog="eywa", description="Eywa session memory CLI")
    sub = parser.add_subparsers(dest="command")

    # eywa get
    p_get = sub.add_parser("get", help="Retrieve past session handoffs")
    p_get.add_argument("query", nargs="?", default=None, help="Search keywords")
    p_get.add_argument("--days-back", type=int, default=14, help="How far back to search (default: 14)")
    p_get.add_argument("--max", type=int, default=3, help="Max handoffs to return (default: 3, max: 5)")

    # eywa extract
    p_ext = sub.add_parser("extract", help="Extract handoff from current or specified session")
    p_ext.add_argument("session_id", nargs="?", default=None, help="Session UUID or 8-char short ID")

    # eywa rebuild-index
    sub.add_parser("rebuild-index", help="Rebuild handoff index from all stored handoffs")

    args = parser.parse_args()

    if args.command == "get":
        sys.exit(cmd_get(args))
    elif args.command == "extract":
        sys.exit(cmd_extract(args))
    elif args.command == "rebuild-index":
        sys.exit(cmd_rebuild_index(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
