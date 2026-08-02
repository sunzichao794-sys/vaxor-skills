---
name: create-beauty-video
description: Use when a user provides a beauty-video script, reference video, image or video assets, or asks Codex to plan, generate, record, schedule, or export a shot-based beauty video through Tianzuo Prompt Studio. Analyze source media, propose user-confirmed asset roles, preserve character/product/style continuity, compile first-frame and motion prompts, select currently available models through the automation API, and report recorded instance, run, and export states. Do not call provider APIs directly.
---

# Create Beauty Video

## Role

This skill is the orchestration layer between Codex and the Tianzuo Prompt Studio
workflow. Codex does the creative analysis and prompt writing; the server owns
authentication, model capability checks, credits, queues, asset persistence, and
the final export. Provider APIs and provider credentials never appear in this
skill.

Generation and prompt-writing rules are selected from versioned rule profiles;
they are not built into the API client. Record `workflowProfile`,
`profileVersion`, and `rulesHash` in every new plan. Treat `ugc-commerce-v1` as
a reserved workflow identifier until the user supplies and approves its rule
file. Existing market-specific prompt profiles remain opt-in references only.
Never infer final prompt rules from a profile name.

## Workflow

Follow these stages in order. Stop at the first stage that needs a user decision
and show the exact pending decision rather than silently guessing.

1. `inspect_input`: identify the script, reference video, arbitrary images,
   existing folders, and any constraints (duration, aspect ratio, language,
   platform, budget). Treat every supplied file as semantically unknown until
   inspected.
2. `analyze_reference`: run the local video analyzer for technical metadata,
   representative frames, and candidate shot boundaries. Codex then inspects
   the extracted frames and writes the semantic shot breakdown.
3. `propose_asset_roles`: propose roles for supplied or generated assets. A
   role is a suggestion, not a hard-coded taxonomy. Ask the user to confirm,
   rename, merge, or remove roles. Common suggestions are product, person,
   scene, first frame, and clip, but any user-defined role is valid.
4. `build_continuity_bible`: record only confirmed visual facts for person,
   product, scene, lighting, color, lens, makeup state, wardrobe, and style.
   Mark unknowns explicitly; do not invent a face or product specification.
5. `select_rule_profile`: present available workflow and prompt profiles, their
   version/hash, and unresolved rule status. Require the user to select one.
   Stop before prompt generation when the selected profile is only a scaffold.
6. `build_shot_plan`: split the reference into independently renderable clips.
   Preserve source timing, camera intent, and transitions. Keep each clip to
   use the selected profile's action rules. When no approved profile supplies
   an action budget, mark it unresolved instead of assuming a fixed count.
7. `build_product_angle_refs`: generate a product angle reference only when a
   shot needs an angle that is not already available. Store it in the existing
   user-selected collection and link it to the shot.
8. `build_first_frames`: compile image prompts from the continuity bible and
   shot state. Generate candidates, compare them against the bible, and lock
   one first frame per clip before video generation.
9. `build_video_prompts`: write motion, camera, timing, and transition
   instructions relative to the locked first frame using the selected approved
   prompt profile. Do not mutate confirmed person, product, or scene facts.
10. `select_models`: query the server's current image and video availability
   projection. Present capability, duration, aspect, resolution, cost, and
   health constraints. Never embed a fixed provider/model list. The server
   revalidates the selected scenario model at submission time.
11. `compile_workflow`: send the confirmed plan, asset map, model selections,
    output collection bindings, and credit limit to the automation API. The
    compiler produces a versioned node graph but does not create paid tasks.
    Only submit a run after the user explicitly confirms the preview.
12. `run_and_record`: create or reuse the requested Prompt Studio instance,
    ensure the chosen existing folders, start the workflow, poll run events,
    and report actual asset, timeline, and export records. A queue response is
    not a successful generation.
13. `resume_or_retry`: resume from the recorded failed node/run. Reuse locked
    first frames and successful upstream results. Supply an explicit
    `retryOfRunId` when retrying; do not regenerate the whole plan by default.

Read detailed guidance only when needed:

- Frame and continuity rules: `references/beauty-video-methodology.md`
- API paths, payloads, scopes, and state semantics: `references/automation-api.md`
- Plan and prompt field shapes: `references/prompt-templates.md`
- Continuity-bible field guidance: `references/continuity-bible.md`
- Indonesia real-person prompt profile: `references/indonesia-real-person-prompt-profile.md`
- Versioned rule selection and pending-profile behavior: `references/workflow-profiles.md`
- OpenAPI 3.1 tool contract: `references/automation-openapi.json`

## User Confirmation Gates

The following are mandatory confirmation gates on a first run:

- proposed asset roles and which existing collection/folder receives each asset;
- shot boundaries, durations, and the action budget from the selected rule profile;
- continuity facts that were inferred rather than supplied;
- selected models, estimated and maximum credits, and fallback policy;
- the final dry-run preview before any paid generation;
- output collection bindings for generated references, first frames, clips,
  and final export;
- final export settings before composition/export.

For a scheduled run, these decisions must already be persisted in the workflow
template/version. If the new input changes the reference or continuity bible,
pause the schedule and request a new confirmation instead of applying stale
assumptions.

## Deterministic Helpers

Use the bundled scripts for repeatable work:

- `scripts/analyze_reference_video.py INPUT --frames-dir DIR` emits technical
  metadata, candidate boundaries, and frame paths as JSON.
- `scripts/validate_shot_plan.py PLAN.json` checks structural fields and applies
  profile-specific action validation only when that profile is selected.
- `scripts/studio_api.py` is a standard-library client for the automation API.
  Use `auth-start` then `auth-poll` to connect an account. Use `--dry-run` while
  compiling and always pass an idempotency key for a mutating request.

The scripts read `TIANZUO_AUTOMATION_BASE_URL`. After device authorization they
store rotating tokens in `~/.config/tianzuo/automation-credentials.json` with
mode `0600`; `TIANZUO_AUTOMATION_TOKEN` remains a development/service-account
compatibility path. Do not put credentials in prompts, plan files, reference
files, URLs, or asset metadata.

Request `ui-links` after creating an instance or run. Open only the server-
returned `instanceUrl`, `assetManagerUrl`, `workflowUrl`, `runUrl`, or
`exportUrl` with the available browser tool. Never synthesize these routes or
append a token. If the host has no browser tool, return the link to the user.

## Failure and Audit Rules

Return structured errors with the stage, request id, run id (when known), and
whether a retry is safe. Preserve the plan hash and idempotency key in the
workflow run metadata. Distinguish:

- a rejected plan (no generation started);
- a queued/running task (not yet successful);
- a failed node (resume/retry from that node);
- a completed generation with a failed composition/export.

Never claim success from HTTP 2xx, a queue id, or a build result alone. Verify
the persisted instance, assets, workflow run, timeline version, and export
records before reporting completion.

The server is the authority for ownership, billing, folder persistence, model
capabilities, and workflow state. Keep creative reasoning in Codex and
deterministic side effects in the API.
