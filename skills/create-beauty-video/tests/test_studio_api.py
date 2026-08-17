import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "studio_api.py"
spec = importlib.util.spec_from_file_location("studio_api", MODULE_PATH)
studio_api = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = studio_api
spec.loader.exec_module(studio_api)


class PublicSkillCliTests(unittest.TestCase):
    def test_rejects_legacy_model_identity_in_plan(self):
        with self.assertRaises(studio_api.ApiError):
            studio_api.require_public_plan({
                "schemaVersion": 1,
                "name": "legacy",
                "steps": [{
                    "id": "step-1",
                    "kind": "image",
                    "title": "Legacy",
                    "prompt": "user prompt",
                    "scenarioModelId": "private-model",
                    "capability": "text2image",
                    "collectionId": "images",
                }],
            })

    def test_projects_forbidden_response_fields_before_printing(self):
        projected = studio_api.project_command_response("compile", {
            "status": "compiled",
            "workflowInstanceId": "workflow-1",
            "definition": {"providerKey": "PRIVATE_PROVIDER"},
            "capabilitySnapshot": {"scenarioModelId": "PRIVATE_MODEL"},
            "creditEstimate": {"estimatedCredits": 12},
            "quoteConfirmations": [{"stepId": "step-1", "quoteConfirmation": "qc_public"}],
        })
        serialized = json.dumps(projected)
        self.assertIn("workflow-1", serialized)
        self.assertNotIn("PRIVATE_", serialized)
        self.assertNotIn("definition", serialized)
        self.assertNotIn("capabilitySnapshot", serialized)

    def test_projects_nested_model_and_preview_fields_with_allowlists(self):
        models = studio_api.project_command_response("models", {
            "models": [{
                "modelRef": "mr_public",
                "label": "Public model",
                "providerKey": "PRIVATE_PROVIDER",
                "capabilities": [{
                    "capability": "text2image",
                    "available": True,
                    "input": {"image": {"required": False, "providerKey": "PRIVATE_PROVIDER"}},
                    "parameters": {"aspectRatioOptions": ["9:16"], "policyRevision": "PRIVATE_REVISION"},
                }],
            }],
        })
        preview = studio_api.project_command_response("preview", {
            "status": "preview",
            "plan": {
                "schemaVersion": 1,
                "name": "Public plan",
                "steps": [{
                    "id": "step-1", "kind": "image", "title": "Public", "prompt": "user prompt",
                    "modelRef": "mr_public", "capability": "text2image", "collectionId": "images",
                    "parameters": {"aspectRatio": "9:16", "aspect_ratio": "PRIVATE_INTERNAL"},
                    "scenarioModelId": "PRIVATE_MODEL",
                }],
            },
            "validation": {"errors": [{"code": "PUBLIC", "message": "public", "providerKey": "PRIVATE_PROVIDER"}]},
            "creditEstimate": {"estimatedCredits": 12, "policyRevision": "PRIVATE_REVISION"},
        })
        serialized = json.dumps({"models": models, "preview": preview})
        self.assertIn("mr_public", serialized)
        self.assertNotIn("PRIVATE_", serialized)
        self.assertNotIn("scenarioModelId", serialized)
        self.assertNotIn("aspect_ratio", serialized)
        self.assertNotIn("policyRevision", serialized)

    def test_dry_run_validates_public_plan_without_network_access(self):
        plan = {
            "schemaVersion": 1,
            "name": "public",
            "steps": [{
                "id": "step-1",
                "kind": "image",
                "title": "Public",
                "prompt": "user prompt",
                "modelRef": "mr_public",
                "capability": "text2image",
                "collectionId": "images",
                "parameters": {"aspectRatio": "9:16"},
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            args = studio_api.parser().parse_args([
                "preview", str(plan_path), "--dry-run", "--base-url", "https://example.test/api/automation",
            ])
            output = StringIO()
            with redirect_stdout(output):
                result = studio_api.run_command(args)
        self.assertEqual(result, {"dryRun": True})
        serialized = output.getvalue()
        self.assertIn("modelRef", serialized)
        self.assertNotIn("scenarioModelId", serialized)


if __name__ == "__main__":
    unittest.main()
