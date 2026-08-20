#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the canonical static QEI preview.")
    parser.add_argument("--directory", default="site")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    directory = str(Path(args.directory).resolve())

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **handler_kwargs):
            super().__init__(*handler_args, directory=directory, **handler_kwargs)

        def end_headers(self) -> None:
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            super().end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Serving {directory} at http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
