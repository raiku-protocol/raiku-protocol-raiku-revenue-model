"""
Build canonical epoch-level macro market context artifact.
=========================================================

This export is additive and intended for secondary macro benchmark /
congestion context use only. It does not replace the current
program-level scenario framework or live simulator logic.

Input:
  - data/processed/solana_epoch_market_metrics.csv

Output:
  - data/processed/solana_epoch_macro_context.v1.json
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, CSV_DELIMITER, CSV_ENCODING


INPUT_FILE = DATA_PROCESSED / "solana_epoch_market_metrics.csv"
OUTPUT_FILE = DATA_PROCESSED / "solana_epoch_macro_context.v1.json"

METRICS = [
    "avg_cu_per_block",
    "priority_fee_per_cu_lamports",
    "mev_jito_fee_per_cu_lamports",
    "non_base_fee_per_cu_lamports",
    "total_fee_per_cu_lamports",
]

SUBSET_DEFINITIONS = {
    "all_epochs": "All exported epochs with a non-null value for the selected metric.",
    "normal": "Epochs tagged normal by the rolling anomaly logic.",
    "elevated": "Epochs tagged elevated by the rolling anomaly logic.",
    "extreme": "Epochs tagged extreme by the rolling anomaly logic.",
    "intraday_peak_tagged": "Epochs with intraday peak overlay data available for a volatile subset.",
    "non_peak": "Exported epochs without that intraday peak overlay flag.",
}

REGIME_DEFINITION_TEXT = (
    "all_epochs = all exported epochs with a non-null value for the selected metric; "
    "normal / elevated / extreme are the volatility_tag classes produced by the rolling "
    "30-epoch anomaly logic; intraday_peak_tagged marks epochs where an intraday peak "
    "overlay is available for a volatile subset; non_peak is the complement of that flag."
)

ASSIGNMENT_LOGIC_TEXT = (
    "volatility_tag comes from the upstream rolling 30-epoch classification logic: "
    "extreme if any of |price_change_pct| >= 15.0, mev_zscore >= 3.0, pf_zscore >= 3.0, "
    "mev_multiple >= 5.0, or fee_multiple >= 5.0; elevated if not extreme and any of "
    "|price_change_pct| >= 8.0, mev_zscore >= 2.0, pf_zscore >= 2.0, mev_multiple >= 2.5, "
    "or fee_multiple >= 2.5; normal otherwise. intraday_peak_tagged is assigned when "
    "has_intraday_peak_data == true; non_peak otherwise."
)


def load_csv(filepath):
    if not filepath.exists():
        raise FileNotFoundError(f"Missing required file: {filepath}")
    with open(filepath, "r", encoding=CSV_ENCODING) as f:
        content = f.read()
        if content.startswith("\ufeff"):
            content = content[1:]
        return list(csv.DictReader(content.splitlines(), delimiter=CSV_DELIMITER))


def safe_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value):
    number = safe_float(value)
    if number is None:
        return None
    return int(number)


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


def summary_stats(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "median": quantile(values, 0.50),
        "p25": quantile(values, 0.25),
        "p75": quantile(values, 0.75),
        "p90": quantile(values, 0.90),
        "min": min(values),
        "max": max(values),
    }


def subset_specs():
    return [
        ("all_epochs", lambda row: True),
        ("normal", lambda row: row["volatility_tag"] == "normal"),
        ("elevated", lambda row: row["volatility_tag"] == "elevated"),
        ("extreme", lambda row: row["volatility_tag"] == "extreme"),
        ("intraday_peak_tagged", lambda row: row["has_intraday_peak_data"] is True),
        ("non_peak", lambda row: row["has_intraday_peak_data"] is not True),
    ]


def build_epoch_rows(raw_rows):
    epoch_rows = []
    for row in sorted(raw_rows, key=lambda item: int(item["epoch"])):
        epoch_rows.append(
            {
                "epoch": int(row["epoch"]),
                "date": row.get("epoch_start_date") or None,
                "epoch_end_date": row.get("epoch_end_date") or None,
                "regime_label": row.get("volatility_tag") or None,
                "volatility_tag": row.get("volatility_tag") or None,
                "has_intraday_peak_data": (row.get("has_intraday_peak_data") or "").lower() == "true",
                "avg_cu_per_block": safe_float(row.get("avg_cu_per_block")),
                "priority_fee_per_cu_lamports": safe_float(row.get("priority_fee_per_cu_lamports")),
                "mev_jito_fee_per_cu_lamports": safe_float(row.get("mev_jito_fee_per_cu_lamports")),
                "non_base_fee_per_cu_lamports": safe_float(row.get("non_base_fee_per_cu_lamports")),
                "total_fee_per_cu_lamports": safe_float(row.get("total_fee_per_cu_lamports")),
            }
        )
    return epoch_rows


def build_summaries(epoch_rows):
    summaries = {}
    for metric in METRICS:
        metric_summary = {}
        for subset_name, subset_fn in subset_specs():
            values = [row[metric] for row in epoch_rows if subset_fn(row) and row[metric] is not None]
            metric_summary[subset_name] = summary_stats(values)
        summaries[metric] = metric_summary
    return summaries


def build_payload():
    raw_rows = load_csv(INPUT_FILE)
    epoch_rows = build_epoch_rows(raw_rows)
    summaries = build_summaries(epoch_rows)

    epochs = [row["epoch"] for row in epoch_rows]
    start_dates = [row["date"] for row in epoch_rows if row["date"]]
    end_dates = [row["epoch_end_date"] for row in epoch_rows if row["epoch_end_date"]]

    payload = {
        "artifact_name": OUTPUT_FILE.name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_from": str(INPUT_FILE.relative_to(Path(__file__).parent.parent)),
        "generated_by": "02_transform/build_solana_epoch_macro_context_artifact.py",
        "start_epoch": min(epochs),
        "end_epoch": max(epochs),
        "start_date": min(start_dates) if start_dates else None,
        "end_date": max(end_dates) if end_dates else None,
        "row_count": len(epoch_rows),
        "sample_description": (
            "Additive epoch-level Solana-wide macro market context export derived from the "
            "processed epoch market metrics dataset. One row per retained Trillium epoch. "
            "Intended for secondary benchmark and congestion analysis only."
        ),
        "regime_definition_text": REGIME_DEFINITION_TEXT,
        "assignment_logic_text": ASSIGNMENT_LOGIC_TEXT,
        "subset_definitions": SUBSET_DEFINITIONS,
        "metrics": METRICS,
        "epoch_rows": epoch_rows,
        "summary_by_metric": summaries,
    }
    return payload


def build():
    payload = build_payload()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    print(f"Saved: {OUTPUT_FILE}")
    print(f"Epoch rows: {payload['row_count']}")
    print(f"Coverage: epochs {payload['start_epoch']}-{payload['end_epoch']}")
    print(f"Dates: {payload['start_date']} -> {payload['end_date']}")


if __name__ == "__main__":
    print("=== Building Solana Epoch Macro Context Artifact ===")
    build()
    print("Done.")
