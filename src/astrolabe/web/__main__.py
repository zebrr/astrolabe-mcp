"""Entry point: python -m astrolabe.web."""

import argparse

from astrolabe.web.app import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Astrolabe Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8420, help="Bind port (default: 8420)")
    args = parser.parse_args()
    main(host=args.host, port=args.port)
