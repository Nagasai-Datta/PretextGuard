"""Phase 5: the annotation loop. Two ways to run it, with identical files and checks.

AUTOMATIC (recommended): one command sends every batch to the annotator's API and saves the replies.

    python -m src.data.annotate check annotator_1       one tiny real request: is the key, address and model right?
    python -m src.data.annotate auto annotator_1 --limit 2   the first two batches only, to see it work
    python -m src.data.annotate auto annotator_1         all pending batches; safe to stop and start again

BY HAND: copy a batch, paste it into a fresh chat, paste the reply back.

    python -m src.data.annotate next annotator_1  copies the next unanswered batch prompt to the clipboard
    (open a FRESH chat with that service, paste, send, wait, then copy the whole reply)
    python -m src.data.annotate save annotator_1  saves the reply on the clipboard, then checks it

    python -m src.data.annotate status          progress of every annotator

An annotator is annotator_1, annotator_2 or tiebreaker. Whichever way a reply arrives it is saved exactly
as received, as data/labelled/<annotator>/<batch>.txt, checked by validate_labels' rules at once, and logged
in data/labelled/replies_log.csv with the time and the model name. Fresh request per batch, one model per
annotator for the whole run: that is what keeps the labels comparable. Do not edit a reply.

In automatic mode the model name is the API model id plus "(API, temperature 0)", written into annotators.csv for
you. Temperature 0 asks the model for its most likely answer every time, which web chats cannot do. If an
annotator already has replies from a different model, auto refuses: one annotator must be one model.
By hand, the model name in annotators.csv is the one you type (the model shown in the chat window).
"""

import csv
import sys
from datetime import datetime, timezone

from src.data import llm_api
from src.data.batches import read_batch_file
from src.data.clipboard import ClipboardError, copy, paste
from src.data.label_schema import ALL_ANNOTATORS, ANNOTATORS, TIEBREAKER
from src.data.paths import ANNOTATORS_CSV, BATCHES_DIR, REPLIES_LOG_CSV, relative
from src.data.validate_labels import batch_stems, check_reply_file, model_names, reply_ids, reply_path

LOG_COLUMNS = ["time_utc", "annotator", "model_name", "batch", "items", "valid", "invalid"]
TEMPERATURE = 0.0


def fail(message):
    sys.exit(f"{message}")


def require_model(annotator):
    model = model_names().get(annotator, "")
    if not model:
        fail(f"Fill in model_name for {annotator} in {relative(ANNOTATORS_CSV)} first (the model shown in that chat window).")
    return model


def set_model_name(annotator, name, service=None):
    """Write the model name (and, if given, the service) of one annotator into annotators.csv."""
    with open(ANNOTATORS_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["annotator"] == annotator:
            row["model_name"] = name
            if service:
                row["chat_service"] = service
            break
    else:
        rows.append({"annotator": annotator, "chat_service": service or "", "model_name": name, "role": ""})
    with open(ANNOTATORS_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def log_rows():
    if not REPLIES_LOG_CSV.exists():
        return []
    with open(REPLIES_LOG_CSV, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def pending_stems(annotator):
    stems = batch_stems(annotator)
    if not stems:
        fail(f"No batch files for {annotator} yet. " + ("Run python -m src.data.batches first."
             if annotator != TIEBREAKER else "Tie-break batches appear after python -m src.data.agreement."))
    return [stem for stem in stems if not reply_path(annotator, stem).exists()], len(stems)


def next_stem(annotator):
    pending, total = pending_stems(annotator)
    return (pending[0] if pending else None), total - len(pending), total


def store_reply(annotator, stem, text, model, guard):
    """Save a reply as received, check it, log it. guard=True (by hand) refuses a reply that is obviously the wrong one."""
    expected_ids = {local_id for local_id, _ in read_batch_file(BATCHES_DIR / f"{stem}.txt")}
    if guard:
        ids = reply_ids(text)
        if ids and not ids & expected_ids:
            fail(f"This reply answers other emails (ids like {sorted(ids)[0]}), not {stem}. Nothing was saved.\n"
                 f"Run python -m src.data.annotate next {annotator}, paste it into a fresh chat, copy the NEW reply, then save.")
        for other in batch_stems(annotator):
            if other != stem and reply_path(annotator, other).exists() and reply_path(annotator, other).read_text(encoding="utf-8").strip() == text.strip():
                fail(f"The clipboard holds the same reply you already saved as {other}. Nothing was saved.\n"
                     f"Run python -m src.data.annotate next {annotator}, paste it into a fresh chat, copy the NEW reply, then save.")

    path = reply_path(annotator, stem)
    replaced = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    check = check_reply_file(annotator, stem)
    expected = len(expected_ids)

    new_file = not REPLIES_LOG_CSV.exists()
    with open(REPLIES_LOG_CSV, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(LOG_COLUMNS)
        writer.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), annotator, model, stem,
                         expected, len(check.valid), expected - len(check.valid)])
    return check, expected, replaced, path


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

    check, expected, replaced, path = store_reply(annotator, stem, text, model, guard=True)
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
    if after:
        print(f"To continue, run next first: python -m src.data.annotate next {annotator}")


def api_conflicts(annotator, model):
    """Stems whose saved reply came from a different model than the one about to be used."""
    latest = {row["batch"]: row["model_name"] for row in log_rows() if row["annotator"] == annotator}
    return [stem for stem in batch_stems(annotator) if reply_path(annotator, stem).exists() and latest.get(stem, "(unknown)") != model]


def cmd_check(annotator):
    try:
        if not llm_api.get(f"{annotator.upper()}_MODEL") and not llm_api.PROVIDERS[annotator]["model"]:
            models = llm_api.list_models(annotator)
            print(f"The key works. No {annotator.upper()}_MODEL is set yet. Models offered ({len(models)}):")
            for name in models[:60]:
                print(f"  {name}")
            print(f"Pick a fast, free one (for Gemini: an id with 'flash' in it), add  {annotator.upper()}_MODEL=that-id  to .env, then run check again.")
            print("annotator_1, annotator_2 and tiebreaker must each use a DIFFERENT model.")
            return
        s = llm_api.settings(annotator)
        reply = llm_api.chat(annotator, "Reply with the single word: pong", temperature=TEMPERATURE, timeout=(15, 90), attempts=2)
    except llm_api.ApiError as problem:
        message = f"NOT working: {problem}"
        if "Timeout" in str(problem):
            message += "\nNo answer within 90 seconds: this model is too slow, busy, or not a text chat model. Try another id from the list."
        if "model" in str(problem).lower():  # a wrong model id: show the ids this key can use
            try:
                names = llm_api.list_models(annotator)
                message += f"\nModels this key can use:\n  " + "\n  ".join(names[:40]) + f"\nPut one in .env as {annotator.upper()}_MODEL=the-id and run check again."
            except llm_api.ApiError:
                pass
        fail(message)
    print(f"OK: {annotator} answered through the API in {reply.seconds:.1f} s. Model {s.model}, the provider says it used {reply.model}.")
    print(f"Reply: {reply.text.strip()[:60]!r}. Next:  python -m src.data.annotate auto {annotator} --limit 2")


def cmd_auto(annotator, limit, force):
    try:
        model = llm_api.label(annotator, TEMPERATURE)
    except llm_api.ApiError as problem:
        fail(f"{problem}")
    mine = llm_api.identity(annotator)
    for other in ANNOTATORS:
        if annotator in ANNOTATORS and other != annotator and llm_api.identity(other) == mine and not force:
            fail(f"{annotator} and {other} would call the same model ({mine[1]}). Two annotators must be two different models, "
                 f"or their agreement score measures nothing.\nSet a different {annotator.upper()}_MODEL or {other.upper()}_MODEL in .env "
                 f"(python -m src.data.annotate check {annotator} lists the ids). --force overrides.")
    conflicts = api_conflicts(annotator, model)
    if conflicts and not force:
        fail(f"{annotator} already has {len(conflicts)} reply file(s) from another model (for example {conflicts[0]}). One annotator must be one model.\n"
             f"Delete them, for example:  rm {relative(reply_path(annotator, conflicts[0]))}   then run auto again. (--force keeps them and mixes models.)")
    pending, total = pending_stems(annotator)
    if not pending:
        print(f"{annotator}: all {total} batch files are answered. Run python -m src.data.validate_labels.")
        return
    set_model_name(annotator, model, llm_api.service_name(annotator))
    todo = pending[:limit] if limit else pending
    print(f"{annotator}: {len(pending)} batch file(s) to do, running {len(todo)} now with {model}. You can stop with Ctrl+C and start again.")
    for number, stem in enumerate(todo, start=1):
        started = datetime.now()
        try:
            reply = llm_api.chat(annotator, (BATCHES_DIR / f"{stem}.txt").read_text(encoding="utf-8"), temperature=TEMPERATURE)
        except llm_api.ApiError as problem:
            fail(f"Stopped at {stem}: {problem}\nNothing is lost; run the same command again to continue from {stem}.")
        check, expected, _, _ = store_reply(annotator, stem, reply.text, model, guard=False)
        seconds = (datetime.now() - started).total_seconds()
        extra = "  (cut off at the length limit)" if reply.truncated else ""
        print(f"  [{number}/{len(todo)}] {stem}: {len(check.valid)} of {expected} items valid, {seconds:.0f} s{extra}")
        if number < len(todo):
            llm_api.pause()
    pending_now, total_now = pending_stems(annotator)
    print(f"{annotator}: {total_now - len(pending_now)} of {total_now} batch files answered." + (" Run python -m src.data.validate_labels next." if not pending_now else ""))


def cmd_status():
    models = model_names()
    print(f"{'annotator':<10} {'model':<40} {'answered':>10}   next")
    for annotator in ALL_ANNOTATORS:
        stems = batch_stems(annotator)
        pending = [stem for stem in stems if not reply_path(annotator, stem).exists()]
        print(f"{annotator:<10} {(models.get(annotator) or '(model not set)'):<40} {len(stems) - len(pending):>4} of {len(stems):<4}  {pending[0] if pending else '-'}")


def main(argv):
    usage = ("usage: python -m src.data.annotate status | check <annotator> | auto <annotator> [--limit N] [--force]"
             " | next <annotator> | save <annotator> [batch]")
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    limit = None
    if "--limit" in flags:
        try:
            limit = int(args.pop())
        except (IndexError, ValueError):
            fail(usage)
    if args == ["status"]:
        return cmd_status()
    if len(args) in (2, 3) and args[0] in ("next", "save", "check", "auto") and args[1] in ALL_ANNOTATORS:
        if args[0] == "next" and len(args) == 2:
            return cmd_next(args[1])
        if args[0] == "save":
            return cmd_save(args[1], args[2] if len(args) == 3 else None)
        if args[0] == "check" and len(args) == 2:
            return cmd_check(args[1])
        if args[0] == "auto" and len(args) == 2:
            return cmd_auto(args[1], limit, "--force" in flags)
    fail(usage + f"\nannotators: {', '.join(ALL_ANNOTATORS)}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit("\nStopped by you. Nothing is lost; run the same command again to continue.")
