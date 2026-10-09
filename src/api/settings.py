"""Phase 11: the settings of the API, read once at start-up and checked before anything is served.

    from src.api.settings import load_settings
    settings = load_settings()          # raises SettingsError if the API key is missing, too short or still the placeholder

    python -m src.api.settings              # show the settings that would be used (the key is masked)
    python -m src.api.settings --new-key    # print a fresh random key to put in .env

WHERE THE VALUES COME FROM. The real environment first, then the .env file in the project root (never committed; .env.example lists the names).
A line in .env is NAME=VALUE; a line starting with # is a comment; matching quotes around a value are removed. Nothing else is supported on purpose.

    PRETEXTGUARD_API_KEY         required: at least 24 characters, printable ASCII, no spaces, at least 8 different characters, not the placeholder
    PRETEXTGUARD_RATE_ANALYZE    limit per client for /analyze and /analyze/thread together      default 30/minute
    PRETEXTGUARD_RATE_EXPLAIN    limit per client for /explain (LIME costs about 100 times a normal analysis)   default 6/minute
    PRETEXTGUARD_RATE_GLOBAL     limit per client for every route together, counted before anything is read    default 120/minute
    PRETEXTGUARD_EXPLAIN_SAMPLES LIME copies per explanation (50 to 2000)                      default 150 (4.9 s on the Mac; 300 copies take 10.6 s)
    PRETEXTGUARD_WAIT_SECONDS    how long /analyze waits for the classifier before it answers 503 (0 to 30)    default 2
    PRETEXTGUARD_ALLOWED_HOSTS   comma-separated Host header values accepted (no '*')          default 127.0.0.1,localhost
    PRETEXTGUARD_ENABLE_DOCS     1 turns on /docs, /redoc and /openapi.json (development only)  default 0
    PRETEXTGUARD_HOST, _PORT     where `python -m src.api.main` listens                       default 127.0.0.1 and 8000

THE SIZE CAPS ARE CONSTANTS, NOT SETTINGS. A cap that a typo in .env can raise is not a control. They are the numbers of the plan in master
document Section 8.19: 4 MB per request, 300,000 bytes per email (the pipeline's own cap, so the API never accepts what the pipeline would cut),
50 messages and 1.5 MB per thread.

FAIL CLOSED. Anything wrong stops the start-up with a message that never contains the key itself.
"""

import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

from limits import parse as parse_rate

from src.data.paths import PROJECT_ROOT, RESULTS_DIR

ENV_FILE = PROJECT_ROOT / ".env"
PREFIX = "PRETEXTGUARD_"

# The caps (bytes unless stated). The pipeline's own limits (300,000 bytes per message, 50 messages) are a second line behind these.
MAX_BODY_BYTES = 4_000_000          # one request, counted while it streams in (Content-Length can lie or be missing)
MAX_EMAIL_BYTES = 300_000           # one email, in UTF-8 bytes
MAX_THREAD_MESSAGES = 50
MAX_THREAD_BYTES = 1_500_000        # all messages of one thread together
MAX_DOMAIN_CHARS = 253
MIN_KEY_CHARS, MAX_KEY_CHARS, MIN_KEY_DISTINCT = 24, 256, 8
PLACEHOLDER_KEYS = frozenset(("change-me", "changeme", "paste-your-key-here", "your-key-here", "secret", "password"))
LIME_MIN_SAMPLES, LIME_MAX_SAMPLES = 50, 2000
LIMIT_CONCURRENCY = 20              # uvicorn answers 503 beyond this many open connections


class SettingsError(Exception):
    """A setting is missing or unusable. The message never holds the API key."""


def read_env_file(path):
    """{NAME: VALUE} from a .env file (empty when the file is missing). Plain lines only: NAME=VALUE, # comments, optional matching quotes."""
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def check_key(key):
    """The problems with an API key as a list of short sentences (empty when it is usable). Never repeats the key."""
    if not isinstance(key, str) or not key:
        return ["PRETEXTGUARD_API_KEY is missing"]
    problems = []
    if key.strip().lower() in PLACEHOLDER_KEYS:
        problems.append("PRETEXTGUARD_API_KEY is still the placeholder from .env.example")
    if len(key) < MIN_KEY_CHARS:
        problems.append("PRETEXTGUARD_API_KEY is %d characters; at least %d are needed" % (len(key), MIN_KEY_CHARS))
    if len(key) > MAX_KEY_CHARS:
        problems.append("PRETEXTGUARD_API_KEY is longer than %d characters" % MAX_KEY_CHARS)
    if not (key.isascii() and key.isprintable()) or " " in key:
        problems.append("PRETEXTGUARD_API_KEY must be printable ASCII without spaces (it travels in an HTTP header)")
    if len(set(key)) < MIN_KEY_DISTINCT:
        problems.append("PRETEXTGUARD_API_KEY uses fewer than %d different characters" % MIN_KEY_DISTINCT)
    return problems


def new_key():
    """A fresh random key: 32 random bytes as 43 URL-safe characters."""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Settings:
    """Everything the API reads from outside. Checked on creation, so a Settings object that exists is a usable one."""

    api_key: str = field(repr=False)
    rate_analyze: str = "30/minute"
    rate_explain: str = "6/minute"
    rate_global: str = "120/minute"
    explain_samples: int = 150
    wait_seconds: float = 2.0
    allowed_hosts: tuple = ("127.0.0.1", "localhost")
    enable_docs: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    results_dir: Path = RESULTS_DIR

    def __post_init__(self):
        problems = check_key(self.api_key)
        for name in ("rate_analyze", "rate_explain", "rate_global"):
            try:
                parse_rate(getattr(self, name))
            except Exception:
                problems.append("%s%s is not a rate such as 30/minute" % (PREFIX, name.upper()))
        if not LIME_MIN_SAMPLES <= self.explain_samples <= LIME_MAX_SAMPLES:
            problems.append("%sEXPLAIN_SAMPLES must be from %d to %d" % (PREFIX, LIME_MIN_SAMPLES, LIME_MAX_SAMPLES))
        if not 0 <= self.wait_seconds <= 30:
            problems.append("%sWAIT_SECONDS must be from 0 to 30" % PREFIX)
        if not self.allowed_hosts or any((not h) or "*" in h or " " in h for h in self.allowed_hosts):
            problems.append("%sALLOWED_HOSTS must list host names and must not contain '*'" % PREFIX)
        if not 1 <= self.port <= 65535:
            problems.append("%sPORT must be from 1 to 65535" % PREFIX)
        if problems:
            raise SettingsError("; ".join(problems))

    def masked_key(self):
        return "%s... (%d characters)" % (self.api_key[:4], len(self.api_key))

    def summary(self):
        """Lines for a human; the key is masked."""
        lines = ["API key        %s" % self.masked_key(),
                 "listens on     http://%s:%d%s" % (self.host, self.port, "" if self.host in ("127.0.0.1", "localhost") else "   (NOT the loopback address: anyone who can reach this machine can reach the API)"),
                 "rate limits    /analyze %s, /explain %s, every route %s (per client address)" % (self.rate_analyze, self.rate_explain, self.rate_global),
                 "explain        %d LIME copies; /analyze waits %.1f s for the classifier" % (self.explain_samples, self.wait_seconds),
                 "allowed hosts  %s" % ", ".join(self.allowed_hosts),
                 "docs           %s" % ("ON (development only)" if self.enable_docs else "off"),
                 "caps           %d bytes per request, %d per email, %d messages and %d bytes per thread" % (MAX_BODY_BYTES, MAX_EMAIL_BYTES, MAX_THREAD_MESSAGES, MAX_THREAD_BYTES),
                 "results        %s" % self.results_dir]
        return lines


def flag(text):
    return str(text).strip().lower() in ("1", "true", "yes", "on")


def load_settings(environ=None, env_file=ENV_FILE):
    """Settings from the real environment, then the .env file (a name in the environment wins). Raises SettingsError."""
    merged = dict(read_env_file(env_file)) if env_file else {}
    merged.update(os.environ if environ is None else environ)

    def get(name, default):
        value = merged.get(PREFIX + name)
        return default if value is None or str(value).strip() == "" else str(value).strip()

    try:
        return Settings(
            api_key=merged.get(PREFIX + "API_KEY", "") or "",
            rate_analyze=get("RATE_ANALYZE", Settings.rate_analyze), rate_explain=get("RATE_EXPLAIN", Settings.rate_explain),
            rate_global=get("RATE_GLOBAL", Settings.rate_global),
            explain_samples=int(get("EXPLAIN_SAMPLES", Settings.explain_samples)), wait_seconds=float(get("WAIT_SECONDS", Settings.wait_seconds)),
            allowed_hosts=tuple(h.strip().lower() for h in get("ALLOWED_HOSTS", ",".join(Settings.allowed_hosts)).split(",") if h.strip()),
            enable_docs=flag(get("ENABLE_DOCS", "0")), host=get("HOST", Settings.host), port=int(get("PORT", Settings.port)))
    except ValueError:
        raise SettingsError("a setting that should be a number is not one")


def main(argv):
    if "--new-key" in argv:
        print(new_key())
        return 0
    try:
        settings = load_settings()
    except SettingsError as error:
        print("Settings problem: %s" % error)
        if "API_KEY" in str(error):
            print("Make a key with:  python -m src.api.settings --new-key")
            print("and put it in %s as  PRETEXTGUARD_API_KEY=..." % ENV_FILE)
        return 1
    print("\n".join(settings.summary()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
