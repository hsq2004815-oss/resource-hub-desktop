"""Entry point for the Resource Hub backend process.

Spawned by the Flutter client; speaks the JSON Lines protocol on stdin/stdout.

    python backend/main.py [base_dir]

``base_dir`` is where ``sites.json`` / ``folders.json`` / ``settings.json`` live.
It defaults to the repository root when run from source, and should be passed
explicitly (the executable's directory) when packaged.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from resource_hub_core.protocol import JsonLinesServer, configure_stdio  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    base_dir = (
        Path(args[0]).resolve() if args else Path(__file__).resolve().parent.parent
    )
    configure_stdio()
    server = JsonLinesServer(base_dir, in_stream=sys.stdin, out_stream=sys.stdout)
    return server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
