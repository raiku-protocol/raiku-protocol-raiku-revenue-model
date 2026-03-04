# RAIKU Revenue Estimation Model

## Objective

Estimate RAIKU's future protocol revenues from two auction types:
- **AOT (Ahead-of-Time)** — sealed-bid blockspace reservations
- **JIT (Just-in-Time)** — real-time tip-based transaction ordering

Revenue formula: `Protocol Revenue = Total Auction Revenue × Take Rate (1-5%)`

## Architecture

```
Python = computation engine │ Google Sheets = presentation layer

01_EXTRACT                  02_TRANSFORM              03_MODEL                04_OUTPUT
──────────────────          ──────────────            ──────────────          ──────────────

Trillium API ─────┐         Merge on epoch key        JIT Revenue Model      Google Sheets
  (PRIMARY)       │         Cross-check sources        ──────────────        (formatted,
  141 fields/     │         Build processed CSV         Total Jito tips ×    shareable,
  epoch           │                                     × protocol fee       scenarios)
                  │
Jito Foundation ──┤         data/processed/            AOT Revenue Model
  (CROSS-CHECK)   │         └── solana_epoch_db.csv    ──────────────
  MEV rewards     │                                     Top-down + Bottom-up
  per epoch       │                                     6 customer archetypes
                  │                                     Scenario matrix
Solana Compass ───┤
  (CROSS-CHECK)   │
  Per-validator   │
  aggregated      │
                  │
Dune Analytics ───┤
  (SECONDARY)     │
  Fee/CU by       │
  program,        │
  daily fees      │
                  │
CoinGecko ────────┘
  (COMPLEMENT)
  FDV, SOL price
```

## Data Sources

| Source | Role | Data | Coverage | Status |
|--------|------|------|----------|--------|
| **Trillium API** | PRIMARY | Epoch economics, MEV breakdown, APY, validators, CU stats | 383 epochs (552–934) | ✅ Extracted |
| **Jito Foundation API** | Cross-check | Official Jito MEV rewards per epoch | 541 epochs (390–934) | ✅ Extracted |
| **Solana Compass API** | Cross-check | Per-validator aggregated fees, slots, CU | 128 epochs (800–935) | ✅ Extracted |
| **Dune** (6773409) | Secondary | Epoch rewards, fees, MEV (epochs 150–935) | 785 epochs | ✅ Extracted |
| **Dune** (6773227) | Secondary | Validator commissions, count | 785 epochs | ✅ Extracted |
| **Dune** (6776267) | Secondary | Active stake per epoch | 785 epochs | ✅ Extracted |
| **Dune** (6777333) | Unique | Fee/CU by program (7-day, 50 programs) | 50 programs | ✅ Extracted |
| **Dune** (6777334) | Unique | Daily priority fees (91 days) | 91 days | ✅ Extracted |
| **CoinGecko** | Complement | SOL price, FDV (365 days) | 365 days | ✅ Extracted |

**Merged database**: 786 rows × 60 columns (epochs 150–935)

### Why 5 Sources?

**Trillium** is the primary source (141 fields/epoch, free, no auth) — MEV breakdown, APY components, CU stats, priority fees. **Jito Foundation** provides the official Jito MEV data — perfectly matches Trillium (ratio 1.000x), confirming data integrity. **Solana Compass** includes all fees (vote + non-vote), giving a ~2.15x ratio vs Trillium — useful for understanding the full fee landscape. **Dune** provides unique data: per-program fee/CU breakdown and daily granularity. **CoinGecko** fills in FDV/market cap.

### Cross-Check Results

| Comparison | Ratio | Interpretation |
|-----------|-------|----------------|
| Jito Foundation / Trillium (MEV) | **1.000x** | Perfect match — both measure the same Jito tips |
| Solana Compass / Trillium (priority fees) | **~2.15x** | SC includes ALL tx fees (vote + non-vote), Trillium = non-vote only |

Trillium's non-vote priority fees are the correct measure for RAIKU's revenue model — only non-vote fees are relevant.

### Reserved for later (if needed)

| Source | Use case | Why deferred |
|--------|----------|--------------|
| **Token Terminal for Sheets** | Protocol revenues (Jito DAO fees, Jupiter fees, etc.) | Not needed for core revenue model. Useful later for competitive benchmarking. |
| **BigQuery × Token Terminal** | Transaction-level deep dive (decoded Solana instructions) | Heavy setup (GCP). Only needed for granular customer archetype sizing. |

## Project Structure

```
raiku-revenue-model/
├── CLAUDE.md              ← Complete project guide (for Claude Code)
├── README.md              ← This file (for humans)
├── config.py              ← API keys (.env), business parameters, scenarios
├── run_pipeline.py        ← Master entry point
│
├── 01_extract/            ← Data extraction (API calls)
│   ├── extract_trillium.py      ← PRIMARY (epochs 552–934, 383 epochs) ✅
│   ├── extract_jito_mev.py      ← Jito Foundation MEV (epochs 390–934, 541 epochs) ✅
│   ├── extract_solana_compass.py ← Solana Compass (epochs 800–935, 128 epochs) ✅
│   ├── dune_client.py           ← Dune API wrapper
│   ├── dune_epochs.py           ← Epoch economics (query 6773409)
│   ├── dune_validators.py       ← Commission/validators (query 6773227)
│   ├── dune_active_stake.py     ← Active stake (query 6776267)
│   └── coingecko_prices.py      ← SOL price + FDV
│
├── 02_transform/          ← Merge & compute
│   └── build_database.py      ← Merge all 5 sources → processed CSV (786 rows × 60 cols)
│
├── 03_model/              ← Revenue estimation
│   ├── aot_revenue.py         ← AOT: top-down + bottom-up (6 archetypes)
│   └── jit_revenue.py         ← JIT: Total Jito tips × share × fee
│
├── 04_output/             ← Google Sheets export (Phase 4 — TODO)
│
├── data/
│   ├── raw/               ← Extracted CSVs (never edit, re-extractable)
│   │   ├── trillium_epoch_data.csv          (383 epochs, 552–934)
│   │   ├── jito_mev_rewards.csv             (541 epochs, 390–934)
│   │   ├── solana_compass_epochs.csv        (128 epochs, 800–935)
│   │   ├── dune_epoch_data_v2.csv           (785 rows, epochs 150–935)
│   │   ├── dune_commission_validators_v2.csv (785 rows)
│   │   ├── dune_active_stake_v1.csv         (785 rows)
│   │   ├── dune_fee_per_cu_by_program.csv   (50 programs, 7-day)
│   │   ├── dune_daily_priority_fees.csv     (91 days)
│   │   └── coingecko_sol_price.csv          (365 days)
│   └── processed/         ← Generated by Python (gitignored)
│       ├── solana_epoch_database.csv        (786 rows × 60 cols)
│       ├── aot_revenue_scenarios.csv        (302 scenarios)
│       └── jit_revenue_scenarios.csv        (40 scenarios)
│
└── docs/                  ← 7 RAIKU internal documents (read-only)
```

## Setup

```bash
# Python 3.10+
pip install requests pandas python-dotenv

# Create .env with your API keys
echo "DUNE_API_KEY=your_key_here" > .env

# Run full extraction pipeline
python 01_extract/extract_trillium.py --full
python 01_extract/extract_jito_mev.py --full
python 01_extract/extract_solana_compass.py --full
python 02_transform/build_database.py
```

## Execution Plan

1. **Phase 1** ✅ — Enrich Solana database: Extract Trillium + Jito + SC → merge with Dune → processed CSV (786 rows × 60 cols)
2. **Phase 2** (partial) — RAIKU-specific data: MEV breakdown ✅, fee/CU by program ✅, validator economics (TODO)
3. **Phase 3** ✅ — Revenue model: JIT + AOT (top-down + bottom-up) + scenario matrix
4. **Phase 4** (TODO) — Output: Google Sheets (presentation, scenarios, sensitivity analysis)

## API Coverage Summary

```
Epoch:  150────────────390──────────552──────800──────934/935
        │               │            │        │        │
Dune:   ████████████████████████████████████████████████  785 epochs
Jito:                   ██████████████████████████████    541 epochs
Trillium:                            █████████████████    383 epochs
SC:                                          █████████    128 epochs
```

## Key Business Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Protocol take rate | 5% (range 1-5%) | Post-TGE Design |
| Validator share | 95% (96.5% high perf) | Post-TGE Design |
| P(Inclusion) AOT vs Standard | 0.89 vs 0.40 | Mainnet doc |
| Jito 2025 total tips | ~$720M | Post-TGE Design |
| Conservative MEV base | $100M/year (Q4-25 ann.) | Post-TGE Design |
| TGE target | Q4 2026 | Post-TGE Design |
