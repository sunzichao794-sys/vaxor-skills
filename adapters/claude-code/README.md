# Claude Code adapter (Verification)

Claude Code has no verified native Vaxor Skill protocol in this release. Use
the Portable Markdown/OpenAPI/CLI adapter or load the instructions as a local
Claude Code command. This is not represented as a native Claude plugin.

The public auth DTO currently accepts `custom`, so use `clientType=custom` for
device authorization. Keep the adapter marked `Verification` until Claude
Code local loading and the complete public API smoke sequence have passed.
