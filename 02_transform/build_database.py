"""
Build unified Solana epoch database by merging:
  - Trillium epoch data (primary, epochs 553+)
  - Dune epoch economics (secondary, epochs 150-935)
  - Dune commission/validators
  - Dune active stake
  - CoinGecko SOL price (365 days, daily)
  - Solana Compass epoch performance (cross-check: txns, CU, fees, Jito tips)
  - Jito Foundation MEV rewards (cross-check: official Jito MEV per epoch)

Output: data/processed/solana_epoch_database.csv (semicolon-delimited)
All computations happen in Python. CSVs are intermediates, Sheets is presentation.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_RAW, DATA_PROCESSED, CSV_DELIMITER, CSV_ENCODING


# ── Input files ───────────────────────────────────────────
TRILLIUM_FILE = DATA_RAW / "trillium_epoch_data.csv"
DUNE_EPOCHS_FILE = DATA_RAW / "dune_epoch_data_v2.csv"
DUNE_VALIDATORS_FILE = DATA_RAW / "dune_commission_validators_v2.csv"
DUNE_ACTIVE_STAKE_FILE = DATA_RAW / "dune_active_stake_v1.csv"
COINGECKO_FILE = DATA_RAW / "coingecko_sol_price.csv"
SOLANA_COMPASS_FILE = DATA_RAW / "solana_compass_epochs.csv"
JITO_MEV_FILE = DATA_RAW / "jito_mev_rewards.csv"

OUTPUT_FILE = DATA_PROCESSED / "solana_epoch_database.csv"


def safe_float(val, default=None):
    """Convert to float safely, returning default on failure."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def load_csv(filepath: Path) -> list[dict]:
    """Load a semicolon-delimited CSV."""
    if not filepath.exists():
        print(f"  WARNING: {filepath} not found, skipping")
        return []
    with open(filepath, "r", encoding=CSV_ENCODING) as f:
        # Handle BOM if present
        content = f.read()
        if content.startswith("\ufeff"):
            content = content[1:]
        reader = csv.DictReader(content.splitlines(), delimiter=CSV_DELIMITER)
        return list(reader)


def build():
    """Main merge & computation logic."""
    print("  Loading raw data sources...")

    # ── 1. Load Trillium (PRIMARY for epochs 553+) ──────────
    trillium_rows = load_csv(TRILLIUM_FILE)
    trillium = {}
    for row in trillium_rows:
        ep = int(row.get("epoch", 0))
        trillium[ep] = row
    print(f"    Trillium: {len(trillium)} epochs ({min(trillium) if trillium else '?'}-{max(trillium) if trillium else '?'})")

    # ── 2. Load Dune epoch economics (epochs 150-935) ───────
    dune_epoch_rows = load_csv(DUNE_EPOCHS_FILE)
    dune_epochs = {}
    for row in dune_epoch_rows:
        ep = int(row.get("epoch", 0))
        dune_epochs[ep] = row
    print(f"    Dune epochs: {len(dune_epochs)} epochs ({min(dune_epochs) if dune_epochs else '?'}-{max(dune_epochs) if dune_epochs else '?'})")

    # ── 3. Load Dune commission/validators ──────────────────
    dune_val_rows = load_csv(DUNE_VALIDATORS_FILE)
    dune_validators = {}
    for row in dune_val_rows:
        ep = int(row.get("epoch", 0))
        dune_validators[ep] = row
    print(f"    Dune validators: {len(dune_validators)} epochs")

    # ── 4. Load Dune active stake ───────────────────────────
    dune_stake_rows = load_csv(DUNE_ACTIVE_STAKE_FILE)
    dune_stake = {}
    for row in dune_stake_rows:
        ep = int(row.get("epoch", 0))
        dune_stake[ep] = row
    print(f"    Dune active stake: {len(dune_stake)} epochs")

    # ── 5. Load CoinGecko prices (daily) ────────────────────
    cg_rows = load_csv(COINGECKO_FILE)
    cg_prices = {}
    for row in cg_rows:
        date_str = row.get("date", "")
        price = safe_float(row.get("sol_price_usd"))
        if date_str and price:
            cg_prices[date_str] = {
                "cg_sol_price_usd": price,
                "cg_fdv_usd": safe_float(row.get("fdv_usd")),
                "cg_market_cap_usd": safe_float(row.get("market_cap_usd")),
            }
    print(f"    CoinGecko: {len(cg_prices)} daily prices")

    # ── 6. Load Solana Compass epoch performance ──────────
    sc_rows = load_csv(SOLANA_COMPASS_FILE)
    solana_compass = {}
    for row in sc_rows:
        ep = int(row.get("epoch", 0))
        solana_compass[ep] = row
    print(f"    Solana Compass: {len(solana_compass)} epochs ({min(solana_compass) if solana_compass else '?'}-{max(solana_compass) if solana_compass else '?'})")

    # ── 7. Load Jito Foundation MEV rewards ───────────────
    jito_rows = load_csv(JITO_MEV_FILE)
    jito_mev = {}
    for row in jito_rows:
        ep = int(row.get("epoch", 0))
        jito_mev[ep] = row
    print(f"    Jito MEV: {len(jito_mev)} epochs ({min(jito_mev) if jito_mev else '?'}-{max(jito_mev) if jito_mev else '?'})")

    # ── 8. Merge all sources ────────────────────────────────
    print("\n  Merging sources...")

    # Collect all unique epoch numbers (from all sources)
    all_epochs = sorted(set(
        list(trillium.keys()) + list(dune_epochs.keys())
        + list(solana_compass.keys()) + list(jito_mev.keys())
    ))
    print(f"    Total unique epochs: {len(all_epochs)} ({min(all_epochs)}-{max(all_epochs)})")

    merged = []
    for ep in all_epochs:
        t = trillium.get(ep, {})      # Trillium data (primary)
        d = dune_epochs.get(ep, {})    # Dune epoch economics
        v = dune_validators.get(ep, {})  # Dune commission/validators
        s = dune_stake.get(ep, {})     # Dune active stake

        # === Core identifiers ===
        row = {"epoch": ep}

        # === Date/timing (prefer Trillium, fallback Dune) ===
        epoch_date = t.get("min_block_time_calendar", "") or ""
        if not epoch_date and d.get("block_time"):
            epoch_date = d["block_time"][:10]  # "2021-02-10 15:46:44.000 UTC" → "2021-02-10"
        elif epoch_date:
            epoch_date = epoch_date[:10]  # "2026-03-01T11:01:18" → "2026-03-01"
        row["epoch_date"] = epoch_date
        row["epoch_end_date"] = (t.get("max_block_time_calendar") or "")[:10]
        row["elapsed_time_minutes"] = safe_float(t.get("elapsed_time_minutes"))
        row["epochs_per_year"] = safe_float(t.get("epochs_per_year"))

        # === MEV breakdown (Trillium only, epochs 553+) ===
        row["total_mev_earned"] = safe_float(t.get("total_mev_earned"))
        row["mev_to_validator"] = safe_float(t.get("total_mev_to_validator"))
        row["mev_to_stakers"] = safe_float(t.get("total_mev_to_stakers"))
        row["mev_to_jito_block_engine"] = safe_float(t.get("total_mev_to_jito_block_engine"))
        row["mev_to_jito_tip_router"] = safe_float(t.get("total_mev_to_jito_tip_router"))

        # === Fees (prefer Trillium, fallback Dune) ===
        row["priority_fees"] = safe_float(t.get("total_validator_priority_fees")) or safe_float(d.get("fee_reward"))
        row["signature_fees"] = safe_float(t.get("total_validator_signature_fees"))
        row["block_rewards"] = safe_float(t.get("total_block_rewards"))

        # === Inflation (prefer Trillium, fallback Dune) ===
        row["inflation_reward"] = safe_float(t.get("total_total_inflation_reward")) or safe_float(d.get("inflationary_reward"))
        row["inflation_rate"] = safe_float(t.get("inflation_rate"))

        # === MEV from Dune (for pre-Trillium epochs) ===
        if row["total_mev_earned"] is None:
            row["total_mev_earned"] = safe_float(d.get("mev_reward"))

        # === Total rewards (compute) ===
        inf = row["inflation_reward"] or 0
        fee = row["priority_fees"] or 0
        mev = row["total_mev_earned"] or 0
        sig = row["signature_fees"] or 0
        row["total_reward_sol"] = inf + fee + mev + sig

        # === SOL Price (prefer Trillium, then CoinGecko by date, then Dune) ===
        sol_price = safe_float(t.get("sol_price_usd"))
        if sol_price is None and epoch_date and epoch_date in cg_prices:
            sol_price = cg_prices[epoch_date]["cg_sol_price_usd"]
        if sol_price is None:
            # Derive from Dune: total_reward_usd / total_reward
            dune_usd = safe_float(d.get("total_reward_usd"))
            dune_sol = safe_float(d.get("total_reward"))
            if dune_usd and dune_sol and dune_sol > 0:
                sol_price = dune_usd / dune_sol
        row["sol_price_usd"] = sol_price

        # === USD values (computed) ===
        if sol_price and sol_price > 0:
            row["total_reward_usd"] = round(row["total_reward_sol"] * sol_price, 2)
            row["priority_fees_usd"] = round(fee * sol_price, 2) if fee else None
            row["mev_earned_usd"] = round(mev * sol_price, 2) if mev else None
            row["inflation_reward_usd"] = round(inf * sol_price, 2) if inf else None
        else:
            row["total_reward_usd"] = safe_float(d.get("total_reward_usd"))
            row["priority_fees_usd"] = None
            row["mev_earned_usd"] = None
            row["inflation_reward_usd"] = None

        # === APY (prefer Trillium) ===
        row["compound_overall_apy"] = safe_float(t.get("avg_compound_overall_apy")) or safe_float(d.get("total_apy"))
        row["compound_inflation_apy"] = safe_float(t.get("avg_total_compound_inflation_apy"))
        row["compound_mev_apy"] = safe_float(t.get("avg_total_compound_mev_apy")) or safe_float(d.get("mev_apy"))
        row["compound_block_reward_apy"] = safe_float(t.get("avg_total_compound_block_rewards_apy"))
        row["delegator_apy"] = safe_float(t.get("avg_delegator_compound_total_apy"))
        row["validator_apy"] = safe_float(t.get("avg_validator_compound_total_apy"))
        row["issue_apy"] = safe_float(d.get("issue_apy"))

        # === Network (prefer Trillium, fallback Dune) ===
        row["active_validators"] = safe_float(t.get("total_active_validators")) or safe_float(v.get("validator_count"))
        row["active_stake_sol"] = safe_float(t.get("total_active_stake")) or safe_float(s.get("active_stake_sol"))
        row["avg_commission_rate"] = safe_float(v.get("avg_commission_rate"))
        row["stake_account_count"] = safe_float(v.get("stake_account_count"))

        # === Compute Units (Trillium only) ===
        row["avg_cu_per_block"] = safe_float(t.get("avg_cu_per_block"))
        row["total_cu"] = safe_float(t.get("total_cu"))
        row["avg_cu_per_user_tx"] = safe_float(t.get("avg_cu_per_user_tx"))
        row["priority_fee_per_10m_cu"] = safe_float(t.get("avg_priority_fee_per_10m_cu"))
        row["mev_per_10m_cu"] = safe_float(t.get("avg_mev_per_10m_cu"))

        # === Transactions (Trillium only) ===
        row["total_user_tx"] = safe_float(t.get("total_user_tx"))
        row["total_vote_tx"] = safe_float(t.get("total_vote_tx"))
        row["total_blocks"] = safe_float(t.get("total_blocks_produced"))

        # === Fee composition (computed) ===
        total_fees = fee + sig
        if total_fees > 0 and row["total_reward_sol"] > 0:
            row["fee_pct_of_reward"] = round(total_fees / row["total_reward_sol"] * 100, 4)
        else:
            row["fee_pct_of_reward"] = safe_float(d.get("fee_percent"))
        if fee > 0 and mev > 0:
            row["mev_to_fee_ratio"] = round(mev / fee, 4)
        else:
            row["mev_to_fee_ratio"] = None

        # === Annualized estimates (computed for Trillium epochs) ===
        epy = row["epochs_per_year"]
        if epy and epy > 0:
            row["annual_priority_fees_sol"] = round(fee * epy, 2) if fee else None
            row["annual_mev_sol"] = round(mev * epy, 2) if mev else None
            row["annual_inflation_sol"] = round(inf * epy, 2) if inf else None
            if sol_price and sol_price > 0:
                row["annual_priority_fees_usd"] = round(fee * epy * sol_price, 2) if fee else None
                row["annual_mev_usd"] = round(mev * epy * sol_price, 2) if mev else None
            else:
                row["annual_priority_fees_usd"] = None
                row["annual_mev_usd"] = None
        else:
            row["annual_priority_fees_sol"] = None
            row["annual_mev_sol"] = None
            row["annual_inflation_sol"] = None
            row["annual_priority_fees_usd"] = None
            row["annual_mev_usd"] = None

        # === Solana Compass cross-check (epochs with SC data) ===
        sc = solana_compass.get(ep, {})
        row["sc_priority_fees_sol"] = safe_float(sc.get("total_priority_fees_sol"))
        row["sc_jito_tips_sol"] = safe_float(sc.get("total_jito_tips_sol"))
        row["sc_all_fees_sol"] = safe_float(sc.get("total_all_fees_sol"))
        row["sc_base_fees_sol"] = safe_float(sc.get("total_base_fees_sol"))
        row["sc_non_vote_txns"] = safe_float(sc.get("total_non_vote_txns"))
        row["sc_total_txns"] = safe_float(sc.get("total_txns"))
        row["sc_total_cu"] = safe_float(sc.get("total_cu"))
        row["sc_total_slots"] = safe_float(sc.get("total_slots"))
        row["sc_skipped_slots"] = safe_float(sc.get("total_skipped_slots"))
        row["sc_validator_count"] = safe_float(sc.get("validator_count"))

        # === Jito Foundation cross-check (official MEV) ===
        jm = jito_mev.get(ep, {})
        row["jito_official_mev_sol"] = safe_float(jm.get("jito_total_mev_sol"))
        row["jito_stake_weight"] = safe_float(jm.get("jito_stake_weight_lamports"))

        # === Data source flag ===
        sources = []
        if t: sources.append("trillium")
        if d: sources.append("dune")
        if sc: sources.append("sc")
        if jm: sources.append("jito")
        row["source"] = "+".join(sources) if sources else "none"

        merged.append(row)

    # ── 7. Define output columns ────────────────────────────
    output_columns = [
        # Core
        "epoch", "epoch_date", "epoch_end_date", "elapsed_time_minutes", "epochs_per_year",
        # MEV
        "total_mev_earned", "mev_to_validator", "mev_to_stakers",
        "mev_to_jito_block_engine", "mev_to_jito_tip_router",
        # Fees
        "priority_fees", "signature_fees", "block_rewards",
        # Inflation
        "inflation_reward", "inflation_rate",
        # Totals
        "total_reward_sol", "total_reward_usd",
        # USD breakdowns
        "priority_fees_usd", "mev_earned_usd", "inflation_reward_usd",
        # Price
        "sol_price_usd",
        # APY
        "compound_overall_apy", "compound_inflation_apy", "compound_mev_apy",
        "compound_block_reward_apy", "delegator_apy", "validator_apy", "issue_apy",
        # Network
        "active_validators", "active_stake_sol", "avg_commission_rate", "stake_account_count",
        # CU
        "avg_cu_per_block", "total_cu", "avg_cu_per_user_tx",
        "priority_fee_per_10m_cu", "mev_per_10m_cu",
        # Transactions
        "total_user_tx", "total_vote_tx", "total_blocks",
        # Computed
        "fee_pct_of_reward", "mev_to_fee_ratio",
        # Annualized
        "annual_priority_fees_sol", "annual_mev_sol", "annual_inflation_sol",
        "annual_priority_fees_usd", "annual_mev_usd",
        # Solana Compass cross-check
        "sc_priority_fees_sol", "sc_jito_tips_sol", "sc_all_fees_sol", "sc_base_fees_sol",
        "sc_non_vote_txns", "sc_total_txns", "sc_total_cu",
        "sc_total_slots", "sc_skipped_slots", "sc_validator_count",
        # Jito Foundation cross-check
        "jito_official_mev_sol", "jito_stake_weight",
        # Meta
        "source",
    ]

    # ── 8. Save ─────────────────────────────────────────────
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns, delimiter=CSV_DELIMITER, extrasaction="ignore")
        writer.writeheader()
        for row in merged:
            # Convert None to empty string for CSV
            clean = {k: ("" if v is None else v) for k, v in row.items()}
            writer.writerow(clean)

    print(f"  Saved: {OUTPUT_FILE} ({len(merged)} rows, {len(output_columns)} columns)")

    # ── 9. Summary stats ────────────────────────────────────
    trillium_epochs = [r for r in merged if "trillium" in str(r.get("source", ""))]
    dune_only = [r for r in merged if r.get("source") == "dune"]

    print(f"\n  Summary:")
    print(f"    Trillium-enriched epochs: {len(trillium_epochs)}")
    print(f"    Dune-only epochs: {len(dune_only)}")

    # Latest epoch stats
    if merged:
        last = merged[-1]
        print(f"\n  Latest epoch ({last['epoch']}):")
        print(f"    SOL price: ${last.get('sol_price_usd')}")
        print(f"    Priority fees: {last.get('priority_fees')} SOL")
        print(f"    MEV earned: {last.get('total_mev_earned')} SOL")
        print(f"    Inflation: {last.get('inflation_reward')} SOL")
        print(f"    Overall APY: {last.get('compound_overall_apy')}%")
        print(f"    Active stake: {last.get('active_stake_sol')} SOL")
        if last.get("annual_priority_fees_usd"):
            print(f"    Annualized priority fees: ${last['annual_priority_fees_usd']:,.0f}")
        if last.get("annual_mev_usd"):
            print(f"    Annualized MEV: ${last['annual_mev_usd']:,.0f}")


if __name__ == "__main__":
    print("\n=== Building Solana Epoch Database ===")
    build()
    print("Done.")
