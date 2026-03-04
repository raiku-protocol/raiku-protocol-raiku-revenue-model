"""
Extract Jito MEV rewards per epoch from Jito Foundation API (free, no auth).

Uses POST to https://kobe.mainnet.jito.network/api/v1/mev_rewards
with body {"epoch": N} — one epoch per request.

Output columns:
  epoch, jito_total_mev_lamports, jito_total_mev_sol,
  jito_stake_weight_lamports, jito_mev_reward_per_lamport

Output: data/raw/jito_mev_rewards.csv (semicolon-delimited)
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
from config import JITO_MEV_API_URL, JITO_MEV_FIRST_EPOCH, DATA_RAW, CSV_DELIMITER, CSV_ENCODING

OUTPUT_FILE = "jito_mev_rewards.csv"
LAMPORTS_PER_SOL = 1_000_000_000

HTTP_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

COLUMNS = [
    "epoch",
    "jito_total_mev_lamports",
    "jito_total_mev_sol",
    "jito_stake_weight_lamports",
    "jito_mev_reward_per_lamport",
]


def fetch_epoch(epoch: int) -> dict | None:
    """Fetch Jito MEV rewards for a single epoch via POST."""
    body = json.dumps({"epoch": epoch}).encode("utf-8")
    try:
        req = urllib.request.Request(JITO_MEV_API_URL, data=body, headers=HTTP_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            # Verify we got the requested epoch (API may return latest if epoch invalid)
            if data and data.get("epoch") == epoch:
                return data
            return None
    except urllib.error.HTTPError as e:
        if e.code in (404, 400):
            return None
        raise
    except urllib.error.URLError:
        return None


def get_current_epoch() -> int:
    """Detect latest epoch by fetching without specific epoch (GET returns latest)."""
    try:
        req = urllib.request.Request(JITO_MEV_API_URL, headers={
            "Accept": "application/json",
            "User-Agent": HTTP_HEADERS["User-Agent"],
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data and data.get("epoch"):
                return data["epoch"]
    except Exception:
        pass
    # Fallback: try known recent epochs
    return 934


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
    print(f"  Jito MEV API: {JITO_MEV_API_URL}")
    print(f"  First epoch: {JITO_MEV_FIRST_EPOCH}")

    # Determine current epoch
    print("  Detecting current epoch...")
    current_epoch = get_current_epoch()
    print(f"  Current epoch: {current_epoch}")

    total_epochs = current_epoch - JITO_MEV_FIRST_EPOCH + 1
    print(f"  Total range: {total_epochs} epochs ({JITO_MEV_FIRST_EPOCH}-{current_epoch})")

    # Determine which epochs to fetch
    if full:
        epochs_to_fetch = list(range(JITO_MEV_FIRST_EPOCH, current_epoch + 1))
        existing_rows = []
        print(f"  Mode: FULL re-extraction ({len(epochs_to_fetch)} epochs)")
    else:
        existing_epochs = load_existing_epochs()
        all_epochs = set(range(JITO_MEV_FIRST_EPOCH, current_epoch + 1))
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
    consecutive_errors = 0
    for i, epoch in enumerate(epochs_to_fetch):
        data = fetch_epoch(epoch)
        if data:
            total_mev = int(data.get("total_network_mev_lamports", 0))
            row = {
                "epoch": epoch,
                "jito_total_mev_lamports": total_mev,
                "jito_total_mev_sol": round(total_mev / LAMPORTS_PER_SOL, 6),
                "jito_stake_weight_lamports": data.get("jito_stake_weight_lamports", ""),
                "jito_mev_reward_per_lamport": data.get("mev_reward_per_lamport", ""),
            }
            new_rows.append(row)
            consecutive_errors = 0
        else:
            errors.append(epoch)
            consecutive_errors += 1
            # If many consecutive errors, we might be before Jito's earliest epoch
            if consecutive_errors >= 20:
                print(f"    20 consecutive errors at epoch {epoch} — skipping ahead...")
                # Skip to a later range
                remaining = [e for e in epochs_to_fetch[i+1:] if e > epoch + 50]
                if remaining:
                    # Update epochs_to_fetch for reporting but break this loop
                    pass
                break

        # Progress
        if (i + 1) % 25 == 0 or (i + 1) == len(epochs_to_fetch):
            pct = (i + 1) / len(epochs_to_fetch) * 100
            print(f"    [{i+1}/{len(epochs_to_fetch)}] {pct:.0f}% — last: epoch {epoch} ({len(new_rows)} OK)")

        # Rate limit
        time.sleep(0.3)

    print(f"  Fetched: {len(new_rows)} epochs OK, {len(errors)} errors")
    if errors and len(errors) <= 20:
        print(f"  Failed epochs: {errors}")
    elif errors:
        print(f"  Failed epochs: {errors[:10]}...{errors[-5:]} ({len(errors)} total)")

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
        print(f"    jito_total_mev_sol: {last.get('jito_total_mev_sol')} SOL")
        print(f"    jito_stake_weight_lamports: {last.get('jito_stake_weight_lamports')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Jito MEV rewards per epoch")
    parser.add_argument("--full", action="store_true", help="Re-extract ALL epochs (ignores existing)")
    args = parser.parse_args()

    print("\n=== Extracting Jito MEV Rewards ===")
    extract(full=args.full)
    print("Done.")
