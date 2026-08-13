#!/usr/bin/env python3
"""Offline contract tests for the public multi-host Skill package."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import HOST_ADAPTERS, build_preview_request, redact_secrets, validate_external_plan  # noqa: E402


GOOD_PLAN = json.loads(
    (ROOT / "skills/create-beauty-video/examples/good_plan.json").read_text(encoding="utf-8")
)


class CoreContractTests(unittest.TestCase):
    def test_all_hosts_are_explicitly_statused(self) -> None:
        self.assertEqual(set(HOST_ADAPTERS), {"codex", "zcode", "chatgpt_work", "workbuddy", "claude_code", "portable"})
        self.assertEqual(HOST_ADAPTERS["codex"]["status"], "stable")
        for host in ("zcode", "chatgpt_work", "workbuddy", "claude_code"):
            self.assertEqual(HOST_ADAPTERS[host]["status"], "verification")
            self.assertFalse(HOST_ADAPTERS[host]["adapter"] == "native_skill")

    def test_good_plan_builds_side_effect_free_preview(self) -> None:
        self.assertEqual(validate_external_plan(GOOD_PLAN), [])
        request = build_preview_request(instance_id="instance-1", plan=GOOD_PLAN)
        self.assertEqual(request["path"], "/v2/studio/plans/preview")
        self.assertEqual(request["body"], {"plan": GOOD_PLAN})
        self.assertEqual(request["instanceId"], "instance-1")
        self.assertEqual(request["sideEffect"], "preview_only")
        self.assertIn("idempotencyKey", request)

    def test_private_fields_are_rejected(self) -> None:
        bad = dict(GOOD_PLAN)
        bad["rulesHash"] = "must-not-cross-public-boundary"
        errors = validate_external_plan(bad)
        self.assertTrue(any("private field" in error for error in errors))

    def test_redaction_covers_credentials_and_storage(self) -> None:
        safe = redact_secrets({"accessToken": "secret", "objectKey": "private", "name": "visible"})
        self.assertEqual(safe["accessToken"], "[REDACTED]")
        self.assertEqual(safe["objectKey"], "[REDACTED]")
        self.assertEqual(safe["name"], "visible")


if __name__ == "__main__":
    unittest.main()
