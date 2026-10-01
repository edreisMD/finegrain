"""Client for the open teacher model that writes training data.

The teacher must be an open-weight model. Anthropic's and OpenAI's terms bar
using their outputs to train a competing model, so this client refuses to run
against them.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

CLOSED_MODEL = re.compile(r"claude|anthropic|\bgpt|openai|\bo[1-9]\b", re.IGNORECASE)
CLOSED_HOST = re.compile(r"anthropic\.com|openai\.com", re.IGNORECASE)
RETRIES = 3
MAX_TOKENS = 4096  # caps each reply; without it providers reserve credit for the model's max


class TeacherError(Exception):
    pass


class Teacher:
    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 120):
        if not base_url or not model:
            raise TeacherError("set TEACHER_BASE_URL and TEACHER_MODEL in .env")
        if CLOSED_MODEL.search(model) or CLOSED_HOST.search(base_url):
            raise TeacherError(f"teacher must be an open model, got {model} at {base_url}")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Teacher":
        return cls(
            os.environ.get("TEACHER_BASE_URL", ""),
            os.environ.get("TEACHER_MODEL", ""),
            os.environ.get("TEACHER_API_KEY", ""),
        )

    def chat(self, system: str, user: str, temperature: float = 0.9) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,
        }
        if "openrouter.ai" in self.url:
            # Thinking tokens count toward max_tokens. On long pages the model spent the
            # whole budget thinking and returned no content, so we turn thinking off.
            payload["reasoning"] = {"enabled": False}
        body = json.dumps(payload).encode()
        request = urllib.request.Request(self.url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        data = self._post(request)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TeacherError(f"unexpected response: {str(data)[:300]}") from exc
        if not content:  # some OpenRouter providers return null content
            raise TeacherError(f"empty reply (finish_reason={choice.get('finish_reason')})")
        return content

    def _post(self, request: urllib.request.Request) -> dict:
        """Send the request. Retry rate limits, server errors and dropped connections."""
        for attempt in range(RETRIES):
            if attempt:
                time.sleep(2 ** attempt)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                error = f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}"
                if exc.code != 429 and exc.code < 500:
                    raise TeacherError(error) from exc
            except OSError as exc:  # connection refused, reset, timeout
                error = f"cannot reach {self.url}: {exc}"
        raise TeacherError(f"{error} (after {RETRIES} tries)")


def extract_json(text: str):
    """Pull the first JSON array or object out of a model reply.

    Open models often wrap JSON in prose or ``` fences, so we scan for the
    first bracket that parses instead of calling json.loads on the whole reply.
    """
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char in "[{":
            try:
                value, _ = decoder.raw_decode(text[i:])
                return value
            except json.JSONDecodeError:
                continue
    raise TeacherError(f"no JSON in reply: {text[:200]}")
