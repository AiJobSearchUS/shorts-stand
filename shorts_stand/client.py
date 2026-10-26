"""Minimal OpenAI-compatible client (stdlib only).

Defaults to Lemonade Server's local endpoint: http://localhost:13305/api/v1
Override with LEMONADE_BASE_URL / LEMONADE_MODEL env vars or constructor args,
so the same code also talks to LM Studio, Ollama, vLLM, etc.

Beyond chat, the client covers Lemonade's omni surface — same base URL,
same OpenAI-compatible shapes:

  speech()          POST /audio/speech         (TTS, default kokoro-v1)
  transcribe()      POST /audio/transcriptions (default Whisper-Large-v3-Turbo)
  vision()          POST /chat/completions     (image input, default Gemma-4)
  generate_image()  POST /images/generations   (default SDXL-Turbo)

Each model is overridable via its own LEMONADE_*_MODEL env var.
"""

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid


DEFAULT_BASE_URL = "http://localhost:13305/api/v1"
DEFAULT_MODEL = "Qwen3-8B"
DEFAULT_TTS_MODEL = "kokoro-v1"
DEFAULT_TTS_VOICE = "af_heart"
DEFAULT_STT_MODEL = "Whisper-Large-v3-Turbo"
DEFAULT_VISION_MODEL = "Gemma-4-E2B-it-GGUF"
DEFAULT_IMAGE_MODEL = "SDXL-Turbo"


class LemonadeClient:
    def __init__(self, base_url=None, model=None, api_key="lemonade", timeout=None):
        self.base_url = (
            base_url or os.environ.get("LEMONADE_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model = model or os.environ.get("LEMONADE_MODEL", DEFAULT_MODEL)
        self.tts_model = os.environ.get("LEMONADE_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.tts_voice = os.environ.get("LEMONADE_TTS_VOICE", DEFAULT_TTS_VOICE)
        self.stt_model = os.environ.get("LEMONADE_STT_MODEL", DEFAULT_STT_MODEL)
        self.vision_model = os.environ.get(
            "LEMONADE_VISION_MODEL", DEFAULT_VISION_MODEL)
        self.image_model = os.environ.get(
            "LEMONADE_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
        self.api_key = api_key
        # Generous default: CPU inference of a full pack can take 10+ minutes.
        self.timeout = (
            timeout if timeout is not None
            else int(os.environ.get("LEMONADE_TIMEOUT", "900"))
        )

    # -- transport ------------------------------------------------------

    def _send(self, req):
        """Open req and return raw response bytes; errors map to RuntimeError."""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"LLM API error {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach the model server at {self.base_url} "
                f"(is `lemonade serve` running? {e.reason})"
            ) from e

    def _post_json(self, path, payload):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        return json.loads(self._send(req).decode("utf-8"))

    @staticmethod
    def _extract_content(data):
        try:
            message = data["choices"][0]["message"]
            content = (message.get("content") or "").strip()
            if not content:
                # Reasoning models (e.g. Qwen3) may put output in reasoning_content
                content = (message.get("reasoning_content") or "").strip()
            return content
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected API response shape: {str(data)[:300]}") from e

    # -- chat -----------------------------------------------------------

    def chat(self, messages, temperature=0.7, max_tokens=2000):
        data = self._post_json("/chat/completions", {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self._extract_content(data)

    # -- speech (TTS) -----------------------------------------------------

    def speech(self, text):
        """Synthesize text to WAV bytes via POST /audio/speech."""
        req = urllib.request.Request(
            self.base_url + "/audio/speech",
            data=json.dumps({
                "model": self.tts_model,
                "input": text,
                "voice": self.tts_voice,
                "response_format": "wav",
            }).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        return self._send(req)

    # -- transcription (Whisper) ------------------------------------------

    def transcribe(self, audio_path):
        """Transcribe an audio file; returns the verbose_json response dict.

        The multipart/form-data body is built by hand (stdlib only). If the
        server answers with plain text instead of JSON, the transcript is
        returned as {"text": ..., "segments": []}.
        """
        boundary = "----shortsstand-" + uuid.uuid4().hex
        filename = os.path.basename(audio_path)
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(audio_path, "rb") as f:
            audio = f.read()

        def field(name, value):
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")

        body = b"".join([
            field("model", self.stt_model),
            field("response_format", "verbose_json"),
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode("utf-8"),
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ])
        req = urllib.request.Request(
            self.base_url + "/audio/transcriptions",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        raw = self._send(req).decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"text": raw.strip(), "segments": []}
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected transcription response: {raw[:300]}")
        data.setdefault("segments", [])
        return data

    # -- vision -------------------------------------------------------------

    def vision(self, image_path, prompt, system=None, temperature=0.4,
               max_tokens=1200):
        """Chat completion with an image, in OpenAI vision message format."""
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        })
        data = self._post_json("/chat/completions", {
            "model": self.vision_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self._extract_content(data)

    # -- image generation ---------------------------------------------------

    def generate_image(self, prompt):
        """Generate image(s); returns a list of raw image byte strings."""
        data = self._post_json("/images/generations", {
            "model": self.image_model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        })
        try:
            return [base64.b64decode(item["b64_json"]) for item in data["data"]]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"Unexpected image response shape: {str(data)[:300]}") from e

    # -- misc -----------------------------------------------------------------

    def health(self):
        """Best-effort reachability check; tries /health then /models."""
        for path in ("/health", "/models"):
            try:
                with urllib.request.urlopen(
                    self.base_url + path, timeout=5
                ) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                continue
        return False
