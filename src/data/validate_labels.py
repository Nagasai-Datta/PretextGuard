"""Phase 5: check every annotator reply against the schema, and write re-ask batches for the invalid items.

Run from the project root, any time replies have been saved (annotate.py also runs the same check on
every reply it saves):
    python -m src.data.validate_labels

A reply is the raw text a chat gave back, saved as data/labelled/<annotator>/<batch>.txt. check_reply
accepts it as JSON plain, inside a code fence, or inside a sentence of prose, then checks each item:
- the id is one the batch asked about, once;
- "tactics" has exactly the seven tactic keys, each 0 or 1;
- every claim has a known type, a non-empty span (at most 300 characters) that appears in the email as
  the annotator saw it (case and spacing ignored), and an organisation that is text or null;
- not more than 12 claims.
A reply that gives the same answer for every one of 10 or more emails, with no claims, is rejected as a
likely hijacked or lazy answer (LLM01, prompt injection: an email can tell the model to answer all zeros).

Items that fail, or that the reply left out, are re-asked once: they are written into
batches/reask_<annotator>_NNN.txt and the same annotator answers that file. An item that still fails after
its re-ask is dropped and counted (results/label_validation.csv).

The file names decide everything: batch_NNN (main batches, answered by annotator_1 and annotator_2),
reask_<annotator>_NNN (re-asks) and tiebreak_NNN (disagreements, answered by the tie-breaker).
"""

import csv
import json
import re
import sys

import pandas as pd

from src.data.batches import read_batch_file, write_batch_file
from src.data.label_schema import (
    ALL_ANNOTATORS,
    ANNOTATORS,
    BATCH_SIZE,
    CLAIM_TYPES,
    MAX_CLAIMS,
    MAX_SPAN_CHARS,
    TACTICS,
)
from src.data.paths import ANNOTATORS_CSV, BATCHES_DIR, LABEL_VALIDATION_CSV, LABELLED_DIR, RESULTS_DIR, relative

MAX_REPLY_CHARS = 400_000
MAX_ORGANISATION_CHARS = 100
LIST_KEYS = ("items", "results", "annotations", "emails")  # a reply that wrapped the array in an object


class ReplyProblem(ValueError):
    """The reply as a whole cannot be read."""


class ReplyCheck:
    """valid: {local_id: clean item}; problems: {local_id: [text]}; notes: reply-level remarks."""

    def __init__(self):
        self.valid, self.problems, self.notes = {}, {}, []


def extract_json(text):
    """Find the JSON array in a chat reply: plain, inside a code fence, or inside prose."""
    text = text.strip()
    if not text:
        raise ReplyProblem("the reply is empty")
    if len(text) > MAX_REPLY_CHARS:
        raise ReplyProblem("the reply is far too long")
    candidates = [text]
    fence = text.find("```")
    if fence >= 0:
        body_start, body_end = text.find("\n", fence), text.rfind("```")
        if 0 <= body_start < body_end:
            candidates.append(text[body_start + 1:body_end])
    first, last = text.find("["), text.rfind("]")
    if 0 <= first < last:
        candidates.append(text[first:last + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            data = next((data[key] for key in LIST_KEYS if isinstance(data.get(key), list)), data)
        if isinstance(data, list):
            return data
    raise ReplyProblem("no JSON array found in the reply")


def squash(text):
    """Lowercase with single spaces, for comparing two texts."""
    return " ".join(text.split()).casefold()


WORD = re.compile(r"[^\W_]+")  # a run of letters or digits; one character class, so it cannot backtrack


def word_key(text):
    """The email as a row of lowercase words with single spaces around each: punctuation and spacing do not matter."""
    return " " + " ".join(WORD.findall(text.casefold())) + " "


def span_in(span, key):
    """True if the span's words appear in a row in the email (key = word_key(email)).

    Comparing words, not characters, accepts what chats do to quotes (a restored apostrophe in the
    pre-tokenised Enron and Ling text, a dropped space before a comma) but still rejects a span whose words are
    not in the email.
    """
    words = WORD.findall(span.casefold())
    return bool(words) and " " + " ".join(words) + " " in key


def check_claims(raw_claims, shown_key):
    """Return (clean claims, problems) for a claims list checked against the email (shown_key = word_key(email))."""
    if not isinstance(raw_claims, list):
        return [], ["claims must be a list"]
    if len(raw_claims) > MAX_CLAIMS:
        return [], [f"more than {MAX_CLAIMS} claims"]
    claims, problems = [], []
    for claim in raw_claims:
        if not isinstance(claim, dict):
            problems.append("a claim is not an object")
            continue
        kind, span, organisation = claim.get("type"), claim.get("span"), claim.get("organisation")
        if kind not in CLAIM_TYPES:
            problems.append(f"unknown claim type {str(kind)[:40]!r}")
        elif not isinstance(span, str) or not span.strip():
            problems.append("a claim has no span")
        elif len(span) > MAX_SPAN_CHARS:
            problems.append("a claim span is too long")
        elif not span_in(span, shown_key):
            problems.append(f"a claim span is not in the email [{span.strip()[:60]!r}]")
        elif organisation is not None and (not isinstance(organisation, str) or len(organisation) > MAX_ORGANISATION_CHARS):
            problems.append("a claim organisation must be text or null")
        else:
            claims.append({"type": kind, "span": span.strip(), "organisation": organisation or None})
    return claims, problems


def check_item(item, shown_key):
    """Return (clean item or None, problems). shown_key is word_key() of the email as the annotator saw it."""
    if not isinstance(item, dict):
        return None, ["the item is not an object"]
    problems, tactics = [], {}

    raw_tactics = item.get("tactics")
    if not isinstance(raw_tactics, dict) or set(raw_tactics) != set(TACTICS):
        problems.append("tactics must have exactly the seven tactic keys")
    else:
        for name in TACTICS:
            value = raw_tactics[name]
            if isinstance(value, bool) or (isinstance(value, (int, float)) and value in (0, 1)):
                tactics[name] = int(value)
            else:
                problems.append(f"tactic {name} must be 0 or 1")

    claims, claim_problems = check_claims(item.get("claims"), shown_key)
    problems += claim_problems
    if problems:
        return None, problems
    return {"tactics": tactics, "claims": claims}, []


def check_reply(raw_text, expected):
    """Check one reply. expected is {local_id: shown text} for the batch it answers."""
    result = ReplyCheck()
    try:
        data = extract_json(raw_text)
    except ReplyProblem as problem:
        result.problems = {local_id: [f"reply unreadable: {problem}"] for local_id in expected}
        return result

    shown = {local_id: word_key(text) for local_id, text in expected.items()}
    seen, unknown = set(), []
    for item in data:
        local_id = item.get("id") if isinstance(item, dict) else None
        if local_id not in expected:
            unknown.append(str(local_id)[:30])
        elif local_id in seen:
            result.problems[local_id] = ["id appears twice"]
            result.valid.pop(local_id, None)
        else:
            seen.add(local_id)
            clean, problems = check_item(item, shown[local_id])
            if problems:
                result.problems[local_id] = problems
            else:
                result.valid[local_id] = clean
    for local_id in expected:
        if local_id not in seen:
            result.problems[local_id] = ["missing from the reply"]
    if unknown:
        result.notes.append(f"{len(unknown)} ids that are not in this batch were ignored (for example {unknown[0]!r})")

    answers = list(result.valid.values())
    if len(expected) >= 10 and len(answers) >= 10:
        first = answers[0]["tactics"]
        if all(a["tactics"] == first and not a["claims"] for a in answers):
            result.notes.append("identical answers for every email: rejected as a likely hijacked or lazy reply")
            result.problems.update({local_id: ["identical answers for every email"] for local_id in result.valid})
            result.valid = {}
    return result


def reply_path(annotator, stem):
    return LABELLED_DIR / annotator / f"{stem}.txt"


def batch_stems(annotator):
    """The batch files this annotator answers, in the order to do them."""
    names = sorted(path.stem for path in BATCHES_DIR.glob("*.txt")) if BATCHES_DIR.exists() else []
    reasks = [n for n in names if n.startswith(f"reask_{annotator}_")]
    if annotator in ANNOTATORS:
        return [n for n in names if n.startswith("batch_")] + reasks
    return [n for n in names if n.startswith("tiebreak_")] + reasks


def reply_ids(raw_text):
    """The set of ids a reply mentions, or None if the reply cannot be read as a JSON array."""
    try:
        data = extract_json(raw_text)
    except ReplyProblem:
        return None
    return {str(item.get("id")) for item in data if isinstance(item, dict)}


def check_reply_file(annotator, stem):
    expected = dict(read_batch_file(BATCHES_DIR / f"{stem}.txt"))
    return check_reply(reply_path(annotator, stem).read_text(encoding="utf-8"), expected)


class Answers:
    """Everything one annotator has answered so far."""

    def __init__(self):
        self.valid = {}           # local_id -> clean item (the latest valid answer)
        self.open = {}            # local_id -> problems, for items with no valid answer yet
        self.stems_total = 0
        self.stems_replied = 0
        self.problem_counts = {}  # problem text -> how often it occurred, over every reply
        self.notes = []


def load_answers(annotator):
    answers = Answers()
    for stem in batch_stems(annotator):
        answers.stems_total += 1
        if not reply_path(annotator, stem).exists():
            continue
        answers.stems_replied += 1
        check = check_reply_file(annotator, stem)
        answers.valid.update(check.valid)
        answers.notes += [f"{stem}: {note}" for note in check.notes]
        for local_id, problems in check.problems.items():
            answers.open[local_id] = problems
            for problem in problems:
                kind = problem.split(" [", 1)[0]  # the quoted detail is for reading, not for counting
                answers.problem_counts[kind] = answers.problem_counts.get(kind, 0) + 1
    answers.open = {k: v for k, v in answers.open.items() if k not in answers.valid}
    return answers


def reasked_ids(annotator):
    """(ids already put into a re-ask batch, ids in re-ask batches that have no reply yet)."""
    asked, waiting = set(), set()
    for stem in batch_stems(annotator):
        if stem.startswith("reask_"):
            ids = {local_id for local_id, _ in read_batch_file(BATCHES_DIR / f"{stem}.txt")}
            asked |= ids
            if not reply_path(annotator, stem).exists():
                waiting |= ids
    return asked, waiting


def all_texts():
    """{local_id: shown text} for every email in every main and tie-break batch file."""
    texts = {}
    for path in sorted(BATCHES_DIR.glob("*.txt")):
        if not path.stem.startswith("reask_"):
            texts.update(read_batch_file(path))
    return texts


def write_reasks(annotator, answers):
    """Write re-ask batches for items with no valid answer that have not been re-asked yet. Returns the file names."""
    asked, _ = reasked_ids(annotator)
    todo = [local_id for local_id in answers.open if local_id not in asked]
    if not todo:
        return []
    texts = all_texts()
    number = sum(1 for stem in batch_stems(annotator) if stem.startswith("reask_"))
    written = []
    for start in range(0, len(todo), BATCH_SIZE):
        number += 1
        name = f"reask_{annotator}_{number:03d}"
        write_batch_file(name, [(local_id, texts[local_id]) for local_id in todo[start:start + BATCH_SIZE]])
        written.append(name)
    return written


def model_names():
    if not ANNOTATORS_CSV.exists():
        return {}
    with open(ANNOTATORS_CSV, newline="", encoding="utf-8") as handle:
        return {row["annotator"]: row["model_name"].strip() for row in csv.DictReader(handle)}


def main():
    pd.set_option("display.width", 200)
    models = model_names()
    rows, summary = [], []
    for annotator in ALL_ANNOTATORS:
        answers = load_answers(annotator)
        written = write_reasks(annotator, answers)
        asked, waiting = reasked_ids(annotator)
        awaiting = [i for i in answers.open if i in waiting]
        dropped = [i for i in answers.open if i in asked and i not in waiting]
        if answers.stems_replied and not models.get(annotator):
            print(f"WARNING: {annotator} has replies but no model_name in {relative(ANNOTATORS_CSV)}")
        summary.append({
            "annotator": annotator, "model": models.get(annotator) or "(not set)",
            "batch files replied": f"{answers.stems_replied} of {answers.stems_total}",
            "items valid": len(answers.valid), "items awaiting re-ask": len(awaiting),
            "re-ask files written now": len(written), "items dropped": len(dropped),
        })
        rows += [(annotator, "batch_files_total", answers.stems_total), (annotator, "batch_files_replied", answers.stems_replied),
                 (annotator, "items_valid", len(answers.valid)), (annotator, "items_awaiting_reask", len(awaiting)),
                 (annotator, "reask_files_written", len(written)), (annotator, "items_dropped", len(dropped))]
        rows += [(annotator, f"problem: {problem}", count) for problem, count in sorted(answers.problem_counts.items())]
        for note in answers.notes:
            print(f"  note ({annotator}) {note}")

    print("Reply check, per annotator")
    print(pd.DataFrame(summary).to_string(index=False))
    for annotator in ALL_ANNOTATORS:
        counts = [(metric[9:], value) for who, metric, value in rows if who == annotator and metric.startswith("problem: ")]
        if counts:
            print(f"\nProblems seen in {annotator}'s replies (every reply file, before re-asks)")
            for problem, count in counts:
                print(f"  {count:>4}  {problem}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["annotator", "metric", "value"]).to_csv(LABEL_VALIDATION_CSV, index=False)
    print(f"\nSaved {relative(LABEL_VALIDATION_CSV)}")
    if any(entry["re-ask files written now"] for entry in summary):
        print("Re-ask files were written into data/labelled/batches/: run annotate.py next for that annotator to answer them.")


if __name__ == "__main__":
    sys.exit(main())
