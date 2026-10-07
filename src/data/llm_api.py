"""Call a chat model through its API: one function for Gemini and any other OpenAI-style service.

Services that accept the "chat completions" request (the format OpenAI made common) all work with this one
function. It replaces pasting by hand: annotate.py auto <annotator> and synthetic.py auto send each prompt and
save the reply exactly as the copy-and-paste loop would.

Three roles are configured here: annotator_1, annotator_2 and tiebreaker. By default all three call Google's
Gemini API with the one GEMINI_API_KEY (the only free key that was available), each with its own model id.
Settings come from environment variables or from the project's .env file (never committed; .env.example lists
the names). For a role P in ANNOTATOR_1, ANNOTATOR_2, TIEBREAKER:
    GEMINI_API_KEY  the key (or P_API_KEY to give one role a different service's key)
    P_MODEL        required: the model id this role calls. Use a DIFFERENT model for each role; list the ids your
                   key can use with  python -m src.data.annotate check annotator_1
    P_BASE_URL     optional: another service's address (for example another provider's OpenAI-style endpoint)
    P_MAX_TOKENS   optional: longest reply to allow, default 8000 (0 leaves the provider's own limit)
    API_PAUSE_SECONDS   optional: wait between two requests, default 3
    API_RETRY_SECONDS   optional: first wait after a rate-limit or server error, default 10

Free tiers have rate limits, so a request that gets 429 or a server error is retried up to 5 times with a
growing wait. Any other error stops with the provider's own message.

Security:
- The key is read from .env or the environment, sent only in the Authorization header, and removed from
  every error message. It is never printed or logged.
- Only https:// addresses are accepted (http:// only for 127.0.0.1 and localhost, so the code can be tested
  against a local stand-in).
- Every request has a timeout, and a reply over 4 MB is refused.
- The prompts hold public-corpus emails with links, addresses and domains already replaced by placeholders
  (body_redacted). They still leave the machine, and a free tier may let the provider use them to improve its
  products: check each provider's terms, and say so in the report.
"""

import os
import time
from typing import NamedTuple
from urllib.parse import urlparse

import requests

from src.data.paths import PROJECT_ROOT, relative

ENV_FILE = PROJECT_ROOT / ".env"

# Addresses taken from each provider's OpenAI-compatible quickstart (checked in October 2026 against
# several independent sources; the official pages could not be reached from the build sandbox, so
# annotate.py check <annotator> makes one tiny real request before you start).
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
PROVIDERS = {
    role: {"name": role.replace("_", " "), "base": GEMINI_BASE, "model": "", "key_fallback": "GEMINI_API_KEY"}
    for role in ("annotator_1", "annotator_2", "tiebreaker")
}

MAX_ATTEMPTS = 5
MAX_RESPONSE_BYTES = 4_000_000
RETRY_STATUS = (408, 429, 500, 502, 503, 504)
DEFAULT_MAX_TOKENS = 8000


class ApiError(RuntimeError):
    """A request failed in a way retrying will not fix."""


class Settings(NamedTuple):
    provider: str
    key: str
    model: str
    base: str
    max_tokens: int


class Reply(NamedTuple):
    text: str
    model: str            # the model name the provider says it used
    truncated: bool       # the provider stopped at its length limit
    prompt_tokens: object
    completion_tokens: object
    seconds: float = 0.0   # how long the successful request took


def _env_file_values():
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, _, value = line.partition("=")
                values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def get(name):
    """An environment variable, else the value in .env, else an empty string."""
    return (os.environ.get(name) or _env_file_values().get(name) or "").strip()


def settings(provider, need_model=True):
    info, prefix = PROVIDERS[provider], provider.upper()
    key = get(f"{prefix}_API_KEY") or (get(info["key_fallback"]) if info.get("key_fallback") else "")
    if not key or "paste" in key.lower():
        raise ApiError(f"No API key for {provider} in {relative(ENV_FILE)}. Add the line {info.get('key_fallback') or prefix + '_API_KEY'}=your-key")
    model = get(f"{prefix}_MODEL") or info["model"]
    if need_model and not model:
        raise ApiError(f"No {prefix}_MODEL in {relative(ENV_FILE)}. Run python -m src.data.annotate check {provider} to list the model ids, then add {prefix}_MODEL=the-id")
    base = (get(f"{prefix}_BASE_URL") or info["base"]).rstrip("/")
    if not (base.startswith("https://") or urlparse(base).hostname in ("127.0.0.1", "localhost")):
        raise ApiError(f"{prefix}_BASE_URL must start with https://")
    return Settings(provider, key, model, base, int(get(f"{prefix}_MAX_TOKENS") or DEFAULT_MAX_TOKENS))


def identity(provider):
    """(address, model) a role would call, or None when it is not set up yet. Two annotators must differ."""
    try:
        s = settings(provider)
    except ApiError:
        return None
    return (s.base, s.model)


def label(provider, temperature):
    """The model name to record in annotators.csv and the reply log."""
    return f"{settings(provider).model} (API, temperature {temperature:g})"


def service_name(provider):
    """The host name the role calls (for example generativelanguage.googleapis.com), for the records."""
    return urlparse(settings(provider, need_model=False).base).hostname or ""


def scrub(text, key):
    """Shorten a provider's error text and remove the key from it."""
    return str(text).replace(key, "[key]")[:300]


def pause():
    time.sleep(float(get("API_PAUSE_SECONDS") or 3))


def _parse(response, s):
    try:
        data = response.json()
        choice = data["choices"][0]
        text = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ApiError(f"{s.provider}: the reply was not in the expected format: {scrub(response.text, s.key)}")
    if not isinstance(text, str) or not text.strip():
        raise ApiError(f"{s.provider}: the reply was empty (finish reason {choice.get('finish_reason')})")
    usage = data.get("usage") or {}
    return Reply(text, str(data.get("model") or s.model), choice.get("finish_reason") == "length",
                 usage.get("prompt_tokens"), usage.get("completion_tokens"))


def chat(provider, prompt, temperature=0.0, timeout=(15, 600), attempts=MAX_ATTEMPTS):
    """Send one prompt as a single user message and return a Reply. Raises ApiError when it cannot.

    timeout is (seconds to connect, seconds to wait for the answer); attempts is how many times a rate-limit or
    server error is tried. The defaults suit a full 20-email batch; check uses much shorter ones."""
    s = settings(provider)
    body = {"model": s.model, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    if s.max_tokens:
        body["max_tokens"] = s.max_tokens
    headers = {"Authorization": f"Bearer {s.key}", "Content-Type": "application/json"}
    wait, problem = float(get("API_RETRY_SECONDS") or 10), ""
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            response = requests.post(f"{s.base}/chat/completions", headers=headers, json=body, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as error:
            problem = f"network error ({type(error).__name__})"
        else:
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ApiError(f"{provider}: the reply is far too large")
            if response.status_code == 200:
                return _parse(response, s)._replace(seconds=time.perf_counter() - started)
            if response.status_code == 400:  # a model that refuses an optional setting: drop it and ask again
                refused = [p for p in ("temperature", "max_tokens") if p in body and p in response.text.lower()]
                for p in refused:
                    del body[p]
                if refused:
                    continue
            if response.status_code not in RETRY_STATUS:
                raise ApiError(f"{provider}: HTTP {response.status_code}: {scrub(response.text, s.key)}")
            problem = f"HTTP {response.status_code}"
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                wait = max(wait, min(int(retry_after), 300))
        if attempt == attempts:
            raise ApiError(f"{provider}: {problem} on all {attempts} tries")
        print(f"    {problem}; waiting {wait:.0f} s, then trying again ({attempt} of {attempts})")
        time.sleep(wait)
        wait = min(wait * 2, 120)


def list_models(provider):
    """The model ids the provider offers this key, or raises ApiError."""
    s = settings(provider, need_model=False)
    try:
        response = requests.get(f"{s.base}/models", headers={"Authorization": f"Bearer {s.key}"}, timeout=(15, 60))
    except (requests.ConnectionError, requests.Timeout) as error:
        raise ApiError(f"{provider}: network error ({type(error).__name__})")
    if response.status_code != 200:
        raise ApiError(f"{provider}: HTTP {response.status_code}: {scrub(response.text, s.key)}")
    try:
        entries = response.json().get("data", [])
    except ValueError:
        raise ApiError(f"{provider}: the model list was not JSON")
    return sorted({str(m.get("id", "")).removeprefix("models/") for m in entries if isinstance(m, dict)} - {""})
