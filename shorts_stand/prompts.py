"""Prompt templates for the Shorts Stand production pack.

Two LLM calls per pack:
  1. creative() -> hooks, timestamped script (VO + on-screen text + shot
     direction), and clean voiceover narration.
  2. metadata() -> title, description, hashtags as JSON.

v2 additions: take_script() (clean a recorded take's transcript into the
same sections), critique() (vision scoring of a thumbnail/frame), and
thumbnail_concept() (image-generation prompt for concept thumbnails).
"""

SCRIPT_FORMAT = """\
## HOOKS
1. <hook option 1 — under 12 words, spoken in first 3 seconds>
2. <hook option 2>
3. <hook option 3>

## SCRIPT
[00:00-00:03] VO: <voiceover line> | TEXT: <on-screen text, max 6 words> | SHOT: <visual direction for the editor>
(one line per beat, timestamps covering the full duration, no gaps)

## VOICEOVER
<the full narration as flowing paragraphs, no timestamps, no stage directions>
"""


def creative(topic, niche, duration_sec, hook_count=3):
    system = (
        "You are Shorts Stand, a pre-production assistant for short-form video. "
        "You write punchy, high-retention scripts for TikTok / YouTube Shorts / Reels. "
        "Every line must be filmable by a solo creator with a phone. "
        "No placeholders, no bracketed notes to self — output only the requested sections."
    )
    user = (
        f"Topic: {topic}\n"
        f"Niche/audience: {niche}\n"
        f"Target duration: {duration_sec} seconds.\n\n"
        f"Write exactly these sections:\n{SCRIPT_FORMAT}\n"
        f"Rules:\n"
        f"- {hook_count} distinct hook options: curiosity gap, bold claim, or pattern interrupt.\n"
        f"- SCRIPT beats must tile the full {duration_sec}s with no gaps or overlaps.\n"
        f"- VO lines are spoken aloud; TEXT is big on-screen captions (<=6 words each);\n"
        f"  SHOT tells the editor exactly what to show (camera move, subject, vibe).\n"
        f"- VOICEOVER must read naturally when spoken and match the SCRIPT beats.\n"
        f"- Keep total spoken words near {int(duration_sec * 2.5)} (about 150 words/minute)."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def take_script(transcript, duration_sec):
    """Clean a recorded take's transcript into the standard pack sections."""
    system = (
        "You are Shorts Stand, a pre-production assistant for short-form video. "
        "A creator recorded a take; you turn the raw transcript into a clean, "
        "shootable script. Keep the creator's own words and meaning — fix "
        "filler words, false starts, and rambling; do not invent new claims. "
        "Output only the requested sections."
    )
    user = (
        f"The take runs about {duration_sec} seconds. Raw transcript:\n\n"
        f"{transcript[:6000]}\n\n"
        f"Write exactly these sections:\n{SCRIPT_FORMAT}\n"
        f"Rules:\n"
        f"- HOOKS: pull the 3 strongest lines from the take itself, lightly polished.\n"
        f"- SCRIPT beats must tile the full {duration_sec}s with no gaps, following\n"
        f"  the order of the transcript; VO lines are the cleaned spoken words.\n"
        f"- VOICEOVER is the full cleaned narration, matching the SCRIPT beats."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


CRITIQUE_SYSTEM = (
    "You are Shorts Stand's thumbnail coach for short-form video. You judge "
    "a single frame the way a scroller's thumb does: in under a second. "
    "Be specific and blunt — vague praise helps nobody. Score only what is "
    "actually visible in the image."
)

CRITIQUE_FORMAT = """\
## Scores
- Scroll-stop power: <1-10> — <one short reason>
- On-screen text legibility: <1-10> — <one short reason>
- Framing/composition: <1-10> — <one short reason>
- Lighting/clarity: <1-10> — <one short reason>

## Top 3 fixes
1. <most impactful concrete change>
2. <second concrete change>
3. <third concrete change>

## Verdict
<one line: post it, fix it first, or reshoot — and why>
"""


def critique(topic):
    """User prompt for the vision critique (image attached by the client)."""
    subject = f' for a video about "{topic}"' if topic else ""
    return (
        f"This is a thumbnail / first frame{subject} for a short-form video "
        f"(TikTok / Shorts / Reels). Judge it as a viewer mid-scroll.\n\n"
        f"Reply with exactly this structure, no extra sections:\n{CRITIQUE_FORMAT}"
    )


def thumbnail_concept(topic):
    """Image-generation prompt for a thumbnail concept."""
    subject = topic or "a short-form video"
    return (
        f"Bold YouTube Shorts thumbnail concept for {subject}: one expressive "
        f"creator face in the foreground, high contrast, saturated colors, "
        f"dramatic lighting, clean uncluttered background, space for large "
        f"text on the left third, no text or letters in the image"
    )


def metadata(topic, niche, script_excerpt):
    system = (
        "You are Shorts Stand's packaging assistant. "
        "Reply with ONLY a JSON object, no markdown fences, no commentary."
    )
    user = (
        f"Topic: {topic}\nNiche/audience: {niche}\n\n"
        f"Script excerpt:\n{script_excerpt[:1500]}\n\n"
        "Return JSON with exactly these keys:\n"
        "{\n"
        '  "title": "<under 60 chars, curiosity-driven>",\n'
        '  "description": "<2 sentences + call to action>",\n'
        '  "hashtags": ["<5-8 niche + broad tags, no # symbol>"],\n'
        '  "pinned_comment": "<one question to drive comments>"\n'
        "}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
