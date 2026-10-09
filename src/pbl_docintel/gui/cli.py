"""Start the optional, read-only local workspace."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        import uvicorn
        from .server import create_app
    except ImportError:
        parser.exit(1, 'Install the optional GUI: python -m pip install -e ".[gui]"\n')
    try:
        app = create_app(args.workspace)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Workspace cannot open: {error}\n")
    print(f"Research evidence workspace: http://127.0.0.1:{args.port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
