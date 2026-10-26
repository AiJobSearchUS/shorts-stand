"""CLI for Shorts Stand.

  python -m shorts_stand.cli "topic" [--niche ...] [--duration 45] [--voice]
  python -m shorts_stand.cli generate "topic" ...        (same, explicit)
  python -m shorts_stand.cli transcribe <audio_file> --out <dir>
  python -m shorts_stand.cli critique <image_file> [--topic "..."] [--concepts]
"""

import argparse
import os
import sys

from .client import LemonadeClient
from .pack import critique_image, generate_pack, transcribe_take

COMMANDS = ("generate", "transcribe", "critique")


def _slug(text, fallback):
    slug = "".join(c.lower() if c.isalnum() else "-" for c in text)[:40].strip("-")
    return slug or fallback


def _generate(argv):
    p = argparse.ArgumentParser(
        prog="shorts-stand generate",
        description="Generate a short-form video production pack with a local LLM (Lemonade).",
    )
    p.add_argument("topic", help="Video topic, e.g. '5 side hustles with no money'")
    p.add_argument("--niche", default="general audience",
                   help="Target audience/niche (default: general audience)")
    p.add_argument("--duration", type=int, default=45,
                   help="Target duration in seconds (default: 45)")
    p.add_argument("--out", default=None,
                   help="Output directory (default: ./pack-<slug>)")
    p.add_argument("--voice", action="store_true",
                   help="Also synthesize voiceover.wav with the TTS model")
    p.add_argument("--base-url", default=None, help="Override LEMONADE_BASE_URL")
    p.add_argument("--model", default=None, help="Override LEMONADE_MODEL")
    args = p.parse_args(argv)

    outdir = os.path.abspath(args.out or ("pack-" + _slug(args.topic, "pack")))

    client = LemonadeClient(base_url=args.base_url, model=args.model)
    print(f"Talking to model server at {client.base_url} (model: {client.model}) ...")
    try:
        result = generate_pack(args.topic, args.niche, args.duration, client,
                               outdir, with_voice=args.voice)
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    for w in result.get("warnings", []):
        print(f"WARNING: {w}", file=sys.stderr)
    print(f"\nPack ready in {result['outdir']}")
    print(f"  beats: {result['beats']}  hooks: {result['hooks']}")
    print(f"  title: {result['title']}")
    for f in result["files"]:
        print(f"  - {f}")
    return 0


def _transcribe(argv):
    p = argparse.ArgumentParser(
        prog="shorts-stand transcribe",
        description="Transcribe a recorded take (Whisper) and derive a production pack.",
    )
    p.add_argument("audio", help="Audio file of the recorded take (wav, mp3, m4a, ...)")
    p.add_argument("--out", default=None,
                   help="Output directory (default: ./take-<audio name>)")
    p.add_argument("--base-url", default=None, help="Override LEMONADE_BASE_URL")
    p.add_argument("--model", default=None, help="Override LEMONADE_MODEL")
    args = p.parse_args(argv)

    if not os.path.exists(args.audio):
        print(f"\nERROR: no such audio file: {args.audio}", file=sys.stderr)
        return 1
    stem = os.path.splitext(os.path.basename(args.audio))[0]
    outdir = os.path.abspath(args.out or ("take-" + _slug(stem, "take")))

    client = LemonadeClient(base_url=args.base_url, model=args.model)
    print(f"Transcribing with {client.stt_model} at {client.base_url} ...")
    try:
        result = transcribe_take(args.audio, client, outdir)
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    for w in result.get("warnings", []):
        print(f"WARNING: {w}", file=sys.stderr)
    print(f"\nTake pack ready in {result['outdir']}")
    print(f"  segments: {result['segments']}  beats: {result['beats']}")
    print(f"  title: {result['title']}")
    for f in result["files"]:
        print(f"  - {f}")
    return 0


def _critique(argv):
    p = argparse.ArgumentParser(
        prog="shorts-stand critique",
        description="Score a thumbnail / first frame with the vision model.",
    )
    p.add_argument("image", help="Thumbnail or first-frame image (png, jpg, ...)")
    p.add_argument("--topic", default="",
                   help="Video topic the frame is for (sharpens the critique)")
    p.add_argument("--out", default=None,
                   help="Output directory (default: alongside the image)")
    p.add_argument("--concepts", action="store_true",
                   help="Also generate thumbnail concept image(s) from the topic")
    p.add_argument("--base-url", default=None, help="Override LEMONADE_BASE_URL")
    p.add_argument("--model", default=None,
                   help="Override LEMONADE_MODEL (vision uses LEMONADE_VISION_MODEL)")
    args = p.parse_args(argv)

    if not os.path.exists(args.image):
        print(f"\nERROR: no such image file: {args.image}", file=sys.stderr)
        return 1
    outdir = os.path.abspath(
        args.out or os.path.dirname(os.path.abspath(args.image)))

    client = LemonadeClient(base_url=args.base_url, model=args.model)
    print(f"Critiquing with {client.vision_model} at {client.base_url} ...")
    try:
        result = critique_image(args.image, args.topic, client, outdir,
                                concepts=args.concepts)
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    for w in result.get("warnings", []):
        print(f"WARNING: {w}", file=sys.stderr)
    print(f"\nCritique ready in {result['outdir']}")
    for f in result["files"]:
        print(f"  - {f}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in COMMANDS:
        cmd, rest = argv[0], argv[1:]
    else:
        # Legacy form: a bare topic (or bare flags) means "generate".
        cmd, rest = "generate", argv
    if cmd == "transcribe":
        return _transcribe(rest)
    if cmd == "critique":
        return _critique(rest)
    return _generate(rest)


if __name__ == "__main__":
    sys.exit(main())
