"""
Extract epoch data from Trillium API (free, no auth required).

Fetches /epoch_data/{epoch} for epochs 553+ (earliest available ~Dec 2023).
Supports --full (re-extract all) and incremental (only new epochs) modes.

Output: data/raw/trillium_epoch_data.csv (semicolon-delimited)
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Import config from parent
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TRILLIUM_BASE_URL, TRILLIUM_FIRST_EPOCH, DATA_RAW, CSV_DELIMITER, CSV_ENCODING


OUTPUT_FILE = "trillium_epoch_data.csv"

# Browser-like headers to avoid 403 (Trillium blocks default Python User-Agent)
HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# ~30 most relevant fields for RAIKU revenue model (from 141 available)
COLUMNS = [
    # Identifiers
    "epoch",
    # MEV breakdown
    "total_mev_earned",
    "total_mev_to_validator",
    "total_mev_to_stakers",
    "total_mev_to_jito_block_engine",
    "total_mev_to_jito_tip_router",
    # Fees
    "total_validator_priority_fees",
    "total_validator_signature_fees",
    "total_block_rewards",
    # Inflation
    "total_total_inflation_reward",
    "inflation_rate",
    "epochs_per_year",
    # APY components (compound)
    "avg_compound_overall_apy",
    "avg_total_compound_inflation_apy",
    "avg_total_compound_mev_apy",
    "avg_total_compound_block_rewards_apy",
    "avg_delegator_compound_total_apy",
    "avg_validator_compound_total_apy",
    # Network
    "total_active_validators",
    "total_active_stake",
    "sol_price_usd",
    # Compute Units
    "avg_cu_per_block",
    "total_cu",
    "avg_cu_per_user_tx",
    "avg_priority_fee_per_10m_cu",
    "avg_mev_per_10m_cu",
    # Transactions
    "total_user_tx",
    "total_vote_tx",
    "total_blocks_produced",
    # Epoch timing
    "min_block_time_calendar",
    "max_block_time_calendar",
    "elapsed_time_minutes",
]


def get_current_epoch() -> int:
    """Fetch the latest available epoch from Trillium."""
    # Try a high epoch and binary search down, or just try recent epochs
    # Simpler: fetch a known recent epoch and walk forward
    test_epoch = 950
    while True:
        try:
            url = f"{TRILLIUM_BASE_URL}/epoch_data/{test_epoch}"
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data and data.get("epoch") is not None:
                    test_epoch += 1
                    time.sleep(0.1)
                else:
                    return test_epoch - 1
        except (urllib.error.HTTPError, urllib.error.URLError):
            return test_epoch - 1


def fetch_epoch(epoch: int) -> dict | None:
    """Fetch a single epoch's data from Trillium API."""
    url = f"{TRILLIUM_BASE_URL}/epoch_data/{epoch}"
    try:
        req = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data and data.get("epoch") is not None:
                return data
            return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except urllib.error.URLError:
        return None


def load_existing_epochs() -> set:
    """Load already-extracted epoch numbers from the output CSV."""
    filepath = DATA_RAW / OUTPUT_FILE
    if not filepath.exists():
        return set()
    epochs = set()
    with open(filepath, "r", encoding=CSV_ENCODING) as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        for row in reader:
            try:
                epochs.add(int(row["epoch"]))
            except (ValueError, KeyError):
                pass
    return epochs


def extract(full: bool = False):
    """Main extraction logic."""
    print(f"  Trillium API: {TRILLIUM_BASE_URL}")
    print(f"  First epoch: {TRILLIUM_FIRST_EPOCH}")

    # Determine current epoch
    print("  Detecting current epoch...")
    current_epoch = get_current_epoch()
    print(f"  Current epoch: {current_epoch}")

    total_epochs = current_epoch - TRILLIUM_FIRST_EPOCH + 1
    print(f"  Total available: {total_epochs} epochs ({TRILLIUM_FIRST_EPOCH}-{current_epoch})")

    # Determine which epochs to fetch
    if full:
        epochs_to_fetch = list(range(TRILLIUM_FIRST_EPOCH, current_epoch + 1))
        existing_rows = []
        print(f"  Mode: FULL re-extraction ({len(epochs_to_fetch)} epochs)")
    else:
        existing_epochs = load_existing_epochs()
        all_epochs = set(range(TRILLIUM_FIRST_EPOCH, current_epoch + 1))
        missing = sorted(all_epochs - existing_epochs)
        epochs_to_fetch = missing

        # Load existing data to merge later
        filepath = DATA_RAW / OUTPUT_FILE
        existing_rows = []
        if filepath.exists():
            with open(filepath, "r", encoding=CSV_ENCODING) as f:
                reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
                existing_rows = list(reader)

        print(f"  Mode: INCREMENTAL ({len(existing_epochs)} existing, {len(missing)} new)")

    if not epochs_to_fetch:
        print("  Nothing to fetch — already up to date!")
        return

    # Fetch epochs
    new_rows = []
    errors = []
    for i, epoch in enumerate(epochs_to_fetch):
        data = fetch_epoch(epoch)
        if data:
            # Extract only the columns we need
            row = {}
            for col in COLUMNS:
                row[col] = data.get(col, "")
            new_rows.append(row)
        else:
            errors.append(epoch)

        # Progress
        if (i + 1) % 25 == 0 or (i + 1) == len(epochs_to_fetch):
            pct = (i + 1) / len(epochs_to_fetch) * 100
            print(f"    [{i+1}/{len(epochs_to_fetch)}] {pct:.0f}% — last: epoch {epoch}")

        # Rate limit: 0.2s between requests (be polite)
        time.sleep(0.2)

    print(f"  Fetched: {len(new_rows)} epochs OK, {len(errors)} errors")
    if errors:
        print(f"  Failed epochs: {errors[:20]}{'...' if len(errors) > 20 else ''}")

    # Merge with existing data (if incremental)
    all_rows = existing_rows + new_rows

    # Sort by epoch
    all_rows.sort(key=lambda r: int(r.get("epoch", 0)))

    # Save CSV
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    filepath = DATA_RAW / OUTPUT_FILE
    with open(filepath, "w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=CSV_DELIMITER)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    print(f"  Saved: {filepath} ({len(all_rows)} rows)")

    # Summary stats from last epoch
    if new_rows:
        last = new_rows[-1]
        print(f"\n  Latest epoch ({last.get('epoch')}) sample:")
        print(f"    total_mev_earned: {last.get('total_mev_earned')} SOL")
        print(f"    total_validator_priority_fees: {last.get('total_validator_priority_fees')} SOL")
        print(f"    total_active_stake: {last.get('total_active_stake')} SOL")
        print(f"    sol_price_usd: ${last.get('sol_price_usd')}")
        print(f"    total_active_validators: {last.get('total_active_validators')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Trillium epoch data")
    parser.add_argument("--full", action="store_true", help="Re-extract ALL epochs (ignores existing)")
    args = parser.parse_args()

    print("\n=== Extracting Trillium Epoch Data ===")
    extract(full=args.full)
    print("Done.")
