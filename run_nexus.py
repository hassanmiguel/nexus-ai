"""Start NEXUS AI with the Windows-friendly event loop and quiet socket error handling.

Run ``python run_nexus.py --host 127.0.0.1 --port 8000`` (or use start_nexus.bat).
"""
from __future__ import annotations

import argparse
import sys
import uvicorn


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the NEXUS AI local server.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--reload', action='store_true', help='Reload on source changes (development).')
    args = parser.parse_args(argv)

    uvicorn.run(
        'backend.main:app',
        host=args.host,
        port=args.port,
        loop='backend.loop:selector_loop_factory',
        reload=args.reload,
        reload_dirs=['backend'] if args.reload else None,
    )


if __name__ == '__main__':
    main()
