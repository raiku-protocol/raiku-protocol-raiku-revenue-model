# RAIKU Revenue Model — Lessons Learned

> **Instruction for Claude**: Read this file at the start of every session.
> After any correction from the user, add an entry here.
> Format: `## [Category]` → `**Mistake**:` → `**Rule**:`

---

## CSV / Data

**Mistake**: Using comma as CSV delimiter.
**Rule**: Always use **semicolon** (`;`) as delimiter. UTF-8 encoding. See `config.py`.

**Mistake**: Manually editing files in `data/raw/`.
**Rule**: `data/raw/` is read-only. These files are produced by extraction scripts and re-extractable from source APIs.

**Mistake**: Modifying `data/mapping/program_categories.csv`.
**Rule**: This file is **SACRED**. Manual classification of 314 programs. Never touch without explicit instruction.

---

## APIs — Known Behaviors

**Jito Foundation API**:
**Rule**: Always use **POST**, never GET. `POST https://kobe.mainnet.jito.network/api/v1/mev_rewards` with body `{"epoch": N}`. GET only returns the latest epoch.

**Trillium API**:
**Rule**: Epoch 551 = 404 (unavailable). Epoch 552 = first valid epoch. Epoch 935+ = 404 (not yet indexed). No authentication required.

**Solana Compass API**:
**Rule**: Epochs 801, 803-809 = **permanently unavailable** (HTTP errors). Use 3 retries, 60s timeout. Returns a per-validator array — must aggregate (SUM). All values in lamports (÷1e9 for SOL).

**Dune Analytics**:
**Rule**: Use existing `dune_client.py` wrapper (stdlib urllib, no `requests`). Never rewrite the wrapper. API key in `config.py` via `.env`.

---

## HTML Simulator

**Mistake**: Modifying the simulator without reading the relevant section first.
**Rule**: The active simulator lives in the separate `raiku-simulator` repo as `index.html`. Always search for the specific function/variable first, then read only the relevant lines.

**Mistake**: Treating the legacy inline-data simulator architecture as the current one.
**Rule**: The active simulator is artifact-driven on the AOT side (`data/aot_programs.v1.js`). Legacy inline `D.p` notes apply only to `raiku_revenue_simulator.html`, which is now a historical snapshot.

**Mistake**: Changing the Chart.js version.
**Rule**: Chart.js **4.5.1** via CDN. Never change the version without explicit instruction.

**Mistake**: Injecting data through any mechanism other than `inject_daily_data.py`.
**Rule**: Temporal data injection for the legacy inline simulator goes through Pipeline B: `download_dune_daily_C.py` → `build_daily_temporal.py` → `inject_daily_data.py`. Do not confuse that path with the separate AOT artifact flow used by the active simulator.

---

## Python Pipeline

**Mistake**: Importing `requests` in a new script.
**Rule**: **stdlib only**. Use `urllib.request` / `urllib.parse`. See pattern in `dune_client.py` and `extract_trillium.py`.

**Mistake**: Hardcoding derived values in Python scripts.
**Rule**: Python is primarily the extraction / transform / artifact-preparation layer. Do not move core simulator business logic upstream unless explicitly requested.

**Mistake**: Running the full pipeline to test a single module.
**Rule**: Use flags: `--model-only` (models only), `--full-extract` (force full re-extraction), `--export` (with Sheets).

**Mistake**: Modifying columns A-W of the epoch DB without updating both `build_database.py` AND `PLAN_COMPLET.md`.
**Rule**: The 23 RAW columns (A-W) are documented in `PLAN_COMPLET.md`. Any change must be consistent across `build_database.py`, `PLAN_COMPLET.md`, and `DATA_LINEAGE.md`.

---

## Revenue Models

**Mistake**: Confusing Trillium `priority_fees_sol` (non-vote only) with Solana Compass (vote + non-vote).
**Rule**: For the RAIKU model, always use **Trillium `priority_fees_sol`** (non-vote only). The SC/Trillium ratio ≈ 2.15x is expected and documented.

**Mistake**: Modifying hardcoded protocol constants without verification.
**Rule**: The **only** allowed hardcoded constants are: take rate 1-5%, validator share 95-99%, RAIKU token supply 1B. Everything else is a scenario parameter.

---

## Program Classification

**Mistake**: Prefix-inferred names like "Forge Protocol" or "Fragment Protocol" assumed to be real without verification.
**Rule**: Program names derived from address prefixes are **NOT real names**. Always verify on Solscan before keeping. If unverifiable, use pattern `"Trading Bot (prefix)"` or `"Unknown (prefix)"`.

**Mistake**: Leaving `raiku_product` empty for auto-classified programs.
**Rule**: Every program in `program_categories.csv` MUST have a `raiku_product` value. For `unknown` category with high CU: use `potential`. For known categories: derive from `TAXONOMY[category]["raiku_product"]`.

**Mistake**: Trying to write to a file open in VS Code on Windows.
**Rule**: VS Code locks files with exclusive OS-level locks on Windows. Cannot `cp`, `mv`, or `open(..., 'w')`. Must close the VS Code tab first.

---

## External APIs — Identification Sources

**SolanaFM API**: Persistently returns 502 Bad Gateway (as of 2026-03-11). Not reliable.
**Solscan API (api.solscan.io)**: DNS resolution fails from this Windows VM. Use Firecrawl scraping of `solscan.io/account/{address}` instead.
**Dune solana.labels**: Requires query execution credits. When out of credits, cannot look up program names.
**OtterSec verify.osec.io**: Only covers ~200 verified programs. Most are already known (Jupiter, Raydium, etc.).
**SolWatch (lead_pipeline_sheet.xlsx)**: 20630 rows but only matches ~1 unknown program (Pyth Receiver). Low hit rate for unknowns.

---

## Dune Query Patterns

**Mistake**: Using `SUM(fee)` for both `total_fees_sol` and `priority_fees_sol` in `SQL_AGGREGATE` (extract_dune_programs.py lines 57-58).
**Rule**: `fee` in `solana.transactions` = base + priority combined. Must derive: `base = required_signatures * 5000`, `priority = fee - required_signatures * 5000`. The `dune_program_fees_aggregate.csv` column `priority_fees_sol` is actually total fees — a known data quality bug.

**Mistake**: Using `cardinality(signatures)` for signature count.
**Rule**: Use `required_signatures` (integer) — it's a native column, cleaner and more reliable.

**Mistake**: Using `amount` as column name in `system_program_solana.system_program_call_transfer`.
**Rule**: The column is `lamports` (uint256), not `amount`. Also, table name is lowercase `transfer` (Trino is case-insensitive, but document correctly).

**Dune accounts**: Two accounts exist. Compte A (@syhmeon) = 0 community credits, MCP-authenticated. Compte B (@syh) = has credits, API key in `.env`. MCP `createDuneQuery` uses @syhmeon; must set query to public (`is_private: false`) so Compte B can execute it via REST API.

**Dune credits**: Community plan = 2500 credits/month, resets ~6th of month. @syhmeon exhausted. @syh (Compte B) is the active execution account.

**Jito JOIN feasibility**: JOIN with `system_program_call_transfer` works on 48h windows (proven by @ilemi query 4314734). 30d = guaranteed timeout. If 48h times out, try 24h.

---

## Git / GitHub

**Rule**: Always verify `data/processed/` is in `.gitignore` before pushing (large generated files).
**Rule**: Check that no API keys are visible in any file before pushing (use `security-auditor`).

---

## Revenue Model — Core Waterfall Correction

> Recorded: 2026-03-10. ✅ IMPLEMENTED 2026-03-10.
> Status: Implemented in simulator (separate AOT/JIT panels, guard logic, ratio display) + Python models (jit_revenue.py, aot_revenue.py, sanity_check.py) + config.py.

**Mistake**: Rebates and validator bonus were applied directly on gross revenue, not constrained by the protocol take.

**Rule**: The correct revenue waterfall is strictly:

```
Gross Revenue = 100

Step 1 — Split gross revenue:
  Validator Base    = Gross Revenue × (1 - Protocol Take Rate)
  Protocol Pool     = Gross Revenue × Protocol Take Rate

Step 2 — Protocol redistributes its own pool:
  Customer Rebate   = funded from Protocol Pool
  Validator Bonus   = funded from Protocol Pool (AOT only)
  Raiku Treasury    = Protocol Pool − Rebate − Validator Bonus

Step 3 — Total check:
  Validator Base + Rebate + Validator Bonus + Raiku Treasury = Gross Revenue ✓
```

**Example (take rate = 5%, rebate = 1%, validator bonus = 0%)**:
```
Protocol Pool     = 5.00
Validator Base    = 95.00
Customer Rebate   = 1.00   (out of the 5, not out of 100)
Raiku Treasury    = 4.00
Total             = 100.00 ✓
```

**Guard rule**: If Protocol Take Rate = 0%, then Rebate = 0 and Validator Bonus = 0 must be enforced. The model must not allow positive rebate or bonus when there is no protocol pool to fund them.

**AOT vs JIT separation**:
- AOT: has Protocol Take Rate + Customer Rebate + Validator Bonus (separate parameter panel)
- JIT: has Protocol Take Rate + Customer Rebate only (no Validator Bonus)
- Both follow the same top-level waterfall rule

**Naming correction**:
- Rename "commission" → "Protocol Take Rate" everywhere (simulator labels, sliders, tooltips, Python variable names, documentation)

**Economic interpretation**:
- 1% rebate on gross = 20% of the protocol take (when take rate = 5%)
- The simulator should make this ratio explicit for clarity

**Files that must be updated when implemented**:
- `raiku-simulator/index.html` — active simulator labels, waterfall formula, guard logic, AOT/JIT separation
- `03_model/jit_revenue.py` — waterfall logic
- `03_model/aot_revenue.py` — waterfall logic + validator bonus handling
- `CLAUDE.md` → Protocol Constants section
- `DATA_LINEAGE.md` — if output column names change
