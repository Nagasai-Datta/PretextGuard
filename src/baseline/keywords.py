"""Keyword baseline: score an email body for the seven manipulation tactics with fixed word lists.

score_tactics(text) is the one function other code calls. It returns, for each tactic,
a score and the phrases that produced it:

    {"urgency": {"score": 1.0, "phrases": ["it is urgent"]}, "secrecy": {...}, ...}

How it works, in order:
1. normalise(text): lowercase, straight apostrophes, pre-tokenised contractions glued back
   ("don ' t" -> "don't"), apostrophes dropped ("dont"), every other punctuation mark turned
   into a space, placeholders such as [URL] kept as one word. The phrases in lexicon.py go
   through the same function, so both sides always look the same.
2. Split into words. For each word, look up the phrases that start with it and check that
   the next words match too. Matching is whole-word only: "now" never fires inside "know".
3. When two phrases of one tactic overlap in the text, the longer one wins ("this is urgent"
   beats "urgent"), so the same words are not counted twice.
4. Each distinct phrase counts once, however often it appears (a long spam message cannot score
   high by repeating itself). Strong phrases weigh 1.0, weak ones 0.5; the tactic score is the sum.
5. fired_tactics(scores) says which tactics reach the threshold (1.0 by default): one strong
   phrase, or two different weak ones.

This is the simple-rules baseline DistilBERT has to beat. It reads body_redacted, the same
payload-free text every PretextGuard model reads, so links and addresses never help it.

Security: phrase matching uses no regular expressions, and the few short patterns in normalise
have no nested or open-ended repeats beyond one character class, so nothing backtracks: the cost
grows in proportion to the text length. Bodies are cut at 200,000 characters (as in cleaning).
A crafted-input check runs in the self-test below.

Run the self-test from the project root:   python -m src.baseline.keywords
"""

import re
import time
import unicodedata
from typing import NamedTuple

from src.baseline.lexicon import LEXICON, LEXICON_VERSION, STRONG_WEIGHT, TACTICS, WEAK_WEIGHT

MAX_CHARS = 200_000
MAX_PHRASE_WORDS = 12
DEFAULT_THRESHOLD = 1.0

# Invisible characters that spammers insert inside words ("kee<zero-width space>p"), plus soft hyphen.
INVISIBLE = re.compile("[​-‏⁠﻿­]")
# Curly and look-alike apostrophes written as the plain one.
APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "‛": "'", "ʼ": "'", "´": "'", "`": "'"})
PLACEHOLDER = re.compile(r"\[(url|email|file|domain)\]")
# Pre-tokenised text (Kaggle Enron and Ling) writes "don't" as "don ' t". Only the real
# contraction endings are glued back, so a quoted word ("he said ' hello ' to her") stays apart.
SPACED_CONTRACTION = re.compile(r"(?<=[a-z]) ' (?=(?:t|s|re|ve|ll|d|m)(?![a-z0-9]))")
INNER_APOSTROPHE = re.compile(r"(?<=[a-z])'(?=[a-z])")
NOT_WORD = re.compile(r"[\W_]+")


class Entry(NamedTuple):
    """One phrase of the lexicon, ready for matching."""
    tactic: str
    phrase: str      # normalised text, used as the phrase's identity
    rest: list       # the words after the first one
    length: int      # number of words
    weight: float


def _placeholder_word(match):
    """[URL] becomes the word plhurl, so punctuation stripping cannot turn it into "url"."""
    return " plh" + match.group(1) + " "


def normalise(text):
    """Lowercase text with one space between words and no punctuation. Not a string -> ""."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text[:MAX_CHARS]).lower()
    text = INVISIBLE.sub("", text).translate(APOSTROPHES)
    text = PLACEHOLDER.sub(_placeholder_word, text)
    text = SPACED_CONTRACTION.sub("'", text)
    text = INNER_APOSTROPHE.sub("", text)
    return " ".join(NOT_WORD.sub(" ", text).split())


def build_index(lexicon):
    """Check a lexicon and turn it into {first word: [Entry, ...]}. Raises ValueError if it is malformed."""
    if set(lexicon) != set(TACTICS):
        raise ValueError("lexicon tactics must be exactly %s" % (TACTICS,))
    weights = {"strong": STRONG_WEIGHT, "weak": WEAK_WEIGHT}
    index = {}
    for tactic in TACTICS:
        if not set(lexicon[tactic]) <= set(weights):
            raise ValueError("%s: strengths must be 'strong' or 'weak'" % tactic)
        seen = set()
        for strength, phrases in lexicon[tactic].items():
            for raw in phrases:
                phrase = normalise(raw)
                words = phrase.split()
                if not words or len(words) > MAX_PHRASE_WORDS:
                    raise ValueError("%s: bad phrase %r" % (tactic, raw))
                if phrase in seen:
                    raise ValueError("%s: duplicate phrase %r" % (tactic, raw))
                seen.add(phrase)
                index.setdefault(words[0], []).append(Entry(tactic, phrase, words[1:], len(words), weights[strength]))
    return index


INDEX = build_index(LEXICON)


def score_tactics(text, index=INDEX):
    """Score text for every tactic: {tactic: {"score": float, "phrases": [matched phrases in text order]}}."""
    words = normalise(text).split()
    found = {tactic: [] for tactic in TACTICS}  # (length, start, entry) for every match
    for i, word in enumerate(words):
        for entry in index.get(word, ()):
            if words[i + 1:i + entry.length] == entry.rest:
                found[entry.tactic].append((entry.length, i, entry))

    result = {}
    for tactic in TACTICS:
        covered = bytearray(len(words)) if found[tactic] else b""
        chosen = {}  # phrase -> (start, weight): first accepted occurrence, so a phrase counts once
        # Longest phrases first: a phrase that overlaps an accepted longer one is dropped.
        for length, start, entry in sorted(found[tactic], key=lambda m: (-m[0], m[1])):
            if any(covered[start:start + length]):
                continue
            covered[start:start + length] = b"\x01" * length
            chosen.setdefault(entry.phrase, (start, entry.weight))
        ordered = sorted(chosen.items(), key=lambda item: item[1][0])
        result[tactic] = {"score": sum(weight for _, (_, weight) in ordered), "phrases": [p for p, _ in ordered]}
    return result


def fired_tactics(scores, threshold=DEFAULT_THRESHOLD):
    """Tactics whose score reaches the threshold. threshold is one number, or {tactic: number}
    where a tactic left out of the dict uses DEFAULT_THRESHOLD."""
    def limit(tactic):
        return threshold.get(tactic, DEFAULT_THRESHOLD) if isinstance(threshold, dict) else threshold
    return [t for t in TACTICS if scores[t]["score"] >= limit(t)]


# --------------------------------------------------------------------------------------
# Self-test: python -m src.baseline.keywords
# --------------------------------------------------------------------------------------

NORMALISE_PAIRS = [
    ("Don’t tell ANYONE!", "don ' t tell anyone ."),
    ("Please KEEP this\u2014between us.", "please keep this - between us ."),
    ("I’m sure you’ll help", "i ' m sure you ' ll help"),
    ("Click [URL] now", "click [url] now"),
    ("kee​p this", "keep this"),
    ("he said 'hello' to her", "he said ' hello ' to her"),
]

SAMPLES = [
    ("fake David (BEC)",
     "Hi, this is David from Finance. I need a quick favor. Please wire the payment before 3 PM today, "
     "it is urgent. Keep this between us and don't loop in your manager. I covered for you last month.",
     {"reciprocity", "urgency", "secrecy"}),
    ("ordinary work email",
     "Hi Sarah, attached are the notes from Tuesday's meeting. Can you send me the revised budget by Friday? "
     "Thanks, Mark",
     set()),
    ("advance-fee fraud",
     "Dear friend, I am the manager of the bank. This transaction is strictly confidential and requires "
     "absolute secrecy. In return for your help you will receive 30%. God bless you.",
     {"liking", "secrecy", "reciprocity"}),
    ("account phishing",
     "Your account will be suspended within 24 hours unless you verify. Final notice from the IT Security Team. "
     "Click [URL]",
     {"scarcity", "urgency", "authority"}),
]

BAD_LEXICONS = {
    "unknown tactic": {**{t: {"strong": ["x"]} for t in TACTICS}, "flattery": {"strong": ["x"]}},
    "bad strength": {**{t: {"strong": ["x"]} for t in TACTICS}, "urgency": {"medium": ["x"]}},
    "duplicate phrase": {**{t: {"strong": ["x"]} for t in TACTICS}, "urgency": {"strong": ["Don't"], "weak": ["dont"]}},
    "empty phrase": {**{t: {"strong": ["x"]} for t in TACTICS}, "urgency": {"strong": ["?!"]}},
}

CRAFTED_INPUTS = {
    "100,000 x 'i '": "i " * 100_000,
    "'keep this ' repeated": "keep this " * 20_000,
    "'act now ' repeated": "act now " * 25_000,
    "200,000 apostrophes": "'" * 200_000,
    "66,000 x ' ' ": " ' " * 66_000,
    "40,000 x [URL]": "[URL]" * 40_000,
    "zero-width spam": "kee​p​ " * 25_000,
    "one 200,000-letter word": "a" * 200_000,
}


def _self_test():
    failures = 0

    def check(ok, label):
        nonlocal failures
        failures += not ok
        print("  %s  %s" % ("PASS" if ok else "FAIL", label))

    print("Lexicon version %s: %d phrases, %d distinct first words" % (
        LEXICON_VERSION, sum(len(v) for v in INDEX.values()), len(INDEX)))
    print("Phrases per tactic (strong + weak):")
    for tactic in TACTICS:
        print("  %-13s %3d + %3d" % (tactic, len(LEXICON[tactic]["strong"]), len(LEXICON[tactic]["weak"])))

    print("\n1. Normalisation: both spellings must give the same text")
    for a, b in NORMALISE_PAIRS:
        check(normalise(a) == normalise(b), "%r == %r  ->  %r" % (a, b, normalise(a)))

    print("\n2. Sample emails (fires at score >= %.1f)" % DEFAULT_THRESHOLD)
    for name, text, expected in SAMPLES:
        scores = score_tactics(text)
        fired = set(fired_tactics(scores))
        check(fired == expected, "%s: fired %s" % (name, sorted(fired) or "nothing"))
        for tactic in TACTICS:
            if scores[tactic]["phrases"]:
                print("        %-13s %.1f  %s" % (tactic, scores[tactic]["score"], scores[tactic]["phrases"]))

    print("\n3. Scoring rules")
    check(score_tactics("This is urgent")["urgency"]["score"] == 1.0, "longest phrase wins: 'this is urgent' = 1.0, not 1.5")
    check(score_tactics("keep this between us " * 5)["secrecy"]["score"] == 1.0, "a repeated phrase counts once")
    check(score_tactics("hope you are well, my friend")["liking"]["score"] == 1.0, "two weak phrases add up to 1.0")
    check(score_tactics("hope you are well")["liking"]["score"] == 0.5, "one weak phrase alone (0.5) does not fire")
    check(not fired_tactics(score_tactics("I know the answer now")), "'now' inside 'know' does not match")
    check(score_tactics(None)["urgency"]["score"] == 0.0, "None scores zero")
    mixed = score_tactics("hope you are well. keep this between us")
    check(fired_tactics(mixed, {"liking": 0.5}) == ["liking", "secrecy"], "per-tactic thresholds: a tactic left out uses the default")
    a = score_tactics("Don't tell anyone")["secrecy"]
    b = score_tactics("don ' t tell anyone")["secrecy"]
    check(a == b and a["score"] == 1.0, "pre-tokenised text scores like normal text")

    print("\n4. Lexicon validation refuses a malformed lexicon")
    for name, bad in BAD_LEXICONS.items():
        try:
            build_index(bad)
            check(False, name)
        except ValueError as problem:
            check(True, "%s -> ValueError: %s" % (name, problem))

    print("\n5. Crafted inputs of 200,000 characters (each must take under 1 second)")
    slowest = 0.0
    for name, text in CRAFTED_INPUTS.items():
        start = time.perf_counter()
        score_tactics(text)
        seconds = time.perf_counter() - start
        slowest = max(slowest, seconds)
        check(seconds < 1.0, "%-28s %.3f s" % (name, seconds))

    print("\n%s" % ("All checks passed." if not failures else "%d check(s) FAILED." % failures))
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _self_test() else 0)
