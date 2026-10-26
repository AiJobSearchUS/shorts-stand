"""Orchestrates pack generation: LLM calls -> parse -> write production pack."""

import json
import re
import os
from datetime import datetime

from . import prompts

BEAT_RE = re.compile(
    r"\[(\d{2}:\d{2})-(\d{2}:\d{2})\]\s*VO:\s*(.*?)\s*\|\s*TEXT:\s*(.*?)\s*\|\s*SHOT:\s*(.*)",
    re.IGNORECASE,
)
SECTION_RE = re.compile(r"^##\s+(HOOKS|SCRIPT|VOICEOVER)\s*$", re.IGNORECASE | re.MULTILINE)


def _split_sections(text):
    """Split model output into HOOKS / SCRIPT / VOICEOVER sections."""
    parts = SECTION_RE.split(text)
    # parts: [prelude, name1, body1, name2, body2, ...]
    sections = {}
    for i in range(1, len(parts), 2):
        sections[parts[i].upper()] = parts[i + 1].strip()
    return sections


def _ts_to_seconds(ts):
    m, s = ts.split(":")
    return int(m) * 60 + int(s)


def _srt_timestamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def beats_to_srt(beats):
    """Build SRT captions from parsed beats (uses the model's timestamps)."""
    lines = []
    for i, b in enumerate(beats, 1):
        start = _srt_timestamp(_ts_to_seconds(b["start"]))
        end = _srt_timestamp(_ts_to_seconds(b["end"]))
        lines.append(f"{i}\n{start} --> {end}\n{b['text']}\n")
    return "\n".join(lines)


def _estimate_srt(vo_text, duration_sec):
    """Fallback SRT: distribute voiceover sentences across the duration by word count."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", vo_text.strip()) if s.strip()]
    if not sentences:
        return ""
    words = [len(s.split()) for s in sentences]
    total = sum(words) or 1
    t = 0.0
    lines = []
    for i, s in enumerate(sentences, 1):
        dur = max(1.0, duration_sec * words[i - 1] / total)
        lines.append(f"{i}\n{_srt_timestamp(t)} --> {_srt_timestamp(t + dur)}\n{s}\n")
        t += dur
    return "\n".join(lines)


def _parse_json_lenient(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return json.loads(text)


def generate_pack(topic, niche, duration_sec, client, outdir):
    os.makedirs(outdir, exist_ok=True)

    creative_out = client.chat(prompts.creative(topic, niche, duration_sec))
    sections = _split_sections(creative_out)

    beats = []
    for m in BEAT_RE.finditer(sections.get("SCRIPT", "")):
        beats.append(
            {
                "start": m.group(1),
                "end": m.group(2),
                "vo": m.group(3).strip(),
                "text": m.group(4).strip(),
                "shot": m.group(5).strip(),
            }
        )

    meta_out = client.chat(
        prompts.metadata(topic, niche, sections.get("SCRIPT", "")[:1500]),
        temperature=0.5,
        max_tokens=600,
    )
    try:
        meta = _parse_json_lenient(meta_out)
    except json.JSONDecodeError:
        meta = {"title": "", "description": "", "hashtags": [], "pinned_comment": "",
                "_raw": meta_out}

    hooks = sections.get("HOOKS", "")
    voiceover = sections.get("VOICEOVER", "")

    srt = beats_to_srt(beats) if beats else _estimate_srt(voiceover, duration_sec)

    # --- write the pack ---
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    script_md = (
        f"# {topic}\n\n_Pack generated {stamp} with Shorts Stand (local LLM via Lemonade)._  \n"
        f"Niche: {niche} · Target duration: {duration_sec}s\n\n"
        f"## Recommended hook\n{hooks}\n\n## Script\n"
    )
    for b in beats:
        script_md += (
            f"- **[{b['start']}-{b['end']}]** \U0001f3a4 {b['vo']}  \n"
            f"  \U0001f4ac On-screen: _{b['text']}_  \n"
            f"  \U0001f3ac Shot: {b['shot']}\n"
        )
    if not beats:
        script_md += "_Beats did not parse — see raw_model_output.md._\n"

    files = {
        "script.md": script_md,
        "voiceover.txt": voiceover + "\n",
        "captions.srt": srt,
        "metadata.json": json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        "raw_model_output.md": creative_out + "\n\n---\n\n" + meta_out + "\n",
    }
    for name, content in files.items():
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
            f.write(content)

    return {
        "outdir": outdir,
        "beats": len(beats),
        "hooks": len([h for h in hooks.splitlines() if h.strip().startswith(tuple("123456789"))]),
        "title": meta.get("title", ""),
        "files": sorted(files),
    }
