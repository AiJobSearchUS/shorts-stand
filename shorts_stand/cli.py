"""CLI: python -m shorts_stand.cli "topic" [--niche ...] [--duration 45]"""

import argparse
import os
import sys

from .client import LemonadeClient
from .pack import generate_pack


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="shorts-stand",
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

    outdir = args.out or ("pack-" + "".join(
        c.lower() if c.isalnum() else "-" for c in args.topic)[:40].strip("-"))
    outdir = os.path.abspath(outdir)

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


if __name__ == "__main__":
    sys.exit(main())
