"""Backward-compatible script entry point for the packaged evidence CLI."""

from pbl_docintel.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
