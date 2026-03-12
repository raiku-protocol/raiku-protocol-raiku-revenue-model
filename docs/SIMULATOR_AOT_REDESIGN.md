# Simulator AOT Redesign (Frozen Decision Memory)

Last updated: 2026-03-12  
Status: Analytical design frozen, implementation pending

## 1. Validated Analytical Scope

Canonical inputs for this redesign:

- `data/mapping/program_categories.csv`
- `data/processed/program_database.csv`

Join key:

- `program_id`

Product scope semantics:

- In scope for core simulator customer analysis: `aot`, `both`
- In scope for benchmark analysis: `jit` (`raiku_category = arb_bot`)
- Excluded from core analysis: `neither`, `potential`
- Current taxonomy convention: `potential` maps operationally to `unknown`

Main category basis for simulator logic:

- Use top-level `raiku_category` as primary display layer.
- Do not use subcategory as the primary layer, except for internal `dex` sub-breakdown.

## 2. Prop AMM Validation (Strategic Category)

Canonical 14-program list audited:

- BisonFi, HumidiFi, AlphaQ, Aquifer, GoonFi V2, Obric V2, Scorch, SolFi V2, Tessera V, WhaleStreet, ZeroFi, Lifinity, SolFi, GoonFi v1

Summary:

- Present in taxonomy and economics with usable data: 10
- Present in taxonomy, absent from current economics window: 4 (`GoonFi V2`, `Scorch`, `Tessera V`, `Lifinity`)
- Economically dominant names in current window: `BisonFi`, `HumidiFi`
- Outlier caution: `WhaleStreet` has very high fee/CU with small CU base

Category-level signal (`prop_amm`, core scope):

- CU-weighted non-base fee/CU: `7.249875`
- CU-weighted total fee/CU: `23.578861`
- Median non-base fee/CU: `2.289923`
- p25/p75 non-base fee/CU: `0.263943 / 3.698523`

## 3. Final Category Display Structure

### 3.1 Categories shown directly

- `prop_amm`
- `dex` (with required sub-breakdown)
- `lending`
- `oracle`
- `bridge`
- `perps`

### 3.2 Categories grouped into long tail

- `cranker + depin + payments` shown as one grouped block

### 3.3 Benchmark shown separately

- `arbitrage_bot` (`jit`) shown as benchmark only

### 3.4 Excluded from primary AOT display

- `neither` and `potential` populations
- `unknown` and `other` in primary story
- `market_maker` (not currently present as a top-level taxonomy category)

## 4. DEX Sub-Breakdown Logic (Mandatory)

Within top-level `dex`, show three components:

- `aggregator`
- `amm_family` = `amm + clmm + dlmm + pool + stableswap + bonding_curve + swap + liquidity + launchpad`
- `orderbook`

Metrics (`aot + both` scope):

| DEX component | Programs | Usable programs | Total CU | Non-base fees | Total fees | CU-w non-base fee/CU | CU-w total fee/CU | Median non-base fee/CU | p25/p75 non-base fee/CU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| aggregator | 12 | 8 | 425,954,864,193 | 171.123148 | 188.282073 | 0.401740 | 0.442024 | 0.117172 | 0.007768 / 0.590972 |
| amm_family | 27 | 17 | 622,773,703,022 | 266.771888 | 337.049218 | 0.428361 | 0.541207 | 0.243199 | 0.000223 / 0.339594 |
| orderbook | 8 | 6 | 10,681,914,251 | 6.508667 | 10.698037 | 0.609317 | 1.001509 | 0.103041 | 0.004531 / 0.649408 |

## 5. Core vs Benchmark Distinction (Jito-Aware)

Required analytical split:

1. AOT/Both with positive Jito fees
2. Arbitrage/searcher/bot-style with positive Jito fees
3. AOT/Both with zero Jito fees

Current validated counts:

- AOT/Both with positive Jito: `34` (non-bot subset: `31`)
- Bot-style positive Jito: `24` (strict `arb_bot` subset: `21`)
- AOT/Both with zero Jito and usable economics: `83`

Interpretation rule:

- Do not mix bot benchmark economics into core AOT customer storytelling.

## 6. Metric System (Primary, Secondary, Dispersion)

Definitions:

- Non-base fees = `priority + jito`
- Total fees = `base + priority + jito`
- Fee/CU metrics are in lamports/CU

Display policy:

- Primary: CU-weighted non-base fee/CU
- Secondary: CU-weighted total fee/CU
- Dispersion: median non-base fee/CU and p25/p75

## 7. Weighted vs Median Gap Notes

Gap classification rule:

- Small: weighted/median ratio <= 2
- Moderate: > 2 and <= 5
- Large: > 5

Current gap assessment:

- `prop_amm`: Moderate (weighted > median)
- `dex`: Moderate (weighted > median)
- `lending`: Large (weighted >> median)
- `oracle`: Large (weighted >> median)
- `bridge`: Large (median >> weighted)
- `perps`: Large (weighted >> median, near-zero median)
- `cranker`: Large (weighted >> median)

Implication:

- Any category with large gap must display a caveat/range note in UI to avoid over-interpreting a single aggregate.

## 8. Scenario Design Principles (No Hardcoded New Ladder Here)

Scenario ladder must be calibrated from artifact-observed economics, not legacy UI constants.

Principles:

- Anchor on core AOT application groups, excluding bot benchmark.
- Use CU-weighted non-base fee/CU as central anchor.
- Add dispersion guardrails from median and p25/p75.
- Keep benchmark (`arbitrage_bot`) as separate context input, not as direct core scenario driver.
- Ensure scenario text explicitly states:
  - default view = non-base (`priority + jito`)
  - comparison view = total (`base + priority + jito`)

## 9. Strict UI Spec (Locked)

### 9.1 Block order

1. Global methodology header (metric definitions and scope)
2. Core AOT category cards
3. DEX sub-breakdown panel
4. Long-tail grouped block
5. Benchmark block (`arbitrage_bot`)
6. Scenario panel
7. Caveats/dispersion legend

### 9.2 Exact core category order

1. `prop_amm`
2. `dex`
3. `lending`
4. `oracle`
5. `bridge`
6. `perps`
7. `ops_long_tail` (`cranker + depin + payments`)

### 9.3 Exact metrics per block

Each block must show:

- Primary: CU-weighted non-base fee/CU
- Secondary: CU-weighted total fee/CU
- Dispersion: median non-base fee/CU with p25/p75

### 9.4 Exact caveat/dispersion notes per block

- `prop_amm`: "Moderate dispersion; weighted mean above median."
- `dex`: "Moderate dispersion; see DEX component breakdown."
- `lending`: "Large concentration; weighted mean dominated by top programs."
- `oracle`: "Large concentration; weighted mean dominated by top programs."
- `bridge`: "Skewed volume profile; median above weighted mean."
- `perps`: "Low non-base intensity; median near zero."
- `ops_long_tail`: "Heterogeneous long tail; use as directional signal."
- `arbitrage_bot` benchmark: "Benchmark only; not part of core AOT customer pool."

### 9.5 Grouping and benchmark rules

- Grouped category block: `cranker + depin + payments`
- Separate benchmark block: `arbitrage_bot` (`jit`)
- Excluded from primary display: all `neither` and `potential`

