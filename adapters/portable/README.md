# Portable Vaxor Adapter

Use this adapter when a host does not expose a verified native Skill format.
It is a host-neutral Markdown/OpenAPI/CLI contract, not a claim of native
integration. Copy the instructions below into the host's tool/rules file and
use the existing public client or an OpenAPI-compatible HTTP client.

## Required sequence

1. Set `VAXOR_AUTOMATION_BASE_URL` to the Vaxor `/api/automation` root.
2. Start device authorization with the host's declared `clientType` and the
   smallest required scopes.
3. Open only the verification URL returned by Vaxor and poll the device token.
4. Read instances/assets only after the user approves the device authorization.
5. Author a generic `ExternalWorkflowPlan` and call `POST /v2/studio/plans/preview`.
6. Show the Preview result and wait for explicit approval before compile/run.
7. Verify persisted run result and export status before reporting completion.

The adapter never accepts bearer tokens in URLs, object keys, signed URLs,
Provider credentials, private Vaxor profiles, or private prompt artifacts.

## CLI reference

The Codex reference client is a transport example and can be used by a
portable host where Python is available:

```bash
python3 skills/create-beauty-video/scripts/studio_api.py auth-start \
  --client-type custom --client-instance-id "<host-instance-id>" \
  --display-name "Portable Vaxor Adapter" \
  --scope studio:instances:read --scope studio:assets:read \
  --scope studio:models:read --scope studio:workflows:write \
  --scope studio:runs:read --scope studio:runs:write \
  --scope studio:exports:read
```

For ZCode, ChatGPT Work and WorkBuddy use their public client type. Claude
Code currently uses `custom` because the Vaxor auth contract has no native
`claude_code` value. This is intentionally marked Verification.

To build a no-side-effect Preview descriptor locally:

```bash
python3 adapters/portable/adapter.py --host portable \
  --instance-id "<authorized-instance-id>" \
  --plan skills/create-beauty-video/examples/good_plan.json
```
