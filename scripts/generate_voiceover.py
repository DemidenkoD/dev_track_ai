#!/usr/bin/env python3
"""
DevTrack AI — Voiceover Generator using ElevenLabs REST API.

Generates scene-by-scene audio voiceovers for the DevTrack AI application demo.
Reads ELEVEN_LABS_API_KEY from .env.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# Popular high-quality ElevenLabs voices
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # "Adam" - Crisp, professional, deep American male
# Alternatives:
# "21m00Tcm4TlvDq8ikWAM" - "Rachel" (Calm, articulate female)
# "nPczCjzI2devNBz1zQrb" - "Brian" (Deep, authoritative, British male)
# "ErXwobaYiN019PkySvjV" - "Antoni" (Well-rounded narrator)

DEMO_SCENES = [
    {
        "id": "scene_01_intro",
        "title": "Scene 1: Introduction & The Core Problem",
        "screen": "Landing page / Course dilemma graphic",
        "narration": (
            "Building technical course projects is challenging. Students and developers often ask themselves: "
            "Am I truly meeting the rubric requirements? How many points will my project actually get? "
            "And what blockers are standing between me and a passing grade? "
            "Meet DevTrack AI: your course-first AI project mentor, designed from the ground up "
            "for DataTalksClub Zoomcamps and developer capstone projects."
        )
    },
    {
        "id": "scene_02_login_dashboard",
        "title": "Scene 2: Reviewer Login & Project Dashboard",
        "screen": "Login screen -> Projects Dashboard",
        "narration": (
            "Reviewers can log in instantly with pre-seeded credentials. "
            "The Project Dashboard immediately surfaces active assignments with clear deadlines, "
            "health indicators, and our signature two-dimensional tracking. "
            "Unlike naive tools that conflate tasks with grades, DevTrack AI strictly separates "
            "Development Completion from your Expected Course Score."
        )
    },
    {
        "id": "scene_03_scorecard",
        "title": "Scene 3: Official Rubric Scorecard & Safety Invariants",
        "screen": "Project Detail -> Rubric Scorecard Panel",
        "narration": (
            "Inside the project, we see the official AI Dev Tools Zoomcamp 2026 scorecard, "
            "spanning twelve criteria and twenty-four maximum points with a ten-point passing threshold. "
            "Notice the strict safety invariant: every score is explicitly tagged as Estimated, "
            "Verified, or Needs Review. DevTrack AI never masquerades AI guesses as official grades, "
            "and when a human reviewer overrides a score, the original AI reasoning remains fully preserved."
        )
    },
    {
        "id": "scene_04_analysis_pipeline",
        "title": "Scene 4: Triggering Multi-Agent Analysis & Security Scans",
        "screen": "Trigger Analysis Modal -> Live Scanning Progress",
        "narration": (
            "When we trigger an analysis, background worker agents inspect the public GitHub repository, "
            "parse the development diary, and verify live deployments with SSRF protection. "
            "Crucially, we never execute untrusted code. "
            "Instead, deterministic scanners like Semgrep, Gitleaks, and Bandit run in isolated sandboxes, "
            "feeding structured evidence directly to Gemini for rubric matching."
        )
    },
    {
        "id": "scene_05_mentor_milestones",
        "title": "Scene 5: AI Mentor Chat & Actionable Milestones",
        "screen": "Mentor Chat Panel & Milestones View",
        "narration": (
            "Need to know what to build next? The AI Mentor acts as a personal tutor. "
            "Asking 'What is preventing me from reaching twenty points?' produces evidence-backed guidance "
            "tied directly to your repository commits and missing rubric deliverables. "
            "Milestones are split into official course milestones and practical development subtasks, "
            "keeping your engineering plan organized and focused."
        )
    },
    {
        "id": "scene_06_observability_oncall",
        "title": "Scene 6: Phase 4 On-Call Diagnostics & Observability",
        "screen": "On-Call Page & Grafana Dashboard",
        "narration": (
            "DevTrack AI doesn't stop at code evaluation. "
            "With Phase Four Observability, pre-configured Grafana dashboards correlate Prometheus metrics, "
            "Loki logs, and Tempo distributed traces via unique trace IDs. "
            "Our read-only On-Call Diagnostic Agent can investigate alerts and diagnose system incidents in seconds "
            "without mutating production state."
        )
    },
    {
        "id": "scene_07_architecture_closing",
        "title": "Scene 7: Architecture, Single-Command Setup & Wrap-Up",
        "screen": "VS Code repository overview / make up terminal output",
        "narration": (
            "Under the hood, DevTrack AI was built using a six-track parallel multi-agent architecture, "
            "comprehensive test coverage, and a single-command Docker Compose startup. "
            "DevTrack AI: bridging the gap between project idea and a verified, secure, and successful deployment. "
            "Thank you for watching!"
        )
    }
]


def load_api_key_from_env() -> str:
    """Reads ELEVEN_LABS_API_KEY from environment or .env file."""
    api_key = os.getenv("ELEVEN_LABS_API_KEY")
    if api_key:
        return api_key.strip().strip("\"'")

    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ELEVEN_LABS_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    return val

    # Fallback to ELEVENLABS_API_KEY variant
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        return api_key.strip().strip("\"'")

    return ""


def synthesize_speech(text: str, voice_id: str, api_key: str, model_id: str = "eleven_turbo_v2_5") -> bytes:
    """Calls ElevenLabs Text-to-Speech REST API."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "User-Agent": "DevTrackAI-DemoGenerator/1.0"
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        if e.code == 403 and "not allowed by policy" in error_body:
            raise PermissionError(
                f"ElevenLabs 403 Forbidden: API key policy restriction.\n"
                f"Response: {error_body}\n\n"
                f"Fix in ElevenLabs Dashboard:\n"
                f"1. Go to https://elevenlabs.io/app/settings/api-keys\n"
                f"2. Inspect your API key permissions/scopes.\n"
                f"3. Ensure 'Generate speech' (Text to Speech) is ENABLED, or create a key with Full Access."
            ) from e
        raise RuntimeError(f"ElevenLabs API Error (HTTP {e.code}): {error_body}") from e


def generate_vtt_subtitles(scenes: list, output_path: Path):
    """Generates a WebVTT file with estimated subtitle timings based on word counts."""
    # Rough estimate: ~140 words per minute -> ~2.3 words per second
    current_time_sec = 0.0
    vtt_lines = ["WEBVTT", ""]

    def format_ts(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{mins:02d}:{secs:02d}.{millis:03d}"

    for i, scene in enumerate(scenes, 1):
        words = len(scene["narration"].split())
        duration = max(3.0, (words / 140.0) * 60.0)
        start_ts = format_ts(current_time_sec)
        end_ts = format_ts(current_time_sec + duration)

        vtt_lines.append(f"{i}")
        vtt_lines.append(f"{start_ts} --> {end_ts}")
        vtt_lines.append(f"[{scene['title']}] {scene['narration']}")
        vtt_lines.append("")

        current_time_sec += duration + 0.5  # 0.5s pause between scenes

    output_path.write_text("\n".join(vtt_lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate voiceovers for DevTrack AI demo via ElevenLabs.")
    parser.add_argument("--voice", default=DEFAULT_VOICE_ID, help="ElevenLabs Voice ID (default: Adam)")
    parser.add_argument("--model", default="eleven_turbo_v2_5", help="ElevenLabs Model ID (default: eleven_turbo_v2_5)")
    parser.add_argument("--output-dir", default="demo/audio", help="Directory where mp3 files will be stored")
    parser.add_argument("--test", action="store_true", help="Generate only scene 1 as a smoke test")
    parser.add_argument("--dry-run", action="store_true", help="Print scripts and word counts without calling API")
    args = parser.parse_args()

    api_key = load_api_key_from_env()
    if not api_key and not args.dry_run:
        print("ERROR: ELEVEN_LABS_API_KEY not found in environment or .env file.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes_to_run = [DEMO_SCENES[0]] if args.test else DEMO_SCENES

    print(f"=== DevTrack AI Demo Voiceover Generator ===")
    print(f"Output directory: {out_dir.resolve()}")
    print(f"Voice ID:         {args.voice}")
    print(f"Model:            {args.model}")
    print(f"Total scenes:     {len(scenes_to_run)}")
    print("============================================\n")

    manifest = []

    for i, scene in enumerate(scenes_to_run, 1):
        filename = f"{scene['id']}.mp3"
        filepath = out_dir / filename
        words = len(scene["narration"].split())
        est_sec = round((words / 140.0) * 60.0, 1)

        print(f"[{i}/{len(scenes_to_run)}] {scene['title']}")
        print(f"    Words: ~{words} (est: {est_sec}s)")
        print(f"    Screen: {scene['screen']}")

        if args.dry_run:
            print(f"    [DRY-RUN] Script: \"{scene['narration']}\"")
        else:
            print(f"    Synthesizing to {filename}...", end="", flush=True)
            try:
                audio_bytes = synthesize_speech(scene["narration"], args.voice, api_key, args.model)
                filepath.write_bytes(audio_bytes)
                print(f" OK ({len(audio_bytes):,} bytes)")
            except Exception as e:
                print(f" FAILED!\n\n{e}\n")
                if not args.test:
                    print("Aborting remaining scenes.")
                    break
                sys.exit(1)

        manifest.append({
            "scene_id": scene["id"],
            "title": scene["title"],
            "screen_cue": scene["screen"],
            "audio_file": str(filepath.relative_to(out_dir)),
            "word_count": words,
            "estimated_seconds": est_sec,
            "narration": scene["narration"]
        })

    # Save manifest and subtitles
    manifest_path = out_dir / "demo_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest written to: {manifest_path}")

    vtt_path = out_dir / "demo_subtitles.vtt"
    generate_vtt_subtitles(scenes_to_run, vtt_path)
    print(f"Subtitles written to: {vtt_path}")

    print("\nNext Steps:")
    print("1. To record video, start the local stack: make up (or run frontend: npm --prefix frontend run dev)")
    print("2. Play each audio track while walking through the corresponding screen, or edit together in your video tool.")
    print("Done!")


if __name__ == "__main__":
    main()

