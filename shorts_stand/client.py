"""Minimal OpenAI-compatible chat client (stdlib only).

Defaults to Lemonade Server's local endpoint: http://localhost:13305/api/v1
Override with LEMONADE_BASE_URL / LEMONADE_MODEL env vars or constructor args,
so the same code also talks to LM Studio, Ollama, vLLM, etc.
"""

import json
import os
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://localhost:13305/api/v1"
DEFAULT_MODEL = "Qwen3-8B"


class LemonadeClient:
    def __init__(self, base_url=None, model=None, api_key="lemonade", timeout=None):
        self.base_url = (
            base_url or os.environ.get("LEMONADE_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model = model or os.environ.get("LEMONADE_MODEL", DEFAULT_MODEL)
        self.api_key = api_key
        # Generous default: CPU inference of a full pack can take 10+ minutes.
        self.timeout = (
            timeout if timeout is not None
            else int(os.environ.get("LEMONADE_TIMEOUT", "900"))
        )

    def chat(self, messages, temperature=0.7, max_tokens=2000):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"LLM API error {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach the model server at {self.base_url} "
                f"(is `lemonade serve` running? {e.reason})"
            ) from e
        try:
            message = data["choices"][0]["message"]
            content = (message.get("content") or "").strip()
            if not content:
                # Reasoning models (e.g. Qwen3) may put output in reasoning_content
                content = (message.get("reasoning_content") or "").strip()
            return content
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Unexpected API response shape: {str(data)[:300]}") from e

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
