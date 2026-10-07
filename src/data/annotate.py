"""Phase 5: the annotation loop. Copies the next batch to the clipboard and saves the chat's reply from it.

One batch, start to finish (an annotator is gemini, deepseek or zai):

    python -m src.data.annotate next gemini     copies the next unanswered batch prompt to the clipboard
    (open a FRESH chat with that service, paste, send, wait, then copy the whole reply)
    python -m src.data.annotate save gemini     saves the reply on the clipboard, then checks it

    python -m src.data.annotate status          progress of every annotator

The reply is saved exactly as the chat gave it, as data/labelled/<annotator>/<batch>.txt (the raw reply
is the record: nothing is edited). The check that follows is the same one validate_labels.py runs, so a
bad reply is known at once. Every save is logged in data/labelled/replies_log.csv with the time and the
model name from data/labelled/annotators.csv: fill that name in once per annotator (it is the model
shown in the chat window). Web chats cannot fix a temperature and their models change, so the log is
the record of which model answered when.

Fresh chat per batch, same service and same model for the whole run: that is what keeps the labels
comparable. Do not edit a reply, and do not answer a batch yourself.
"""

import csv
import sys
from datetime import datetime, timezone

from src.data.batches import read_batch_file
from src.data.clipboard import ClipboardError, copy, paste
from src.data.label_schema import ALL_ANNOTATORS
from src.data.paths import ANNOTATORS_CSV, BATCHES_DIR, REPLIES_LOG_CSV, relative
from src.data.validate_labels import batch_stems, check_reply_file, model_names, reply_path

LOG_COLUMNS = ["time_utc", "annotator", "model_name", "batch", "items", "valid", "invalid"]


def fail(message):
    sys.exit(f"{message}")


def require_model(annotator):
    model = model_names().get(annotator, "")
    if not model:
        fail(f"Fill in model_name for {annotator} in {relative(ANNOTATORS_CSV)} first (the model shown in that chat window).")
    return model


def next_stem(annotator):
    stems = batch_stems(annotator)
    if not stems:
        fail(f"No batch files for {annotator} yet. " + ("Run python -m src.data.batches first."
             if annotator != "zai" else "Tie-break batches appear after python -m src.data.agreement."))
    pending = [stem for stem in stems if not reply_path(annotator, stem).exists()]
    return (pending[0] if pending else None), len(stems) - len(pending), len(stems)


def cmd_next(annotator):
    require_model(annotator)
    stem, done, total = next_stem(annotator)
    if stem is None:
        print(f"{annotator}: all {total} batch files are answered. Run python -m src.data.validate_labels.")
        return
    prompt = (BATCHES_DIR / f"{stem}.txt").read_text(encoding="utf-8")
    try:
        copy(prompt)
        print(f"Copied {stem} ({done + 1} of {total} for {annotator}, {len(read_batch_file(BATCHES_DIR / f'{stem}.txt'))} emails) to the clipboard.")
        print("Open a fresh chat, paste, send. When the reply is complete, copy all of it and run:")
        print(f"  python -m src.data.annotate save {annotator}")
    except ClipboardError as problem:
        print(f"{problem}. Open {relative(BATCHES_DIR / (stem + '.txt'))}, copy it by hand, paste it into a fresh chat,")
        print(f"then save the reply as {relative(reply_path(annotator, stem))}.")


def cmd_save(annotator, stem=None):
    model = require_model(annotator)
    pending, done, total = next_stem(annotator)
    stem = stem or pending
    if stem is None:
        fail(f"{annotator} has no unanswered batch. To replace a reply, name it: save {annotator} batch_007")
    if stem not in batch_stems(annotator):
        fail(f"{stem} is not a batch for {annotator}")
    try:
        text = paste()
    except ClipboardError as problem:
        fail(f"{problem}. Save the reply by hand as {relative(reply_path(annotator, stem))} and run validate_labels.")
    if not text.strip():
        fail("The clipboard is empty. Copy the chat's reply first.")
    if "SECURITY NOTE" in text and '<email id="' in text:
        fail("The clipboard holds the prompt, not the reply. Copy the chat's answer and try again.")

    path = reply_path(annotator, stem)
    replaced = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    check = check_reply_file(annotator, stem)
    expected = len(read_batch_file(BATCHES_DIR / f"{stem}.txt"))

    new_file = not REPLIES_LOG_CSV.exists()
    with open(REPLIES_LOG_CSV, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(LOG_COLUMNS)
        writer.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), annotator, model, stem,
                         expected, len(check.valid), expected - len(check.valid)])

    print(f"Saved {relative(path)}" + (" (replaced an earlier reply)" if replaced else ""))
    print(f"{stem}: {len(check.valid)} of {expected} items valid")
    for local_id, problems in list(check.problems.items())[:8]:
        print(f"  {local_id}: {'; '.join(problems)}")
    for note in check.notes:
        print(f"  note: {note}")
    if check.problems:
        print("Invalid or missing items are re-asked once: run python -m src.data.validate_labels at the end.")
    after, done_now, total_now = next_stem(annotator)
    print(f"{annotator}: {done_now} of {total_now} batch files answered" + (f"; next: {after}" if after else "; all done"))


def cmd_status():
    models = model_names()
    print(f"{'annotator':<10} {'model':<28} {'answered':>10}   next")
    for annotator in ALL_ANNOTATORS:
        stems = batch_stems(annotator)
        pending = [stem for stem in stems if not reply_path(annotator, stem).exists()]
        print(f"{annotator:<10} {(models.get(annotator) or '(model not set)'):<28} {len(stems) - len(pending):>4} of {len(stems):<4}  {pending[0] if pending else '-'}")


def main(argv):
    usage = "usage: python -m src.data.annotate status | next <annotator> | save <annotator> [batch]"
    if len(argv) == 1 and argv[0] == "status":
        return cmd_status()
    if len(argv) in (2, 3) and argv[0] in ("next", "save") and argv[1] in ALL_ANNOTATORS:
        if argv[0] == "next" and len(argv) == 2:
            return cmd_next(argv[1])
        if argv[0] == "save":
            return cmd_save(argv[1], argv[2] if len(argv) == 3 else None)
    fail(usage + f"\nannotators: {', '.join(ALL_ANNOTATORS)}")


if __name__ == "__main__":
    main(sys.argv[1:])
