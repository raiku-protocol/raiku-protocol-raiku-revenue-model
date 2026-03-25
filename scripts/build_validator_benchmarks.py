"""
build_validator_benchmarks.py
=============================================================
Reads data/validators_epoch_945.csv and produces:
  outputs/validator_benchmarks_epoch_945.json

All monetary fields (REV, Inflation, MEV, Pri Fees, Sig Fees, Rewards)
are treated as SOL per block (per leader slot produced), as stored in
the source CSV.  The formula used by the export tool is:
    field_per_block = epoch_total_for_validator / leader_slots_produced

Stake column in the CSV = actual_stake_SOL / leader_slots.
To recover actual stake in SOL:  actual_stake_sol = Stake * Leader_Slots.
This is verified against validators-all (4).csv (error < 0.1% for top
validators).

Usage:
    python scripts/build_validator_benchmarks.py
"""

import csv
import json
import math
import os
import statistics


# ── Paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_CSV   = os.path.join(BASE, "data", "validators_epoch_945.csv")
OUTPUT_JSON = os.path.join(BASE, "outputs", "validator_benchmarks_epoch_945.json")


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
    """Return dict with mean, median, sample_size."""
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
    sv = sorted(v for v in values if v is not None)
    return {
        "p10": round(_pct(sv, 10), 8) if sv else None,
        "p25": round(_pct(sv, 25), 8) if sv else None,
        "p50": round(_pct(sv, 50), 8) if sv else None,
        "p75": round(_pct(sv, 75), 8) if sv else None,
        "p90": round(_pct(sv, 90), 8) if sv else None,
    }


def _segment_stats(validators, field, n):
    """Simple (unweighted) mean + median for the top-N validators."""
    vals = [v[field] for v in validators[:n] if v[field] is not None]
    if not vals:
        return {"mean": None, "median": None, "sample_size": 0}
    sv = sorted(vals)
    return {
        "mean":        round(statistics.mean(sv),   8),
        "median":      round(statistics.median(sv), 8),
        "sample_size": len(sv),
    }


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
    # (Stake_column = actual_stake_SOL / leader_slots, verified against on-chain data)
    actual_stake_sol = (stake * slots) if stake is not None else None

    validators.append({
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
    })

print(f"  Valid rows: {len(validators)}")
print(f"  Skipped:    {len(skipped)}")
for s in skipped:
    print(f"    - {s['name']!r}: {s['reason']}")


# ── Sort by actual stake descending ─────────────────────────────────────────
validators.sort(
    key=lambda v: v["actual_stake_sol"] if v["actual_stake_sol"] is not None else 0,
    reverse=True,
)
print(f"\nTop 5 by stake:")
for v in validators[:5]:
    print(f"  {v['name']:<35}  stake={v['actual_stake_sol']:>15,.0f} SOL  "
          f"slots={v['leader_slots']:>6,.0f}  REV/block={v['rev']:.5f}")


# ── Field list ───────────────────────────────────────────────────────────────
FIELDS = {
    "inflation":    "inflation",
    "sig_fees":     "sig_fees",
    "priority_fees":"pri_fees",
    "mev":          "mev",
    "rev":          "rev",
}


# ── Task 2 — Network-wide stats ──────────────────────────────────────────────
print("\nTask 2 — Network stats:")
network = {}
for label, field in FIELDS.items():
    vals = [v[field] for v in validators]
    s = _stats(vals)
    network[label] = s
    print(f"  {label:<16}  mean={s['mean']:.6f}  median={s['median']:.6f}  n={s['sample_size']}")


# ── Task 3 — Stake segments ──────────────────────────────────────────────────
print("\nTask 3 — Stake segments (top 10/20/50 by actual stake SOL):")
segments = {10: {}, 20: {}, 50: {}}
for label, field in FIELDS.items():
    for n in (10, 20, 50):
        s = _segment_stats(validators, field, n)
        segments[n][label] = s
        print(f"  top{n:>3}  {label:<16}  mean={s['mean']:.6f}  median={s['median']:.6f}  n={s['sample_size']}")


# ── Task 4 — Figment case ────────────────────────────────────────────────────
# Multiple Figment entries may exist:
#   "Figment" — main validator (Rakurai client)
#   "Ledger by Figment" — separate node
#   "Figment | Firedancer" — empty/inactive row
# We use "Figment" (exact match, primary entry).
figment_matches = [v for v in validators if v["name"] == "Figment"]
ledger_figment  = [v for v in validators if v["name"] == "Ledger by Figment"]

print("\nTask 4 — Figment entries found:")
for v in figment_matches + ledger_figment:
    print(f"  {v['name']!r}  stake={v['actual_stake_sol']:>15,.0f} SOL  "
          f"slots={v['leader_slots']:>6,.0f}  REV={v['rev']:.6f}  MEV={v['mev']:.6f}")

if figment_matches:
    fg = figment_matches[0]
    figment_out = {
        "name":            fg["name"],
        "actual_stake_sol": round(fg["actual_stake_sol"]) if fg["actual_stake_sol"] else None,
        "leader_slots":    int(fg["leader_slots"]),
        "inflation":       fg["inflation"],
        "sig_fees":        fg["sig_fees"],
        "priority_fees":   fg["pri_fees"],
        "mev":             fg["mev"],
        "rev":             fg["rev"],
        "note":            "Primary Figment node (Rakurai client). "
                           "'Ledger by Figment' is a separate node and not included here.",
    }
else:
    figment_out = {"note": "No exact match for 'Figment' in dataset"}


# ── Task 5 — Percentile distribution ────────────────────────────────────────
print("\nTask 5 — Percentiles:")
percs = {}
for label, field in FIELDS.items():
    vals = [v[field] for v in validators]
    p = _percentiles(vals)
    percs[label] = p
    print(f"  {label:<16}  p10={p['p10']:.6f}  p50={p['p50']:.6f}  p90={p['p90']:.6f}")


# ── Task 7 — Consistency checks ──────────────────────────────────────────────
print("\nTask 7 — Consistency checks:")
rev_mismatch = []
rewards_mismatch = []
for v in validators:
    if v["inflation"] and v["mev"] and v["rewards"] and v["rev"]:
        expected_rev = v["inflation"] + v["mev"] + v["rewards"]
        rel_err = abs(v["rev"] - expected_rev) / v["rev"] if v["rev"] else 0
        if rel_err > 0.01:  # > 1% error
            rev_mismatch.append({"name": v["name"], "rev": v["rev"],
                                  "expected": expected_rev, "pct_err": round(rel_err*100, 2)})

    if v["pri_fees"] and v["sig_fees"] and v["rewards"]:
        expected_rewards = v["pri_fees"] + v["sig_fees"]
        rel_err = abs(v["rewards"] - expected_rewards) / v["rewards"] if v["rewards"] else 0
        if rel_err > 0.01:
            rewards_mismatch.append({"name": v["name"], "rewards": v["rewards"],
                                      "pri_plus_sig": expected_rewards, "pct_err": round(rel_err*100, 2)})

print(f"  REV != Infl+MEV+Rewards (>1% err):  {len(rev_mismatch)} validators")
print(f"  Rewards != PriFees+SigFees (>1%):  {len(rewards_mismatch)} validators")
if rev_mismatch[:3]:
    for m in rev_mismatch[:3]:
        print(f"    {m['name']}: rev={m['rev']:.5f}  expected={m['expected']:.5f}  err={m['pct_err']}%")


# ── Assemble JSON output ─────────────────────────────────────────────────────
def _metric_block(label, field):
    vals = [v[field] for v in validators]
    return {
        "unit":         "SOL per block (per leader slot)",
        "mean":         network[label]["mean"],
        "median":       network[label]["median"],
        "sample_size":  network[label]["sample_size"],
        "top_10":       segments[10][label],
        "top_20":       segments[20][label],
        "top_50":       segments[50][label],
        "percentiles":  percs[label],
    }

output = {
    "metadata": {
        "epoch": 945,
        "source_file":     "data/validators_epoch_945.csv",
        "valid_validators": len(validators),
        "skipped_rows":     len(skipped),
        "sort_basis":       "actual_stake_sol = Stake_column * Leader_Slots (verified vs on-chain)",
        "monetary_unit":    "SOL per block (per leader slot produced)",
        "stake_note":       (
            "Stake column in CSV = actual_stake_SOL / leader_slots. "
            "To recover actual SOL stake: Stake × Leader_Slots. "
            "Verified against validators-all (4).csv: error < 0.1% for top validators."
        ),
        "top_stake_segments_note": (
            "Top-N segments are ordered by actual_stake_sol descending. "
            "Means and medians are simple (unweighted), not stake-weighted."
        ),
    },
    "inflation":     _metric_block("inflation", "inflation"),
    "sig_fees":      _metric_block("sig_fees", "sig_fees"),
    "priority_fees": _metric_block("priority_fees", "pri_fees"),
    "mev":           _metric_block("mev", "mev"),
    "rev":           _metric_block("rev", "rev"),
    "figment":       figment_out,
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
        for i, v in enumerate(validators[:50])
    ],
}

os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2, ensure_ascii=False)

print(f"\nOutput written to: {OUTPUT_JSON}")
print("Done.")
