#!/usr/bin/env python3
"""Extract technical metadata and representative frames for Codex video analysis.

The script deliberately stops at evidence collection. It does not pretend to
understand faces, products, or actions; those semantic decisions belong to Codex
and the user's confirmation gate.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class AnalysisError(RuntimeError):
    pass


def run_command(command: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=not allow_failure)
    except FileNotFoundError as exc:
        raise AnalysisError(f"required executable is missing: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise AnalysisError(f"command failed: {' '.join(command[:3])}: {detail}") from exc
    return result


def parse_rate(value: Any) -> float | None:
    if not value or not isinstance(value, str):
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def probe_video(path: Path) -> dict[str, Any]:
    result = run_command([
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AnalysisError("ffprobe returned invalid JSON") from exc

    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video:
        raise AnalysisError("input has no video stream")
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    format_data = data.get("format", {})
    duration = float(format_data.get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise AnalysisError("video duration is unavailable or zero")
    frame_rate = parse_rate(video.get("avg_frame_rate")) or parse_rate(video.get("r_frame_rate"))
    frame_count = video.get("nb_frames")
    try:
        frame_count_value = int(frame_count) if frame_count else None
    except (TypeError, ValueError):
        frame_count_value = None
    if frame_count_value is None and frame_rate:
        frame_count_value = int(round(duration * frame_rate))

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    return {
        "durationSec": round(duration, 4),
        "width": width,
        "height": height,
        "aspectRatio": f"{width}:{height}" if width and height else None,
        "frameRate": round(frame_rate, 4) if frame_rate else None,
        "frameCount": frame_count_value,
        "videoCodec": video.get("codec_name"),
        "audio": bool(audio_streams),
        "audioCodec": audio_streams[0].get("codec_name") if audio_streams else None,
        "format": format_data.get("format_name"),
    }


def detect_scene_cuts(path: Path, threshold: float) -> list[float]:
    if shutil.which("ffmpeg") is None:
        return []
    filter_value = f"select=gt(scene\\,{threshold}),showinfo"
    result = run_command([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(path),
        "-vf",
        filter_value,
        "-an",
        "-f",
        "null",
        "-",
    ], allow_failure=True)
    output = f"{result.stdout}\n{result.stderr}"
    values = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", output):
        value = float(match.group(1))
        if not values or abs(values[-1] - value) > 0.05:
            values.append(value)
    return values


def uniform_timestamps(
    duration: float,
    sample_count: int,
    frame_rate: float | None = None,
) -> list[float]:
    if sample_count <= 1:
        return [0.0]
    # Seeking exactly at EOF can return no decoded frame. Keep the final sample
    # inside the last frame while preserving the requested coverage.
    tail_margin = max(0.05, 1.0 / frame_rate) if frame_rate else 0.1
    last_timestamp = max(0.0, duration - tail_margin)
    return [round(last_timestamp * index / (sample_count - 1), 4) for index in range(sample_count)]


def merge_timestamps(duration: float, values: list[float], max_count: int) -> list[float]:
    clipped = [min(duration, max(0.0, value)) for value in values]
    unique: list[float] = []
    for value in sorted(clipped):
        if not unique or abs(unique[-1] - value) >= 0.05:
            unique.append(round(value, 4))
    if len(unique) <= max_count:
        return unique
    stride = (len(unique) - 1) / (max_count - 1)
    return [unique[round(index * stride)] for index in range(max_count)]


def candidate_shots(duration: float, cuts: list[float]) -> list[dict[str, Any]]:
    boundaries = [0.0]
    for cut in cuts:
        if 0.08 < cut < duration - 0.08:
            boundaries.append(round(cut, 4))
    boundaries.append(round(duration, 4))
    boundaries = sorted(set(boundaries))
    shots = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        if end - start < 0.08:
            continue
        shots.append({
            "shotId": f"candidate-{index:02d}",
            "startSec": start,
            "endSec": end,
            "durationSec": round(end - start, 4),
            "source": "ffmpeg_scene_detection" if cuts else "whole_video",
            "semanticReviewRequired": True,
        })
    return shots


def extract_frames(path: Path, timestamps: list[float], frames_dir: Path) -> list[dict[str, Any]]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    for index, timestamp in enumerate(timestamps, start=1):
        output_path = frames_dir / f"frame-{index:04d}.jpg"
        result = run_command([
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.4f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output_path),
        ], allow_failure=True)
        if result.returncode == 0 and output_path.exists():
            extracted.append({"timestampSec": timestamp, "path": str(output_path)})
        else:
            extracted.append({
                "timestampSec": timestamp,
                "path": None,
                "error": (result.stderr or "frame extraction failed").strip(),
            })
    return extracted


def build_analysis(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input).expanduser().resolve()
    if "://" in args.input:
        raise AnalysisError("only local video files are accepted; download first")
    if not input_path.is_file():
        raise AnalysisError(f"input file does not exist: {input_path}")
    technical = probe_video(input_path)
    duration = technical["durationSec"]
    cuts = detect_scene_cuts(input_path, args.scene_threshold) if not args.skip_scene_detection else []
    timestamps = merge_timestamps(
        duration,
        uniform_timestamps(duration, args.samples, technical.get("frameRate")) + cuts,
        args.max_frames,
    )
    frames = extract_frames(input_path, timestamps, Path(args.frames_dir).expanduser()) if args.frames_dir else [
        {"timestampSec": timestamp, "path": None} for timestamp in timestamps
    ]
    interval = round(1.0 / technical["frameRate"], 6) if technical.get("frameRate") else None
    return {
        "schemaVersion": 1,
        "source": {"path": str(input_path), "fileName": input_path.name},
        "technical": technical,
        "allFrameScan": {
            "status": "metadata_only",
            "frameIntervalSec": interval,
            "frameCount": technical.get("frameCount"),
            "semanticReviewRequired": True,
        },
        "sceneCutsSec": cuts,
        "sampleFrames": frames,
        "shotCandidates": candidate_shots(duration, cuts),
        "transcript": None,
        "notes": [
            "代表帧需要由 Codex 进行语义检查",
            "未知人物、产品和场景事实必须经过用户确认",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="local video path")
    parser.add_argument("--frames-dir", help="directory for extracted representative JPG frames")
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    parser.add_argument("--samples", type=int, default=24, help="uniform sample count")
    parser.add_argument("--max-frames", type=int, default=48, help="maximum merged frame count")
    parser.add_argument("--scene-threshold", type=float, default=0.28)
    parser.add_argument("--skip-scene-detection", action="store_true")
    args = parser.parse_args()
    if args.samples < 1 or args.max_frames < 1:
        parser.error("--samples and --max-frames must be positive")
    try:
        payload = build_analysis(args)
    except AnalysisError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
