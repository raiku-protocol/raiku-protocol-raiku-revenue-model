"""
Build additive Solana-wide epoch market metrics dataset.
========================================================

This dataset is additive and intended only for secondary benchmark analysis.
It does not replace the current program-level scenario framework or live logic.

Primary source:
  - data/raw/trillium_epoch_data.csv

Supporting / validation sources:
  - data/raw/trillium_intraday_peaks.csv
  - data/raw/jito_mev_rewards.csv
  - data/raw/solana_compass_epochs.csv
  - data/processed/solana_epoch_database.csv  (regime consistency helper)

Output:
  - data/processed/solana_epoch_market_metrics.csv
"""

import csv
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, DATA_PROCESSED, CSV_DELIMITER, CSV_ENCODING


TRILLIUM_FILE = DATA_RAW / "trillium_epoch_data.csv"
INTRADAY_FILE = DATA_RAW / "trillium_intraday_peaks.csv"
JITO_FILE = DATA_RAW / "jito_mev_rewards.csv"
SC_FILE = DATA_RAW / "solana_compass_epochs.csv"
EPOCH_DB_FILE = DATA_PROCESSED / "solana_epoch_database.csv"
OUTPUT_FILE = DATA_PROCESSED / "solana_epoch_market_metrics.csv"

LAMPORTS_PER_SOL = 1_000_000_000

OUTPUT_COLUMNS = [
    # Identity / coverage
    "epoch",
    "epoch_start_date",
    "epoch_end_date",
    "duration_days",
    "source_primary",
    "source_mev_crosscheck",
    "source_skiprate",
    "has_intraday_peak_data",
    "coverage_notes",
    # Activity / throughput
    "total_cu",
    "avg_cu_per_block",
    "avg_cu_per_user_tx",
    "total_user_txns",
    "total_vote_txns",
    "total_all_txns",
    "user_tx_per_block",
    "all_tx_per_block",
    "total_blocks",
    "total_slots",
    "total_skipped_slots",
    "skip_rate_pct",
    # Fees
    "base_fees_sol",
    "priority_fees_sol",
    "mev_jito_tips_sol",
    "non_base_fees_sol",
    "total_fees_sol",
    # Fee / CU metrics
    "base_fee_per_cu_lamports",
    "priority_fee_per_cu_lamports",
    "mev_jito_fee_per_cu_lamports",
    "non_base_fee_per_cu_lamports",
    "total_fee_per_cu_lamports",
    # Market / regime context
    "sol_price_usd",
    "volatility_tag",
    "price_change_pct",
    "pf_zscore",
    "mev_zscore",
    "fee_multiple",
    "mev_multiple",
    # Intraday peak overlay
    "baseline_pf_per_block_sol",
    "baseline_tx_per_block",
    "peak_pf_per_block_sol",
    "peak_pf_multiple",
    "peak_pf_time",
    "peak_tx_per_block",
    "peak_tx_multiple",
    "peak_tx_time",
    "peak_hour_pf_sol",
    "peak_hour_pf_time",
]


def load_csv(filepath):
    if not filepath.exists():
        return []
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


def safe_int(val):
    num = safe_float(val)
    if num is None:
        return None
    return int(num)


def first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def sum_if_complete(*values):
    if any(value is None for value in values):
        return None
    return sum(values)


def div_if_possible(num, den):
    if num is None or den is None or den == 0:
        return None
    return num / den


def fee_per_cu_lamports(fees_sol, total_cu):
    if fees_sol is None or total_cu is None or total_cu == 0:
        return None
    return fees_sol * LAMPORTS_PER_SOL / total_cu


def parse_date_prefix(value):
    if not value:
        return None
    return str(value)[:10]


def coverage_note_list(row, has_intraday):
    notes = []
    if row["mev_jito_tips_sol"] is None:
        notes.append("missing_trillium_mev")
    if row["source_mev_crosscheck"] == "":
        notes.append("no_jito_crosscheck")
    if row["total_slots"] is None:
        notes.append("no_total_slots")
    if row["skip_rate_pct"] is None:
        notes.append("no_skip_rate")
    if not has_intraday:
        notes.append("no_intraday_peak_overlay")
    return "|".join(notes)


def build():
    print("  Loading sources...")
    trillium_rows = load_csv(TRILLIUM_FILE)
    if not trillium_rows:
        raise FileNotFoundError(f"Missing required primary source: {TRILLIUM_FILE}")

    intraday = {int(r["epoch"]): r for r in load_csv(INTRADAY_FILE) if r.get("epoch")}
    jito = {int(r["epoch"]): r for r in load_csv(JITO_FILE) if r.get("epoch")}
    sc = {int(r["epoch"]): r for r in load_csv(SC_FILE) if r.get("epoch")}
    epoch_db = {int(r["epoch"]): r for r in load_csv(EPOCH_DB_FILE) if r.get("epoch")}

    print(f"    Trillium epochs: {len(trillium_rows)}")
    print(f"    Intraday peak epochs: {len(intraday)}")
    print(f"    Jito cross-check epochs: {len(jito)}")
    print(f"    Solana Compass epochs: {len(sc)}")
    print(f"    Epoch DB helper rows: {len(epoch_db)}")

    results = []
    for t in sorted(trillium_rows, key=lambda r: int(r["epoch"])):
        epoch = int(t["epoch"])
        intr = intraday.get(epoch, {})
        jito_row = jito.get(epoch, {})
        sc_row = sc.get(epoch, {})
        helper = epoch_db.get(epoch, {})

        total_cu = safe_float(t.get("total_cu"))
        avg_cu_per_block = safe_float(t.get("avg_cu_per_block"))
        avg_cu_per_user_tx = safe_float(t.get("avg_cu_per_user_tx"))
        total_user_txns = safe_int(t.get("total_user_tx"))
        total_vote_txns = safe_int(t.get("total_vote_tx"))
        total_all_txns = sum_if_complete(total_user_txns, total_vote_txns)
        total_blocks = safe_int(t.get("total_blocks_produced"))

        base_fees_sol = safe_float(t.get("total_validator_signature_fees"))
        priority_fees_sol = safe_float(t.get("total_validator_priority_fees"))
        mev_jito_tips_sol = safe_float(t.get("total_mev_earned"))
        non_base_fees_sol = sum_if_complete(priority_fees_sol, mev_jito_tips_sol)
        total_fees_sol = sum_if_complete(base_fees_sol, priority_fees_sol, mev_jito_tips_sol)

        total_slots = safe_int(sc_row.get("total_slots"))
        total_skipped_slots = first_present(
            safe_int(sc_row.get("total_skipped_slots")),
            safe_int(intr.get("total_skipped_slots")),
        )
        skip_rate_pct = first_present(
            div_if_possible(total_skipped_slots, total_slots) * 100 if total_slots else None,
            safe_float(intr.get("skip_rate_pct")),
        )

        has_intraday = epoch in intraday
        source_skiprate = ""
        if sc_row and total_slots is not None:
            source_skiprate = "solana_compass_epochs.csv"
        elif intr and safe_float(intr.get("skip_rate_pct")) is not None:
            source_skiprate = "trillium_intraday_peaks.csv"

        row = {
            "epoch": epoch,
            "epoch_start_date": parse_date_prefix(t.get("min_block_time_calendar")) or helper.get("date") or "",
            "epoch_end_date": parse_date_prefix(t.get("max_block_time_calendar")),
            "duration_days": div_if_possible(safe_float(t.get("elapsed_time_minutes")), 1440),
            "source_primary": "trillium_epoch_data.csv",
            "source_mev_crosscheck": "jito_mev_rewards.csv" if jito_row else "",
            "source_skiprate": source_skiprate,
            "has_intraday_peak_data": "true" if has_intraday else "false",
            "coverage_notes": "",
            "total_cu": total_cu,
            "avg_cu_per_block": avg_cu_per_block,
            "avg_cu_per_user_tx": avg_cu_per_user_tx,
            "total_user_txns": total_user_txns,
            "total_vote_txns": total_vote_txns,
            "total_all_txns": total_all_txns,
            "user_tx_per_block": div_if_possible(total_user_txns, total_blocks),
            "all_tx_per_block": div_if_possible(total_all_txns, total_blocks),
            "total_blocks": total_blocks,
            "total_slots": total_slots,
            "total_skipped_slots": total_skipped_slots,
            "skip_rate_pct": skip_rate_pct,
            "base_fees_sol": base_fees_sol,
            "priority_fees_sol": priority_fees_sol,
            "mev_jito_tips_sol": mev_jito_tips_sol,
            "non_base_fees_sol": non_base_fees_sol,
            "total_fees_sol": total_fees_sol,
            "base_fee_per_cu_lamports": fee_per_cu_lamports(base_fees_sol, total_cu),
            "priority_fee_per_cu_lamports": fee_per_cu_lamports(priority_fees_sol, total_cu),
            "mev_jito_fee_per_cu_lamports": fee_per_cu_lamports(mev_jito_tips_sol, total_cu),
            "non_base_fee_per_cu_lamports": fee_per_cu_lamports(non_base_fees_sol, total_cu),
            "total_fee_per_cu_lamports": fee_per_cu_lamports(total_fees_sol, total_cu),
            "sol_price_usd": safe_float(t.get("sol_price_usd")),
            "volatility_tag": helper.get("volatility_tag", ""),
            "price_change_pct": safe_float(helper.get("price_change_pct")),
            "pf_zscore": safe_float(helper.get("pf_zscore")),
            "mev_zscore": safe_float(helper.get("mev_zscore")),
            "fee_multiple": safe_float(helper.get("fee_multiple")),
            "mev_multiple": safe_float(helper.get("mev_multiple")),
            "baseline_pf_per_block_sol": safe_float(intr.get("baseline_pf_per_block_sol")),
            "baseline_tx_per_block": safe_float(intr.get("baseline_tx_per_block")),
            "peak_pf_per_block_sol": safe_float(intr.get("peak_pf_per_block_sol")),
            "peak_pf_multiple": safe_float(intr.get("peak_pf_multiple")),
            "peak_pf_time": intr.get("peak_pf_time", ""),
            "peak_tx_per_block": safe_float(intr.get("peak_tx_per_block")),
            "peak_tx_multiple": safe_float(intr.get("peak_tx_multiple")),
            "peak_tx_time": intr.get("peak_tx_time", ""),
            "peak_hour_pf_sol": safe_float(intr.get("peak_hour_pf_sol")),
            "peak_hour_pf_time": intr.get("peak_hour_pf_time", ""),
        }

        row["coverage_notes"] = coverage_note_list(row, has_intraday)
        results.append(row)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        for row in results:
            clean = {k: ("" if row.get(k) is None else row.get(k)) for k in OUTPUT_COLUMNS}
            writer.writerow(clean)

    epochs = [r["epoch"] for r in results]
    print(f"\n  Saved: {OUTPUT_FILE}")
    print(f"  Rows: {len(results)}")
    print(f"  Coverage: epochs {min(epochs)}-{max(epochs)}")
    print(f"  Intraday overlay rows: {sum(1 for r in results if r['has_intraday_peak_data'] == 'true')}")


if __name__ == "__main__":
    print("\n=== Building Solana Epoch Market Metrics (additive benchmark) ===")
    build()
    print("\nDone.")
