"""Phase 5: synthetic pretexting emails with matched benign twins, written by a free web chat.

Real corpora have almost no modern, link-free pretexting and almost no reciprocity or social proof.
This script fills that gap the way master document Section 8.4 describes: it writes fixed prompt
templates, you paste each into a fresh chat, and the replies are checked and loaded. Labels are known
from the prompt (which tactics the attack was told to use), and every attack has a benign twin from the
same template (style-confound control, Section 8.5): same sender kind, same situation, same claims,
no manipulation. Synthetic results are always reported separately from real-email results.

    python -m src.data.synthetic build               write the plan and 30 prompts (240 pairs, 8 per prompt)
    python -m src.data.synthetic auto annotator_1    send every pending prompt to that role's API (--limit 2 tries two; see llm_api.py)
    python -m src.data.synthetic next                by hand: copy the next unanswered prompt to the clipboard
    (fresh chat, paste, send, copy the whole reply)
    python -m src.data.synthetic save                by hand: save the reply on the clipboard and check it
    python -m src.data.synthetic collect             check every reply, write re-ask prompts for failures, write synthetic.csv

"Labels known from the prompt" is only true if the chat did what it was told, so every reply is
verified: each attack must quote, word for word, the phrase that carries each required tactic
(tactic_cues) and each required claim; every quoted phrase must appear in the body; an email may contain
no link; and the benign twin is run through the frozen keyword baseline, which must not fire on it. A pair
that fails is re-asked once, then dropped.

Files: data/synthetic/plan.csv (what every pair was told to be), prompts/synth_NNN.txt, replies/synth_NNN.txt
(the raw replies), generator.csv (which chat and model wrote them: fill in the model name),
replies_log.csv, and synthetic.csv (the loaded emails, with the same label columns as the real labels).
"""

import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timezone

import pandas as pd

from src.baseline.keywords import DEFAULT_THRESHOLD, score_tactics
from src.data import llm_api
from src.data.clipboard import ClipboardError, copy, paste
from src.data.label_schema import CLAIM_DEFINITIONS, CLAIM_TYPES, TACTIC_DEFINITIONS, TACTICS
from src.data.paths import RESULTS_DIR, SYNTHETIC_COUNTS_CSV, SYNTHETIC_CSV, SYNTHETIC_DIR, relative
from src.data.validate_labels import ReplyProblem, check_claims, extract_json, span_in, squash, word_key
from src.preprocess.redact import redact

SEED = 42
SYNTH_TEMPERATURE = 0.8  # some variety between emails; annotation uses 0
PAIRS = 240
PAIRS_PER_PROMPT = 8
MIN_WORDS, MAX_WORDS = 20, 260
LINK_MARKERS = ("http://", "https://", "www.", "://")
PLAN_CSV = SYNTHETIC_DIR / "plan.csv"
PROMPTS_DIR = SYNTHETIC_DIR / "prompts"
REPLIES_DIR = SYNTHETIC_DIR / "replies"
GENERATOR_CSV = SYNTHETIC_DIR / "generator.csv"
LOG_CSV = SYNTHETIC_DIR / "replies_log.csv"

# Twelve situations. attack_claims must all appear in the attack; twin_claims in the benign twin.
SCENARIOS = {
    "ceo_wire": ("An executive writes to someone in finance asking for a wire transfer to a payee they have not paid before.",
                 ["affiliation_internal", "authority", "payment_request", "reply_direction"], ["affiliation_internal", "payment_request"],
                 "a routine payment request that names the purchase order and follows the normal approval process"),
    "gift_cards": ("A manager asks a team member to buy gift cards for clients.",
                   ["authority", "gift_card", "reply_direction"], ["gift_card"],
                   "a manager asking for gift cards for a client event to be ordered through procurement"),
    "payroll_change": ("An employee asks HR or payroll to change their direct-deposit bank details.",
                       ["affiliation_internal", "payment_change", "reply_direction"], ["affiliation_internal", "payment_change"],
                       "an employee asking how to update their bank details through the HR portal"),
    "vendor_bank_change": ("A supplier says its bank account has changed and asks that the next invoice be paid there.",
                           ["affiliation_external", "payment_change", "signature_contact"], ["affiliation_external", "signature_contact"],
                           "a supplier sending an invoice reminder with unchanged payment details"),
    "tax_forms": ("Someone in finance or HR asks for employee tax forms or a staff list.",
                  ["affiliation_internal", "authority", "data_request"], ["affiliation_internal", "data_request"],
                  "a request for the same documents through the approved secure channel for an audit"),
    "it_password": ("The IT help desk says a mailbox will be disabled and asks for a password or a verification code.",
                    ["affiliation_internal", "credential_request"], ["affiliation_internal"],
                    "a scheduled maintenance notice that asks the reader for nothing"),
    "invoice_followup": ("A vendor chases an unpaid invoice and refers to an earlier conversation.",
                         ["affiliation_external", "payment_request", "prior_relationship"], ["affiliation_external", "payment_request", "prior_relationship"],
                         "a polite reminder about a normal invoice, quoting its number and due date"),
    "legal_confidential": ("A lawyer or compliance officer asks for documents about a confidential matter.",
                           ["affiliation_external", "authority", "data_request", "prior_relationship"], ["affiliation_external", "data_request"],
                           "a documented request from outside counsel through the normal legal channel"),
    "travel_funds": ("An executive abroad says they are stuck and asks for emergency funds.",
                     ["authority", "payment_request", "reply_direction"], ["affiliation_internal", "payment_request"],
                     "a colleague asking about the expense approval for an upcoming trip"),
    "thread_account_change": ("A reply in an ongoing project conversation suddenly asks to pay a new account.",
                              ["prior_relationship", "payment_change", "signature_contact"], ["prior_relationship", "signature_contact"],
                              "a normal follow-up in the same project conversation about the agreed schedule"),
    "secret_deal": ("An executive asks for a payment tied to a confidential acquisition.",
                    ["authority", "payment_request", "prior_relationship"], ["affiliation_internal", "payment_request"],
                    "a payment for a signed contract that legal has already reviewed"),
    "assistant_scheduling": ("An executive's assistant sets up a call and then asks the reader for a favour.",
                             ["affiliation_internal", "prior_relationship", "payment_request"], ["affiliation_internal", "prior_relationship"],
                             "an assistant simply confirming a meeting time and room"),
}
INDUSTRIES = ["logistics", "software", "retail", "healthcare", "manufacturing", "education", "construction",
              "legal services", "energy", "hospitality"]
TONES = ["formal", "friendly", "terse", "rushed", "warm and chatty", "polite but firm"]
LENGTHS = ["short (about 40 to 70 words)", "medium (about 80 to 130 words)", "longer (about 140 to 200 words)"]
PLAN_COLUMNS = ["pair", "scenario", "industry", "tone", "length", "attack_tactics", "attack_claims", "benign_claims", "split"]


def split_of(pair):
    """train / validation / test by pair, so an attack and its twin never sit on both sides of the line."""
    bucket = int(hashlib.sha256(f"{SEED}|split|{pair}".encode("utf-8")).hexdigest(), 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def build_plan():
    """The 240 pair specifications. Each tactic is the primary tactic of a seventh of the attacks."""
    names = sorted(SCENARIOS)
    plan = []
    for i in range(PAIRS):
        rng = random.Random(f"{SEED}|{i}")
        primary = TACTICS[i % len(TACTICS)]
        extras = rng.sample([t for t in TACTICS if t != primary], rng.choice([1, 2]))
        scenario = names[i % len(names)]
        _, attack_claims, twin_claims, _ = SCENARIOS[scenario]
        pair = f"p{i + 1:03d}"
        plan.append({"pair": pair, "scenario": scenario, "industry": rng.choice(INDUSTRIES), "tone": rng.choice(TONES),
                     "length": rng.choice(LENGTHS), "attack_tactics": "|".join(t for t in TACTICS if t in [primary] + extras),
                     "attack_claims": "|".join(attack_claims), "benign_claims": "|".join(twin_claims), "split": split_of(pair)})
    return plan


def read_plan():
    with open(PLAN_CSV, newline="", encoding="utf-8") as handle:
        return {row["pair"]: row for row in csv.DictReader(handle)}


def prompt_for(specs):
    """The message for one chat: rules, definitions, the pairs to write, the output format."""
    tactic_lines = "\n".join(f"- {name}: {TACTIC_DEFINITIONS[name]}" for name in TACTICS)
    claim_lines = "\n".join(f"- {name}: {CLAIM_DEFINITIONS[name]}" for name in CLAIM_TYPES)
    blocks = []
    for spec in specs:
        premise, _, _, twin_note = SCENARIOS[spec["scenario"]]
        blocks.append(
            f"Pair {spec['pair']}\n"
            f"  Situation: {premise}\n"
            f"  Setting: a {spec['industry']} organisation; tone {spec['tone']}; length {spec['length']}\n"
            f"  ATTACK email uses these tactics and no others: {spec['attack_tactics'].replace('|', ', ')}\n"
            f"  ATTACK email makes these claims: {spec['attack_claims'].replace('|', ', ')}\n"
            f"  BENIGN email: {twin_note}. It uses none of the seven tactics.\n"
            f"  BENIGN email makes these claims: {spec['benign_claims'].replace('|', ', ')}")
    example = {"pair": specs[0]["pair"],
               "attack": {"subject": "...", "body": "...", "tactic_cues": {t: "exact words from the body" for t in specs[0]["attack_tactics"].split("|")},
                          "claims": [{"type": specs[0]["attack_claims"].split("|")[0], "span": "exact words from the body", "organisation": None}]},
               "benign": {"subject": "...", "body": "...",
                          "claims": [{"type": specs[0]["benign_claims"].split("|")[0], "span": "exact words from the body", "organisation": None}]}}
    return f"""You are helping build a research dataset of workplace emails to train and test an email-security classifier. Everything you write is fictional: invent company and person names, and never use real companies, products or people.

Write {len(specs)} PAIRS of emails. In each pair, the ATTACK email is a pretexting message (an invented identity or story used to get the reader to act). The BENIGN email is a legitimate message about a similar situation from a similar kind of sender that uses no manipulation. The two must read like different emails, not like one with a sentence removed.

Rules for every email
- Plain text body only (put the subject in its own field), 40 to 200 words as asked. No links, no web addresses, no attachments, no markdown, no emoji.
- Write naturally and vary the wording between pairs. Do not start every email with "Dear".
- The ATTACK uses exactly the tactics listed for it and none of the other seven. The BENIGN uses none.

The seven tactics
{tactic_lines}

The claim types
{claim_lines}

Pairs to write
{chr(10).join(blocks)}

Output: one JSON array and nothing else (no explanation, no code fence), one object per pair, in this order. For the attack, "tactic_cues" must give, for each tactic it uses, the exact words from the body that carry that tactic. Every "span" and every cue must be copied exactly from the body of that email. Example shape:
{json.dumps(example)}
"""


def write_plan_and_prompts():
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    REPLIES_DIR.mkdir(parents=True, exist_ok=True)
    plan = build_plan()
    with open(PLAN_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        writer.writerows(plan)
    for number, start in enumerate(range(0, PAIRS, PAIRS_PER_PROMPT), start=1):
        (PROMPTS_DIR / f"synth_{number:03d}.txt").write_text(prompt_for(plan[start:start + PAIRS_PER_PROMPT]), encoding="utf-8")
    if not GENERATOR_CSV.exists():
        GENERATOR_CSV.write_text("chat_service,model_name\n,\n", encoding="utf-8")
    return plan


def words(text):
    return len(text.split())


def check_email(email, required_claims, cues):
    """Check one email object of a pair. Returns (clean email, problems). cues: required tactics (attack) or None (twin)."""
    if not isinstance(email, dict) or not isinstance(email.get("subject"), str) or not isinstance(email.get("body"), str):
        return None, ["subject and body must be text"]
    body, problems = email["body"].strip(), []
    if not MIN_WORDS <= words(body) <= MAX_WORDS:
        problems.append(f"body has {words(body)} words, outside {MIN_WORDS} to {MAX_WORDS}")
    if any(marker in body.lower() for marker in LINK_MARKERS):
        problems.append("the body contains a link")
    key = word_key(body)
    claims, claim_problems = check_claims(email.get("claims"), key)
    problems += claim_problems
    listed = {c["type"] for c in claims}
    problems += [f"required claim {c} is missing" for c in required_claims if c not in listed]
    clean_cues = {}
    if cues is not None:
        given = email.get("tactic_cues")
        if not isinstance(given, dict) or set(given) != set(cues):
            problems.append("tactic_cues must have exactly the required tactics")
        else:
            for tactic, phrase in given.items():
                if not isinstance(phrase, str) or not span_in(phrase, key):
                    problems.append(f"the cue for {tactic} is not in the body")
                else:
                    clean_cues[tactic] = phrase.strip()
    if problems:
        return None, problems
    return {"subject": email["subject"].strip(), "body": body, "claims": claims, "cues": clean_cues}, []


def check_pairs(raw_text, specs):
    """Check one reply against the specs it was asked for. Returns (valid {pair: clean}, problems {pair: [..]}, notes)."""
    valid, problems, notes = {}, {}, []
    try:
        data = extract_json(raw_text)
    except ReplyProblem as problem:
        return valid, {pair: [f"reply unreadable: {problem}"] for pair in specs}, notes
    seen = set()
    for item in data:
        pair = item.get("pair") if isinstance(item, dict) else None
        if pair not in specs:
            notes.append(f"unknown pair {str(pair)[:20]!r} ignored")
            continue
        if pair in seen:
            problems[pair] = ["pair appears twice"]
            valid.pop(pair, None)
            continue
        seen.add(pair)
        spec = specs[pair]
        attack, attack_problems = check_email(item.get("attack"), spec["attack_claims"].split("|"), spec["attack_tactics"].split("|"))
        twin, twin_problems = check_email(item.get("benign"), spec["benign_claims"].split("|"), None)
        found = []
        if twin is not None:
            scores = score_tactics(twin["body"])
            found = [t for t in TACTICS if scores[t]["score"] >= DEFAULT_THRESHOLD]
        issues = [f"attack: {p}" for p in attack_problems] + [f"benign: {p}" for p in twin_problems]
        if found:
            issues.append(f"benign twin contains manipulation wording (keyword baseline fired: {', '.join(found)})")
        if attack and twin and squash(attack["body"]) == squash(twin["body"]):
            issues.append("attack and benign bodies are identical")
        if issues:
            problems[pair] = issues
        else:
            valid[pair] = {"attack": attack, "benign": twin}
    for pair in specs:
        if pair not in seen:
            problems[pair] = ["missing from the reply"]
    return valid, problems, notes


# ----------------------------------------------------------------------------- commands

def stems():
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.txt")) if PROMPTS_DIR.exists() else []


def model_name():
    if not GENERATOR_CSV.exists():
        sys.exit("Run python -m src.data.synthetic build first.")
    with open(GENERATOR_CSV, newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle), {})
    if not (row.get("model_name") or "").strip() or not (row.get("chat_service") or "").strip():
        sys.exit(f"Fill in chat_service and model_name in {relative(GENERATOR_CSV)} first (the model shown in the chat window).")
    return f"{row['chat_service'].strip()} {row['model_name'].strip()}"


def specs_of(stem):
    """The pair specs a prompt file asked for, in order (read back from the pair ids inside it)."""
    plan = read_plan()
    text = (PROMPTS_DIR / f"{stem}.txt").read_text(encoding="utf-8")
    ids = [line.split()[1] for line in text.splitlines() if line.startswith("Pair p")]
    return {pair: plan[pair] for pair in ids}


def next_stem():
    pending = [s for s in stems() if not (REPLIES_DIR / f"{s}.txt").exists()]
    return (pending[0] if pending else None), len(stems()) - len(pending), len(stems())


def cmd_next():
    model_name()
    stem, done, total = next_stem()
    if stem is None:
        return print(f"All {total} prompts are answered. Run python -m src.data.synthetic collect.")
    try:
        copy((PROMPTS_DIR / f"{stem}.txt").read_text(encoding="utf-8"))
        print(f"Copied {stem} ({done + 1} of {total}) to the clipboard. Fresh chat, paste, send, copy the whole reply, then:")
        print("  python -m src.data.synthetic save")
    except ClipboardError as problem:
        print(f"{problem}. Copy {relative(PROMPTS_DIR / (stem + '.txt'))} by hand; save the reply as {relative(REPLIES_DIR / (stem + '.txt'))}.")


def store_reply(stem, text, model):
    """Save a reply as received, check it, log it. Returns (valid, problems, notes, number of pairs asked)."""
    path = REPLIES_DIR / f"{stem}.txt"
    path.write_text(text, encoding="utf-8")
    specs = specs_of(stem)
    valid, problems, notes = check_pairs(text, specs)
    new = not LOG_CSV.exists()
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(["time_utc", "model", "prompt", "pairs", "valid"])
        writer.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), model, stem, len(specs), len(valid)])
    return valid, problems, notes, len(specs)


def cmd_save():
    model = model_name()
    stem, _, _ = next_stem()
    if stem is None:
        sys.exit("Every prompt already has a reply.")
    try:
        text = paste()
    except ClipboardError as problem:
        sys.exit(f"{problem}. Save the reply by hand as {relative(REPLIES_DIR / (stem + '.txt'))}.")
    if not text.strip():
        sys.exit("The clipboard is empty. Copy the chat's reply first.")
    if "PAIRS of emails" in text and "Pairs to write" in text:
        sys.exit("The clipboard holds the prompt, not the reply.")
    valid, problems, notes, asked = store_reply(stem, text, model)
    print(f"Saved {relative(REPLIES_DIR / (stem + '.txt'))}\n{stem}: {len(valid)} of {asked} pairs valid")
    for pair, issues in list(problems.items())[:6]:
        print(f"  {pair}: {'; '.join(issues)[:230]}")
    for note in notes:
        print(f"  note: {note}")
    if problems:
        print("Failed pairs are re-asked once: run python -m src.data.synthetic collect at the end.")
    after, done, total = next_stem()
    print(f"{done} of {total} prompts answered" + (f"; next: {after}" if after else "; all done"))


def cmd_auto(provider, limit, force):
    """Send every unanswered prompt to the provider's API and save the replies as the by-hand loop would."""
    try:
        label = llm_api.label(provider, SYNTH_TEMPERATURE)
    except llm_api.ApiError as problem:
        sys.exit(str(problem))
    if not GENERATOR_CSV.exists():
        sys.exit("Run python -m src.data.synthetic build first.")
    with open(GENERATOR_CSV, newline="", encoding="utf-8") as handle:
        current = next(csv.DictReader(handle), {}).get("model_name", "").strip()
    if current and current != label and any(REPLIES_DIR.glob("*.txt")) and not force:
        sys.exit(f"Replies already exist from a different model ({current}). Delete them (the files in {relative(REPLIES_DIR)}) or use --force.")
    with open(GENERATOR_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["chat_service", "model_name"])
        writer.writerow([llm_api.service_name(provider), label])
    pending = [s for s in stems() if not (REPLIES_DIR / f"{s}.txt").exists()]
    todo = pending[:limit] if limit else pending
    print(f"{len(pending)} prompt(s) to do, running {len(todo)} now with {label}. You can stop with Ctrl+C and start again.")
    for number, stem in enumerate(todo, start=1):
        try:
            reply = llm_api.chat(provider, (PROMPTS_DIR / f"{stem}.txt").read_text(encoding="utf-8"), temperature=SYNTH_TEMPERATURE)
        except llm_api.ApiError as problem:
            sys.exit(f"Stopped at {stem}: {problem}\nNothing is lost; run the same command again to continue from {stem}.")
        valid, _, _, asked = store_reply(stem, reply.text, label)
        print(f"  [{number}/{len(todo)}] {stem}: {len(valid)} of {asked} pairs valid" + ("  (cut off at the length limit)" if reply.truncated else ""))
        if number < len(todo):
            llm_api.pause()
    left = [s for s in stems() if not (REPLIES_DIR / f"{s}.txt").exists()]
    print(f"{len(stems()) - len(left)} of {len(stems())} prompts answered." + (" Run python -m src.data.synthetic collect next." if not left else ""))


def cmd_collect():
    plan = read_plan()
    valid, problems, tally = {}, {}, {}
    for stem in stems():
        reply = REPLIES_DIR / f"{stem}.txt"
        if not reply.exists():
            continue
        specs = specs_of(stem)
        good, bad, _ = check_pairs(reply.read_text(encoding="utf-8"), specs)
        valid.update(good)
        for pair in good:
            problems.pop(pair, None)
        for pair, issues in bad.items():
            if pair not in valid:
                problems[pair] = issues
            for issue in issues:
                tally[issue] = tally.get(issue, 0) + 1

    reask_stems = [s for s in stems() if s.startswith("synth_reask_")]
    asked = {pair for s in reask_stems for pair in specs_of(s)}
    answered = {pair for s in reask_stems if (REPLIES_DIR / f"{s}.txt").exists() for pair in specs_of(s)}
    retry = [pair for pair in problems if pair not in asked]
    for number, start in enumerate(range(0, len(retry), PAIRS_PER_PROMPT), start=1 + sum(s.startswith("synth_reask_") for s in stems())):
        (PROMPTS_DIR / f"synth_reask_{number:03d}.txt").write_text(
            prompt_for([plan[p] for p in retry[start:start + PAIRS_PER_PROMPT]]), encoding="utf-8")
    waiting = [p for p in problems if p in asked and p not in answered]
    dropped = [p for p in problems if p in answered]
    unanswered = [p for p in plan if p not in valid and p not in problems]

    print(f"Pairs planned {len(plan)}: valid {len(valid)}, re-ask prompts written for {len(retry)}, "
          f"awaiting a re-ask reply {len(waiting)}, dropped after a re-ask {len(dropped)}, not answered yet {len(unanswered)}")
    for issue, count in sorted(tally.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {count:>3}  {issue[:120]}")
    if not valid:
        return
    rows = []
    for pair, got in sorted(valid.items()):
        spec = plan[pair]
        for role in ("attack", "benign"):
            email = got[role]
            labels = {f"tactic_{t}": int(role == "attack" and t in spec["attack_tactics"].split("|")) for t in TACTICS}
            rows.append({"id": f"{pair}_{role}", "pair": pair, "role": role, "scenario": spec["scenario"], "split": spec["split"],
                         "subject": email["subject"], "body": email["body"], "body_redacted": redact(email["body"])[0],
                         **labels, "claims": json.dumps(email["claims"], ensure_ascii=False), "label_source": "synthetic"})
    table = pd.DataFrame(rows)
    table.to_csv(SYNTHETIC_CSV, index=False)

    counts = [{"group": "all", "label": "pairs_valid", "value": len(valid)}, {"group": "all", "label": "pairs_planned", "value": len(plan)},
              {"group": "all", "label": "pairs_dropped", "value": len(dropped)}]
    for split, part in table.groupby("split"):
        counts.append({"group": split, "label": "emails", "value": len(part)})
    for t in TACTICS:
        counts += [{"group": split, "label": f"tactic_{t}", "value": int(part[f"tactic_{t}"].sum())} for split, part in table.groupby("split")]
        counts.append({"group": "all", "label": f"tactic_{t}", "value": int(table[f"tactic_{t}"].sum())})
    for role, part in table.groupby("role"):
        for kind in CLAIM_TYPES:
            counts.append({"group": role, "label": f"claim_{kind}", "value": int(part["claims"].map(lambda c, k=kind: any(x["type"] == k for x in json.loads(c))).sum())})
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(counts).to_csv(SYNTHETIC_COUNTS_CSV, index=False)

    print("\nAttack emails per tactic (the label comes from the plan, confirmed by a quoted cue), per split")
    attack = table[table.role == "attack"]
    print(pd.DataFrame({t: attack.groupby("split")[f"tactic_{t}"].sum() for t in TACTICS}).T.assign(all=lambda d: d.sum(axis=1)).to_string())
    print(f"\nSaved {relative(SYNTHETIC_CSV)} ({len(table)} emails) and {relative(SYNTHETIC_COUNTS_CSV)}")
    if retry:
        print("Re-ask prompts were written: run python -m src.data.synthetic auto <annotator_1|annotator_2|tiebreaker> (or next and save by hand), then collect again.")


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    limit = None
    if "--limit" in flags:
        try:
            limit = int(args.pop())
        except (IndexError, ValueError):
            sys.exit("usage: python -m src.data.synthetic auto <annotator_1|annotator_2|tiebreaker> [--limit N] [--force]")
    commands = {"build": lambda: print(f"Wrote {len(write_plan_and_prompts())} pairs to {relative(PLAN_CSV)} and "
                                       f"{len(stems())} prompts to {relative(PROMPTS_DIR)}. Then run auto <provider> (or fill in {relative(GENERATOR_CSV)} and use next and save)."),
                "next": cmd_next, "save": cmd_save, "collect": cmd_collect}
    if len(args) == 1 and args[0] in commands:
        return commands[args[0]]()
    if len(args) == 2 and args[0] == "auto" and args[1] in llm_api.PROVIDERS:
        return cmd_auto(args[1], limit, "--force" in flags)
    sys.exit("usage: python -m src.data.synthetic build | auto <annotator_1|annotator_2|tiebreaker> [--limit N] [--force] | next | save | collect")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit("\nStopped by you. Nothing is lost; run the same command again to continue.")
