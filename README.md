# Vaxor Skills

Public, versioned distribution for Vaxor agent integrations. A locally installed
Skill contains no user token, provider credential, or credit authority. It must
obtain a device-code authorization from the Vaxor service before it can create
instances, access assets, run workflows, or export media.

## Available Skills

| Skill | Version | Status | Host |
| --- | --- | --- | --- |
| `create-beauty-video` | `0.2.0` | Stable | Codex |

## Install In Codex

In Codex, ask the built-in installer to install the pinned release:

```text
Install skill `skills/create-beauty-video` from GitHub repository
`sunzichao794-sys/vaxor-skills` at ref `v0.2.0`.
```

For a local Codex runtime that exposes the standard installer script, the
equivalent command is:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo sunzichao794-sys/vaxor-skills \
  --path skills/create-beauty-video \
  --ref v0.2.0
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

## Host Support

`SKILL.md` is a Codex package. ChatGPT Work, ZCode, and WorkBuddy will receive
their own thin host adapters after each platform's installation and OAuth/tool
contract has been validated. All adapters share the Vaxor Automation OpenAPI;
they must not contain provider credentials or duplicate billing logic.
