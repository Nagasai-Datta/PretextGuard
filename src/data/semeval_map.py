"""Phase 5: the mapping from SemEval-2023 Task 3 (Subtask 3) persuasion techniques to PretextGuard's seven tactics.

SemEval labels news paragraphs with 23 persuasion techniques. Optional pretraining (master document
Section 12.4: the first thing dropped if time runs short) could teach DistilBERT the vocabulary of
persuasion before it sees emails, but only if those 23 labels are translated into our seven. This file is
that translation, written down so it can be defended:

    python -m src.data.semeval_map                      print the table, write results/semeval_mapping.csv
    python -m src.data.semeval_map --check FILE         look for the 23 names in a downloaded label file

How well a technique matches a tactic is recorded, not hidden:
    direct   the technique is the news-text version of the tactic (Appeal_to_Time is urgency).
    partial  related but not the same thing (Appeal_to_Fear-Prejudice is loss framing aimed at groups,
             not "your account will be deleted").
    none     no counterpart.

Two consequences for any pretraining that uses this table (tactic_labels below):
- Reciprocity has no matching technique at all, and secrecy only a weak one. SemEval cannot say whether
  a paragraph uses them, so those labels are None (masked: left out of the loss), never 0. Calling them 0
  would teach the model that reciprocity is absent from text that simply was not annotated for it.
- A tactic with a direct technique (authority, urgency, social proof) gets a real 0 when its technique is
  absent, because SemEval annotators marked every technique they found. A tactic with only partial
  techniques gets 1 when one is present and None otherwise.

The technique names are written from the task description. The data needs registration on the task
website and could not be reached from the build sandbox, so the names have NOT been checked against a
real label file yet: run --check on one before using the table. Names it does not recognise are listed.
"""

import csv
import sys

from src.data.label_schema import TACTICS
from src.data.paths import RESULTS_DIR, SEMEVAL_MAPPING_CSV, relative

# technique -> (tactic or None, match, reason)
MAPPING = {
    "Appeal_to_Authority": ("authority", "direct", "cites a person or institution to be believed"),
    "Appeal_to_Time": ("urgency", "direct", "says the moment to act is now"),
    "Appeal_to_Popularity": ("social_proof", "direct", "says everyone supports or does it"),
    "Appeal_to_Fear-Prejudice": ("scarcity", "partial", "threat of a bad outcome; loss framing, but aimed at groups"),
    "False_Dilemma-No_Choice": ("scarcity", "partial", "only one option is left; finality framing"),
    "Appeal_to_Values": ("liking", "partial", "appeals to shared values; closest to manufactured affinity"),
    "Flag_Waving": ("liking", "partial", "plays on group identity; affinity with the in-group"),
    "Conversation_Killer": ("secrecy", "partial", "words meant to stop discussion; closest to cutting off checking"),
    "Appeal_to_Hypocrisy": (None, "none", "attack on the other side's consistency"),
    "Causal_Oversimplification": (None, "none", "one cause for a complex event"),
    "Consequential_Oversimplification": (None, "none", "a chain of consequences without support"),
    "Doubt": (None, "none", "casts doubt on a person or claim"),
    "Exaggeration-Minimisation": (None, "none", "makes something bigger or smaller than it is"),
    "Guilt_by_Association": (None, "none", "links someone to a disliked group"),
    "Loaded_Language": (None, "none", "emotionally charged words; too broad to equal any one tactic"),
    "Name_Calling-Labeling": (None, "none", "labels a person or group"),
    "Obfuscation-Vagueness-Confusion": (None, "none", "deliberately unclear wording"),
    "Questioning_the_Reputation": (None, "none", "attacks a person's credibility"),
    "Red_Herring": (None, "none", "introduces an irrelevant topic"),
    "Repetition": (None, "none", "repeats a message"),
    "Slogans": (None, "none", "a short striking phrase"),
    "Straw_Man": (None, "none", "misrepresents the other side's position"),
    "Whataboutism": (None, "none", "answers a charge with a counter-charge"),
}
assert len(MAPPING) == 23
KNOWN_ZERO = {tactic for tactic, match, _ in MAPPING.values() if match == "direct"}


def tactic_labels(techniques, use_partial=True):
    """Our seven tactic labels for one paragraph, from the SemEval techniques annotated in it.

    Returns {tactic: 1, 0 or None}; None means SemEval cannot say (mask it, do not train on it).
    Raises ValueError for a technique name that is not in MAPPING.
    """
    present = set()
    for name in techniques:
        if name not in MAPPING:
            raise ValueError(f"unknown SemEval technique {name!r}")
        tactic, match, _ = MAPPING[name]
        if tactic and (use_partial or match == "direct"):
            present.add(tactic)
    return {tactic: 1 if tactic in present else (0 if tactic in KNOWN_ZERO else None) for tactic in TACTICS}


def check_file(path):
    """Report which of the 23 names occur in a label file and which technique-like names are unknown."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        tokens = [t.strip(",;:.()[]\"'") for t in handle.read().split()]
    found = {name: tokens.count(name) for name in MAPPING}
    unknown = sorted({t for t in tokens if t not in MAPPING and 3 < len(t) < 45 and t[0].isupper() and ("_" in t or "-" in t)})
    print(f"{sum(1 for c in found.values() if c)} of 23 mapped names occur in {path}")
    for name, count in found.items():
        print(f"  {count:>7}  {name}" if count else f"  {'-':>7}  {name}   (not found)")
    if unknown:
        print("\nTechnique-like names in the file that are NOT in the mapping (fix MAPPING, then rerun):")
        for name in unknown[:30]:
            print(f"  {name}")
    return not unknown and all(found.values())


def main(argv):
    if argv and argv[0] == "--check":
        if len(argv) != 2:
            sys.exit("usage: python -m src.data.semeval_map --check FILE")
        return 0 if check_file(argv[1]) else 1
    print(f"{'technique':<34} {'tactic':<13} {'match':<8} reason")
    for name, (tactic, match, reason) in MAPPING.items():
        print(f"{name:<34} {tactic or '-':<13} {match:<8} {reason}")
    print("\nTactics and the techniques mapped to them")
    for tactic in TACTICS:
        names = [n for n, (t, _, _) in MAPPING.items() if t == tactic]
        status = "real 0 when absent" if tactic in KNOWN_ZERO else ("positive only" if names else "no technique: always masked")
        print(f"  {tactic:<13} {len(names)} technique(s): {', '.join(names) or '-'}   [{status}]")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEMEVAL_MAPPING_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["technique", "tactic", "match", "reason"])
        writer.writerows([[name, tactic or "", match, reason] for name, (tactic, match, reason) in MAPPING.items()])
    print(f"\nSaved {relative(SEMEVAL_MAPPING_CSV)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
