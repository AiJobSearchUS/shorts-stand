"""Tiny OpenAI-compatible stub server for offline testing.

Serves canned responses so the pack pipeline can be exercised end-to-end
without a real model. Run: python -m shorts_stand.mock_server [port]
"""

import json
import sys
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

    def do_GET(self):
        if self.path.rstrip("/").endswith("/health") or self.path.rstrip("/").endswith("/models"):
            return self._send({"status": "ok"} if "health" in self.path else {"data": []})
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode() or "{}")
        text = json.dumps(payload.get("messages", []))
        content = METADATA if "hashtags" in text or "pinned_comment" in text else CREATIVE
        # Second call asks for JSON; first call is the creative brief.
        self._send({
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "model": payload.get("model", "mock"),
        })


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 13305
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
