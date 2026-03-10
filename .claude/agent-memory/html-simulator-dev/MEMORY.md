# HTML Simulator Dev — Agent Memory

## Key File Facts
- Path: `C:\Users\Utilisateur\Dev-RAIKU\raiku-revenue-model\raiku_revenue_simulator.html`
- Size: ~2683 lines (self-contained, zero runtime fetches)
- Always grep before reading — file is large

## Major Function Line Ranges (approximate, verify with grep)
- Slider controls HTML: lines 463–560
- Methodology text (Model Constants): lines 962–973
- `gp()` (get params): lines 1251–1262
- `calc()` (waterfall math): lines 1296–1337
- `update()` (DOM writes): lines 1706–1800+
- Scenario presets `SC`: lines 1202–1211

## Slider IDs → gp() field mapping
- `sl-comm` → `p.c` (protocol take rate %, raw e.g. 5)
- `sl-rebate-aot` → `p.ra` (AOT rebate %, raw e.g. 0.25)
- `sl-rebate-jit` → `p.rj` (JIT rebate %, raw e.g. 0.25)
- `sl-val-bonus` → `p.vb` (AOT validator bonus %, raw e.g. 1.0)
- `sl-jit-market` → `p.jm` (JIT total market SOL/yr)
- `sl-jit` → `p.j` (JIT share, divided by 100 in gp())
- `sl-stake` → `p.s` (stake %, divided by 100)
- `sl-blk` → `p.b` (block %, divided by 100)
- `sl-fcu` → `p.f` (fee per CU, lamports)
- `sl-price` → `p.p` (SOL price USD)

## Waterfall Model (corrected 2026-03-10)
The correct revenue waterfall implemented in `calc()`:
1. `cR = p.c / 100` (take rate as decimal)
2. Guard clamps: `jitRebateRate = min(rj/100, cR)`, `aotRebateRate = min(ra/100, cR)`, `aotBonusRate = min(vb/100, cR - aotRebateRate)` — all zero if cR=0
3. JIT: `jitProtocol = jitGross * cR - jitRebate` (no validator bonus on JIT)
4. AOT: `aotProtocol = aotGross * cR - aotRebate - aotValBonus`
5. Guard message element: `id="waterfall-guard-msg"` (shown by update())

## CSS Pattern
- CSS vars at top of `<style>` block
- Guard/warning color: `#F5A623` (amber)
- Secondary text: `var(--text2)`

## Chart.js
- Version 4.5.1 via CDN — NEVER change
- Chart instances: `cE, cA, cP, cF`
- Update after data changes: `chart.update()`

## 6 Data Objects (inline, never extract)
`D.a`, `D.e`, `D.p`, `D.daily`, `D.dailyNet`, `D_JITO`
