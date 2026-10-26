"""Tiny OpenAI-compatible stub server for offline testing.

Serves canned responses so the pack pipeline — including the v2 omni
endpoints — can be exercised end-to-end without a real model:

  POST /chat/completions       creative / metadata / vision-critique text
  POST /audio/speech           tiny valid WAV (404 if MOCK_404_SPEECH=1)
  POST /audio/transcriptions   verbose_json with segments + timestamps
  POST /images/generations     a 1x1 PNG as b64_json

Run: python -m shorts_stand.mock_server [port]
"""

import io
import json
import os
import sys
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

CREATIVE = """\
## HOOKS
1. Stop scrolling — this 45 second video will change your mornings.
2. I tried the 5AM club for 30 days so you don't have to.
3. Nobody talks about the dark side of hustle culture.

## SCRIPT
[00:00-00:05] VO: I woke up at 5AM for thirty days straight, and here's what actually happened. | TEXT: I tried 5AM for 30 days | SHOT: Phone alarm close-up in a dark bedroom, hand slamming snooze
[00:05-00:15] VO: Week one was pure misery. My brain felt like wet cement until noon. | TEXT: Week 1: miserable | SHOT: Creator shuffling to kitchen, messy hair, harsh morning light
[00:15-00:30] VO: But by week three something clicked. Deep work before the world woke up felt like a superpower. | TEXT: Week 3: it clicked | SHOT: Time-lapse of sunrise over a desk, coffee steaming, fast typing
[00:30-00:45] VO: Verdict? It's not the hour, it's the ritual. Steal my exact routine below. | TEXT: It's the ritual, not the hour | SHOT: Creator pointing at camera, bold text pop, upbeat music swell

## VOICEOVER
I woke up at 5AM for thirty days straight, and here's what actually happened. Week one was pure misery. My brain felt like wet cement until noon. But by week three something clicked. Deep work before the world woke up felt like a superpower. Verdict? It's not the hour, it's the ritual. Steal my exact routine below.
"""

METADATA = json.dumps({
    "title": "I Woke Up at 5AM for 30 Days (Honest Results)",
    "description": "30 days of 5AM mornings — the misery, the breakthrough, and the exact routine. Would you try it?",
    "hashtags": ["5amclub", "morningroutine", "productivity", "selfimprovement", "shorts"],
    "pinned_comment": "What time do YOU wake up? Be honest.",
})

CRITIQUE = """\
## Scores
- Scroll-stop power: 7/10 — strong facial expression, but the background competes for attention
- On-screen text legibility: 5/10 — the headline is small and low-contrast against the wall
- Framing/composition: 6/10 — face is dead-center with dead space on the right
- Lighting/clarity: 8/10 — bright and sharp, no motion blur

## Top 3 fixes
1. Double the headline size and add a dark outline so it survives a bright feed
2. Crop tighter on the face and shift it into the left third
3. Dim or blur the background so the subject pops first

## Verdict
Fix the text first — the frame itself is postable after that.
"""

TRANSCRIPTION = {
    "text": (
        "Okay so today I am going to show you the exact morning routine "
        "that fixed my focus. It takes five minutes and you need zero equipment."
    ),
    "duration": 7.5,
    "language": "en",
    "segments": [
        {"id": 0, "start": 0.0, "end": 2.5,
         "text": "Okay so today I am going to show you the exact morning routine"},
        {"id": 1, "start": 2.5, "end": 5.0,
         "text": "that fixed my focus. It takes five minutes"},
        {"id": 2, "start": 5.0, "end": 7.5,
         "text": "and you need zero equipment."},
    ],
}

# 1x1 transparent PNG
PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _tiny_wav():
    """A valid WAV: 0.25s of silence, 8kHz mono 16-bit."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 2000)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/health") or self.path.rstrip("/").endswith("/models"):
            return self._send({"status": "ok"} if "health" in self.path else {"data": []})
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        path = self.path.rstrip("/")

        if path.endswith("/audio/speech"):
            if os.environ.get("MOCK_404_SPEECH") == "1":
                return self._send({"error": "model not found"}, 404)
            return self._send_bytes(_tiny_wav(), "audio/wav")

        if path.endswith("/audio/transcriptions"):
            # Body is multipart form data; the stub ignores it.
            return self._send(TRANSCRIPTION)

        if path.endswith("/images/generations"):
            return self._send({"data": [{"b64_json": PNG_1X1_B64}]})

        # /chat/completions (and anything else): canned chat responses.
        payload = json.loads(raw.decode() or "{}")
        text = json.dumps(payload.get("messages", []))
        if "image_url" in text:
            content = CRITIQUE
        elif "hashtags" in text or "pinned_comment" in text:
            content = METADATA  # the packaging call asks for JSON
        else:
            content = CREATIVE
        self._send({
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "model": payload.get("model", "mock"),
        })


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 13305
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
