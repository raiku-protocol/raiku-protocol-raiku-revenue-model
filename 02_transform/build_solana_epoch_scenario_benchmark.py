"""
Build additive scenario-vs-epoch benchmark table.
=================================================

This output is additive and intended only for secondary benchmark /
stress analysis. It does not replace the current program-level
scenario framework or live simulator logic.

Inputs:
  - data/processed/solana_epoch_market_metrics.csv
  - data/processed/program_database.csv

Output:
  - data/processed/solana_epoch_scenario_benchmark.csv
"""

import bisect
import csv
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, CSV_DELIMITER, CSV_ENCODING


EPOCH_METRICS_FILE = DATA_PROCESSED / "solana_epoch_market_metrics.csv"
PROGRAM_DB_FILE = DATA_PROCESSED / "program_database.csv"
OUTPUT_FILE = DATA_PROCESSED / "solana_epoch_scenario_benchmark.csv"

LAMPORTS_PER_SOL = 1_000_000_000
CORE_SEGMENTS = {
    "prop_amm",
    "cranker",
    "oracle",
    "depin",
    "payments",
    "aggregator",
    "amm_pools",
    "orderbook",
    "lending",
    "perps",
    "bridge",
    "nft",
    "gaming",
}

OUTPUT_COLUMNS = [
    "anchor_name",
    "anchor_display_fee_cu_lamports",
    "anchor_raw_reference_fee_cu_lamports",
    "anchor_reference_label",
    "comparison_metric",
    "epoch_subset",
    "sample_size",
    "subset_median_fee_cu_lamports",
    "subset_p75_fee_cu_lamports",
    "subset_p90_fee_cu_lamports",
    "anchor_display_percentile_rank_pct",
    "anchor_raw_percentile_rank_pct",
    "anchor_display_ratio_vs_median",
    "anchor_raw_ratio_vs_median",
    "anchor_display_ratio_vs_p75",
    "anchor_raw_ratio_vs_p75",
    "anchor_display_ratio_vs_p90",
    "anchor_raw_ratio_vs_p90",
    "percentile_rank_pct",
    "ratio_vs_median",
    "ratio_vs_p75",
    "ratio_vs_p90",
]


def load_csv(filepath):
    if not filepath.exists():
        raise FileNotFoundError(f"Missing required file: {filepath}")
    with open(filepath, "r", encoding=CSV_ENCODING) as f:
        content = f.read()
        if content.startswith("\ufeff"):
            content = content[1:]
        return list(csv.DictReader(content.splitlines(), delimiter=CSV_DELIMITER))


def safe_float(val):
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def quantile(values, q):
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def percentile_rank(values, anchor):
    if not values:
        return None
    sorted_vals = sorted(values)
    return bisect.bisect_right(sorted_vals, anchor) / len(sorted_vals) * 100


def round2(value):
    if value is None:
        return None
    return round(value + 1e-12, 2)


def safe_ratio(num, den):
    if num is None or den in (None, 0, 0.0):
        return None
    return num / den


def derive_segment_key(category, subcategory):
    cat = (category or "").strip().lower()
    sub = (subcategory or "").strip().lower()

    if cat == "arb_bot":
        return "arb_bot"
    if cat == "prop_amm":
        return "prop_amm"
    if cat == "dex":
        if sub == "orderbook":
            return "orderbook"
        if sub == "aggregator":
            return "aggregator"
        return "amm_pools"
    if cat in {
        "lending",
        "perps",
        "oracle",
        "bridge",
        "cranker",
        "depin",
        "payments",
        "nft",
        "gaming",
    }:
        return cat
    return "other"


def build_anchor_rows():
    rows = load_csv(PROGRAM_DB_FILE)
    core_rows = []

    for row in rows:
        product = (row.get("raiku_product") or "").strip().lower()
        category = (row.get("raiku_category") or "").strip().lower()
        subcategory = (row.get("raiku_subcategory") or "").strip().lower()
        total_cu = safe_float(row.get("total_cu"))
        if product not in {"aot", "both"}:
            continue
        if category in {"other", "unknown", ""}:
            continue
        if total_cu in (None, 0, 0.0):
            continue

        segment_key = derive_segment_key(category, subcategory)
        if segment_key not in CORE_SEGMENTS:
            continue

        base_fees_sol = safe_float(row.get("base_fees_sol")) or 0.0
        priority_fees_sol = safe_float(row.get("priority_fees_sol")) or 0.0
        jito_mev_fees_sol = safe_float(row.get("jito_mev_fees_sol")) or 0.0
        non_base_fees_sol = priority_fees_sol + jito_mev_fees_sol
        total_fees_sol = base_fees_sol + non_base_fees_sol

        core_rows.append(
            {
                "total_cu": total_cu,
                "fpc_nb": non_base_fees_sol * LAMPORTS_PER_SOL / total_cu,
                "fpc_tot": total_fees_sol * LAMPORTS_PER_SOL / total_cu,
                "base_fees_sol": base_fees_sol,
                "non_base_fees_sol": non_base_fees_sol,
                "total_fees_sol": total_fees_sol,
            }
        )

    if not core_rows:
        raise RuntimeError("No core scenario rows found in program_database.csv")

    active_rows = [row for row in core_rows if row["fpc_nb"] > 0]
    total_cu = sum(row["total_cu"] for row in core_rows)
    weighted_non_base = sum(row["non_base_fees_sol"] for row in core_rows) * LAMPORTS_PER_SOL / total_cu
    weighted_total = sum(row["total_fees_sol"] for row in core_rows) * LAMPORTS_PER_SOL / total_cu
    p25_active_non_base = quantile([row["fpc_nb"] for row in active_rows], 0.25)
    p75_active_non_base = quantile([row["fpc_nb"] for row in active_rows], 0.75)

    return [
        {
            "anchor_name": "Conservative",
            "anchor_display_fee_cu_lamports": round2(max(0.10, p25_active_non_base or 0.0)),
            "anchor_raw_reference_fee_cu_lamports": p25_active_non_base,
            "anchor_reference_label": "P25 active-payer non-base fee/CU with 0.10 floor",
        },
        {
            "anchor_name": "Base",
            "anchor_display_fee_cu_lamports": round2(weighted_non_base),
            "anchor_raw_reference_fee_cu_lamports": weighted_non_base,
            "anchor_reference_label": "CU-weighted non-base fee/CU on included core programs",
        },
        {
            "anchor_name": "Optimistic",
            "anchor_display_fee_cu_lamports": 1.50,
            "anchor_raw_reference_fee_cu_lamports": weighted_total,
            "anchor_reference_label": "Fixed display anchor; current total-fee reference is CU-weighted total fee/CU",
        },
        {
            "anchor_name": "Bull",
            "anchor_display_fee_cu_lamports": 2.00,
            "anchor_raw_reference_fee_cu_lamports": p75_active_non_base,
            "anchor_reference_label": "Fixed display anchor; current non-base reference is P75 active-payer fee/CU",
        },
    ]


def subset_specs():
    return [
        ("all_epochs", lambda row: True),
        ("normal", lambda row: (row.get("volatility_tag") or "") == "normal"),
        ("elevated", lambda row: (row.get("volatility_tag") or "") == "elevated"),
        ("extreme", lambda row: (row.get("volatility_tag") or "") == "extreme"),
        ("intraday_peak_tagged", lambda row: (row.get("has_intraday_peak_data") or "").lower() == "true"),
        ("non_peak", lambda row: (row.get("has_intraday_peak_data") or "").lower() != "true"),
    ]


def benchmark_rows():
    epoch_rows = load_csv(EPOCH_METRICS_FILE)
    anchors = build_anchor_rows()
    metric_columns = [
        "non_base_fee_per_cu_lamports",
        "total_fee_per_cu_lamports",
    ]

    out = []
    for metric in metric_columns:
        for subset_name, subset_fn in subset_specs():
            values = [
                safe_float(row.get(metric))
                for row in epoch_rows
                if subset_fn(row) and safe_float(row.get(metric)) is not None
            ]
            if not values:
                continue

            subset_median = quantile(values, 0.50)
            subset_p75 = quantile(values, 0.75)
            subset_p90 = quantile(values, 0.90)

            for anchor in anchors:
                display_val = anchor["anchor_display_fee_cu_lamports"]
                raw_val = anchor["anchor_raw_reference_fee_cu_lamports"]
                display_percentile = percentile_rank(values, display_val)
                raw_percentile = percentile_rank(values, raw_val)
                display_ratio_median = safe_ratio(display_val, subset_median)
                raw_ratio_median = safe_ratio(raw_val, subset_median)
                display_ratio_p75 = safe_ratio(display_val, subset_p75)
                raw_ratio_p75 = safe_ratio(raw_val, subset_p75)
                display_ratio_p90 = safe_ratio(display_val, subset_p90)
                raw_ratio_p90 = safe_ratio(raw_val, subset_p90)
                out.append(
                    {
                        "anchor_name": anchor["anchor_name"],
                        "anchor_display_fee_cu_lamports": display_val,
                        "anchor_raw_reference_fee_cu_lamports": raw_val,
                        "anchor_reference_label": anchor["anchor_reference_label"],
                        "comparison_metric": metric,
                        "epoch_subset": subset_name,
                        "sample_size": len(values),
                        "subset_median_fee_cu_lamports": subset_median,
                        "subset_p75_fee_cu_lamports": subset_p75,
                        "subset_p90_fee_cu_lamports": subset_p90,
                        "anchor_display_percentile_rank_pct": display_percentile,
                        "anchor_raw_percentile_rank_pct": raw_percentile,
                        "anchor_display_ratio_vs_median": display_ratio_median,
                        "anchor_raw_ratio_vs_median": raw_ratio_median,
                        "anchor_display_ratio_vs_p75": display_ratio_p75,
                        "anchor_raw_ratio_vs_p75": raw_ratio_p75,
                        "anchor_display_ratio_vs_p90": display_ratio_p90,
                        "anchor_raw_ratio_vs_p90": raw_ratio_p90,
                        # Backward-compatible aliases: these remain tied to displayed anchors.
                        "percentile_rank_pct": display_percentile,
                        "ratio_vs_median": display_ratio_median,
                        "ratio_vs_p75": display_ratio_p75,
                        "ratio_vs_p90": display_ratio_p90,
                    }
                )
    return out


def build():
    results = benchmark_rows()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        for row in results:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in OUTPUT_COLUMNS})

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Rows: {len(results)}")


if __name__ == "__main__":
    print("=== Building Solana Epoch Scenario Benchmark (additive) ===")
    build()
    print("Done.")
