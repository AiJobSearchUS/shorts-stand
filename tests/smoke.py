"""End-to-end smoke test: mock server -> CLI -> verify all pack flows.

Covers, fully offline:
  1. topic pack (baseline v1 flow)
  2. topic pack with --voice (voiceover.wav from the TTS stub)
  3. transcribe a recorded take -> transcript + real-timestamp captions
  4. vision critique of a thumbnail (+ generated concept image)
  5. degradation: TTS endpoint 404s -> pack still completes, no audio
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shorts_stand.mock_server import Handler, PNG_1X1_B64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 18055
OUT = tempfile.mkdtemp(prefix="shorts-stand-smoke-")


def run_cli(args):
    env = dict(os.environ, LEMONADE_BASE_URL=f"http://127.0.0.1:{PORT}/api/v1",
               LEMONADE_MODEL="mock")
    r = subprocess.run(
        [sys.executable, "-m", "shorts_stand.cli", *args],
        capture_output=True, text=True, env=env, cwd=ROOT,
    )
    if r.returncode != 0:
        print(r.stdout)
        print("STDERR:", r.stderr)
    return r


def _check_baseline_pack(pack_dir):
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


def _scenario_topic_pack():
    pack_dir = os.path.join(OUT, "pack-test")
    r = run_cli(["5AM morning routine", "--niche", "productivity",
                 "--duration", "45", "--out", pack_dir])
    print(r.stdout)
    assert r.returncode == 0, "topic pack failed"
    _check_baseline_pack(pack_dir)
    print("  [ok] topic pack")


def _scenario_voice_pack():
    pack_dir = os.path.join(OUT, "pack-voice")
    r = run_cli(["5AM morning routine", "--duration", "45",
                 "--out", pack_dir, "--voice"])
    print(r.stdout)
    assert r.returncode == 0, "voice pack failed"
    _check_baseline_pack(pack_dir)
    wav = os.path.join(pack_dir, "voiceover.wav")
    assert os.path.exists(wav), "voiceover.wav missing"
    data = open(wav, "rb").read()
    assert len(data) > 44 and data[:4] == b"RIFF", "voiceover.wav is not a WAV"
    print("  [ok] pack with --voice (voiceover.wav synthesized)")


def _scenario_transcribe():
    audio = os.path.join(OUT, "take.wav")
    with wave.open(audio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    take_dir = os.path.join(OUT, "take-test")
    r = run_cli(["transcribe", audio, "--out", take_dir])
    print(r.stdout)
    assert r.returncode == 0, "transcribe failed"

    transcript = open(os.path.join(take_dir, "transcript.txt")).read()
    assert "morning routine" in transcript, "transcript text wrong"

    srt = open(os.path.join(take_dir, "captions.srt")).read()
    assert srt.count("-->") == 3, f"expected 3 SRT cues, got {srt.count('-->')}"
    assert "00:00:00,000 --> 00:00:02,500" in srt, "segment timestamps not used"
    assert "00:00:05,000 --> 00:00:07,500" in srt, "last segment timing wrong"

    meta = json.load(open(os.path.join(take_dir, "metadata.json")))
    assert meta["source"] == "take-transcription", "source not marked"
    assert os.path.exists(os.path.join(take_dir, "script.md")), "script.md missing"
    print("  [ok] transcribe take (transcript + real-timestamp captions)")


def _scenario_critique():
    img = os.path.join(OUT, "thumb.png")
    with open(img, "wb") as f:
        f.write(base64.b64decode(PNG_1X1_B64))
    crit_dir = os.path.join(OUT, "critique-test")
    r = run_cli(["critique", img, "--topic", "5AM morning routine",
                 "--out", crit_dir, "--concepts"])
    print(r.stdout)
    assert r.returncode == 0, "critique failed"

    md = open(os.path.join(crit_dir, "vision-critique.md")).read()
    for section in ("Scroll-stop power: 7/10", "On-screen text legibility: 5/10",
                    "Framing/composition: 6/10", "Lighting/clarity: 8/10",
                    "## Top 3 fixes", "## Verdict"):
        assert section in md, f"critique missing section: {section}"
    concept = os.path.join(crit_dir, "concept-1.png")
    assert os.path.exists(concept) and os.path.getsize(concept) > 0, \
        "concept-1.png missing/empty"
    print("  [ok] vision critique (+ concept image)")


def _scenario_tts_degradation():
    os.environ["MOCK_404_SPEECH"] = "1"  # stub now 404s the speech endpoint
    try:
        pack_dir = os.path.join(OUT, "pack-degraded")
        r = run_cli(["5AM morning routine", "--duration", "45",
                     "--out", pack_dir, "--voice"])
        print(r.stdout)
        assert r.returncode == 0, "pack should survive a TTS failure"
        _check_baseline_pack(pack_dir)
        assert not os.path.exists(os.path.join(pack_dir, "voiceover.wav")), \
            "voiceover.wav should not exist when TTS fails"
        assert "voiceover audio skipped" in r.stderr, "warning not surfaced"
    finally:
        del os.environ["MOCK_404_SPEECH"]
    print("  [ok] TTS failure degrades gracefully (pack completes, no audio)")


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)

    try:
        _scenario_topic_pack()
        _scenario_voice_pack()
        _scenario_transcribe()
        _scenario_critique()
        _scenario_tts_degradation()
    finally:
        server.shutdown()
        shutil.rmtree(OUT, ignore_errors=True)
    print("SMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
