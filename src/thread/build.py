"""Phase 9: rebuild the real threads, measure how often the thread verifier fires on them, and check the work.

Run from the project root (after Phases 1 to 8; the tactic model and spaCy are needed only for the last two commands):
    python -m src.thread.selftest                      # hand-made threads and crafted input only (no data, no model)
    python -m src.thread.build --count                 # find the threads and print what was found; no model, no scoring
    python -m src.thread.build --train-only            # also compute features and score the TRAIN threads: false alarms on real threads
    python -m src.thread.build --train-only --show-rules tv_quote_mismatch,tv_who_other_domain
                                                       # also print up to 12 examples of each named rule per source (never saved)
    python -m src.thread.build                         # the final run of a frozen version: also scores the VALIDATION threads, once

--enron-threads N        how many Enron threads to keep (default 1200; candidates are read in hash order, 1,000 at a time, until that many pass the rules)
--enron-files N          read only the first N files of the Enron maildir (a quick test; neither the index nor the threads are saved)
--reuse                  use data/processed/threads.parquet if it exists instead of rebuilding the threads (the scoring runs after a rule change)

Reads  data/processed/staged.parquet, headers.parquet     the Apache list mail (ids, raw bodies, Phase 3 header fields)
       data/raw/enron/.../maildir                          raw Enron, two passes: an index of every message, then the full text of the threads kept
Writes data/processed/enron_index.parquet                  the Enron index (never committed; about 5 minutes the first time)
       data/processed/threads.parquet                      one row per message of every thread kept, with thread_id, position, split (never committed)
       data/processed/thread_features/                     tactic probabilities and claims per message, cached (never committed)
       results/thread_counts.csv                           threads found and why groups were dropped, per source and split (counts only)
       results/thread_signal_rates.csv                     per split, source and rule: how often a rule fired on REAL threads (counts only)
       results/thread_checks.csv                           PASS/FAIL checks, rule version and run details

WHAT THE RATES MEAN. These threads are real and unmodified, nobody hijacked them, so every medium or high contradiction the verifier
finds here is a FALSE ALARM (or a hijack nobody noticed, which is rare). The rates say how noisy each rule is; the benchmark of
src/data/hijack_benchmark.py says how many hijacks the same rules catch. Rules are written from the definitions and revised
only after reading TRAIN results: `--train-only` never scores a validation thread; the final run scores the validation threads once;
the test threads are built but never scored here (Phase 13). The thread split is by thread, so no thread straddles two splits.
"""

import argparse
import json
import time
import warnings
from collections import Counter, defaultdict

import pandas as pd
from bs4 import XMLParsedAsHTMLWarning
from tqdm import tqdm

from src.data.paths import (
    ENRON_INDEX_PARQUET, ENRON_MAILDIR, HEADERS_PARQUET, LABELS_CSV, STAGED_PARQUET, THREAD_CHECKS_CSV, THREAD_COUNTS_CSV,
    THREAD_SIGNAL_RATES_CSV, THREADS_PARQUET, RESULTS_DIR, relative,
)
from src.thread import builder
from src.thread.features import attach_features, load_thresholds
from src.thread.selftest import run_crafted, self_test
from src.thread.signals import MAX_MESSAGES
from src.verifiers.rows import check_row
from src.verifiers.thread_verifier import CONTRADICTION_RULES, RULES, THREAD_RULES_VERSION, scan_thread

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)   # a few Apache bodies are XML; Phase 2 reads them as HTML on purpose

APACHE_SOURCES = ["apache_tomcat_users", "apache_kafka_users"]
SPLITS = ["train", "validation", "test"]
EXAMPLES = 12     # per rule and source
SCAN_CHUNK = 100


# ------------------------------------------------------------------------------------------------ finding threads

def build_apache():
    """Apache threads from the Phase 1 and Phase 3 tables. Returns (threads, counts, keys in the tactic model's training data)."""
    staged = pd.read_parquet(STAGED_PARQUET, columns=["id", "source", "body_raw"], filters=[("source", "in", APACHE_SOURCES)])
    headers = pd.read_parquet(HEADERS_PARQUET, filters=[("id", "in", staged["id"].tolist())])
    table = staged.merge(headers, on="id", how="inner", validate="one_to_one")
    print("  Apache: %d messages with headers" % len(table))
    records = []
    for row in tqdm(table.to_dict("records"), desc="  apache messages", unit=" msgs"):
        records.append(builder.record_from_table(row["id"], row["source"], row, row["body_raw"]))
    threads, counts = builder.apache_threads(records)
    counts["messages"] = len(records)
    return threads, counts


def read_enron_index(limit_files):
    """The Enron index (one row per file): from the cache, or by reading the first 8,000 bytes of every file once."""
    if limit_files == 0 and ENRON_INDEX_PARQUET.exists():
        frame = pd.read_parquet(ENRON_INDEX_PARQUET)
        print("  Enron index from %s: %d files" % (relative(ENRON_INDEX_PARQUET), len(frame)))
    else:
        if not ENRON_MAILDIR.exists():
            raise SystemExit("raw Enron not found at %s (Phase 1 unpacks it)" % relative(ENRON_MAILDIR))
        paths = sorted(p for p in ENRON_MAILDIR.rglob("*") if p.is_file())
        if limit_files:
            paths = paths[:limit_files]
        print("  Reading the headers of %d Enron files (about 5 minutes for all 517,000; saved afterwards)" % len(paths))
        rows = [builder.enron_index_row(p, p.relative_to(ENRON_MAILDIR).as_posix()) for p in tqdm(paths, desc="  enron index", unit=" files")]
        frame = pd.DataFrame(rows)
        frame["people"] = frame["people"].map(json.dumps)
        if not limit_files:
            frame.to_parquet(ENRON_INDEX_PARQUET, index=False)
    rows = frame.to_dict("records")
    del frame
    for row in rows:
        for key, value in row.items():                      # a missing value must stay None: two NaNs would otherwise look like one shared participant
            if isinstance(value, float) and value != value:
                row[key] = None
        row["people"] = json.loads(row["people"]) if isinstance(row["people"], str) else []
    return rows


READ_CHUNK = 1000            # Enron candidate threads read per round
READ_LIMIT = 20_000          # at most this many candidates are read in all (most candidates fail the sender and reply rules)


def build_enron(limit_files, keep):
    """Enron threads: candidates from the index, read in rounds of 1,000 in hash order until `keep` threads pass the rules (or READ_LIMIT is reached)."""
    candidates, counts = builder.enron_candidates(read_enron_index(limit_files))
    print("  Enron: %d files, %d distinct messages after removing copies, %d candidate threads before reading any text" % (
        counts["files"], counts["distinct_messages"], len(candidates)))
    # An order that does not depend on the data's own order (the SHA-256 of the seed and the first message's key), so a rerun picks the same threads.
    ordered = sorted(candidates, key=lambda c: builder.hash_order(c[0]["key"]))
    threads, totals = [], {}
    read = 0
    while len(threads) < keep and read < min(len(ordered), READ_LIMIT):
        chunk = ordered[read:read + READ_CHUNK]
        found, more = builder.enron_threads(chunk, ENRON_MAILDIR, require_replies=True)
        threads += found
        for key, value in more.items():
            totals[key] = totals.get(key, 0) + value
        read += len(chunk)
        print("    read %d candidates, %d threads kept so far" % (read, len(threads)))
    threads = threads[:keep]
    counts.update({**{k: v for k, v in totals.items() if k != "kept"}, "read": read, "kept": len(threads)})
    return threads, counts


def flatten(threads, tactic_training_ids):
    """One DataFrame row per message, with thread_id, position, n_messages, split and whether the tactic model trained on it."""
    rows = []
    for thread in threads:
        tid = thread[0]["thread_id"]
        split = builder.split_of_thread(tid)
        for m in thread:
            row = {k: v for k, v in m.items() if k not in ("tactics", "claims", "facts")}
            row.update({"facts": json.dumps(m["facts"], default=str), "references": json.dumps(m["references"]), "n_messages": len(thread), "split": split,
                        "in_tactic_training": m["key"] in tactic_training_ids})
            rows.append(row)
    return pd.DataFrame(rows)


def count_rows(threads, apache_counts, enron_counts):
    rows = []
    for source, counts in (("apache", apache_counts), ("enron", enron_counts)):
        for label, value in counts.items():
            rows.append({"source": source, "split": "all", "what": label, "value": value})
        mine = [t for t in threads if t[0]["thread_id"].startswith(source)]
        for split in SPLITS:
            part = [t for t in mine if builder.split_of_thread(t[0]["thread_id"]) == split]
            rows.append({"source": source, "split": split, "what": "threads", "value": len(part)})
            rows.append({"source": source, "split": split, "what": "messages", "value": sum(len(t) for t in part)})
            sizes = Counter(min(len(t), 10) for t in part)
            for size in sorted(sizes):
                rows.append({"source": source, "split": split, "what": "threads_of_%s%s_messages" % (size, "+" if size == 10 else ""), "value": sizes[size]})
    return pd.DataFrame(rows)


# -------------------------------------------------------------------------------------------- scoring real threads

class Tally:
    """Counts per (split, source, rule) and per (split, source): messages judged, messages flagged, threads flagged."""

    def __init__(self):
        self.rule = defaultdict(lambda: defaultdict(int))
        self.group = defaultdict(lambda: defaultdict(int))
        self.examples = defaultdict(list)

    def add_thread(self, split, source, thread, result, show_rules):
        flagged_thread = False
        for entry, message in zip(result["messages"], thread):
            self.group[(split, source)]["messages"] += 1
            self.group[(split, source)]["judged"] += int(entry["index"] >= 1)
            if entry["index"] >= 1 and entry["worst"] in ("medium", "high"):
                self.group[(split, source)]["flagged_messages"] += 1
                flagged_thread = True
            if entry["worst"] == "high":
                self.group[(split, source)]["high_messages"] += 1
            for row in entry["rows"]:
                status = "contradiction" if row["contradiction"] else ("consistent" if row["contradiction"] is False else "not_checkable")
                self.rule[(split, source, row["rule"])][status] += 1
                if row["contradiction"] and row["rule"] in show_rules and len(self.examples[(row["rule"], source)]) < EXAMPLES:
                    self.examples[(row["rule"], source)].append((source, message["thread_id"], entry["index"], message["subject"][:60], row["severity"], row["reason"]))
        self.group[(split, source)]["threads"] += 1
        self.group[(split, source)]["flagged_threads"] += int(flagged_thread)
        self.group[(split, source)]["flip_found"] += int(result["flip_index"] is not None)


def rate_frames(tally):
    rules, groups = [], []
    for (split, source, rule), counts in sorted(tally.rule.items()):
        claim_type = RULES[rule][0]
        rows = counts["contradiction"] + counts["consistent"] + counts["not_checkable"]
        rules.append({"split": split, "source": source, "rule": rule, "signal": claim_type, "rows": rows, "contradiction": counts["contradiction"],
                      "consistent": counts["consistent"], "not_checkable": counts["not_checkable"]})
    for (split, source), c in sorted(tally.group.items()):
        groups.append({"split": split, "source": source, "rule": "(all rules)", "signal": "messages",
                       "rows": c["judged"], "contradiction": c["flagged_messages"], "consistent": c["high_messages"], "not_checkable": c["threads"],
                       "note": "rows = messages with a past; contradiction = messages with a medium or high contradiction; consistent = messages with a high one; not_checkable = threads"})
    return pd.DataFrame(rules + groups)


def print_rates(tally):
    print("\nFalse alarms on REAL threads (medium or high contradictions on messages that have a past; nobody hijacked these)")
    print("%-11s %-8s %8s %9s %9s %8s %9s" % ("split", "source", "threads", "messages", "flagged", "share", "high"))
    for (split, source), c in sorted(tally.group.items()):
        share = 100.0 * c["flagged_messages"] / c["judged"] if c["judged"] else 0.0
        print("%-11s %-8s %8d %9d %9d %7.1f%% %9d" % (split, source, c["threads"], c["judged"], c["flagged_messages"], share, c["high_messages"]))
    print("\nRules that fired as contradictions (all splits read so far)")
    totals = defaultdict(lambda: defaultdict(int))
    for (split, source, rule), counts in tally.rule.items():
        for status, value in counts.items():
            totals[(source, rule)][status] += value
    for (source, rule), counts in sorted(totals.items(), key=lambda kv: -kv[1]["contradiction"]):
        if counts["contradiction"]:
            print("  %-8s %-24s contradiction %5d  consistent %5d  not checkable %5d" % (source, rule, counts["contradiction"], counts["consistent"], counts["not_checkable"]))


def print_examples(tally):
    for (rule, source), examples in sorted(tally.examples.items()):
        print("\nExamples of %s on %s threads (printed to be read, never saved)" % (rule, source))
        for source, tid, index, subject, severity, reason in examples:
            print("  [%s] %s message %d (%s) subject %r\n      %s" % (source, tid, index, severity, subject, reason))


# ------------------------------------------------------------------------------------------------------- checks

def make_checks(table, tally, problems, splits, args, started, apache_counts, enron_counts, text_mismatch, single_rate):
    checks = []

    def add(check, item, value, expected, status):
        checks.append({"check": check, "item": item, "value": value, "expected": expected, "status": status})

    passed, total = self_test(verbose=False)
    add("selftest", "hand-made threads, helper checks and crafted inputs", "%s of %d" % ("all" if passed else "NOT all", total), "all pass", "PASS" if passed else "FAIL")
    add("rows_valid", "ledger rows that fail check_row (keys, severity fits contradiction, known rule, safe reason)", len(problems), "0", "PASS" if not problems else "FAIL")
    ordered = table.groupby("thread_id")["position"].apply(lambda s: list(s) == list(range(len(s))))
    add("structure", "threads whose positions are not 0, 1, 2 ...", int((~ordered).sum()), "0", "PASS" if ordered.all() else "FAIL")
    sizes = table.groupby("thread_id").size()
    add("structure", "threads with fewer than 3 or more than %d messages" % MAX_MESSAGES, int(((sizes < 3) | (sizes > MAX_MESSAGES)).sum()), "0", "PASS" if not ((sizes < 3) | (sizes > MAX_MESSAGES)).any() else "FAIL")
    spread = table.groupby("thread_id")["split"].nunique()
    add("leakage_guard", "threads that straddle more than one split", int((spread > 1).sum()), "0", "PASS" if (spread == 1).all() else "FAIL")
    add("leakage_guard", "splits scored in this run", "+".join(splits), "train only (--train-only) or train and validation; never test", "PASS" if set(splits) <= {"train", "validation"} else "FAIL")
    add("leakage_guard", "Apache messages the tactic classifier trained on (kept in train; benchmark threads for validation and test must avoid them)",
        int(table["in_tactic_training"].sum()), "(a finding)", "info")
    add("text", "Apache messages whose new text differs from the Phase 2 body_clean (sample)", text_mismatch, "0", "PASS" if text_mismatch == 0 else "FAIL")
    for source in ("apache", "enron"):
        mine = table[table["thread_id"].str.startswith(source)]
        add("coverage", "%s threads / messages" % source, "%d / %d" % (mine["thread_id"].nunique(), len(mine)), ">= 100 threads (a finding if not)",
            "PASS" if mine["thread_id"].nunique() >= 100 else "info")
    for source in ("apache", "enron"):
        for split in splits:
            c = tally.group.get((split, source))
            if not c or not c["judged"]:
                continue
            share = 100.0 * c["flagged_messages"] / c["judged"]
            add("false_alarms", "%s %s: share of messages with a past that get a medium or high contradiction" % (split, source), "%.1f%%" % share,
                "<= 20% (a finding if not; these threads are real and unmodified)", "PASS" if share <= 20.0 else "info")
    train_rules = defaultdict(int)
    for (split, source, rule), counts in tally.rule.items():
        if split == "train":
            train_rules[rule] += counts["contradiction"]
    silent = sorted(r for r in CONTRADICTION_RULES if train_rules.get(r, 0) == 0)
    add("coverage", "contradiction rules that never fired on the train threads", "%d of %d" % (len(silent), len(CONTRADICTION_RULES)), "(a finding, not a failure)", "info")
    add("single_email", "Apache replies with quoted history but no In-Reply-To or References (the single-email rule tv_single_no_reply_ids)", single_rate, "(a finding: the rule is low severity because many real replies lack the headers)", "info")
    slowest = max(seconds for _, seconds, _, _ in run_crafted())
    add("crafted_inputs", "slowest of the crafted threads (50 large messages, 100 IDs, floods of '>', 100,000 'Re:' ...)", "%.2f s" % slowest, "< 2 s", "PASS" if slowest < 2.0 else "FAIL")
    add("run", "thread rules version", THREAD_RULES_VERSION, "", "info")
    add("run", "tactic thresholds from", args.thresholds_source, "", "info")
    add("run", "Enron threads kept / Apache threads kept", "%s / %s" % (enron_counts.get("kept"), apache_counts.get("kept")), "", "info")
    add("run", "--enron-files (0 means every file)", args.enron_files, "0 in the final run", "info" if args.enron_files else "PASS")
    add("run", "validation threads scored in this run", "no (--train-only or --count)" if "validation" not in splits else "yes", "yes in the final run of a frozen version", "info" if "validation" not in splits else "PASS")
    add("run", "seconds", round(time.time() - started), "", "info")
    return pd.DataFrame(checks)


def apache_text_mismatches(table, sample=300):
    """How many sampled Apache messages have a new text that differs from the Phase 2 body_clean. Zero means the thread code cuts bodies exactly as Phase 2 did."""
    from src.data.paths import CLEANED_PARQUET

    mine = table[table["thread_id"].str.startswith("apache")].head(sample)
    if mine.empty:
        return 0
    cleaned = pd.read_parquet(CLEANED_PARQUET, columns=["id", "body_clean", "signature"], filters=[("id", "in", mine["key"].tolist())]).set_index("id")
    wrong = 0
    for key, text in zip(mine["key"], mine["text"]):
        if key in cleaned.index and cleaned.loc[key, "body_clean"] != text:
            wrong += 1
    return wrong


def single_email_rate(table):
    """The share of Apache replies with quoted history that carry no reply headers: the false-alarm rate of the single-email rule."""
    from src.thread.signals import MIN_QUOTE_WORDS, is_reply_subject, reply_ids, words_of

    mine = table[table["thread_id"].str.startswith("apache")]
    replies = [r for r in mine.to_dict("records") if is_reply_subject(r["subject"]) and len(words_of(r["quoted"])) >= MIN_QUOTE_WORDS]
    if not replies:
        return "no replies with quoted history"
    bare = sum(1 for r in replies if not reply_ids({"in_reply_to": builder.json_safe(r.get("in_reply_to")),
                                                    "references": builder.decode_references(r.get("references"))}))
    return "%.1f%% of %d" % (100.0 * bare / len(replies), len(replies))


# ------------------------------------------------------------------------------------------------------------ main

def main():
    parser = argparse.ArgumentParser(description="Rebuild real threads and measure the thread verifier on them (Phase 9).")
    parser.add_argument("--count", action="store_true", help="find the threads and print counts; compute no features and score nothing")
    parser.add_argument("--train-only", action="store_true", help="score the train threads only (use while writing rules)")
    parser.add_argument("--enron-threads", type=int, default=1200, help="Enron threads to keep (default 1200)")
    parser.add_argument("--enron-files", type=int, default=0, help="read only the first N Enron files (a quick test)")
    parser.add_argument("--show-rules", default="", help="comma-separated rule ids: print up to 12 examples of each, per source (never saved)")
    parser.add_argument("--reuse", action="store_true", help="use data/processed/threads.parquet if it exists instead of rebuilding the threads")
    args = parser.parse_args()
    show_rules = [r for r in args.show_rules.split(",") if r]
    unknown = [r for r in show_rules if r not in RULES]
    if unknown:
        raise SystemExit("--show-rules: unknown rules %s" % unknown)
    started = time.time()
    pd.set_option("display.width", 220)
    thresholds, source = load_thresholds()
    args.thresholds_source = source
    print("Thread rules version %s; tactic thresholds from %s" % (THREAD_RULES_VERSION, source))

    if args.reuse and THREADS_PARQUET.exists():
        table = pd.read_parquet(THREADS_PARQUET)
        apache_counts = {"kept": table.loc[table["thread_id"].str.startswith("apache"), "thread_id"].nunique()}
        enron_counts = {"kept": table.loc[table["thread_id"].str.startswith("enron"), "thread_id"].nunique()}
        print("Threads from %s: %d threads, %d messages" % (relative(THREADS_PARQUET), table["thread_id"].nunique(), len(table)))
    else:
        print("\nApache threads")
        apache, apache_counts = build_apache()
        print("\nEnron threads")
        enron, enron_counts = build_enron(args.enron_files, args.enron_threads)
        labels = pd.read_csv(LABELS_CSV, usecols=["id", "split"], dtype={"id": str})
        trained_on = set(labels.loc[labels["split"] == "train", "id"])
        table = flatten(apache + enron, trained_on)
        counts = count_rows(apache + enron, apache_counts, enron_counts)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        counts.to_csv(THREAD_COUNTS_CSV, index=False)
        if not args.enron_files:
            table.to_parquet(THREADS_PARQUET, index=False)
        print("\nThreads kept")
        shown = counts[counts["what"].isin(["threads", "messages"]) & counts["split"].isin(SPLITS)]
        print(shown.pivot_table(index=["source", "split"], columns="what", values="value", aggfunc="sum").astype(int).to_string())
        print("\nGroups dropped, and why (all splits)")
        print(counts[(counts["split"] == "all")].pivot_table(index="what", columns="source", values="value", aggfunc="sum", fill_value=0).astype(int).to_string())
        print("\nSaved %s%s and %s" % (relative(THREADS_PARQUET) if not args.enron_files else "(not saved: --enron-files)", "", relative(THREAD_COUNTS_CSV)))
    if args.count:
        return

    splits = ["train"] if args.train_only else ["train", "validation"]
    by_thread = builder.table_to_threads(table[table["split"].isin(splits)])
    print("\nFeatures and scan: %s threads (%s)" % (len(by_thread), ", ".join(splits)))
    tally, problems = Tally(), []
    for split in splits:
        wanted = [tid for tid, ms in by_thread.items() if builder.split_of_thread(tid) == split]
        messages = [m for tid in wanted for m in by_thread[tid]]
        attach_features(messages, split)
        for tid in tqdm(wanted, desc="  scanning %s" % split, unit=" threads"):
            thread = by_thread[tid]
            result = scan_thread(thread, thresholds)
            for entry in result["messages"]:
                problems += ["%s/%s: %s" % (tid, entry["index"], p) for row in entry["rows"] for p in check_row(row, RULES)]
            tally.add_thread(split, tid.split("_")[0], thread, result, show_rules)
    print_rates(tally)
    print_examples(tally)
    rates = rate_frames(tally)
    rates.to_csv(THREAD_SIGNAL_RATES_CSV, index=False)
    checks = make_checks(table, tally, problems, splits, args, started, apache_counts, enron_counts, apache_text_mismatches(table), single_email_rate(table))
    checks.to_csv(THREAD_CHECKS_CSV, index=False)
    print("\nChecks (%s)" % relative(THREAD_CHECKS_CSV))
    print(checks[checks["status"] != "info"].to_string(index=False))
    print("%d PASS, %d FAIL, %d info" % tuple(int((checks["status"] == s).sum()) for s in ("PASS", "FAIL", "info")))
    if (checks["status"] == "FAIL").any():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
