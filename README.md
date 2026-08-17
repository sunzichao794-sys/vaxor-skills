# Vaxor Skills

Public, versioned distribution for Vaxor agent integrations. A locally installed
Skill contains no user token, provider credential, or credit authority. It must
obtain a device-code authorization from the Vaxor service before it can create
instances, access assets, run workflows, or export media.

## Available Skills

| Skill | Version | Status | Host |
| --- | --- | --- | --- |
| `create-beauty-video` | `0.4.0` | Stable | Codex |

The `create-beauty-video` Codex package and the shared public connector core
and host adapters are released in `v0.4.0`.

## Host adapters (`v0.4.0`)

| Host | Adapter | Status | Client type | Native protocol |
| --- | --- | --- | --- | --- |
| Codex | Existing `SKILL.md` | Stable | `codex` | Verified |
| ZCode | Markdown/OpenAPI/CLI | Verification | `zcode` | Not verified |
| ChatGPT Work | Markdown/OpenAPI/CLI | Verification | `chatgpt_work` | Not verified |
| WorkBuddy | Markdown/OpenAPI/CLI | Verification | `workbuddy` | Not verified |
| Claude Code | Local command/Portable | Verification | `custom` | Not verified |
| Portable | Markdown/OpenAPI/CLI | Beta | `custom` | Host independent |

The four non-Codex hosts deliberately do not claim native Skill installation.
They must pass real installation, device authorization, Preview, Run,
persisted-result, export and error-boundary verification before being promoted
to Stable.

The public API is the only integration boundary. The host supplies user-owned
creative intent and prompts; Vaxor supplies authorization, instance/resource
ownership, live models, billing, workflow execution and exports.

## Install In Codex

In Codex, ask the built-in installer to install the pinned release:

```text
Install skill `skills/create-beauty-video` from GitHub repository
`sunzichao794-sys/vaxor-skills` at ref `v0.4.0`.
```

For a local Codex runtime that exposes the standard installer script, the
equivalent command is:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo sunzichao794-sys/vaxor-skills \
  --path skills/create-beauty-video \
  --ref v0.4.0
```

Start a new Codex turn after installation. On first use, the Skill opens the
Vaxor website for login and device-code approval. Credentials are stored only on
the user's machine; never paste them into prompts, URLs, plan files, or assets.

## Updates And Revocation

- Pin every production use to an annotated Git tag. Do not install from an
  unreviewed branch.
- Install upgrades only after reviewing the release notes and replacing the
  existing local Skill deliberately. The Codex installer refuses to overwrite a
  Skill directory by design.
- The Vaxor website lists authorized agents and can revoke an authorization.
  Revocation invalidates API access even when the local Skill folder remains.

## Portable adapters

When a host has no verified native Skill protocol, use the adapter under
`adapters/<host>/` or the generic `adapters/portable/` package. These packages
provide Markdown/OpenAPI/CLI instructions and a local Preview descriptor
builder; they never make a generation request by themselves.

All dynamic instance and asset access requires device authorization and the
appropriate scopes. Preview is side-effect free: it does not create a run or
charge credits. The user must explicitly approve the plan before compile/run.

## Host Support

`SKILL.md` is the verified Codex package. The other adapters share the Vaxor
Automation OpenAPI and must not contain provider credentials or duplicate
billing logic. See `catalog.json` for machine-readable status and install
metadata.
