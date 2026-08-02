#!/usr/bin/env python3
"""Validate the stable, provider-neutral BeautyVideoPlan shape."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

INDONESIA_REAL_PERSON_PROFILE = "id_tiktok_beauty_ugc_real_person_v1"
RULE_HASH_PREFIXES = ("sha256:", "draft:")


def read_json(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("plan root must be an object")
    return value


def field(obj: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in obj:
            return obj[name]
    return None


def non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(errors: list[str], obj: dict[str, Any], prefix: str, *names: str) -> None:
    if not non_empty_text(field(obj, *names)):
        errors.append(f"{prefix}.{names[0]} is required by the Indonesia real-person prompt profile")


def require_object(errors: list[str], obj: dict[str, Any], prefix: str, *names: str) -> dict[str, Any]:
    value = field(obj, *names)
    if not isinstance(value, dict) or not value:
        errors.append(f"{prefix}.{names[0]} must be a non-empty object")
        return {}
    return value


def validate_indonesia_prompt_facts(
    shot: dict[str, Any],
    prefix: str,
    duration_value: float,
    actions: Any,
    errors: list[str],
) -> None:
    facts = field(shot, "promptFacts", "prompt_facts")
    if not isinstance(facts, dict) or not facts:
        errors.append(f"{prefix}.promptFacts is required by {INDONESIA_REAL_PERSON_PROFILE}")
        return

    require_text(errors, facts, f"{prefix}.promptFacts", "startState", "start_state")
    require_text(errors, facts, f"{prefix}.promptFacts", "audioMode", "audio_mode")
    prompt_duration = field(facts, "durationSeconds", "duration_seconds")
    try:
        prompt_duration_value = float(prompt_duration)
    except (TypeError, ValueError):
        prompt_duration_value = 0
    if prompt_duration_value <= 0:
        errors.append(f"{prefix}.promptFacts.durationSeconds must be a positive number")
    elif duration_value > 0 and abs(prompt_duration_value - duration_value) > 0.001:
        errors.append(f"{prefix}.promptFacts.durationSeconds must equal durationSec")

    if not isinstance(actions, list) or len(actions) != 1:
        errors.append(f"{prefix}.actions must contain exactly one primary action for Indonesia real-person UGC")

    primary_action = require_object(
        errors, facts, f"{prefix}.promptFacts", "primaryAction", "primary_action"
    )
    for key in ("name", "start", "path", "end", "pace"):
        require_text(errors, primary_action, f"{prefix}.promptFacts.primaryAction", key)
    window = field(primary_action, "actionWindowSeconds", "action_window_seconds")
    if (
        not isinstance(window, list)
        or len(window) != 2
        or any(not isinstance(value, (int, float)) for value in window)
        or float(window[0]) < 0
        or float(window[1]) <= float(window[0])
        or (prompt_duration_value > 0 and float(window[1]) > prompt_duration_value)
    ):
        errors.append(
            f"{prefix}.promptFacts.primaryAction.actionWindowSeconds must be an increasing window inside the clip"
        )

    person_visible = field(facts, "personVisible", "person_visible") is not False
    if person_visible:
        anchors = field(facts, "identityAnchors", "identity_anchors")
        if not isinstance(anchors, list) or not any(non_empty_text(value) for value in anchors):
            errors.append(f"{prefix}.promptFacts.identityAnchors must list visible approved-reference facts")
        require_object(errors, facts, f"{prefix}.promptFacts", "makeupState", "makeup_state")
        camera = require_object(errors, facts, f"{prefix}.promptFacts", "camera")
        require_text(errors, camera, f"{prefix}.promptFacts.camera", "shotSize", "shot_size")
        require_text(errors, camera, f"{prefix}.promptFacts.camera", "gazeAtT0", "gaze_at_t0")
        require_text(errors, camera, f"{prefix}.promptFacts.camera", "movement")
        lighting = require_object(errors, facts, f"{prefix}.promptFacts", "lighting")
        require_text(errors, lighting, f"{prefix}.promptFacts.lighting", "keyDirection", "key_direction")
        require_text(errors, lighting, f"{prefix}.promptFacts.lighting", "quality")
        require_text(errors, lighting, f"{prefix}.promptFacts.lighting", "whiteBalance", "white_balance")
        expression = require_object(errors, facts, f"{prefix}.promptFacts", "expressionArc", "expression_arc")
        for key in ("baseline", "trigger", "reaction", "recovery"):
            require_text(errors, expression, f"{prefix}.promptFacts.expressionArc", key)
        references = field(facts, "referenceAssetIds", "reference_asset_ids")
        if not isinstance(references, list) or not any(non_empty_text(value) for value in references):
            errors.append(f"{prefix}.promptFacts.referenceAssetIds must preserve approved reference order")

    product = require_object(errors, facts, f"{prefix}.promptFacts", "productState", "product_state")
    visible = product.get("visible")
    if not isinstance(visible, bool):
        errors.append(f"{prefix}.promptFacts.productState.visible must be boolean")
    elif visible:
        for camel, snake in (
            ("angleAssetId", "angle_asset_id"),
            ("openState", "open_state"),
            ("primaryHand", "primary_hand"),
            ("grip", "grip"),
        ):
            require_text(errors, product, f"{prefix}.promptFacts.productState", camel, snake)
        angle_asset_id = field(product, "angleAssetId", "angle_asset_id")
        bound_assets = {
            value.strip()
            for name in ("inputAssetIds", "productAngleRefIds")
            for value in (shot.get(name) if isinstance(shot.get(name), list) else [])
            if non_empty_text(value)
        }
        if non_empty_text(angle_asset_id) and angle_asset_id not in bound_assets:
            errors.append(f"{prefix}.promptFacts.productState.angleAssetId must be bound to the shot")

    if field(facts, "audioMode", "audio_mode") == "visible_speech" and not non_empty_text(facts.get("dialogue")):
        errors.append(f"{prefix}.promptFacts.dialogue is required for visible_speech")


def validate(plan: dict[str, Any]) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    prompt_profile = field(plan, "promptProfile", "prompt_profile")
    workflow_profile = field(
        plan, "workflowProfile", "workflowProfileId", "workflow_profile", "workflow_profile_id"
    )
    profile_version = field(plan, "profileVersion", "profile_version")
    rules_hash = field(plan, "rulesHash", "rules_hash")
    if any(value is not None for value in (workflow_profile, profile_version, rules_hash)):
        if not non_empty_text(workflow_profile):
            errors.append("workflowProfile is required when a versioned rule profile is declared")
        if not non_empty_text(profile_version):
            errors.append("profileVersion is required when a versioned rule profile is declared")
        if not non_empty_text(rules_hash):
            errors.append("rulesHash is required when a versioned rule profile is declared")
        elif not rules_hash.startswith(RULE_HASH_PREFIXES):
            errors.append("rulesHash must start with sha256: or draft:")
    else:
        warnings.append("versioned rule profile is absent; legacy plan remains readable but is not publishable as a new template")
    shots = plan.get("shots")
    if shots is None and isinstance(plan.get("shotPlan"), dict):
        shots = plan["shotPlan"].get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("shots must be a non-empty array")
        return errors, warnings, {"shotCount": 0, "totalDurationSec": 0}

    seen_ids: set[str] = set()
    total_duration = 0.0
    for index, shot in enumerate(shots, start=1):
        prefix = f"shots[{index - 1}]"
        if not isinstance(shot, dict):
            errors.append(f"{prefix} must be an object")
            continue
        shot_id = field(shot, "shotId", "id")
        if not isinstance(shot_id, str) or not shot_id.strip():
            errors.append(f"{prefix}.shotId is required")
        elif shot_id in seen_ids:
            errors.append(f"{prefix}.shotId is duplicated: {shot_id}")
        else:
            seen_ids.add(shot_id)

        duration = field(shot, "durationSec", "duration")
        try:
            duration_value = float(duration)
        except (TypeError, ValueError):
            duration_value = 0
            errors.append(f"{prefix}.durationSec must be a positive number")
        if duration_value <= 0:
            if not any(message.startswith(f"{prefix}.durationSec") for message in errors):
                errors.append(f"{prefix}.durationSec must be a positive number")
        else:
            total_duration += duration_value

        actions = shot.get("actions")
        if actions is not None and not isinstance(actions, list):
            errors.append(f"{prefix}.actions must be an array when provided")
        elif isinstance(actions, list):
            for action_index, action in enumerate(actions, start=1):
                if isinstance(action, str) and action.strip():
                    continue
                if isinstance(action, dict) and isinstance(
                    field(action, "text", "description"), str
                ) and field(action, "text", "description").strip():
                    continue
                errors.append(f"{prefix}.actions[{action_index - 1}] needs text or description")
            if len(actions) > 3 and prompt_profile != INDONESIA_REAL_PERSON_PROFILE:
                warnings.append(
                    f"{prefix}.actions has {len(actions)} actions; confirm the selected rule profile allows this complexity"
                )

        first_frame = field(shot, "firstFramePrompt", "first_frame_prompt")
        if not isinstance(first_frame, str) or not first_frame.strip():
            errors.append(f"{prefix}.firstFramePrompt is required")
        video_prompt = field(shot, "videoPrompt", "video_prompt")
        if not isinstance(video_prompt, str) or not video_prompt.strip():
            errors.append(f"{prefix}.videoPrompt is required")

        asset_ids = field(shot, "inputAssetIds", "assetIds", "asset_ids")
        if asset_ids is not None and not isinstance(asset_ids, list):
            errors.append(f"{prefix}.inputAssetIds must be an array when provided")

        if isinstance(shot.get("modelStrategy"), dict):
            warnings.append(f"{prefix}.modelStrategy is per-shot; server will revalidate scenarioModelId")
        if prompt_profile == INDONESIA_REAL_PERSON_PROFILE:
            validate_indonesia_prompt_facts(shot, prefix, duration_value, actions, errors)

    if not isinstance(plan.get("continuityBible"), dict):
        warnings.append("continuityBible is absent; inferred identity facts must be confirmed before submit")
    if not isinstance(plan.get("assetMap"), list):
        warnings.append("assetMap is absent; ask the user to confirm asset roles and collections")
    return errors, warnings, {
        "shotCount": len(shots),
        "totalDurationSec": round(total_duration, 4),
        "planConfirmed": bool(plan.get("confirmed") or plan.get("userConfirmed")),
        "workflowProfile": workflow_profile,
        "profileVersion": profile_version,
        "rulesHash": rules_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="BeautyVideoPlan JSON path, or - for stdin")
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args()
    try:
        plan = read_json(args.plan)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"valid": False, "errors": [f"cannot read plan: {exc}"], "warnings": [], "summary": {}}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["errors"][0])
        return 2

    errors, warnings, summary = validate(plan)
    result = {"valid": not errors, "errors": errors, "warnings": warnings, "summary": summary}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "valid" if not errors else "invalid"
        print(f"{status}: {summary.get('shotCount', 0)} shots, {summary.get('totalDurationSec', 0)}s")
        for message in errors:
            print(f"ERROR: {message}")
        for message in warnings:
            print(f"WARNING: {message}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
