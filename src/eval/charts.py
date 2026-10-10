"""Phase 13: the charts of the report, drawn from the CSV files in results/ (and nothing else: no data, no model, no email text).

Run from the project root, after the experiments:
    python -m src.eval.charts --split test            # draws docs/figures/results/*.png from results/
    python -m src.eval.charts --split validation      # a rehearsal: draws data/processed/rehearsal/figures/*.png from the rehearsal tables
    python -m src.eval.charts --only n1,n3            # only the charts whose name contains one of these words

Every number in a chart is read from a results file, so a chart can be redrawn at any time and always agrees with its table. A chart whose table is missing is skipped with a note.
The dashboard of the interface draws its own charts with Recharts from the same files; these PNGs are for the report and the slides.

Design rules followed (the dataviz method of this project): one colour per entity and the same colour in every chart (a system, a model, a class); at most five categorical colours, in a fixed
order; thin bars with a surface-coloured gap between them; solid hairline grids; text in ink colours, never in a series colour; a legend whenever there are two or more series; a 95% interval drawn
for every rate that has one; cells that are counts only (fewer than 10 or 20 items) are hatched and drawn from the count; no dual axes; the table behind each chart is the results file named in
the caption under the figure. Mark text that says what a chart cannot show is printed under it.
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import MaxNLocator, PercentFormatter  # noqa: E402

from src.data import paths  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#74736d", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]           # categorical slots 1 to 5 of the reference palette (validated: adjacent pairs pass the colour-vision gates)
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SYSTEM_COLOUR = {"full": SERIES[0], "text": SERIES[1], "headers": SERIES[2], "fusion": SERIES[3], "flat": SERIES[4]}
SYSTEM_NAME = {"full": "full (claim-routed score)", "text": "text only", "headers": "headers only", "fusion": "parallel fusion", "flat": "flat classifier"}
KIND_COLOUR = {"attack": SERIES[0], "ham": SERIES[1], "spam": SERIES[2]}
MAIN_TACTICS = ("authority", "urgency", "scarcity", "secrecy")
LABEL_NOTE = "labels are LLM labels from one model family"


def setup():
    plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK, "legend.frameon": False,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.8, "hatch.linewidth": 0.8,
                         "axes.axisbelow": True, "figure.dpi": 100})


class Reader:
    """Reads a results table from the folder of the run, else from results/ (the tables of earlier phases live there)."""

    def __init__(self, folder):
        self.folders = [Path(folder), Path(paths.RESULTS_DIR)]

    def get(self, name):
        for folder in self.folders:
            path = folder / (name + ".csv")
            if path.exists():
                return pd.read_csv(path)
        return None


def finish(fig, out, name, caption):
    """Add the title (left aligned, wrapped), the legend and the caption outside the plot area, grow the figure so the plot keeps its size, and save the PNG."""
    import textwrap

    width, height = fig.get_size_inches()
    title = textwrap.fill(getattr(fig, "_title", ""), width=max(30, int(width * 9.5)))
    caption = textwrap.fill(caption, width=max(40, int(width * 15.5)))
    title_h = 0.12 + 0.2 * (title.count("\n") + 1) if title else 0.0
    caption_h = 0.1 + 0.125 * (caption.count("\n") + 1)
    handles = getattr(fig, "_handles", [])
    legend_h = 0.36 if handles else 0.0
    fig.set_size_inches(width, height + title_h + caption_h + legend_h)
    total = height + title_h + caption_h + legend_h
    if title:
        fig.text(0.012, 1 - 0.06 / total, title, fontsize=11, fontweight="bold", ha="left", va="top", color=INK)
    if handles:
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, (caption_h + 0.02) / total), ncol=max(1, min(len(handles), int(width / 2.3), 6)), fontsize=7.5)
    fig.text(0.012, 0.05 / total, caption, fontsize=7, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, (caption_h + legend_h) / total, 1, 1 - title_h / total))
    out.mkdir(parents=True, exist_ok=True)
    path = out / (name + ".png")
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def grid_y(ax):
    ax.yaxis.grid(True)
    ax.xaxis.grid(False)


def grid_x(ax):
    ax.xaxis.grid(True)
    ax.yaxis.grid(False)


def grouped_bars(ax, groups, series, colours, width=0.8, percent=False):
    """Vertical grouped bars. groups: list of labels; series: {name: [(value, low, high, counts_only) per group]}. Counts-only cells are hatched and carry no interval."""
    n = len(series)
    slot = width / n
    for k, (name, cells) in enumerate(series.items()):
        for i, cell in enumerate(cells):
            if cell is None or cell[0] is None or cell[0] != cell[0]:
                continue
            value, low, high, count_only = cell
            x = i - width / 2 + slot * (k + 0.5)
            if value == 0:
                ax.plot([x - slot * 0.43, x + slot * 0.43], [0, 0], color=colours[name], linewidth=2.2, solid_capstyle="butt", zorder=3)
            ax.bar(x, value, width=slot * 0.86, color=colours[name], edgecolor=SURFACE if not count_only else colours[name], linewidth=1.2, hatch="////" if count_only else None, alpha=1.0 if not count_only else 0.55)
            if low is not None and high is not None and low == low and high == high and not count_only:
                ax.plot([x, x], [low, high], color=INK2, linewidth=0.9, zorder=3)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups)
    grid_y(ax)
    if percent:
        ax.set_ylim(0, 1.0)
        ax.set_yticks(np.arange(0, 1.01, 0.2))
        ax.set_yticklabels(["%d%%" % (100 * v) for v in np.arange(0, 1.01, 0.2)])


def pick(table, **conditions):
    mask = pd.Series(True, index=table.index)
    for column, value in conditions.items():
        mask &= table[column] == value
    return table[mask]


# ---------------------------------------------------------------------------------------------------------------------
# The charts
# ---------------------------------------------------------------------------------------------------------------------

def chart_n1(read, out, split):
    scores = read.get("n1_scores")
    if scores is None:
        return None
    overall = scores[(scores["scope"] == "overall") & (scores["metric"] == "f1") & (scores["split"] == split)]
    views = ["raw", "redacted", "linkfree_raw", "linkfree_redacted"]
    view_names = ["raw", "redacted", "link-free,\nraw", "link-free,\nredacted"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9), sharey=True)
    colours = {"A (trained on raw)": SERIES[0], "B (trained on redacted)": SERIES[1]}
    rule_drawn = False
    for ax, (family, title) in zip(axes, [("distilbert", "DistilBERT"), ("tfidf_sample", "TF-IDF + LR, same sample"), ("tfidf_full", "TF-IDF + LR, all train emails")]):
        a, b = ("distilbert_A", "distilbert_B") if family == "distilbert" else ("tfidf_A_" + family.split("_")[1], "tfidf_B_" + family.split("_")[1])
        series = {}
        for label, model in (("A (trained on raw)", a), ("B (trained on redacted)", b)):
            cells = []
            for view in views:
                r = overall[(overall["model"] == model) & (overall["view"] == view)]
                cells.append((r["value"].iloc[0], r["value_ci_low"].iloc[0], r["value_ci_high"].iloc[0], False) if len(r) else None)
            series[label] = cells
        grouped_bars(ax, view_names, series, colours)
        ax.set_ylim(0, 1.0)
        ax.set_title(title)
        ax.tick_params(axis="x", labelsize=8)
        rule = overall[(overall["model"] == "link_rule") & (overall["view"] == "raw")]
        if len(rule):
            ax.axhline(rule["value"].iloc[0], color=INK2, linewidth=0.9)
            rule_drawn = True
    axes[0].set_ylabel("attack-class F1 (higher is better)")
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=c, edgecolor=SURFACE, label=n) for n, c in colours.items()]
    if rule_drawn:
        fig._handles.append(Line2D([0], [0], color=INK2, linewidth=1.2, label="link-presence rule, raw view"))
    fig._title = "N1: how much of a phishing detector's accuracy is link-reading? (%s split)" % split
    return finish(fig, out, "fig_n1_ablation", "Source: results/n1_scores.csv. Bars: attack-class F1 at a fixed threshold of 0.5; lines: 95%% intervals drawing whole subject groups. Corpus labels (attack corpora against the rest). "
                  "Link-free = emails that naturally had no link. Attacks and not-attack emails come from different corpora, so style alone can separate them (see fig_style_auc).")


def chart_n2(read, out, split):
    scores, bench = read.get("n2_scores"), read.get("n2_score_benchmark")
    if scores is None:
        return None
    scores = scores[scores["split"] == split]
    bench = bench[bench["split"] == split] if bench is not None else None
    sources = [s for s in ("apache", "enron") if (scores["source"] == s).any()]
    names = {"N2": "thread verifier (N2)", "P8": "Phase 8 verifiers alone", "SF": "risk score with the thread verifier", "SP": "risk score without it"}
    colours = {"N2": SERIES[0], "P8": SERIES[1], "SF": SERIES[2], "SP": SERIES[3]}
    fig, axes = plt.subplots(1, len(sources), figsize=(4.6 * len(sources) + 1.8, 3.9), sharey=True, squeeze=False)
    for ax, source in zip(axes[0], sources):
        variants = [v for v in ("A", "B", "C") if (scores[(scores["source"] == source)]["variant"] == v).any()]
        series = {k: [] for k in names}
        for variant in variants:
            for key, table, metric in (("N2", scores, "detect_n2"), ("P8", scores, "detect_phase8"), ("SF", bench, "suspicious_or_high_full"), ("SP", bench, "suspicious_or_high_phase8")):
                r = pick(table, source=source, variant=variant, metric=metric) if table is not None else pd.DataFrame()
                if len(r):
                    row = r.iloc[0]
                    count_only = pd.isna(row["rate"])
                    series[key].append((row["hits"] / row["n"] if count_only else row["rate"], None if count_only else row["ci_low"], None if count_only else row["ci_high"], count_only))
                else:
                    series[key].append(None)
        grouped_bars(ax, [{"A": "A takeover", "B": "B look-alike\nswap", "C": "C forged\nthread"}[v] for v in variants], series, colours, percent=True)
        ax.set_title("%s threads" % source.capitalize())
    axes[0][0].set_ylabel("share of hijack cases detected")
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=colours[k], edgecolor=SURFACE, label=n) for k, n in names.items()]
    fig._title = "N2: does checking the thread catch hijacks that single-message checks miss? (%s split)" % split
    return finish(fig, out, "fig_n2_hijack", "Source: results/n2_scores.csv and n2_score_benchmark.csv. A medium or high contradiction on the injected message counts as detection; the score bars use 'Suspicious or above'. Intervals draw whole threads; "
                  "hatched bars have fewer than 10 cases (a count). The injected messages and their headers are synthetic; raw Enron has no sending-path data, so Enron tests the content signals and the quote check only.")


def system_panels(read, out, split, table_name, systems, name, title, caption):
    table = read.get(table_name)
    if table is None:
        return None
    table = table[(table["split"] == split) & table["scope"].str.startswith("source: ")]
    if table.empty:
        return None
    panels = (("detection_rate", "attack sources: share detected (higher is better)"), ("false_alarm_rate", "ordinary mail (ham): share flagged (lower is better)"))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1, 2]})
    for ax, (metric, label) in zip(axes, panels):
        part = table[table["metric"] == metric]
        sources = list(dict.fromkeys(part["scope"]))
        series = {}
        for system in systems:
            cells = []
            for scope in sources:
                r = part[(part["scope"] == scope) & (part["system"] == system)]
                if r.empty:
                    cells.append(None)
                elif pd.isna(r["value"].iloc[0]):
                    cells.append((r["hits"].iloc[0] / r["n"].iloc[0], None, None, True))
                else:
                    cells.append((r["value"].iloc[0], r["value_ci_low"].iloc[0], r["value_ci_high"].iloc[0], False))
            series[system] = cells
        grouped_bars(ax, [s.replace("source: ", "").split(" (")[0].replace("kaggle_", "").replace("apache_", "apache ").replace("_users", "").replace("_", " ") for s in sources], series, SYSTEM_COLOUR)
        ax.set_ylabel(label, fontsize=8)
        ax.tick_params(axis="x", labelsize=7.5, rotation=0 if metric == "detection_rate" else 20)
        if metric == "false_alarm_rate":
            top = max([c[2] if c and c[2] is not None else (c[0] if c else 0) for cells in series.values() for c in cells] + [0.02])
            ax.set_ylim(0, min(1.0, max(0.05, top * 1.15)))
            ax.yaxis.set_major_locator(MaxNLocator(5, steps=[1, 2, 5, 10]))
            ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0 if ax.get_ylim()[1] >= 0.2 else 1))
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=SYSTEM_COLOUR[s], edgecolor=SURFACE, label=SYSTEM_NAME[s]) for s in systems]
    fig._title = title % split
    return finish(fig, out, name, caption)


def chart_n3(read, out, split):
    return system_panels(read, out, split, "n3_systems", ["full", "text", "headers", "fusion"], "fig_n3_detection", "N3: claim-conditioned checks against text only, headers only and parallel fusion (%s split)",
                         "Source: results/n3_systems.csv. Every learned system is held to the false-alarm rate the frozen score shows on validation ham (results/n3_cuts.csv). Lines: 95% intervals drawing whole subject groups. "
                         "No source holds both attacks and ordinary mail, so read the left panel against the right. The learned systems saw attack labels and the headers-only system can partly learn which corpus an email came from.")


def chart_arch(read, out, split):
    return system_panels(read, out, split, "arch_systems", ["full", "flat"], "fig_arch", "Architecture: claim-routed score against a flat classifier on the same signals (%s split)",
                         "Source: results/arch_systems.csv. The flat classifier gets every ledger signal as one vector without the link between a claim and the evidence against it, and is held to the same false-alarm rate. "
                         "Lines: 95% intervals drawing whole subject groups. The routed score's traceable reason is a property of its design (results/arch_reasons.csv), not a measured gain.")


def chart_tactics(read, out, split):
    table = read.get("tactic_test_scores")
    if table is None:
        return None
    real = table[table["data"] == "real_" + split]
    if real.empty:
        return None
    systems = [("distilbert", "DistilBERT"), ("keyword_tuned", "keyword baseline, tuned on validation"), ("keyword_default", "keyword baseline, default")]
    colours = {"distilbert": SERIES[0], "keyword_tuned": SERIES[1], "keyword_default": SERIES[2]}
    labels = list(MAIN_TACTICS) + ["macro_main4"]
    series = {}
    for system, _ in systems:
        cells = []
        for tactic in labels:
            r = real[(real["system"] == system) & (real["tactic"] == tactic)]
            cells.append((r["f1"].iloc[0], r["f1_ci_low"].iloc[0], r["f1_ci_high"].iloc[0], False) if len(r) and pd.notna(r["f1"].iloc[0]) else None)
        series[system] = cells
    fig, ax = plt.subplots(figsize=(8.4, 4))
    grouped_bars(ax, ["authority", "urgency", "scarcity", "secrecy", "macro-F1\n(mean of the four)"], series, colours)
    validation = real[(real["system"] == "distilbert") & real["tactic"].isin(labels)]
    slot = 0.8 / 3
    for i, tactic in enumerate(labels):
        r = validation[validation["tactic"] == tactic]
        if len(r) and pd.notna(r["validation_f1"].iloc[0]):
            ax.plot([i - 0.4 + slot * 0.5], [r["validation_f1"].iloc[0]], marker="D", markersize=5, markerfacecolor=SURFACE, markeredgecolor=INK, markeredgewidth=1.1, linestyle="none", zorder=4)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("F1 on the labelled real %s emails" % split)
    handles = [Patch(facecolor=colours[s], edgecolor=SURFACE, label=n) for s, n in systems] + [Line2D([0], [0], marker="D", color="none", markerfacecolor=SURFACE, markeredgecolor=INK, markersize=5, label="DistilBERT on validation (Phase 6)")]
    fig._handles = getattr(fig, "_handles", []) + handles
    fig._title = "Tactic classifier against the keyword baseline (%s split)" % split
    return finish(fig, out, "fig_tactics_test", "Source: results/tactic_test_scores.csv. Authority, urgency, scarcity and secrecy are the four tactics with 10 or more real positives; the other three are counts only (see the table). Lines: 95% intervals drawing whole "
                  "subject groups. Every score is agreement with LLM labels from one model family, not with people. Validation chose the epoch, the seed and the thresholds, so the validation markers are slightly optimistic.")


def chart_claims(read, out, split):
    table = read.get("claim_test_scores")
    if table is None:
        return None
    part = table[(table["data"] == "real_" + split) & table["chosen"].astype(bool) & table["f1"].notna() & ~table["claim_type"].str.startswith("macro")]
    if part.empty:
        return None
    part = part.sort_values("f1")
    fig, ax = plt.subplots(figsize=(8, 0.9 + 0.55 * len(part)))
    y = np.arange(len(part))
    ax.hlines(y, 0, 1, color=GRID, linewidth=0.8, zorder=0)
    for i, r in enumerate(part.itertuples()):
        ax.plot([r.f1_ci_low, r.f1_ci_high], [i, i], color=INK2, linewidth=1.0, zorder=2)
        ax.plot(r.f1, i, marker="o", markersize=7, color=SERIES[0], markeredgecolor=SURFACE, markeredgewidth=1.4, linestyle="none", zorder=3)
        if pd.notna(r.validation_f1):
            ax.plot(r.validation_f1, i, marker="D", markersize=5.5, markerfacecolor=SURFACE, markeredgecolor=SERIES[1], markeredgewidth=1.5, linestyle="none", zorder=3)
        if pd.notna(r.annotator_agreement_f1):
            ax.plot(r.annotator_agreement_f1, i, marker="s", markersize=5.5, markerfacecolor=SERIES[2], markeredgecolor=SURFACE, linestyle="none", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([("%s (%d positives, %s)" % (r.claim_type.replace("_", " "), r.positives, "strong only" if r.min_confidence >= 0.9 else "every claim")) for r in part.itertuples()], fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("F1")
    grid_x(ax)
    fig._handles = getattr(fig, "_handles", []) + [Line2D([0], [0], marker="o", color="none", markerfacecolor=SERIES[0], markersize=7, label="test, with 95% interval"),
                       Line2D([0], [0], marker="D", color="none", markerfacecolor=SURFACE, markeredgecolor=SERIES[1], markersize=6, label="validation (Phase 7)"),
                       Line2D([0], [0], marker="s", color="none", markerfacecolor=SERIES[2], markersize=6, label="annotator 2 against annotator 1")]
    fig._title = "Claim extractor on the labelled real %s emails" % split
    return finish(fig, out, "fig_claims_test", "Source: results/claim_test_scores.csv. Only the claim types with 10 or more real positives get an F1; six types are counts only. The operating point (every claim or strong claims only) was chosen on validation. "
                  "Scores are agreement with LLM labels from one model family; the square shows how well the two annotators agree with each other.")


def chart_style(read, out, split):
    table = read.get("style_auc")
    if table is None:
        return None
    table = table[table["split"] == split]
    if table.empty:
        return None
    pairs = table[["task", "group_a", "group_b"]].drop_duplicates().reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.6, 1.0 + 0.27 * len(pairs)))
    ax.axvline(0.5, color=INK2, linewidth=0.8)
    previous = None
    for i, p in enumerate(pairs.itertuples()):
        if p.task != previous and previous is not None:
            ax.axhline(i - 0.5, color=GRID, linewidth=0.8)
        previous = p.task
        for features, colour, shift, marker in (("words", SERIES[0], -0.12, "o"), ("tactic probabilities", SERIES[1], 0.12, "s")):
            r = table[(table["task"] == p.task) & (table["group_a"] == p.group_a) & (table["group_b"] == p.group_b) & (table["features"] == features)]
            if len(r):
                r = r.iloc[0]
                ax.plot([r["auc_ci_low"], r["auc_ci_high"]], [i + shift, i + shift], color=colour, linewidth=1.2, zorder=2)
                ax.plot(r["auc"], i + shift, marker=marker, markersize=5, color=colour, markeredgecolor=SURFACE, linestyle="none", zorder=3)
    ax.set_yticks(range(len(pairs)))
    ax.set_yticklabels(["%s: %s | %s" % (p.task.replace("same-kind sources (", "").replace("real against synthetic (", "real vs synthetic, ").replace(")", "").replace(" emails", ""), p.group_a.replace("kaggle_", ""), p.group_b.replace("kaggle_", "")) for p in pairs.itertuples()], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0.3, 1.02)
    ax.set_xlabel("AUC of telling the two collections apart (0.5 = cannot, 1.0 = perfectly)")
    grid_x(ax)
    fig._handles = getattr(fig, "_handles", []) + [Line2D([0], [0], marker="o", color=SERIES[0], markersize=5, label="words of the redacted body"), Line2D([0], [0], marker="s", color=SERIES[1], markersize=5, label="the 7 tactic probabilities")]
    fig._title = "Style-confound test: can the collections be told apart by their writing? (%s split)" % split
    return finish(fig, out, "fig_style_auc", "Source: results/style_auc.csv. Pairs of collections of the SAME kind (ham against ham, attack against attack) and real against synthetic emails. A high AUC on words is a threat to validity: a detector that separates attacks from "
                  "ordinary mail may be separating collections. Lines: 95% intervals drawing whole subject groups.")


def chart_cooccurrence(read, out, split):
    table = read.get("analysis_cooccurrence")
    if table is None:
        return None
    tactics = list(dict.fromkeys(table["tactic_a"]))
    colormap = LinearSegmentedColormap.from_list("ramp", SEQUENTIAL)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    top = max(1, int(table["emails_both"].max()))
    for ax, scope, title in zip(axes, ("labels", "predicted"), ("in the labels", "in the classifier's predictions")):
        grid = np.zeros((len(tactics), len(tactics)))
        for r in table[table["scope"] == scope].itertuples():
            grid[tactics.index(r.tactic_a), tactics.index(r.tactic_b)] = r.emails_both
        image = ax.imshow(grid, cmap=colormap, vmin=0, vmax=top)
        for i in range(len(tactics)):
            for j in range(len(tactics)):
                ax.text(j, i, int(grid[i, j]), ha="center", va="center", fontsize=7.5, color="white" if grid[i, j] > top * 0.55 else INK)
        ax.set_xticks(range(len(tactics)))
        ax.set_xticklabels([t.replace("_", " ") for t in tactics], rotation=40, ha="right", fontsize=8)
        ax.set_yticks(range(len(tactics)))
        ax.set_yticklabels([t.replace("_", " ") for t in tactics], fontsize=8)
        ax.set_title("Emails with both tactics, %s" % title, fontsize=9)
        for spine in ax.spines.values():
            spine.set_visible(False)
    fig.colorbar(image, ax=axes, shrink=0.8, label="emails")
    fig._title = "Which tactics occur together? (labelled real %s emails; analysis only)" % split
    return finish(fig, out, "fig_cooccurrence", "Source: results/analysis_cooccurrence.csv. The diagonal is the number of emails with that tactic. Co-occurrence of tactics is an analysis, not a result of this project (Pan et al. 2026 and Ferreira and Teles did it first). "
                  "%s." % LABEL_NOTE)


def chart_budget(read, out, split):
    table = read.get("score_test_budget")
    if table is None:
        return None
    part = table[(table["kind"].isin(["email", "thread"])) & table["suspicious_or_high_pct"].notna()].copy()
    if part.empty:
        return None
    part["label"] = ["%s: %s (%d checked)" % ("real thread messages" if k == "thread" else "ham", g.replace("kaggle_", "").replace("_users", ""), n) for k, g, n in zip(part["kind"], part["group"], part["checked_n"])]
    fig, ax = plt.subplots(figsize=(8.4, 1.2 + 0.45 * len(part)))
    for x, text in ((5, "budget: Suspicious or above 5%"), (1, "budget: High risk 1%")):
        ax.axvline(x, color=INK2, linewidth=0.8)
        ax.text(x + 0.15, -0.62, text, fontsize=7, color=INK2, va="bottom", rotation=0)
    for i, r in enumerate(part.itertuples()):
        for value, low, high, colour, shift, marker in ((r.suspicious_or_high_pct, r.suspicious_ci_low, r.suspicious_ci_high, SERIES[0], -0.1, "o"), (r.high_pct, r.high_ci_low, r.high_ci_high, SERIES[1], 0.1, "s")):
            ax.plot([low, high], [i + shift, i + shift], color=colour, linewidth=1.2, zorder=2)
            ax.plot(value, i + shift, marker=marker, markersize=5.5, color=colour, markeredgecolor=SURFACE, linestyle="none", zorder=3)
    ax.set_yticks(range(len(part)))
    ax.set_yticklabels(part["label"], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(left=0)
    ax.set_xlabel("share of checked legitimate emails or real thread messages, %")
    grid_x(ax)
    fig._handles = getattr(fig, "_handles", []) + [Line2D([0], [0], marker="o", color=SERIES[0], markersize=5.5, label="Suspicious or above"), Line2D([0], [0], marker="s", color=SERIES[1], markersize=5.5, label="High risk")]
    fig._title = "False-alarm budget of the frozen risk score on the %s split" % split
    return finish(fig, out, "fig_score_budget_test", "Source: results/score_test_budget.csv. Lines: 95% Wilson intervals. The budget was declared before the validation emails were read; Phase 10 found the Enron thread messages over it (the quote check), "
                  "which is why the test run measures it again. Only groups with 10 or more checked items are drawn.")


def chart_paraphrase(read, out, split):
    table = read.get("paraphrase_results")
    if table is None:
        return None
    table = table[table["split"] == split]
    groups = [g for g in dict.fromkeys(table["group"])]
    if not groups:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9), gridspec_kw={"width_ratios": [1, 1.2]})
    ax = axes[0]
    series = {"flagged before": [], "flagged after": []}
    for g in groups:
        for name, item in (("flagged before", "flagged before (Suspicious or above)"), ("flagged after", "flagged after")):
            r = table[(table["group"] == g) & (table["item"] == item)]
            series[name].append((r["hits"].iloc[0] / r["denominator"].iloc[0], r["ci_low"].iloc[0], r["ci_high"].iloc[0], pd.isna(r["rate"].iloc[0])) if len(r) else None)
    grouped_bars(ax, [g.replace("kaggle_", "").replace("_", " ") for g in groups], series, {"flagged before": SERIES[0], "flagged after": SERIES[1]}, percent=True)
    ax.set_title("Flagged Suspicious or above")
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=SERIES[0], edgecolor=SURFACE, label="original"), Patch(facecolor=SERIES[1], edgecolor=SURFACE, label="reworded")]
    ax.tick_params(axis="x", labelsize=7.5)
    ax = axes[1]
    attack_groups = [g for g in groups if not g.startswith("ham")]
    colours = {t: SERIES[i] for i, t in enumerate(MAIN_TACTICS)}
    series = {t: [] for t in MAIN_TACTICS}
    for g in attack_groups:
        for t in MAIN_TACTICS:
            r = table[(table["group"] == g) & (table["item"] == "%s kept among those that fired before" % t)]
            series[t].append((r["hits"].iloc[0] / r["denominator"].iloc[0], r["ci_low"].iloc[0], r["ci_high"].iloc[0], pd.isna(r["rate"].iloc[0])) if len(r) and r["denominator"].iloc[0] else None)
    grouped_bars(ax, [g.replace("kaggle_", "").replace("_", " ") for g in attack_groups], series, colours, percent=True)
    ax.set_title("Tactic still detected after rewording")
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=colours[t], edgecolor=SURFACE, label=t) for t in MAIN_TACTICS]
    fig._title = "Adversarial paraphrase: the same email and headers, other words (%s split)" % split
    return finish(fig, out, "fig_paraphrase", "Source: results/paraphrase_results.csv. One language model rewrote each body; the headers were not touched; meaning was spot-checked on six pairs only. Hatched bars have fewer than 20 emails (counts). "
                  "Lines: 95% Wilson intervals. The ham control shows whether rewording creates false alarms.")


def chart_header_coverage(read, out, split):
    table = read.get("header_coverage")
    if table is None:
        return None
    columns = [c for c in table.columns if c not in ("source", "full_headers", "messages")]
    colormap = LinearSegmentedColormap.from_list("ramp", SEQUENTIAL)
    grid = table[columns].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(10, 0.9 + 0.38 * len(table)))
    image = ax.imshow(grid, cmap=colormap, vmin=0, vmax=100, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, "%d" % round(grid[i, j]), ha="center", va="center", fontsize=7, color="white" if grid[i, j] > 55 else INK)
    ax.set_xticks(range(len(columns)))
    ax.set_xticklabels(columns, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(table)))
    ax.set_yticklabels(["%s (%s messages)" % (s.replace("kaggle_", ""), format(int(m), ",")) for s, m in zip(table["source"], table["messages"])], fontsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.colorbar(image, ax=ax, shrink=0.8, label="% of messages that carry the header")
    fig._title = "Which sources carry which headers?"
    return finish(fig, out, "fig_header_coverage", "Source: results/header_coverage.csv (Phase 1). Header signals can only be scored where the header exists: the Kaggle Enron and Ling emails carry none, which is why every contrast between "
                  "attack and ordinary mail is reported per source.")


def chart_agreement(read, out, split):
    table = read.get("label_agreement")
    if table is None:
        return None
    table = table[table["kind"].isin(["tactic", "claim"]) & table["kappa"].notna()].sort_values("kappa")
    if table.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.6, 1.0 + 0.27 * len(table)))
    colours = {"tactic": SERIES[0], "claim": SERIES[1]}
    ax.barh(range(len(table)), table["kappa"], height=0.62, color=[colours[k] for k in table["kind"]], edgecolor=SURFACE, linewidth=1.2)
    for x, text in ((0.2, "slight | fair"), (0.4, "fair | moderate"), (0.6, "moderate | substantial"), (0.8, "substantial | almost perfect")):
        ax.axvline(x, color=GRID, linewidth=0.8, zorder=0)
        ax.text(x, len(table) - 0.35, text, fontsize=6, color=MUTED, ha="center", va="bottom")
    ax.set_yticks(range(len(table)))
    shared = set(table["label"][table["kind"] == "tactic"]) & set(table["label"][table["kind"] == "claim"])
    ax.set_yticklabels([l.replace("_", " ") + (" (%s)" % k if l in shared else "") for l, k in zip(table["label"], table["kind"])], fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Cohen's kappa between the two LLM annotators")
    grid_x(ax)
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=colours[k], edgecolor=SURFACE, label=n) for k, n in (("tactic", "tactics"), ("claim", "claim types"))]
    fig._title = "How reliable are the labels? Agreement between the two annotators"
    return finish(fig, out, "fig_annotator_agreement", "Source: results/label_agreement.csv (Phase 5). Both annotators are models of one family (Google Gemini), so their errors are partly shared; low kappa on rare labels is expected. Reading scale of Landis and Koch (1977).")


def chart_links(read, out, split):
    table = read.get("n1_view_counts")
    if table is None:
        return None
    part = table[(table["split"] == split) & (table["view"] == "all")].copy()
    if part.empty:
        return None
    part["kind"] = ["attack" if a else c for a, c in zip(part["is_attack"], part["category"])]
    part = part.sort_values(["kind", "link_share_pct"])
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 1.1 + 0.3 * len(part)), sharey=True)
    for ax, column, title in zip(axes, ("link_share_pct", "text_changed_by_redaction_pct"), ("had a link", "text changed by the redaction")):
        ax.barh(range(len(part)), part[column], height=0.62, color=[KIND_COLOUR[k] for k in part["kind"]], edgecolor=SURFACE, linewidth=1.2)
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of the source's emails")
        ax.set_title(title, fontsize=9)
        grid_x(ax)
    axes[0].set_yticks(range(len(part)))
    axes[0].set_yticklabels([s.replace("kaggle_", "") for s in part["source"]], fontsize=8)
    fig._handles = getattr(fig, "_handles", []) + [Patch(facecolor=KIND_COLOUR[k], edgecolor=SURFACE, label=n) for k, n in (("attack", "attack sources"), ("ham", "ham"), ("spam", "spam"))]
    fig._title = "What the N1 views contain (%s split)" % split
    return finish(fig, out, "fig_n1_links", "Source: results/n1_view_counts.csv. The redacted view differs from the raw view only where the redaction found something to replace (links, addresses, domains, file names).")


CHARTS = [("n1", chart_n1), ("links", chart_links), ("n2", chart_n2), ("n3", chart_n3), ("arch", chart_arch), ("tactics", chart_tactics), ("claims", chart_claims), ("style", chart_style),
          ("cooccurrence", chart_cooccurrence), ("budget", chart_budget), ("paraphrase", chart_paraphrase), ("coverage", chart_header_coverage), ("agreement", chart_agreement)]


def draw_all(split, only=None, folder=None, out=None):
    """Draw every chart whose table exists. Returns ({chart name: path}, [names skipped])."""
    setup()
    if folder is None:
        folder = paths.RESULTS_DIR if split == "test" else paths.REHEARSAL_DIR
    if out is None:
        out = Path(paths.FIGURES_DIR) if split == "test" else Path(paths.REHEARSAL_DIR) / "figures"
    read = Reader(folder)
    drawn, skipped = {}, []
    for name, function in CHARTS:
        if only and not any(word in name for word in only):
            continue
        path = function(read, out, split)
        if path is None:
            skipped.append(name)
        else:
            drawn[name] = path
    return drawn, skipped


def main(argv):
    parser = argparse.ArgumentParser(description="Draw the report charts from the results tables (Phase 13).")
    parser.add_argument("--split", default="test", choices=("validation", "test"), help="test reads results/ and writes docs/figures/results/; validation is a rehearsal")
    parser.add_argument("--only", default="", help="comma-separated words: draw only the charts whose name contains one of them")
    args = parser.parse_args(argv)
    drawn, skipped = draw_all(args.split, [w for w in args.only.split(",") if w])
    for name, path in drawn.items():
        print("  drew %-14s %s" % (name, path))
    for name in skipped:
        print("  skipped %-12s (its results table is missing or empty)" % name)
    print("%d charts drawn, %d skipped" % (len(drawn), len(skipped)))
    return 0 if drawn else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
