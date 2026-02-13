"""Eywa MCP package."""


def cli():
    """Entry point — lazy import to avoid mcp namespace collision."""
    from .server import cli as _cli

    _cli()


__all__ = ["cli"]
