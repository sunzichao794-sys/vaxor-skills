#!/usr/bin/env python3
"""Build a safe Vaxor Preview request for any portable host.

This CLI only validates and serializes a request descriptor. It never sends a
network request, creates a workflow, or spends credits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import HOST_ADAPTERS, build_preview_request, redact_secrets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=sorted(HOST_ADAPTERS), default="portable")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--plan", required=True, help="JSON file or - for stdin")
    parser.add_argument("--idempotency-key")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read() if args.plan == "-" else Path(args.plan).expanduser().read_text(encoding="utf-8")
        plan = json.loads(raw)
        request = build_preview_request(
            instance_id=args.instance_id,
            plan=plan,
            idempotency_key=args.idempotency_key,
        )
        output = {
            "host": args.host,
            "adapter": HOST_ADAPTERS[args.host],
            "request": request,
            "sideEffect": "preview_only",
        }
        print(json.dumps(redact_secrets(output), ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
