# RAIKU Revenue Simulator — 20-Minute Demo Script

> **Presenter-facing script.** Timing targets per section. Real numbers from the live tool.
> **URL**: https://raiku-protocol.github.io/raiku-simulator/
> **Repos**: `raiku-protocol/raiku-simulator` (the tool) · `raiku-protocol/raiku-protocol-raiku-revenue-model` (the data pipeline)

---

## PART 1 — Context: Why We Built This *(~4 min)*

*[Simulator is open but not front and center yet. This is spoken context first.]*

---

Before we look at the tool, I want to explain why it exists.

**The problem RAIKU is solving is simple to state and expensive to ignore.**

On Solana today, when you submit a transaction — whether you're a prop AMM updating a quote, a quant desk executing a signal, or a keeper cranking a protocol — your transaction goes through four independent gates before it lands:

> Delivery × Scheduling × Execution × Finality

Under normal network conditions, the composite probability of successful inclusion is roughly **40%**. Bot transactions fail at a 58% rate. During congestion — memecoin surges, high-volatility periods — that failure rate goes above 75%.

This isn't a niche problem. The cost shows up in multiple ways: wasted priority fees on every failed retry, stale quotes leading to adverse selection, and ultimately market share loss to competitors with better execution infrastructure. HumidiFi — a PropAMM that once had 26% market share — collapsed to under 1% in ten weeks when their execution reliability degraded. The market is completely unforgiving.

**RAIKU's answer is blockspace reservation.** Two products:
- **AOT (Ahead-of-Time)**: You bid in an auction *before* you need the slot. When your signal fires, reserved compute units are waiting for you — no race, no tip escalation. Inclusion probability goes from ~40% to ~89%.
- **JIT (Just-in-Time)**: Tip-based real-time ordering for latency-sensitive flow. Similar to Jito today, but layered into the RAIKU validator infrastructure.

**So why are we building this simulator?**

Two reasons. First, **internal clarity**: before we go to market, we need to understand what the economics actually look like — what RAIKU earns, what validators earn, what the market size is. We don't want to build on optimistic assumptions. We want to build on data.

Second, **external credibility**: every number in this tool is extracted from real Solana on-chain data — 100 recent epochs, 205 programs, 30 days of daily program-level fee data. When we sit across from a potential validator partner or investor, we can show them exactly where every assumption comes from.

The simulator has four sections. Let's walk through each one.

---

## PART 2 — Block 1: Revenue Model *(~6 min)*

*[Open the simulator at https://raiku-protocol.github.io/raiku-simulator/ — it opens on Revenue Model by default.]*

---

**This is the protocol-level financial model.** The question it answers: *given a set of market conditions and adoption assumptions, how much revenue flows through RAIKU annually, and where does it go?*

### Scenario Presets

*[Point to the four buttons: Conservative, Base Case, Optimistic, Bull Case.]*

We have four pre-configured scenarios. The description below each button explains the assumptions driving it. Start on Base Case.

At a glance — what the Base Case says about **Protocol Treasury** (that's what RAIKU retains):

| Scenario | Protocol Treasury |
|---|---|
| Conservative | $190K / yr |
| Base Case | $1.5M / yr |
| Optimistic | $4.0M / yr |
| Bull Case | $17.2M / yr |

These numbers are not marketing targets. They are the output of the model given specific input assumptions — all visible and adjustable.

### Calibration Toggle: AOT Fee/CU Source

*[Point to the toggle: "30d AOT scope" vs "Long-horizon".]*

This is a detail worth explaining. The key assumption in AOT revenue is the average fee per compute unit that customers are willing to pay. We have two calibration modes:
- **30d AOT scope**: Uses observed fee/CU data from the 205 programs in our AOT target universe over the last 30 days — arb-bot activity excluded. This is the more conservative, grounded number.
- **Long-horizon**: Uses a broader historical window. More of a market potential anchor.

Base Case uses 0.60 lamports/CU — the raw observed non-base fee across included application categories. This is grounded in data, not a guess.

### Model Parameters

**Global:** SOL price ($100 in base) and Protocol Take Rate (5% for AOT, 5% for JIT). These are governance parameters — the range is 0–10%.

**Protocol Pool Distribution:** Once RAIKU takes its 5%, it redistributes:
- Customer Rebate — returned to paying customers as an incentive
- Validator Bonus (AOT only) — additive reward on top of the base validator share
- What remains = **Protocol Treasury** — the number we care most about

*[Point to the treasury summary row: "AOT treasury: 3.75% of gross · JIT treasury: 4.75% of gross"]*

**Revenue Estimation — two separate models:**

AOT uses a **3-dimensional model**: RAIKU Stake % × Block Share (CU reserved %) × Avg Auction Fee/CU. At 10% stake, 5% block share, 0.60 lam/CU — 3 million CU reserved per block, across 7.8 million RAIKU slots per year.

JIT uses a **market share model**: Total Jito MEV tip market × RAIKU's share. That total market is 812.6K SOL/yr from our data — 100 epochs of real Jito Block Engine API data, not an estimate. At 13% market share in Base Case, RAIKU captures $2.35M SOL/yr of JIT tips.

### Revenue Output

*[Point to the card row at the top of the main panel.]*

Total Gross Revenue at Base Case: **$32M/yr**. The split: $30.6M from JIT, $1.4M from AOT. JIT dominates the base case because the MEV market is large and the AOT adoption assumption is conservative.

*[Scroll down to the Sankey diagram.]*

The flow diagram shows exactly how that $32M splits: $30.4M Validator Base, $14K AOT Validator Bonus, $4K AOT Rebate, $76K JIT Rebate, **$1.5M Protocol Treasury**.

*[Scroll to Scenario Comparison.]*

The four-column comparison makes the range visible. Conservative to Bull is a 90× spread — that's an honest representation of how uncertain early-stage market sizing is. We're not hiding that.

*[Scroll to Sensitivity Table.]*

The sensitivity matrix holds everything constant except Stake % and Fee/CU. Every cell is a Protocol Treasury estimate. The current Base Case cell is highlighted. This is how we pressure-test the model — if fee/CU is lower than expected, or adoption is slower, here's what happens.

*[Scroll to Data Sources.]*

The four Fee/CU anchors are documented here: 0.10 lam/CU (conservative floor), 0.60 (base — raw observed), 1.50 (optimistic — full observed fee burden), 2.00 (bull — P75 active payer). Each one has a "Show calculation" button with the full derivation.

The volatility regime breakdown is also here: 71% of epochs are Normal (mean 1.8 lam/CU), 18% Elevated (2.4 lam/CU), 10% Extreme (4.0 lam/CU). The 2× congestion uplift factor between Normal and Extreme is data-derived, not assumed.

---

## PART 3 — Block 2: Validator Revenue *(~4 min)*

*[Click "Validator Revenue" tab.]*

---

**This tab answers a different question: what's in it for validators?**

For RAIKU to work, validators need to run our client software. That's not free — it's infrastructure investment, software risk, client maintenance. The question a validator asks is simple: *does my APR go up?*

### Revenue Pool

*[Point to the four cards at the top.]*

At Base Case, RAIKU validators collectively earn:
- JIT Validator Revenue: **$29.0M** (290.2K SOL/yr)
- AOT Validator Revenue: **$1.34M** (13.4K SOL/yr)
- AOT Validator Bonus: **$14.1K** (141 SOL/yr — this comes from the protocol pool)
- **Total: $30.4M** (303.6K SOL/yr)

### Yield Uplift

*[Point to the Yield Uplift section.]*

This is translated into APR/APY terms. At 10% RAIKU stake, that's 42.39M SOL of connected stake. The revenue flowing to validators over that stake translates to:

- Incremental APR uplift: **+0.717%**
- Total APR (base staking + priority fees + RAIKU uplift): **5.50%**
- Total APY (with daily compounding): **5.65%**

The APR decomposition bar shows it clearly: base staking is 4.38%, fixed priority fee uplift is 0.40%, RAIKU adds 0.717% on top. That's a meaningful increment for a validator who's already optimizing every basis point.

*[Point to the Scenario Total Yield Composition section.]*

Across scenarios: Conservative gives 5.34% APR, Bull Case gives **6.10%** APR. For validators comparing client options, this range frames the upside and the downside.

The methodology note at the bottom is important: "Phase 1 uses the currently selected simulator state as the source of truth for validator-side annual revenue, then translates that revenue pool into yield uplift on the connected stake." The parameters link directly back to what you set in Tab 1.

---

## PART 4 — Block 3: Block Simulation *(~4 min)*

*[Click "Block Simulation" tab.]*

---

**This is the micro view — one block, not one year.**

Where the Revenue Model asks "how much does RAIKU earn annually?", the Block Simulation asks "what does a single RAIKU block actually contain, and what is it worth at the individual transaction level?"

### Left Panel — Parameters

*[Point to the four controls.]*

- Block Size: 60M CU (Solana's standard capacity — fixed)
- AOT Block Share: 5% → 3M CU reserved for AOT customers
- RAIKU Stake: 10% → 7.8M slots/yr
- AOT Minimum Bid: 10,000 lamports (the floor price to participate in an AOT auction)

### Block Builder

*[Point to the main panel.]*

This is the visual block. Currently one fragment is loaded: **Prop AMM** (Fill #1). The Prop AMM fragment uses the Median client profile, consumes 209,970 CU — about 7% of the AOT block — and bids 3.29 lam/CU, for a total bid of 698,597 lamports = $0.069 per slot.

The "Include Arbitrage Bot" toggle in the top right is off by default. Arb-bot activity has very high fee/CU but is not an AOT customer — toggling it on shows what the block would look like if that CU footprint were included, but it's excluded from the core model because arb bots use JIT, not AOT.

*[Point to the Per-Block Output section.]*

Per-block: 210K CU used, 3.29 lam/CU weighted average fee, **0.000691 SOL = $0.069** total block fees.

Extrapolated: **$541K/yr** at 10% stake. That's the bottom-up cross-check on the Revenue Model — it's in the same ballpark, which gives confidence the model is internally consistent.

### Category Explorer

*[Scroll to Category Explorer.]*

*[Click through the category tabs: Prop AMM, Cranker, Oracle, DEX, Lending, etc.]*

Each category tab shows real data: number of programs with usable economics, 30-day CU total, CU-weighted average fee/CU (primary and secondary), dispersion metrics (median, P25, P75), and total fees over the 30-day window.

For **Prop AMM**: 10 programs, 118.1B CU consumed over 30 days, primary fee/CU 7.25 lam — the highest of any category. This is why PropAMMs are the anchor customer archetype for AOT.

The bar chart on the right shows fee/CU by category. Prop AMM stands far above the rest. That fee/CU dispersion is what creates a functioning auction market: high-value users outbid lower-value ones, blockspace allocates to its highest use.

*[Point to Program Explorer below.]*

Below that, the **Program Explorer** shows individual programs within the selected category — sorted by implied non-base fees per block. For Prop AMM: WhaleStreet at 50.7 lam/CU, SolFi V2 at 3.29, SolFi at 3.84, and so on. These are real program addresses from on-chain data. This is what the model is built on.

---

## PART 5 — Block 4: Solana Market *(~2 min)*

*[Click "Solana Market" tab.]*

---

**This is the market context layer — the foundation everything else sits on.**

*[Point to the five KPI cards.]*

The key numbers:
- **MEV/JIT Tips** (annualized): 812.6K SOL/yr — this is the total addressable JIT market. Real, from Jito Block Engine API.
- **Priority Fees** (annualized): 2.22M SOL/yr — the total non-vote priority fee market. Real, from Trillium API.
- **SOL Price**: $109 (average over tracked epochs)
- **Epochs Tracked**: 100 recent (epochs 836–935)
- **Programs Tracked**: 205 (from our AOT artifact)

*[Point to the two charts.]*

The left chart shows **MEV/JIT Rewards per Epoch** going back to epoch 400 — the spikes are the memecoin surges and high-volatility periods that inflated the JIT market temporarily. The highlighted window (last 100 epochs) is what the Base Case uses — a more recent, calmer period. This is deliberate: we don't want to anchor our base case to peak activity.

The right chart is **SOL price history** over the same range.

The point of this tab is simple: transparency. Every number in the Revenue Model has a traceable source here. The JIT market size isn't a round number — it's the mean of 100 epochs of real Jito data.

---

## COMING NEXT — Customer Economics Block *(~2 min)*

*[The 5th tab doesn't exist yet — describe what you're building.]*

---

The four tabs we've just seen answer the question from RAIKU's perspective and the validator's perspective. What's missing is the customer's perspective.

We're building a **Customer Economics** block — a fifth tab that models the ROI for each of our six target archetypes. The six are:

1. **PropAMMs** — The anchor case. Reserve blockspace to keep quote-update transactions landing reliably. The math: at 26% market share, even a 10% improvement in fill rates represents $163M+ in additional executed flow annually. The break-even cost of AOT reservations is a fraction of the adverse selection cost of stale quotes.

2. **Quant Trading Desks** — AOT raises execution confidence from ~40% to 95%+. A Kelly-criterion position-sizing model allows materially larger positions at the same risk budget when execution probability is near-certain. More size with the same edge = more P&L.

3. **Market Makers (Operational)** — Not for trading. For the critical transactions that MUST land during volatility spikes: margin top-ups, collateral rebalances, position rollovers. The insurance math: $500/day in reservation costs vs. a single prevented forced liquidation worth $2M+.

4. **DEX-DEX Arb Bots** — Clean separation of detection logic from execution. The reserved slot pool fills asynchronously in the background; when a signal fires, there's no race, no tip escalation, no retry loop.

5. **Protocol Crankers/Keepers** — Cadence-aware scheduling. Cranks fail most often during congestion — exactly when they matter most. AOT aligns reservations to the protocol's crank schedule so that Drift funding settlements, Jupiter DCA executions, and Kamino rebalances have guaranteed slots waiting.

6. **CEX-DEX Arb Desks** — The highest-stakes case. When your CEX leg fills in 3ms with 100% certainty and your DEX leg has 40% landing probability, you're holding a naked directional position on every failed attempt. AOT brings DEX-leg reliability to near-parity with CEX, which unlocks position sizes that firms are currently leaving on the table.

The Customer tab will let you configure each archetype's size and see their break-even point — how little blockspace needs to cost for the ROI to be positive.

---

## WRAP-UP *(~1 min)*

---

To close: the RAIKU Revenue Simulator is a **transparent, data-backed financial model** for the RAIKU blockspace marketplace protocol.

It is not a pitch deck. Every assumption is a slider. Every data point has a source. The range from $190K to $17.2M in Protocol Treasury is honest — early-stage adoption is uncertain, and the model shows you exactly why.

The four blocks — Revenue Model, Validator Revenue, Block Simulation, and Solana Market — each answer a different stakeholder question: what does RAIKU earn, what do validators earn, what does one block look like at the micro level, and what is the real Solana market we're working in.

A fifth block — Customer Economics — is in progress and will close the loop by showing the ROI for each customer archetype.

The simulator lives at **raiku-protocol.github.io/raiku-simulator**. Source in `raiku-protocol/raiku-simulator` on GitHub.

---

*Total target: ~23 minutes*

---

> **Presenter Notes**
>
> - Open on Revenue Model, Base Case preset, before you start speaking — let the visual land while you give the problem context
> - The strongest moment: the Sankey diagram. Linger on it. Point to the lime green Protocol Treasury bar and say "this is what we're building toward."
> - When asked about the numbers: "Conservative to Bull is a 90× spread. We didn't pick the middle and call it the answer — we built a model where you can see exactly what changes each assumption."
> - If asked about the customer block: "The methodology is done, it's an implementation task. The six archetypes and their economics are in our internal docs."
> - Avoid saying any specific scenario number is "the target" — the tool is explicitly designed to show a range
> - If asked why JIT dominates (95%+ of revenue in Base Case): "Because the Jito MEV market is already large and our AOT adoption assumption is conservative. As stake grows and AOT adoption increases, that mix shifts."
