"""
build_time_benchmarks.py
=============================================================
Builds outputs/validator_time_benchmarks_12m.json by fetching
per-validator data from the Trillium /validator_rewards/{epoch}
endpoint for epochs 750-945 (12-month window).

For each epoch:
  - Fetch all validators (or load from per-epoch JSON cache)
  - Compute per-block statistics: network mean/median, top-50 cohorts
  - Tag with regime from solana_epoch_database.csv volatility_tag

Then aggregate over all epochs and elevated+extreme epochs.

Per-epoch summaries are cached at:
  data/raw/validator_epoch_summaries/epoch_{N}.json

Final output:
  outputs/validator_time_benchmarks_12m.json

Usage:
    python scripts/build_time_benchmarks.py              # epochs 750-945
    python scripts/build_time_benchmarks.py --start 800 # override start
    python scripts/build_time_benchmarks.py --end 900   # override end
    python scripts/build_time_benchmarks.py --no-cache  # skip cache, re-fetch all
    python scripts/build_time_benchmarks.py --test-api  # probe epoch 945, print keys, exit

Field mapping from Trillium /validator_rewards/{epoch}
------------------------------------------------------
Verified against epoch 945 response with --test-api (2026-03-25).
The API returns per-block AVERAGES directly — no normalization needed.

  leader_slots                   → blocks produced (int)
  activated_stake                → stake in SOL (float, NOT lamports)
  avg_signature_fees_per_block   → base fees per block (SOL)
  avg_priority_fees_per_block    → priority fees per block (SOL)
  avg_mev_per_block              → MEV/Jito tips per block (SOL)
  avg_rewards_per_block          → sig+pri+mev per block (SOL, from API)

  total_reward is recomputed as sig+pri+mev for consistency.
  total_priority_fees is None for many validators — not used.
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE       = Path(__file__).parent.parent
CACHE_DIR  = BASE / "data" / "raw" / "validator_epoch_summaries"
OUTPUTS    = BASE / "outputs"
DB_CSV     = BASE / "data" / "processed" / "solana_epoch_database.csv"
BENCH_945  = OUTPUTS / "validator_benchmarks_epoch_945.json"
OUT_JSON   = OUTPUTS / "validator_time_benchmarks_12m.json"

# ── Constants ──────────────────────────────────────────────────────────────────
TRILLIUM_BASE_URL = "https://api.trillium.so"
DEFAULT_START     = 750
DEFAULT_END       = 945
# 24m lower bound: first epoch where Trillium /validator_rewards/ data is available
# (epoch 552 = first valid Trillium epoch, per CLAUDE.md)
EPOCH_START_24M   = 552
HTTP_HEADERS      = {
    "Accept":     "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# Retry settings
MAX_RETRIES   = 3
RETRY_DELAY_S = 5.0
FETCH_DELAY_S = 0.25   # polite delay between epoch requests


# ── Stat helpers ───────────────────────────────────────────────────────────────

def _pct(sv, p):
    """p-th percentile (0-100) of a *sorted* list, linear interpolation."""
    n = len(sv)
    if n == 0:
        return None
    idx = (p / 100) * (n - 1)
    lo  = int(idx)
    hi  = lo + 1
    if hi >= n:
        return sv[lo]
    return sv[lo] * (1 - (idx - lo)) + sv[hi] * (idx - lo)


def _median(values):
    """Median of a list (filters None)."""
    sv = sorted(v for v in values if v is not None)
    if not sv:
        return None
    return statistics.median(sv)


def _mean(values):
    sv = [v for v in values if v is not None]
    if not sv:
        return None
    return statistics.mean(sv)


def _cohort_median(sorted_validators, field, n):
    """Median of `field` for the first N validators in a pre-sorted list."""
    vals = [v[field] for v in sorted_validators[:n] if v[field] is not None]
    if not vals:
        return None
    return statistics.median(sorted(vals))


def _cohort_mean(sorted_validators, field, n):
    """Mean of `field` for the first N validators in a pre-sorted list."""
    vals = [v[field] for v in sorted_validators[:n] if v[field] is not None]
    if not vals:
        return None
    return statistics.mean(vals)


def _round8(x):
    if x is None:
        return None
    return round(x, 8)


# ── Per-epoch summary builder ─────────────────────────────────────────────────

def _parse_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_validator_row(obj):
    """
    Parse one validator object from the Trillium /validator_rewards/{epoch}
    response.

    Returns a dict with per-block values, or None if the row should be
    skipped (zero or missing leader_slots).

    Confirmed field names (epoch 945, verified with --test-api, 2026-03):
      leader_slots                 → blocks produced (int)
      activated_stake              → stake in SOL (float)  [NOT lamports]
      avg_signature_fees_per_block → base fees, already per-block (SOL)
      avg_priority_fees_per_block  → priority fees, already per-block (SOL)
      avg_mev_per_block            → MEV/Jito tips, already per-block (SOL)
      avg_rewards_per_block        → sig+pri+mev combined, already per-block (SOL)

    The API returns per-block averages directly — no division needed.
    Note: total_priority_fees is None for many validators; use avg_* fields.
    """
    def _get(*keys):
        for k in keys:
            if k in obj and obj[k] is not None:
                v = _parse_float(obj[k])
                if v is not None:
                    return v
        return None

    # Leader slots (blocks produced this epoch)
    slots = _get("leader_slots", "blocks_produced", "leader_slots_produced")
    if slots is None or slots <= 0:
        return None

    # Stake in SOL (already in SOL, not lamports)
    stake = _get("activated_stake", "active_stake", "stake", "delegated_stake")

    # Per-block revenue fields (already normalized by Trillium)
    sig_per_block = _get("avg_signature_fees_per_block",
                         "avg_sig_fees_per_block",
                         "avg_base_fees_per_block")
    pri_per_block = _get("avg_priority_fees_per_block",
                         "avg_priority_fee_per_block")
    mev_per_block = _get("avg_mev_per_block",
                         "avg_jito_tips_per_block",
                         "avg_mev_tips_per_block")
    # avg_rewards_per_block = sig + pri + mev (from Trillium)
    rewards_per_block = _get("avg_rewards_per_block",
                             "avg_reward_per_block")

    return {
        "leader_slots":     slots,
        "actual_stake_sol": stake,
        # per-block values (SOL)
        "sig_per_block":    sig_per_block,
        "pri_per_block":    pri_per_block,
        "mev_per_block":    mev_per_block,
        "rewards_per_block": rewards_per_block,  # sig+pri+mev from API
    }


def _build_epoch_summary(epoch, validators, regime):
    """
    Given a list of parsed validator dicts (from _parse_validator_row),
    compute the per-epoch summary dict cached to disk.
    """
    # Filter to validators with at least the three core per-block fields
    valid = [v for v in validators if v is not None
             and v["sig_per_block"]  is not None
             and v["pri_per_block"]  is not None
             and v["mev_per_block"]  is not None]

    n = len(valid)

    # Compute total_reward = sig + pri + mev (recomputed from components
    # for consistency, even if API also provides avg_rewards_per_block)
    for v in valid:
        v["total_reward_per_block"] = (
            v["sig_per_block"]
            + v["pri_per_block"]
            + v["mev_per_block"]
        )

    # Sort cohorts independently per epoch (per spec)
    by_stake = sorted(valid, key=lambda v: v["actual_stake_sol"] or 0, reverse=True)
    by_mev   = sorted(valid, key=lambda v: v["mev_per_block"]    or 0, reverse=True)

    def _metric_summary(field):
        vals = [v[field] for v in valid]
        net_mean   = _round8(_mean(vals))
        net_median = _round8(_median(vals))
        t50s_med   = _round8(_cohort_median(by_stake, field, 50))
        t50s_mean  = _round8(_cohort_mean  (by_stake, field, 50))
        t50m_med   = _round8(_cohort_median(by_mev,   field, 50))
        t50m_mean  = _round8(_cohort_mean  (by_mev,   field, 50))
        return {
            "network":         {"mean": net_mean, "median": net_median},
            "top_50_by_stake": {"mean": t50s_mean, "median": t50s_med},
            "top_50_by_mev":   {"mean": t50m_mean, "median": t50m_med},
        }

    return {
        "epoch":        epoch,
        "regime":       regime,
        "n_validators": n,
        "metrics": {
            "base_fees":     _metric_summary("sig_per_block"),
            "priority_fees": _metric_summary("pri_per_block"),
            "mev":           _metric_summary("mev_per_block"),
            "total_reward":  _metric_summary("total_reward_per_block"),
        },
    }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _fetch_url(url, timeout=30):
    """
    Fetch URL with retries.  Returns (response_bytes, None) on success,
    (None, error_string) on failure.
    """
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, f"HTTP 404"
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                return None, f"HTTP {e.code}"
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                return None, f"URLError: {e.reason}"
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                return None, f"Error: {e}"
    return None, "max retries exceeded"


def fetch_validator_rewards(epoch):
    """
    Fetch /validator_rewards/{epoch} from Trillium.
    Returns (list_of_dicts, None) on success, (None, error_string) on failure.
    """
    url = f"{TRILLIUM_BASE_URL}/validator_rewards/{epoch}"
    raw, err = _fetch_url(url, timeout=60)
    if err:
        return None, err
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    if not isinstance(data, list):
        return None, f"Expected list, got {type(data).__name__}"
    return data, None


# ── Regime loader ─────────────────────────────────────────────────────────────

def load_epoch_regimes():
    """
    Read solana_epoch_database.csv and return dict: epoch_int → regime_str.
    For epochs not in the DB, we will tag them as "normal" with a warning.
    """
    regimes = {}
    if not DB_CSV.exists():
        print(f"  WARNING: DB not found at {DB_CSV}. All epochs will be tagged 'normal'.")
        return regimes
    import csv
    with open(DB_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            ep  = row.get("epoch", "").strip()
            tag = row.get("volatility_tag", "").strip()
            if ep and tag:
                try:
                    regimes[int(ep)] = tag
                except ValueError:
                    pass
    return regimes


# ── Cache helpers ─────────────────────────────────────────────────────────────

def cache_path(epoch):
    return CACHE_DIR / f"epoch_{epoch}.json"


def load_cached_summary(epoch):
    p = cache_path(epoch)
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save_cached_summary(summary):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path(summary["epoch"])
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)


# ── latest_epoch block (re-use epoch 945 benchmark) ───────────────────────────

def build_latest_epoch_block(regimes):
    """
    Build the latest_epoch JSON block from the cached epoch 945 benchmark.
    Falls back to computing from the epoch 945 summary cache.
    """
    if BENCH_945.exists():
        with open(BENCH_945, encoding="utf-8") as fh:
            b945 = json.load(fh)

        regime = regimes.get(945, "normal")

        def _extract_metric(key_in_bench, alt_key=None):
            """Extract network + top_50 stats from benchmark JSON."""
            src = b945.get(key_in_bench) or (b945.get(alt_key) if alt_key else None)
            if src is None:
                return {
                    "network":         {"mean": None, "median": None},
                    "top_50_by_stake": {"median": None},
                    "top_50_by_mev":   {"median": None},
                }
            net      = src.get("network", {})
            cohorts  = src.get("cohorts", {})
            t50s     = cohorts.get("top_50_by_stake") or {}
            t50m     = cohorts.get("top_50_by_mev")   or {}
            return {
                "network":         {"mean": net.get("mean"), "median": net.get("median")},
                "top_50_by_stake": {"mean": t50s.get("mean"), "median": t50s.get("median")},
                "top_50_by_mev":   {"mean": t50m.get("mean"), "median": t50m.get("median")},
            }

        bf = _extract_metric("sig_fees")
        pf = _extract_metric("priority_fees")
        mv = _extract_metric("mev")

        # total_reward = base + pri + mev (per block)
        def _add_medians(a, b, c):
            vals = [x for x in [a, b, c] if x is not None]
            return sum(vals) if vals else None

        def _add_means(a, b, c):
            vals = [x for x in [a, b, c] if x is not None]
            return round(sum(vals), 8) if vals else None

        total_reward = {
            "network": {
                "mean":   _add_means(
                    bf["network"]["mean"],
                    pf["network"]["mean"],
                    mv["network"]["mean"],
                ),
                "median": _round8(_add_medians(
                    bf["network"]["median"],
                    pf["network"]["median"],
                    mv["network"]["median"],
                )),
            },
            "top_50_by_stake": {
                "median": _round8(_add_medians(
                    bf["top_50_by_stake"]["median"],
                    pf["top_50_by_stake"]["median"],
                    mv["top_50_by_stake"]["median"],
                )),
            },
            "top_50_by_mev": {
                "median": _round8(_add_medians(
                    bf["top_50_by_mev"]["median"],
                    pf["top_50_by_mev"]["median"],
                    mv["top_50_by_mev"]["median"],
                )),
            },
        }

        return {
            "epoch":   945,
            "regime":  regime,
            "metrics": {
                "base_fees":     bf,
                "priority_fees": pf,
                "mev":           mv,
                "total_reward":  total_reward,
            },
        }
    else:
        # Fallback: compute from epoch 945 summary cache if present
        s = load_cached_summary(945)
        if s:
            return {
                "epoch":   945,
                "regime":  s.get("regime", "normal"),
                "metrics": s["metrics"],
            }
        return None


# ── Time aggregation ───────────────────────────────────────────────────────────

def _time_agg_metric(summaries, metric_key, cohort_key):
    """
    Collect per-epoch medians (and means where available) from
    summaries[i].metrics[metric_key][cohort_key] and return aggregated stats.

    Returns:
      mean_of_epoch_medians  — mean   of per-epoch cohort medians
      median_of_epoch_medians — median of per-epoch cohort medians  (canonical)
      p25 / p75               — percentiles of per-epoch cohort medians
      mean_of_epoch_means     — mean of per-epoch cohort means (proxy for pooled mean)
    """
    medians, means = [], []
    for s in summaries:
        m = s.get("metrics", {}).get(metric_key, {})
        c = m.get(cohort_key, {})
        v_med = c.get("median")
        v_mea = c.get("mean")
        if v_med is not None:
            medians.append(v_med)
        if v_mea is not None:
            means.append(v_mea)

    if not medians:
        return {
            "mean_of_epoch_medians":  None,
            "median_of_epoch_medians": None,
            "p25": None, "p75": None,
            "mean_of_epoch_means": None,
        }

    sv = sorted(medians)
    return {
        "mean_of_epoch_medians":   _round8(_mean(sv)),
        "median_of_epoch_medians": _round8(_median(sv)),
        "p25":                     _round8(_pct(sv, 25)),
        "p75":                     _round8(_pct(sv, 75)),
        "mean_of_epoch_means":     _round8(_mean(means)) if means else None,
    }


def _time_agg_network_mean(summaries, metric_key):
    """Collect per-epoch network means and aggregate."""
    vals = []
    for s in summaries:
        m = s.get("metrics", {}).get(metric_key, {})
        v = m.get("network", {}).get("mean")
        if v is not None:
            vals.append(v)
    if not vals:
        return {"mean": None, "median": None, "p25": None, "p75": None}
    sv = sorted(vals)
    return {
        "mean":   _round8(_mean(sv)),
        "median": _round8(_median(sv)),
        "p25":    _round8(_pct(sv, 25)),
        "p75":    _round8(_pct(sv, 75)),
    }


def build_time_agg_block(summaries):
    """
    Build the last_12m_all / last_12m_elevated_extreme metric blocks
    from a list of per-epoch summaries.
    """
    if not summaries:
        return {"metrics": {}}

    metrics_out = {}
    for metric_key in ("base_fees", "priority_fees", "mev", "total_reward"):
        net_agg   = _time_agg_metric(summaries, metric_key, "network")
        s50_agg   = _time_agg_metric(summaries, metric_key, "top_50_by_stake")
        m50_agg   = _time_agg_metric(summaries, metric_key, "top_50_by_mev")
        net_mean_agg = _time_agg_network_mean(summaries, metric_key)

        metrics_out[metric_key] = {
            "network": {
                "mean":   net_mean_agg["mean"],
                "median": net_agg["median_of_epoch_medians"],
                "p25":    net_agg["p25"],
                "p75":    net_agg["p75"],
            },
            "top_50_by_stake": {
                # canonical: median of epoch-level cohort medians
                "median":              s50_agg["median_of_epoch_medians"],
                # secondary: mean of epoch-level cohort medians
                "mean_of_medians":     s50_agg["mean_of_epoch_medians"],
                # proxy pooled mean: mean of per-epoch cohort means (equal-weight epochs)
                "mean_of_means":       s50_agg["mean_of_epoch_means"],
            },
            "top_50_by_mev": {
                # canonical: median of epoch-level cohort medians
                "median":              m50_agg["median_of_epoch_medians"],
                # secondary: mean of epoch-level cohort medians
                "mean_of_medians":     m50_agg["mean_of_epoch_medians"],
                # proxy pooled mean: mean of per-epoch cohort means (equal-weight epochs)
                "mean_of_means":       m50_agg["mean_of_epoch_means"],
            },
        }
    return {"metrics": metrics_out}


# ── --test-api handler ────────────────────────────────────────────────────────

def run_test_api():
    """Fetch epoch 945, print first validator's keys + values, then exit."""
    print("=== --test-api: fetching epoch 945 /validator_rewards/ ===\n")
    data, err = fetch_validator_rewards(945)
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)
    if not data:
        print("ERROR: empty response")
        sys.exit(1)
    print(f"Response type: {type(data).__name__}")
    print(f"Number of validators: {len(data)}")
    print(f"\nFirst validator — all keys and values:\n")
    first = data[0]
    for k, v in sorted(first.items()):
        print(f"  {k!r:40s}: {v!r}")
    print(f"\nTotal keys: {len(first)}")
    sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build validator time benchmarks for a 12-month epoch range."
    )
    parser.add_argument("--start",    type=int, default=DEFAULT_START,
                        help=f"Start epoch (default: {DEFAULT_START})")
    parser.add_argument("--end",      type=int, default=DEFAULT_END,
                        help=f"End epoch (default: {DEFAULT_END})")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache — re-fetch all epochs from API")
    parser.add_argument("--test-api", action="store_true",
                        help="Fetch epoch 945, print first validator keys, then exit")
    args = parser.parse_args()

    if args.test_api:
        run_test_api()

    start_epoch = args.start
    end_epoch   = args.end

    print(f"\n=== Building Validator Time Benchmarks ===")
    print(f"    Epoch range : {start_epoch} - {end_epoch}")
    print(f"    Cache dir   : {CACHE_DIR}")
    print(f"    Output      : {OUT_JSON}\n")

    # Step 0 — Load regime tags from epoch database
    print("Loading regime tags from epoch database...")
    regimes = load_epoch_regimes()
    db_epochs = set(regimes.keys())
    print(f"  Regime tags loaded: {len(regimes)} epochs in DB")

    # ── Step 1 + 2 + 3 — Fetch, summarise, cache ─────────────────────────────
    epoch_range   = list(range(start_epoch, end_epoch + 1))
    n_requested   = len(epoch_range)
    summaries     = []   # list of per-epoch summary dicts (in epoch order)
    failed_epochs = []

    print(f"\nProcessing {n_requested} epochs...\n")

    for epoch in epoch_range:
        # Determine regime
        if epoch in regimes:
            regime = regimes[epoch]
        else:
            regime = "normal"
            print(f"  WARNING: epoch {epoch} not in DB — tagging as 'normal'")

        # Check cache first (unless --no-cache)
        if not args.no_cache:
            cached = load_cached_summary(epoch)
            if cached is not None:
                # Patch regime in case DB was refreshed after caching
                cached["regime"] = regime
                summaries.append(cached)
                print(f"  Epoch {epoch:>4}: cached  ({cached['n_validators']:>4} validators, {regime})")
                continue

        # Fetch from API
        raw_validators, err = fetch_validator_rewards(epoch)
        time.sleep(FETCH_DELAY_S)

        if err:
            failed_epochs.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  ({err})")
            continue

        if not raw_validators:
            failed_epochs.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  (empty response)")
            continue

        # Parse all validators
        parsed = [_parse_validator_row(v) for v in raw_validators]
        parsed = [p for p in parsed if p is not None]

        if not parsed:
            failed_epochs.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  (0 valid validators after parsing)")
            continue

        # Build and cache summary
        summary = _build_epoch_summary(epoch, parsed, regime)
        save_cached_summary(summary)
        summaries.append(summary)
        print(f"  Epoch {epoch:>4}: fetched ({summary['n_validators']:>4} validators, {regime})")

    n_fetched = len(summaries)
    n_failed  = len(failed_epochs)

    print(f"\nFetch complete: {n_fetched} summaries, {n_failed} failed")
    if n_failed > 0:
        print(f"  Failed epochs: {failed_epochs}")
        if n_failed / n_requested > 0.30:
            print("  WARNING: >30% of epochs failed. Consider fallback to network-only data.")

    # ── Step 4 — Time aggregations ─────────────────────────────────────────────
    print("\nBuilding time aggregations...")

    all_summaries = summaries  # already filtered to successful ones

    elevated_extreme = [s for s in all_summaries
                        if s.get("regime") in ("elevated", "extreme")]

    # Determine actual epoch range covered
    covered_epochs = sorted(s["epoch"] for s in all_summaries)
    ep_range_str   = f"{covered_epochs[0]}-{covered_epochs[-1]}" if covered_epochs else "none"

    agg_all  = build_time_agg_block(all_summaries)
    agg_ee   = build_time_agg_block(elevated_extreme)

    # ── 24m loop — fetch/cache epochs below DEFAULT_START ─────────────────────
    # Build a second summary list covering EPOCH_START_24M to EPOCH_END.
    # Epochs already in `summaries` (start_epoch–end_epoch) are reused directly
    # from the cache; only epochs below start_epoch need to be fetched.
    print(f"\nBuilding 24m dataset (epochs {EPOCH_START_24M}-{end_epoch})...")
    summaries_24m = []
    epoch_range_24m = list(range(EPOCH_START_24M, end_epoch + 1))
    failed_24m = []

    # Pre-index already-built summaries by epoch for instant lookup
    summaries_by_epoch = {s["epoch"]: s for s in all_summaries}

    for epoch in epoch_range_24m:
        # Reuse from current run's summaries if already built
        if epoch in summaries_by_epoch:
            summaries_24m.append(summaries_by_epoch[epoch])
            continue

        # Determine regime
        if epoch in regimes:
            regime = regimes[epoch]
        else:
            regime = "normal"
            print(f"  WARNING: epoch {epoch} not in DB — tagging as 'normal'")

        # Check cache first (unless --no-cache)
        if not args.no_cache:
            cached = load_cached_summary(epoch)
            if cached is not None:
                cached["regime"] = regime
                summaries_24m.append(cached)
                print(f"  Epoch {epoch:>4}: cached  ({cached['n_validators']:>4} validators, {regime})")
                continue

        # Fetch from API
        raw_validators, err = fetch_validator_rewards(epoch)
        time.sleep(FETCH_DELAY_S)

        if err:
            failed_24m.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  ({err})")
            continue

        if not raw_validators:
            failed_24m.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  (empty response)")
            continue

        parsed = [_parse_validator_row(v) for v in raw_validators]
        parsed = [p for p in parsed if p is not None]

        if not parsed:
            failed_24m.append(epoch)
            print(f"  Epoch {epoch:>4}: FAILED  (0 valid validators after parsing)")
            continue

        summary = _build_epoch_summary(epoch, parsed, regime)
        save_cached_summary(summary)
        summaries_24m.append(summary)
        print(f"  Epoch {epoch:>4}: fetched ({summary['n_validators']:>4} validators, {regime})")

    print(f"24m fetch complete: {len(summaries_24m)} summaries, {len(failed_24m)} failed")
    if failed_24m:
        print(f"  Failed epochs (24m): {failed_24m}")

    # Build 24m elevated+extreme block
    ee_24m = [s for s in summaries_24m if s.get("regime") in ("elevated", "extreme")]
    agg_ee_24m = build_time_agg_block(ee_24m)

    covered_24m = sorted(s["epoch"] for s in summaries_24m)
    ep_range_24m_str = (
        f"{covered_24m[0]}-{covered_24m[-1]}" if covered_24m else "none"
    )
    ee_24m_epochs = sorted(s["epoch"] for s in ee_24m)
    ee_24m_range_str = (
        f"{ee_24m_epochs[0]}-{ee_24m_epochs[-1]}" if ee_24m_epochs else "none"
    )

    # ── Step 5 — latest_epoch block ───────────────────────────────────────────
    print("Building latest_epoch block from benchmark JSON or epoch 945 cache...")
    latest_epoch_block = build_latest_epoch_block(regimes)
    if latest_epoch_block is None:
        print("  WARNING: could not build latest_epoch block (no benchmark JSON or cache)")

    # ── Assemble output ────────────────────────────────────────────────────────
    per_epoch_list = [
        {
            "epoch":        s["epoch"],
            "regime":       s["regime"],
            "n_validators": s["n_validators"],
            "metrics":      s["metrics"],
        }
        for s in all_summaries
    ]

    output = {
        "latest_epoch":             latest_epoch_block,
        "last_12m_all": {
            "epoch_range": ep_range_str,
            "num_epochs":  len(all_summaries),
            **agg_all,
        },
        "last_12m_elevated_extreme": {
            "epoch_range": f"{ep_range_str} (elevated+extreme only)",
            "num_epochs":  len(elevated_extreme),
            **agg_ee,
        },
        "last_24m_elevated_extreme": {
            "epoch_range": f"{ee_24m_range_str} (elevated+extreme only, full available range)",
            "num_epochs":  len(ee_24m),
            **agg_ee_24m,
        },
        "per_epoch": per_epoch_list,
        "meta": {
            "generated_at":         str(date.today()),
            "epoch_range":          f"{start_epoch}-{end_epoch}",
            "num_epochs_requested": n_requested,
            "num_epochs_fetched":   n_fetched,
            "num_epochs_failed":    n_failed,
            "failed_epochs":        failed_epochs,
            "time_windows": {
                "12m_all": f"epochs {start_epoch}-{end_epoch}, all regimes",
                "12m_elevated_extreme": f"epochs {start_epoch}-{end_epoch}, elevated+extreme only",
                "24m_elevated_extreme": (
                    f"epochs {EPOCH_START_24M}-{end_epoch}, elevated+extreme only"
                    " — extended high-volatility reference across full available epoch range"
                ),
            },
            "benchmark_notes": {
                "primary": "12m_all — main long-run benchmark",
                "extended_high_vol": "24m_elevated_extreme — captures full bull/volatile cycle",
                "contextual": "12m_elevated_extreme — shorter window, same regime filter",
            },
            "methodology": (
                "Validator-level per-block metrics per epoch, "
                "then cohort statistics per epoch, "
                "then aggregation over epoch summaries"
            ),
            "regime_source": "solana_epoch_database.csv volatility_tag",
            "data_source":   "Trillium API /validator_rewards/{epoch}",
            "temporal_aggregation": (
                "For cohort statistics (top_50_by_*), each epoch's cohort is ranked "
                "independently. The canonical benchmark is median_of_epoch_medians: "
                "the median across per-epoch cohort medians. "
                "mean_of_medians is the mean of those same per-epoch medians. "
                "mean_of_means is the mean of per-epoch cohort means, which is a proxy "
                "for the pooled mean (since each epoch contributes exactly 50 validators, "
                "all epochs are equal-weighted). "
                "Pooled median (true median of all 50*N individual rows) is not stored "
                "as it would require caching 50 individual validator values per epoch."
            ),
            "regime_note": (
                "Regime classification (normal/elevated/extreme) uses relative z-scores "
                "over a rolling 30-epoch window, not absolute thresholds. "
                "A spike in MEV relative to a low-MEV baseline still triggers elevated/extreme, "
                "even if the absolute value is below the 12m median. "
                "As a result, the median_of_epoch_medians for elevated+extreme epochs "
                "can be LOWER than for all epochs when the elevated/extreme set includes "
                "both true high-MEV spikes (early range) and relative-spike epochs in "
                "low-MEV periods (later range). This is a valid distribution effect, "
                "not an aggregation artifact."
            ),
            "notes": [
                "total_reward = base_fees + priority_fees + mev (per block)",
                "top_50_by_stake and top_50_by_mev ranked independently per epoch",
                (
                    "time aggregations computed over per-epoch medians "
                    "(not raw validator values)"
                ),
                (
                    "median_of_epoch_medians is the canonical reference; "
                    "mean_of_epoch_means is the proxy for pooled mean"
                ),
                (
                    "base_fees = signature fees (sig_fees from Trillium); "
                    "all values SOL per block (per leader slot)"
                ),
            ],
        },
    }

    # ── Write output ───────────────────────────────────────────────────────────
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"\nJSON written: {OUT_JSON}")

    # ── Validation summary ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    # 1. Epoch coverage
    print(f"\n1. Epoch coverage:")
    print(f"   Requested : {n_requested} epochs ({start_epoch}-{end_epoch})")
    print(f"   Fetched   : {n_fetched} epochs")
    print(f"   Failed    : {n_failed} epochs")

    # 2. Units check: compare total_reward median vs sum of component medians.
    # NOTE: median(a+b+c) != median(a)+median(b)+median(c) in general.
    # A gap of 1-3% is expected and statistically correct.  This check
    # confirms order-of-magnitude consistency, not algebraic equality.
    print(f"\n2. Units check (epoch 945):")
    s945 = next((s for s in all_summaries if s["epoch"] == 945), None)
    if s945:
        m = s945["metrics"]
        bf_med  = (m["base_fees"]["network"]["median"]     or 0)
        pf_med  = (m["priority_fees"]["network"]["median"] or 0)
        mv_med  = (m["mev"]["network"]["median"]           or 0)
        tr_med  = (m["total_reward"]["network"]["median"]  or 0)
        expected = bf_med + pf_med + mv_med
        if tr_med > 0:
            err_pct = abs(tr_med - expected) / tr_med * 100
            # Allow up to 5% — median(sum) != sum(medians) by design
            status  = "OK" if err_pct < 5.0 else "LARGE MISMATCH"
            print(f"   total_reward median  : {tr_med:.8f} SOL/block")
            print(f"   sum of component medians: {expected:.8f} SOL/block")
            print(f"   Relative gap         : {err_pct:.4f}%  [{status}]")
            print(f"   (gap is expected: median(sum) != sum(medians))")
        else:
            print("   total_reward = 0 — cannot check (epoch 945 may have been skipped)")
    else:
        print("   Epoch 945 not in summaries (was it in the range?)")

    # 3. MEV comparison table
    print(f"\n3. MEV comparison (network median SOL/block):")
    if latest_epoch_block:
        le_mev = (latest_epoch_block.get("metrics", {})
                  .get("mev", {}).get("network", {}).get("median"))
        print(f"   latest_epoch (945)              : {le_mev}")
    all_mev    = (agg_all.get("metrics", {}).get("mev", {})
                  .get("network", {}).get("median"))
    ee_mev     = (agg_ee.get("metrics", {}).get("mev", {})
                  .get("network", {}).get("median"))
    ee_24m_mev = (agg_ee_24m.get("metrics", {}).get("mev", {})
                  .get("network", {}).get("median"))
    print(f"   last_12m_all (median of medians): {all_mev}")
    print(f"   last_12m_elevated_extreme       : {ee_mev}")
    print(f"   last_24m_elevated_extreme       : {ee_24m_mev}")
    resolves = (
        ee_24m_mev is not None
        and all_mev is not None
        and ee_24m_mev > all_mev
    )
    print(f"   24m_EE > 12m_all?               : {'YES — resolves low-EE issue' if resolves else 'NO'}")

    # 4. Regime breakdown
    print(f"\n4. Regime breakdown (epochs {start_epoch}-{end_epoch}):")
    from collections import Counter
    regime_counts = Counter(s["regime"] for s in all_summaries)
    for tag in ("normal", "elevated", "extreme"):
        cnt = regime_counts.get(tag, 0)
        print(f"   {tag:<10}: {cnt:>4} epochs")

    print("\nDone.")


if __name__ == "__main__":
    main()
