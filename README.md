# RAIKU Revenue Estimation Model

## Objective

Estimate RAIKU's future protocol revenues from two auction types:
- **AOT (Ahead-of-Time)** — sealed-bid blockspace reservations
- **JIT (Just-in-Time)** — real-time tip-based transaction ordering

Revenue formula: `Protocol Revenue = Total Auction Revenue × Take Rate (0-5%)`

**Primary output**: `raiku_revenue_simulator.html` — a self-contained interactive simulator with 6 embedded data objects, zero runtime fetches. Serves as the investor-facing deliverable.

## Architecture

Two independent pipelines feed the project:

### Pipeline A — Epoch Revenue Model (`run_pipeline.py`)

```
[External APIs]           [01_extract/]          [02_transform/]         [03_model/]
─────────────────         ──────────────         ──────────────          ──────────────
Trillium API ────────┐
Jito Foundation API ─┤    10 extraction          build_database.py       jit_revenue.py
Solana Compass API ──┤    scripts                build_program_conds.py  aot_revenue.py
Dune Analytics ──────┤                           build_program_db.py     sanity_check.py
CoinGecko API ───────┘
                          ↓ data/raw/            ↓ data/processed/       ↓ scenario CSVs
```

### Pipeline B — Simulator Temporal Data (`scripts/`)

```
Dune (6 batch queries) → download_dune_daily_C.py → dune_daily_program_fees_30d.csv
                       → build_daily_temporal.py  → daily_temporal_payload.js
                       → inject_daily_data.py     → raiku_revenue_simulator.html
                                                    (D.daily + D.dailyNet injected)
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

**Merged database**: `solana_epoch_database.csv` — 786 rows × 43 columns (epochs 150–935)

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
├── raiku_revenue_simulator.html  ← PRIMARY OUTPUT (self-contained, 6 inline data objects)
├── config.py                     ← API keys (.env), business parameters, scenarios
├── run_pipeline.py               ← Pipeline A orchestrator (extract → transform → model)
│
├── 01_extract/                   ← Data extraction (10 scripts, 5 APIs)
│   ├── extract_trillium.py           ← PRIMARY (epochs 552+)
│   ├── extract_jito_mev.py           ← Jito MEV rewards (epochs 390+)
│   ├── extract_solana_compass.py     ← Solana Compass (epochs 800+)
│   ├── coingecko_prices.py           ← SOL price + FDV
│   ├── dune_client.py                ← Dune API wrapper (stdlib, no requests)
│   ├── dune_epochs.py                ← Epoch economics (query 6773409)
│   ├── dune_validators.py            ← Commission/validators (query 6773227)
│   ├── dune_active_stake.py          ← Active stake (query 6776267)
│   ├── extract_dune_programs.py      ← Per-program fees (query 6783408/6783409)
│   └── extract_intraday.py           ← Trillium intraday peaks
│
├── 02_transform/                 ← Merge, enrich, classify
│   ├── build_database.py             ← All raw → solana_epoch_database.csv (786×43)
│   ├── build_program_conditions.py   ← Conditions analysis → program_conditions.csv
│   └── build_program_database.py     ← Programs + categories → program_database.csv
│
├── 03_model/                     ← Revenue estimation
│   ├── jit_revenue.py                ← JIT: Jito tips × share × fee → scenarios
│   ├── aot_revenue.py                ← AOT: top-down + bottom-up → scenarios
│   └── sanity_check.py               ← Cross-check model outputs vs on-chain data
│
├── 04_output/                    ← Google Sheets export (optional)
│   └── sheets_export.py
│
├── scripts/                      ← Pipeline B — Simulator temporal data
│   ├── download_dune_daily_C.py      ← Fetch 6 Dune batch queries → merge
│   ├── build_daily_temporal.py       ← daily_temporal_payload.js (D.daily, D.dailyNet)
│   └── inject_daily_data.py          ← Inject payload into simulator HTML
│
├── data/
│   ├── raw/                      ← Extracted CSVs (re-extractable from APIs)
│   ├── processed/                ← Generated outputs (gitignored)
│   │   ├── solana_epoch_database.csv     (786 rows × 43 cols)
│   │   ├── program_database.csv          (500 programs × 23 cols)
│   │   ├── program_conditions.csv        (55 programs × 27 cols)
│   │   ├── jit_revenue_scenarios.csv
│   │   ├── aot_revenue_scenarios.csv
│   │   └── sanity_check_report.csv
│   ├── mapping/                  ← Reference classifications (manual + enriched)
│   │   └── program_categories.csv
│   └── sql_query*.sql            ← Dune SQL templates
│
├── prompts/                      ← Dune query prompt docs
├── archive/                      ← Superseded/diagnostic files (preserved, not active)
└── docs/                         ← RAIKU internal documents (read-only)
```

## Quick Start

```bash
# Python 3.10+ (no pip install required — stdlib only)
# Create .env with API keys
echo "DUNE_API_KEY=your_key" > .env
echo "COINGECKO_API_KEY=your_key" >> .env

# Pipeline A — Core (Trillium + CoinGecko → DB → Models)
python run_pipeline.py

# Pipeline A — Full re-extraction (all sources, requires Dune credits)
python run_pipeline.py --full-extract

# Pipeline A — Models only (skip extraction/transform)
python run_pipeline.py --model-only

# Pipeline B — Simulator temporal charts (after Dune batch downloads)
cd scripts && python build_daily_temporal.py && python inject_daily_data.py

# Serve simulator locally
python -m http.server 8765   # → http://localhost:8765/raiku_revenue_simulator.html
```

## Execution Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Solana epoch database (5 sources → 786×43 merged CSV) | ✅ Complete |
| 2 | Per-program fee/CU database (500 programs, 30-day Dune) | ✅ Complete |
| 3 | Revenue models (JIT + AOT scenarios + sanity check) | ✅ Complete |
| 4 | Google Sheets export | ⬚ Deferred |
| 5 | Simulator v6 (temporal charts, daily data injection) | ✅ Complete |
| 6 | Conditions pipeline (market condition × program analysis) | ✅ Complete |

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
