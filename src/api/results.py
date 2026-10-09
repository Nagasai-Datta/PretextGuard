"""Phase 11: the evaluation numbers the dashboard may read (GET /results).

THE ALLOW-LIST. RESULT_FILES below is the complete list of result files the API can serve, each with a one-line description. The server reads
those files from results/ once, at start-up, into a dictionary {name: table}. A request names a table; the name is looked up in the dictionary.
No part of a request ever becomes a file name or a path, so there is nothing to traverse: '../.env' is simply not a key. A new result file (Phase 13
adds the ablations) is served only after someone adds it to this list, so a file dropped into results/ by accident is not published.

WHAT IS SERVED. Only counts, rates and checks (results/README.md: "The files here hold counts and scores only, never email text"). Each file is
read with the standard csv module, at most MAX_FILE_BYTES and MAX_ROWS rows; numbers become numbers (never NaN or infinity, which JSON cannot
hold), empty cells become null, and every other cell is made display-safe (< > and backticks replaced) as a second line of defence, because the
interface will draw these cells in a table.
"""

import csv
import math

from src.data.paths import RESULTS_DIR
from src.router.pipeline import display_safe

MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 5000
MAX_CELL_CHARS = 1000
NUMBER_CHARS = frozenset('0123456789.-+eE')

RESULT_FILES = {
    # data
    "staged_counts": "Emails per source and category in the staged table (Phase 1)",
    "split_counts": "Emails per source, category and split (train, validation, test)",
    "header_coverage": "Share of each source's messages that carry each header",
    "header_evidence_summary": "Per source: share of emails with each kind of header evidence (Phase 3)",
    "preprocess_summary": "Per source: HTML, links, quotes, footers, signatures and placeholders (Phase 2, N1)",
    "preprocess_checks": "Checks on the cleaning and redaction (Phase 2)",
    # labels
    "label_counts": "Positive labels per tactic and claim type, per split and category (Phase 5)",
    "label_agreement": "Cohen's kappa per tactic and claim type between the two annotators (Phase 5)",
    "synthetic_counts": "Synthetic pairs kept and dropped, attack tactics per split (Phase 5)",
    # tactics
    "keyword_hit_rates": "Keyword baseline: share of train emails where each tactic fires (Phase 4)",
    "keyword_checks": "Checks on the keyword baseline (Phase 4)",
    "tactic_training_log": "DistilBERT training: loss and macro-F1 per epoch, condition and seed (Phase 6)",
    "tactic_seed_summary": "DistilBERT: best epoch and macro-F1 per condition and seed (Phase 6)",
    "tactic_validation_scores": "Precision, recall and F1 per tactic for DistilBERT and the keyword baseline on validation (Phase 6)",
    "tactic_checks": "Checks on the tactic classifier (Phase 6)",
    # claims
    "claim_hit_rates": "Claim extractor: share of train emails where each claim type is found (Phase 7)",
    "claim_scores": "Claim extractor: precision, recall and F1 per claim type against the labels (Phase 7)",
    "claim_checks": "Checks on the claim extractor (Phase 7)",
    # verifiers
    "verifier_rates": "Claims contradicted, consistent and not checkable per verifier, split, group and claim type (Phase 8)",
    "verifier_rule_hits": "How many ledger rows each header or request rule produced (Phase 8)",
    "verifier_checks": "Checks on the header and request verifiers (Phase 8)",
    # threads
    "thread_counts": "Threads and messages found per source and split (Phase 9)",
    "thread_signal_rates": "False alarms of each thread rule on real, unmodified threads (Phase 9)",
    "thread_scores": "Thread-hijack benchmark: detection per variant and source, with and without the thread verifier (Phase 9, N2)",
    "hijack_cases": "Benchmark cases and threads per split, source and variant (Phase 9)",
    "thread_checks": "Checks on the thread builder and verifier (Phase 9)",
    "hijack_checks": "Checks on the hijack benchmark (Phase 9)",
    # score
    "score_config": "The frozen score numbers, the false-alarm budget and the reliability settings (Phase 10)",
    "score_rule_weights": "Per rule and source: how often a rule fires on legitimate mail and real threads, and its reliability factor (Phase 10)",
    "score_grid": "The 27 calibration points of the risk score on validation (Phase 10)",
    "score_distribution": "Validation emails per risk band, per category and source (Phase 10)",
    "score_budget": "The false-alarm budget per source of legitimate mail and real threads (Phase 10)",
    "score_benchmark_check": "The hijack benchmark scored with the frozen numbers (Phase 10)",
    "score_checks": "Checks on the router, ledger and score (Phase 10)",
    "lime_checks": "LIME faithfulness: deletion test against matched random words (Phase 10)",
    # api
    "api_checks": "Checks on the API's security controls (Phase 11)",
    "api_mutations": "Controls of the API broken on purpose, and whether the self-test noticed each (Phase 11)",
    "api_smoke": "Real-server run of the API with the trained model: timings and checks (Phase 11)",
    # interface
    "frontend_checks": "Checks on the interface source, its built bundle and its offset and size logic (Phase 12)",
    "frontend_browser_checks": "The interface driven in a real browser: what is drawn against what the API answered, error states and the security headers (Phase 12)",
    "frontend_mutations": "Parts of the interface and its bundle broken on purpose, and whether the static checks noticed each (Phase 12)",
}


def to_cell(text):
    """One CSV cell as a JSON value: null for empty, an int or a finite float for a number, otherwise display-safe text."""
    text = text.strip()
    if not text:
        return None
    digits = text[1:] if text[0] == "-" else text
    if digits.isascii() and digits.isdigit():
        return int(text) if digits == "0" or digits[0] != "0" else display_safe(text)      # '007' is a code, not the number 7
    if set(text) <= NUMBER_CHARS:      # float() would also accept 'nan', 'inf' and '1_000'; only plain number characters are tried
        try:
            number = float(text)
        except ValueError:
            number = None
        if number is not None and math.isfinite(number):
            return number
    return display_safe(text[:MAX_CELL_CHARS])


def read_table(path):
    """{'columns': [...], 'rows': [{...}]} from one CSV file, or None when the file is missing, too big, empty or not a plain file."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                return None
            columns = [display_safe(name.strip()[:MAX_CELL_CHARS]) for name in header]
            rows = []
            for line in reader:
                if len(rows) >= MAX_ROWS:
                    break
                if line:
                    rows.append({name: to_cell(value) for name, value in zip(columns, line)})
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    return {"columns": columns, "rows": rows}


class ResultStore:
    """The allow-listed tables, read once. `missing` names the allow-listed files that are not there (or were unreadable)."""

    def __init__(self, directory=RESULTS_DIR, names=None):
        self.tables, self.missing = {}, []
        for name, description in (RESULT_FILES if names is None else names).items():
            table = read_table(directory / (name + ".csv"))
            if table is None:
                self.missing.append(name)
            else:
                self.tables[name] = dict(table, name=name, description=description)

    def index(self):
        return {"files": [{"name": t["name"], "description": t["description"], "columns": t["columns"], "rows": len(t["rows"])} for t in self.tables.values()],
                "missing": list(self.missing)}

    def get(self, name):
        """The table called `name` or None. A dictionary lookup: a name that is not a key finds nothing, whatever characters it has."""
        return self.tables.get(name) if isinstance(name, str) else None
