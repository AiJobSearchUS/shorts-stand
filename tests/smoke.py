"""End-to-end smoke test: mock server -> CLI -> verify production pack."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shorts_stand.mock_server import Handler

PORT = 18055
OUT = tempfile.mkdtemp(prefix="shorts-stand-smoke-")


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    env = dict(os.environ, LEMONADE_BASE_URL=f"http://127.0.0.1:{PORT}/api/v1",
               LEMONADE_MODEL="mock")
    pack_dir = os.path.join(OUT, "pack-test")
    r = subprocess.run(
        [sys.executable, "-m", "shorts_stand.cli", "5AM morning routine",
         "--niche", "productivity", "--duration", "45", "--out", pack_dir],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    print(r.stdout)
    if r.returncode != 0:
        print("STDERR:", r.stderr)
        return 1

    expected = ["script.md", "voiceover.txt", "captions.srt", "metadata.json",
                "raw_model_output.md"]
    missing = [f for f in expected if not os.path.exists(os.path.join(pack_dir, f))]
    assert not missing, f"missing files: {missing}"

    srt = open(os.path.join(pack_dir, "captions.srt")).read()
    assert srt.count("-->") == 4, f"expected 4 SRT cues, got {srt.count('-->')}"
    assert "00:00:00,000 --> 00:00:05,000" in srt, "first cue timing wrong"

    meta = json.load(open(os.path.join(pack_dir, "metadata.json")))
    assert meta["title"].startswith("I Woke Up at 5AM"), "title not parsed"
    assert len(meta["hashtags"]) == 5, "hashtags not parsed"

    script = open(os.path.join(pack_dir, "script.md")).read()
    assert "SHOT" in script or "Shot:" in script, "shot directions missing"

    server.shutdown()
    shutil.rmtree(OUT, ignore_errors=True)
    print("SMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
