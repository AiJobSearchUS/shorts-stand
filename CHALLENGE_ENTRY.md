# Lemonade Developer Challenge — entry draft for Shorts Stand 🍋

> Status: DRAFT — needs Christopher's approval before submission.

## Project name
Shorts Stand — a local-AI pre-production studio for short-form video

## One-liner
Type a topic; get a complete short-form video production pack (hooks, timestamped
script, voiceover, captions, title/hashtags) generated 100% locally by Lemonade —
no cloud, no API keys, no per-token cost.

## Description (for the form's "project details" field)
Shorts Stand is an open-source tool (MIT) that removes the pre-production
bottleneck for short-form video creators. You enter a topic and niche; a model
running on your own machine via Lemonade Server generates a full production pack:

- 3 scroll-stopping hook options for the first 3 seconds
- A timestamped script — every beat has a voiceover line, on-screen caption text
  (≤6 words), and shot direction for the editor
- Clean voiceover narration, ready for TTS
- Timed captions (SRT) derived from the script's timestamps
- metadata.json: title, description, hashtags, and a pinned comment to drive engagement
- A single-page web UI (`python web.py`, stdlib only, no npm): topic/niche/duration
  form, background generation jobs against the local Lemonade server, and
  one-click downloads of every pack file

Technical details:
- Pure Python, standard library only — zero dependencies, runs anywhere Python 3.10+ runs
- Speaks plain OpenAI-compatible chat completions; defaults to Lemonade at
  `http://localhost:13305/api/v1` (overridable via `LEMONADE_BASE_URL` / `LEMONADE_MODEL`
  env vars, so it also works with LM Studio / Ollama / vLLM — Lemonade is the
  default, not a lock-in)
- Two LLM calls per pack: a creative pass (hooks + script + voiceover) and a
  packaging pass (metadata as strict JSON, with fenced-code tolerance)
- SRT timing comes straight from the model's own beat timestamps, with a
  word-count fallback if beats don't parse
- Includes a stub OpenAI-compatible server + end-to-end smoke test, so the full
  pipeline is verifiable with no GPU
- Validated end-to-end against real Lemonade Server 11.9.0 running
  Qwen3-4B-Instruct-2507-GGUF locally: a 12-beat/45s pack ("5 side hustles with
  no money") with 3 hooks, clean SRT captions and metadata, zero placeholders —
  committed in the repo as `example-lemonade-qwen3-4b/`. The web UI was validated
  the same way (30s pack, 7 beats, all downloads working)

Why Lemonade: creators making daily content burn out on the blank page, not the
camera. Cloud LLM APIs tax every idea; Shorts Stand makes ideation free and
private — your niche, your voice, your hardware.

## Links (fill in when live)
- GitHub repo: <TODO — publish, then paste URL>
- Demo video: recorded and ready at `demo/shorts-stand-demo.mp4` (25s, 1280x720 — awaiting Christopher's upload, then paste URL)
- Discord #AMDDevChallenge post: <TODO — Christopher posts, then paste URL>

## Judging criteria mapping
- Community impact: free, private, open-source tool for the creator community;
  documented for solo creators with just a phone.
- Technical depth & quality: structured-output prompting, timestamp-derived SRT,
  JSON-tolerant metadata parsing, stdlib-only client with reasoning-model
  fallback, offline smoke-test harness, and a dependency-free web UI with
  background generation jobs.
- Creativity: turns an LLM into a video pre-production crew (writer + director +
  packaging assistant) instead of a chatbot.
