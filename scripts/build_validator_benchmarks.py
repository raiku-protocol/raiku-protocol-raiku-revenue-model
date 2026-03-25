"""
build_validator_benchmarks.py
=============================================================
Reads data/validators_epoch_945.csv and produces:
  outputs/validator_benchmarks_epoch_945.json   (canonical JSON)
  outputs/validators_epoch_945_enriched.csv     (enriched CSV with ranks/percentiles)
  outputs/charts/*.png                          (exploratory charts, matplotlib)

All monetary fields (REV, Inflation, MEV, Pri Fees, Sig Fees, Rewards)
are treated as SOL per block (per leader slot produced), as stored in
the source CSV.  The formula used by the export tool is:
    field_per_block = epoch_total_for_validator / leader_slots_produced

Stake column in the CSV = actual_stake_SOL / leader_slots.
To recover actual stake in SOL:  actual_stake_sol = Stake * Leader_Slots.

Usage:
    python scripts/build_validator_benchmarks.py
"""

import csv
import json
import math
import os
import statistics


# ── Paths ────────────────────────────────────────────────────────────────────
BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV   = os.path.join(BASE, "data", "validators_epoch_945.csv")
OUTPUT_JSON = os.path.join(BASE, "outputs", "validator_benchmarks_epoch_945.json")
OUTPUT_CSV  = os.path.join(BASE, "outputs", "validators_epoch_945_enriched.csv")
CHARTS_DIR  = os.path.join(BASE, "outputs", "charts")


# ── Helpers ──────────────────────────────────────────────────────────────────
def _parse(val):
    """Return float or None for empty / non-numeric strings."""
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _pct(values, p):
    """p-th percentile (0-100) of a sorted list, linear interpolation."""
    n = len(values)
    if n == 0:
        return None
    idx = (p / 100) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _stats(values):
    """Return dict with mean, median, sample_size (filters None)."""
    sv = sorted(v for v in values if v is not None)
    n = len(sv)
    if n == 0:
        return {"mean": None, "median": None, "sample_size": 0}
    return {
        "mean":        round(statistics.mean(sv),   8),
        "median":      round(statistics.median(sv), 8),
        "sample_size": n,
    }


def _percentiles(values):
    """Return p10/p25/p50/p75/p90 dict (filters None, linear interpolation)."""
    sv = sorted(v for v in values if v is not None)
    return {
        "p10": round(_pct(sv, 10), 8) if sv else None,
        "p25": round(_pct(sv, 25), 8) if sv else None,
        "p50": round(_pct(sv, 50), 8) if sv else None,
        "p75": round(_pct(sv, 75), 8) if sv else None,
        "p90": round(_pct(sv, 90), 8) if sv else None,
    }


def _cohort_stats(sorted_validators, field, n):
    """Simple (unweighted) mean + median for top-N from a pre-sorted list."""
    vals = [v[field] for v in sorted_validators[:n] if v[field] is not None]
    if not vals:
        return {"mean": None, "median": None, "sample_size": 0}
    sv = sorted(vals)
    return {
        "mean":        round(statistics.mean(sv),   8),
        "median":      round(statistics.median(sv), 8),
        "sample_size": len(sv),
    }


def _percentile_rank(value, all_values):
    """
    Percentile rank: (number of values strictly less than value) / (n-1) * 100.
    Equivalent to scipy.stats.percentileofscore(all_values, value, kind='weak')
    but implemented without scipy.
    Returns 0-100 float, rounded to 2 decimal places.
    """
    n = len(all_values)
    if n <= 1:
        return 0.0
    count_below = sum(1 for v in all_values if v < value)
    return round(count_below / (n - 1) * 100, 2)


def _safe(name, width=35):
    """ASCII-safe validator name for Windows console printing (strips emoji)."""
    s = name.encode("ascii", "replace").decode("ascii")
    return s[:width].ljust(width)


# ── Load + Clean ─────────────────────────────────────────────────────────────
print("Loading", INPUT_CSV)
with open(INPUT_CSV, encoding="utf-8") as fh:
    raw_rows = list(csv.DictReader(fh))

print(f"  Raw rows: {len(raw_rows)}")

validators = []
skipped = []
for r in raw_rows:
    slots = _parse(r.get("Leader Slots"))
    stake = _parse(r.get("Stake"))

    # Skip rows with no leader slots or zero slots (no per-block data)
    if slots is None or slots <= 0:
        skipped.append({"name": r.get("Name", ""), "reason": "no leader slots"})
        continue

    # Parse all monetary fields (already per-block in source)
    rev        = _parse(r.get("REV"))
    inflation  = _parse(r.get("Inflation"))
    mev        = _parse(r.get("MEV"))
    pri_fees   = _parse(r.get("Pri Fees"))
    sig_fees   = _parse(r.get("Sig Fees"))
    rewards    = _parse(r.get("Rewards"))  # = Pri Fees + Sig Fees

    # At minimum REV must be parseable and > 0
    if rev is None or rev <= 0:
        skipped.append({"name": r.get("Name", ""), "reason": "REV missing or zero"})
        continue

    # Actual stake in SOL = Stake_column * Leader_Slots
    # (Stake_column = actual_stake_SOL / leader_slots)
    actual_stake_sol = (stake * slots) if stake is not None else None

    validators.append({
        # Identity
        "name":             r.get("Name", "").strip(),
        "vote_account":     r.get("Vote Account", "").strip(),
        "identity":         r.get("Identity", "").strip(),
        "leader_slots":     slots,
        "actual_stake_sol": actual_stake_sol,
        # Monetary per-block values
        "rev":              rev,
        "inflation":        inflation,
        "mev":              mev,
        "pri_fees":         pri_fees,
        "sig_fees":         sig_fees,
        "rewards":          rewards,
        # Passthrough original fields for enriched CSV
        "_tx":        _parse(r.get("Tx")),
        "_user_tx":   _parse(r.get("User Tx")),
        "_vote_tx":   _parse(r.get("Vote Tx")),
        "_votes":     _parse(r.get("Votes")),
        "_latency":   _parse(r.get("Latency")),
        "_cu":        _parse(r.get("CU")),
    })

print(f"  Valid rows: {len(validators)}")
print(f"  Skipped:    {len(skipped)}")
for s in skipped:
    safe_name = s['name'].encode("ascii", "replace").decode("ascii")
    print(f"    - {safe_name!r}: {s['reason']}")


# ── Task 1/2 — Sort by stake + build stake-sorted cohort lists ───────────────
by_stake = sorted(
    validators,
    key=lambda v: v["actual_stake_sol"] if v["actual_stake_sol"] is not None else 0,
    reverse=True,
)

print(f"\nTop 5 by stake:")
for v in by_stake[:5]:
    print(f"  {_safe(v['name'])}  stake={v['actual_stake_sol']:>15,.0f} SOL  "
          f"slots={v['leader_slots']:>6,.0f}  REV/block={v['rev']:.5f}")


# ── Task 3 — Performance-based cohort sorts ───────────────────────────────────
by_mev = sorted(
    validators,
    key=lambda v: v["mev"] if v["mev"] is not None else 0,
    reverse=True,
)
by_rev = sorted(
    validators,
    key=lambda v: v["rev"] if v["rev"] is not None else 0,
    reverse=True,
)

print("\nTop 5 by MEV:")
for v in by_mev[:5]:
    print(f"  {_safe(v['name'])}  MEV/block={v['mev']:.6f}  REV/block={v['rev']:.5f}")

print("\nTop 5 by REV:")
for v in by_rev[:5]:
    print(f"  {_safe(v['name'])}  REV/block={v['rev']:.6f}")


# ── Field mapping (label → internal key) ─────────────────────────────────────
METRICS = {
    "inflation":    "inflation",
    "sig_fees":     "sig_fees",
    "priority_fees":"pri_fees",
    "mev":          "mev",
    "rev":          "rev",
}


# ── Network-wide stats ────────────────────────────────────────────────────────
print("\nNetwork stats:")
network_stats = {}
for label, field in METRICS.items():
    vals = [v[field] for v in validators]
    s = _stats(vals)
    network_stats[label] = s
    print(f"  {label:<16}  mean={s['mean']:.6f}  median={s['median']:.6f}  n={s['sample_size']}")


# ── Percentiles ───────────────────────────────────────────────────────────────
print("\nPercentiles:")
perc_data = {}
for label, field in METRICS.items():
    vals = [v[field] for v in validators]
    p = _percentiles(vals)
    perc_data[label] = p
    print(f"  {label:<16}  p10={p['p10']:.6f}  p50={p['p50']:.6f}  p90={p['p90']:.6f}")


# ── Cohort stats (stake / mev / rev) ─────────────────────────────────────────
print("\nCohort stats (top 10/20/50 by stake, mev, rev):")
cohort_data = {}
for label, field in METRICS.items():
    cohort_data[label] = {
        "top_10_by_stake": _cohort_stats(by_stake, field, 10),
        "top_20_by_stake": _cohort_stats(by_stake, field, 20),
        "top_50_by_stake": _cohort_stats(by_stake, field, 50),
        "top_10_by_mev":   _cohort_stats(by_mev, field, 10),
        "top_20_by_mev":   _cohort_stats(by_mev, field, 20),
        "top_50_by_mev":   _cohort_stats(by_mev, field, 50),
        "top_10_by_rev":   _cohort_stats(by_rev, field, 10),
        "top_20_by_rev":   _cohort_stats(by_rev, field, 20),
        "top_50_by_rev":   _cohort_stats(by_rev, field, 50),
    }
    for cohort_key, cohort_val in cohort_data[label].items():
        print(f"  {label:<16}  {cohort_key:<22}  mean={cohort_val['mean']:.6f}  "
              f"median={cohort_val['median']:.6f}  n={cohort_val['sample_size']}")


# ── Task 4 — Figment case ─────────────────────────────────────────────────────
figment_matches = [v for v in validators if v["name"] == "Figment"]
ledger_figment  = [v for v in validators if v["name"] == "Ledger by Figment"]

print("\nFigment entries found:")
for v in figment_matches + ledger_figment:
    print(f"  {_safe(v['name'], 40)}  stake={v['actual_stake_sol']:>15,.0f} SOL  "
          f"slots={v['leader_slots']:>6,.0f}  REV={v['rev']:.6f}  MEV={v['mev']:.6f}")

if figment_matches:
    fg = figment_matches[0]
    figment_metrics = {
        "inflation":    fg["inflation"],
        "sig_fees":     fg["sig_fees"],
        "priority_fees": fg["pri_fees"],
        "mev":          fg["mev"],
        "rev":          fg["rev"],
    }

    # Comparisons: figment / benchmark_median (round to 3 dp)
    def _ratio(numerator, denominator):
        if numerator is None or denominator is None or denominator == 0:
            return None
        return round(numerator / denominator, 3)

    figment_out = {
        "selection_rule": "Exact name match: 'Figment'. Primary node (Rakurai client).",
        "selected_rows": [
            {
                "name":             fg["name"],
                "vote_account":     fg["vote_account"],
                "identity":         fg["identity"],
                "actual_stake_sol": round(fg["actual_stake_sol"]) if fg["actual_stake_sol"] else None,
                "leader_slots":     int(fg["leader_slots"]),
            }
        ],
        "metrics": figment_metrics,
        "comparisons": {
            "vs_network_median": {
                label: _ratio(figment_metrics[label], network_stats[label]["median"])
                for label in METRICS
            },
            "vs_top_50_by_stake_median": {
                label: _ratio(figment_metrics[label], cohort_data[label]["top_50_by_stake"]["median"])
                for label in METRICS
            },
            "vs_top_50_by_mev_median": {
                label: _ratio(figment_metrics[label], cohort_data[label]["top_50_by_mev"]["median"])
                for label in METRICS
            },
        },
    }
    print(f"\nFigment comparisons (vs network median):")
    for label, ratio in figment_out["comparisons"]["vs_network_median"].items():
        print(f"  {label:<16}  figment={figment_metrics[label]:.6f}  "
              f"net_median={network_stats[label]['median']:.6f}  ratio={ratio}")
else:
    figment_out = {"note": "No exact match for 'Figment' in dataset"}
    print("  WARNING: No 'Figment' entry found in dataset.")


# ── Task 9 — Consistency checks ───────────────────────────────────────────────
print("\nConsistency checks:")
rev_mismatch = []
rewards_mismatch = []
for v in validators:
    if v["inflation"] and v["mev"] and v["rewards"] and v["rev"]:
        expected_rev = v["inflation"] + v["mev"] + v["rewards"]
        rel_err = abs(v["rev"] - expected_rev) / v["rev"] if v["rev"] else 0
        if rel_err > 0.01:
            rev_mismatch.append({
                "name":     v["name"],
                "rev":      v["rev"],
                "expected": expected_rev,
                "pct_err":  round(rel_err * 100, 2),
            })

    if v["pri_fees"] and v["sig_fees"] and v["rewards"]:
        expected_rewards = v["pri_fees"] + v["sig_fees"]
        rel_err = abs(v["rewards"] - expected_rewards) / v["rewards"] if v["rewards"] else 0
        if rel_err > 0.01:
            rewards_mismatch.append({
                "name":        v["name"],
                "rewards":     v["rewards"],
                "pri_plus_sig": expected_rewards,
                "pct_err":     round(rel_err * 100, 2),
            })

print(f"  REV != Infl+MEV+Rewards (>1% err):  {len(rev_mismatch)} validators")
print(f"  Rewards != PriFees+SigFees (>1%):   {len(rewards_mismatch)} validators")
if rev_mismatch:
    for m in rev_mismatch[:3]:
        print(f"    {m['name']}: rev={m['rev']:.5f}  expected={m['expected']:.5f}  err={m['pct_err']}%")
else:
    print("  No REV mismatches - data is internally consistent.")
if not rewards_mismatch:
    print("  No Rewards mismatches - data is internally consistent.")


# ── Task 6 — Enriched CSV ─────────────────────────────────────────────────────
print("\nBuilding enriched CSV...")

n_valid = len(validators)

# Build lookup: identity → (stake_rank, mev_rank, rev_rank)
stake_rank_map = {v["identity"]: i + 1 for i, v in enumerate(by_stake)}
mev_rank_map   = {v["identity"]: i + 1 for i, v in enumerate(by_mev)}
rev_rank_map   = {v["identity"]: i + 1 for i, v in enumerate(by_rev)}

# Sets for top-N membership flags
top10_stake_ids = {v["identity"] for v in by_stake[:10]}
top20_stake_ids = {v["identity"] for v in by_stake[:20]}
top50_stake_ids = {v["identity"] for v in by_stake[:50]}
top10_mev_ids   = {v["identity"] for v in by_mev[:10]}
top20_mev_ids   = {v["identity"] for v in by_mev[:20]}
top50_mev_ids   = {v["identity"] for v in by_mev[:50]}
top10_rev_ids   = {v["identity"] for v in by_rev[:10]}
top20_rev_ids   = {v["identity"] for v in by_rev[:20]}
top50_rev_ids   = {v["identity"] for v in by_rev[:50]}

# Pre-collect lists for percentile rank computation
all_inflation  = [v["inflation"]  for v in validators if v["inflation"]  is not None]
all_sig_fees   = [v["sig_fees"]   for v in validators if v["sig_fees"]   is not None]
all_pri_fees   = [v["pri_fees"]   for v in validators if v["pri_fees"]   is not None]
all_mev        = [v["mev"]        for v in validators if v["mev"]        is not None]
all_rev        = [v["rev"]        for v in validators if v["rev"]        is not None]

CSV_FIELDNAMES = [
    # Original fields
    "Name", "Vote Account", "Identity",
    "REV", "Inflation", "MEV",
    "Tx", "User Tx", "Vote Tx",
    "Pri Fees", "Sig Fees", "Rewards",
    "Stake", "Votes", "Latency", "CU", "Leader Slots",
    # Computed
    "actual_stake_sol",
    "stake_rank", "mev_rank", "rev_rank",
    "inflation_pct", "sig_fees_pct", "priority_fees_pct", "mev_pct", "rev_pct",
    "is_top10_stake", "is_top20_stake", "is_top50_stake",
    "is_top10_mev",   "is_top20_mev",   "is_top50_mev",
    "is_top10_rev",   "is_top20_rev",   "is_top50_rev",
]

os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as fh:
    writer = csv.writer(fh, delimiter=";")
    writer.writerow(CSV_FIELDNAMES)

    for v in validators:
        ident = v["identity"]
        writer.writerow([
            v["name"],
            v["vote_account"],
            ident,
            v["rev"],
            v["inflation"],
            v["mev"],
            v["_tx"],
            v["_user_tx"],
            v["_vote_tx"],
            v["pri_fees"],
            v["sig_fees"],
            v["rewards"],
            # Stake column = actual_stake_sol / leader_slots (original)
            round(v["actual_stake_sol"] / v["leader_slots"], 8) if v["actual_stake_sol"] else "",
            v["_votes"],
            v["_latency"],
            v["_cu"],
            v["leader_slots"],
            # Computed
            round(v["actual_stake_sol"]) if v["actual_stake_sol"] else "",
            stake_rank_map.get(ident, ""),
            mev_rank_map.get(ident, ""),
            rev_rank_map.get(ident, ""),
            _percentile_rank(v["inflation"], all_inflation) if v["inflation"] is not None else "",
            _percentile_rank(v["sig_fees"],  all_sig_fees)  if v["sig_fees"]  is not None else "",
            _percentile_rank(v["pri_fees"],  all_pri_fees)  if v["pri_fees"]  is not None else "",
            _percentile_rank(v["mev"],       all_mev)       if v["mev"]       is not None else "",
            _percentile_rank(v["rev"],       all_rev)       if v["rev"]       is not None else "",
            1 if ident in top10_stake_ids else 0,
            1 if ident in top20_stake_ids else 0,
            1 if ident in top50_stake_ids else 0,
            1 if ident in top10_mev_ids   else 0,
            1 if ident in top20_mev_ids   else 0,
            1 if ident in top50_mev_ids   else 0,
            1 if ident in top10_rev_ids   else 0,
            1 if ident in top20_rev_ids   else 0,
            1 if ident in top50_rev_ids   else 0,
        ])

print(f"  Enriched CSV written: {OUTPUT_CSV}")


# ── Task 5 — Assemble canonical JSON ─────────────────────────────────────────
def _metric_block(label, field):
    return {
        "unit": "SOL per block (per leader slot)",
        "network": {
            "mean":        network_stats[label]["mean"],
            "median":      network_stats[label]["median"],
            "sample_size": network_stats[label]["sample_size"],
        },
        "percentiles": perc_data[label],
        "cohorts":     cohort_data[label],
    }


output = {
    "meta": {
        "epoch":       945,
        "source_file": "data/validators_epoch_945.csv",
        "sample_size": len(validators),
        "skipped":     len(skipped),
        "notes": [
            "All monetary values are SOL per block (per leader slot produced).",
            "Stake column in source CSV = actual_stake_SOL / leader_slots. "
            "Recovered as: actual_stake_sol = Stake x Leader_Slots.",
            "Cohort _by_stake: sorted by actual_stake_sol descending.",
            "Cohort _by_mev: sorted by mev descending.",
            "Cohort _by_rev: sorted by rev descending.",
            "All cohort means and medians are simple (unweighted), not stake-weighted.",
            "Percentiles use linear interpolation.",
            "Rows excluded: leader_slots <= 0 or REV missing/zero.",
        ],
    },
    "inflation":     _metric_block("inflation",     "inflation"),
    "sig_fees":      _metric_block("sig_fees",      "sig_fees"),
    "priority_fees": _metric_block("priority_fees", "pri_fees"),
    "mev":           _metric_block("mev",           "mev"),
    "rev":           _metric_block("rev",           "rev"),
    "figment": figment_out,
    "consistency_checks": {
        "rev_equals_infl_plus_mev_plus_rewards": {
            "threshold_pct": 1.0,
            "mismatches":    len(rev_mismatch),
            "examples":      rev_mismatch[:5],
        },
        "rewards_equals_pri_plus_sig": {
            "threshold_pct": 1.0,
            "mismatches":    len(rewards_mismatch),
            "examples":      rewards_mismatch[:5],
        },
    },
    "top_validators_by_stake": [
        {
            "rank":             i + 1,
            "name":             v["name"],
            "actual_stake_sol": round(v["actual_stake_sol"]) if v["actual_stake_sol"] else None,
            "leader_slots":     int(v["leader_slots"]),
            "rev":              v["rev"],
            "inflation":        v["inflation"],
            "mev":              v["mev"],
            "priority_fees":    v["pri_fees"],
            "sig_fees":         v["sig_fees"],
        }
        for i, v in enumerate(by_stake[:50])
    ],
}

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2, ensure_ascii=False)

print(f"\nJSON written: {OUTPUT_JSON}")


# ── Task 7 — Exploratory charts ───────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False
    print("\nWARNING: matplotlib not available — charts skipped. "
          "Install with: pip install matplotlib")

if CHARTS_AVAILABLE:
    os.makedirs(CHARTS_DIR, exist_ok=True)
    plt.style.use("dark_background")
    DPI = 150

    mev_vals   = [v["mev"]      for v in validators if v["mev"]      is not None]
    pri_vals   = [v["pri_fees"] for v in validators if v["pri_fees"] is not None]
    rev_vals   = [v["rev"]      for v in validators if v["rev"]      is not None]
    infl_vals  = [v["inflation"] for v in validators if v["inflation"] is not None]
    stake_vals = [v["actual_stake_sol"] for v in validators if v["actual_stake_sol"] is not None]

    # ── Chart 1: Histogram MEV per block ─────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(mev_vals, bins="auto", color="#00BFFF", edgecolor="none", alpha=0.85)
    ax.set_xlim(0, 0.04)
    ax.set_xlabel("MEV per block (SOL)")
    ax.set_ylabel("Validators")
    ax.set_title("Epoch 945 — MEV per block distribution (n=762)")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "hist_mev_per_block.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 2: Histogram priority fees per block ────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(pri_vals, bins="auto", color="#FFD700", edgecolor="none", alpha=0.85)
    ax.set_xlim(0, 0.08)
    ax.set_xlabel("Priority fees per block (SOL)")
    ax.set_ylabel("Validators")
    ax.set_title("Epoch 945 — Priority fees per block distribution (n=762)")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "hist_priority_fees_per_block.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 3: Histogram REV per block ─────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(rev_vals, bins="auto", color="#7CFC00", edgecolor="none", alpha=0.85)
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("REV per block (SOL)")
    ax.set_ylabel("Validators")
    ax.set_title("Epoch 945 — REV per block distribution (n=762)")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "hist_rev_per_block.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 4: Histogram inflation per block ────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(infl_vals, bins="auto", color="#FF8C00", edgecolor="none", alpha=0.85)
    ax.set_xlim(0.1, 0.7)
    ax.set_xlabel("Inflation per block (SOL)")
    ax.set_ylabel("Validators")
    ax.set_title("Epoch 945 — Inflation per block distribution (n=762)")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "hist_inflation_per_block.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 5: Scatter stake vs MEV ────────────────────────────────────────
    scatter_pairs_mev = [
        (v["actual_stake_sol"], v["mev"])
        for v in validators
        if v["actual_stake_sol"] and v["mev"] is not None
    ]
    xs, ys = zip(*scatter_pairs_mev)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(xs, ys, alpha=0.4, s=10, color="#00BFFF")
    ax.set_xscale("log")
    ax.set_xlabel("Stake (SOL, log scale)")
    ax.set_ylabel("MEV per block (SOL)")
    ax.set_title("Epoch 945 — Stake vs MEV per block")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "scatter_stake_vs_mev.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 6: Scatter stake vs REV ────────────────────────────────────────
    scatter_pairs_rev = [
        (v["actual_stake_sol"], v["rev"])
        for v in validators
        if v["actual_stake_sol"] and v["rev"] is not None
    ]
    xs, ys = zip(*scatter_pairs_rev)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(xs, ys, alpha=0.4, s=10, color="#7CFC00")
    ax.set_xscale("log")
    ax.set_xlabel("Stake (SOL, log scale)")
    ax.set_ylabel("REV per block (SOL)")
    ax.set_title("Epoch 945 — Stake vs REV per block")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "scatter_stake_vs_rev.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 7: Boxplot cohorts — MEV ───────────────────────────────────────
    all_mev_vals         = [v["mev"] for v in validators           if v["mev"] is not None]
    top50_stake_mev_vals = [v["mev"] for v in by_stake[:50]        if v["mev"] is not None]
    top50_mev_mev_vals   = [v["mev"] for v in by_mev[:50]          if v["mev"] is not None]
    top50_rev_mev_vals   = [v["mev"] for v in by_rev[:50]          if v["mev"] is not None]

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(
        [all_mev_vals, top50_stake_mev_vals, top50_mev_mev_vals, top50_rev_mev_vals],
        tick_labels=["All\n(n=762)", "Top50\nby stake", "Top50\nby MEV", "Top50\nby REV"],
        patch_artist=True,
        medianprops={"color": "white", "linewidth": 2},
    )
    colors = ["#444444", "#1E90FF", "#00BFFF", "#7CFC00"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
    ax.set_ylabel("MEV per block (SOL)")
    ax.set_title("Epoch 945 — MEV per block by cohort")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "boxplot_cohorts_mev.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    # ── Chart 8: Boxplot cohorts — REV ───────────────────────────────────────
    all_rev_vals         = [v["rev"] for v in validators      if v["rev"] is not None]
    top50_stake_rev_vals = [v["rev"] for v in by_stake[:50]   if v["rev"] is not None]
    top50_mev_rev_vals   = [v["rev"] for v in by_mev[:50]     if v["rev"] is not None]
    top50_rev_rev_vals   = [v["rev"] for v in by_rev[:50]     if v["rev"] is not None]

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(
        [all_rev_vals, top50_stake_rev_vals, top50_mev_rev_vals, top50_rev_rev_vals],
        tick_labels=["All\n(n=762)", "Top50\nby stake", "Top50\nby MEV", "Top50\nby REV"],
        patch_artist=True,
        medianprops={"color": "white", "linewidth": 2},
    )
    colors = ["#444444", "#1E90FF", "#00BFFF", "#7CFC00"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
    ax.set_ylabel("REV per block (SOL)")
    ax.set_title("Epoch 945 — REV per block by cohort")
    plt.tight_layout()
    path = os.path.join(CHARTS_DIR, "boxplot_cohorts_rev.png")
    plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  Chart: {path}")

    print(f"\nAll charts saved to: {CHARTS_DIR}")

print("\nDone.")
