# RAIKU Simulator — Task Tracker

> Instruction for Claude: read this file at the start of every session.
> This file is a project reference, not permission to implement everything at once.
> Only work on the task explicitly requested in the current prompt.
> After each session, update the relevant status and the Recently Completed section.

## Working Rules

1. One task at a time.
2. Do not jump ahead without an explicit prompt.
3. Do not reopen validated logic unless explicitly requested.
4. Keep repo boundaries strict.
5. Prefer small isolated patches over broad mixed changes.
6. When a value is derived from the active dataset, treat it as dynamic, not as a fixed constant.
7. After each completed task, update status and wait for validation.

## Repo Boundaries

1. Upstream canonical data / model repo  
   `raiku-protocol-raiku-revenue-model`

2. Active UI repo  
   `raiku-simulator`

3. Absolute rule  
   All data / transform / artifact logic belongs in `raiku-protocol-raiku-revenue-model`  
   All front end / HTML / UX logic belongs in `raiku-simulator`

## Current Validated State

1. Active simulator UI lives in `raiku-simulator`.
2. Revenue Model UI is stable again after rollback of the broken large JIT rollout.
3. Hybrid slider controls are in place and stable.
4. JIT scenario presets are wired to dynamic calendar window outputs from the active dataset:
   1. Conservative uses the current 6 month computed window
   2. Base Case uses the current 12 month computed window
   3. Optimistic uses the current 24 month computed window
   4. Bull remains a manual scenario
5. These JIT window values are dynamic and must be recomputed if the dataset changes.
6. JIT market share warning is shown only when JIT market share exceeds 100 percent of Raiku stake.
7. Long horizon AOT calibration values are validated and must not be reopened unless explicitly requested.
8. The fake manual Base Case JIT override was removed and replaced by data driven logic.

## Ordered Task Queue

# Tab 1 — Revenue Model

## 1. JIT Market Assumption & Methodology cleanup
Status: DONE

Scope:
Clean up the JIT methodology section UX and copy without changing layout hierarchy outside that section.

Main goals:
1. Make SOL per year primary and USD secondary.
2. Remove the large empty top spacing caused by the current badge placement.
3. Rewrite the methodology text to be shorter, clearer, and non repetitive.
4. Replace vague backend source labels with real user facing source references.
5. Make source links clickable.
6. Remove competitor names from exclusions.
7. Clarify includes / excludes in a single clean pass.
8. Show scenario assumptions clearly by preset and by window used.
9. Keep the compact 6 month / 12 month / 24 month table coherent with the presets.
10. Update the JIT chart later, in a separate patch.

## 2. Revenue Model bottom scroll / height alignment
Status: DONE

Scope:
Fix bottom scroll behavior and vertical alignment inside Revenue Model.

Main goals:
1. Remove empty space on the right at the bottom.
2. Ensure the right side scroll depth matches the left setup panel.
3. Keep page end visually aligned.

## 3. AOT calibration source clarity
Status: IN PROGRESS

Scope:
Improve clarity when switching between Long horizon and 30d AOT scope.

Main goals:
1. Show the active data source clearly.
2. Present 30d data in a format closer to Long horizon.
3. Add a dedicated 30d line with epochs and relevant fee metrics.
4. Show exactly which values and rules were used for the 4 presets.
5. Highlight the active source and the active values used.
6. Clarify, for each preset, which metric was used.

## 4. Scenario preset UX
Status: DONE

Scope:
Improve usability and visual hierarchy of the four preset buttons, set Long horizon as default on Revenue Model load, and restore practical access to the full left setup panel.

Main goals:
1. Make the 4 preset buttons larger.
2. Use the full useful width for the preset button row.
3. Make the active state more visible.
4. Use a selected style coherent with the yellow already used elsewhere.
5. Set Long horizon as default on Revenue Model load.
6. Restore practical access to the full left setup panel without requiring the user to scroll all the way through the right results panel first.
7. Keep the change local to Revenue Model.

Acceptance criteria:
1. On Revenue Model load, Long horizon is selected by default.
2. The 4 preset buttons are visually larger, clearer, and use the available horizontal space better.
3. The active preset is immediately identifiable.
4. The selected preset style is visually coherent with the existing yellow selection language used elsewhere in the UI.
5. The left setup panel can be accessed fully without having to first reach the bottom of the right results panel.
6. The fix does not introduce regressions in Revenue Model bottom alignment or in other tabs.

## 5. Revenue flow with Other non Raiku JIT
Status: TODO

Scope:
Add a separate Other non Raiku JIT flow across revenue diagrams, cards, and downstream revenue presentation.

Main goals:
1. Introduce a dedicated input parameter for Other non Raiku JIT.
2. Distinguish clearly between Raiku JIT and Other non Raiku JIT everywhere in Revenue Model presentation.
3. Other non Raiku JIT goes directly to validators and does not pass through Raiku protocol take.
4. Validator total must clearly include:
   - Raiku JIT
   - Other non Raiku JIT
   - AOT base
   - AOT validator bonus
5. Protocol revenue must continue to include only the Raiku-captured flows.
6. Rename ambiguous JIT labels where needed so the protocol-tracked flow is explicitly shown as Raiku JIT.
7. Update revenue flow diagrams and value cards so the distinction is visible and intuitive.
8. Clarify the calculation rule for Other non Raiku JIT directly in the UI methodology / definitions.
9. Ensure Raiku JIT + Other non Raiku JIT remain coherent with covered stake share and do not create inconsistent double counting.

Acceptance criteria:
1. The revenue flow diagram shows Raiku JIT and Other non Raiku JIT as separate flows.
2. Other non Raiku JIT visibly bypasses protocol take and goes straight to validators.
3. Cards / tiles / summaries use unambiguous labels.
4. Validator revenue totals reconcile cleanly across all displayed components.
5. No change to unrelated AOT calibration or JIT methodology sections.

## 5.bis Add 3.5L fee/CU bucket to AOT sensitivity chart and table
Status: TODO

Scope:
Add a visible 3.5L fee/CU bucket to the AOT sensitivity chart and table so the Bull Case can be located exactly in the displayed matrix.

Main goals:
1. Insert 3.5L between 2.0L and 5.0L in the sensitivity table.
2. Ensure the chart/table highlight logic can target 3.5L exactly.
3. Keep the change local to the AOT sensitivity display.
4. Do not mix this patch with Other non Raiku JIT revenue flow changes.

Acceptance criteria:
1. The sensitivity table includes a dedicated 3.5L column.
2. The current scenario highlight can land on 3.5L when Bull Case is active.
3. The sensitivity chart/table remains visually consistent.
4. No change to revenue flow logic or downstream validator/protocol splits.

## 6. Annual Revenue Overview update
Status: DONE

Scope:
Reflect the Raiku JIT / Other JIT split in the annual overview cards.

Main goals:
1. Add Other non Raiku JIT revenue card or equivalent line item.
2. Rename Raiku JIT revenue clearly.
3. Update distribution cards consistently.
4. Keep total gross revenue unchanged when only the split changes.
5. Keep the overview coherent with the revenue flow logic.

# Tab 2 — Validator Revenue

## 7. Validator revenue logic cleanup
Status: DONE
Last updated: 2026-03-23

Implemented (raiku-simulator/index.html):
- Epoch-based compounding: EPOCHS_PER_YEAR = Math.round(SY / 432_000) ≈ 182; APY_COMPOUNDING_PERIODS uses this constant
- Validator Revenue Pool KPI cards: Raiku JIT (#5B8DEF), Other JIT (#6B9EBC), AOT Base (#7BBBAF), Validator Bonus (#4178DE), Total (bold)
- "AOT Bonus" → "Validator Bonus" (aggregate: aotValBonus + jitValBonus); validator-bonus-usd/sol now shows combined value
- totalValidatorRevenueSol = r.totalValRev + r.otherJitRev — all 4 components: Raiku JIT, Other JIT, AOT base, Validator bonus
- Formula note updated: "Raiku JIT + Other JIT + AOT base + Validator bonus" + epoch-based compounding convention
- All "daily compounding" wording removed; epoch-based compounding used throughout

## 8. Yield display hierarchy
Status: TODO

Scope:
Make APY primary and APR secondary everywhere relevant.

Main goals:
1. APY visually dominant.
2. APR smaller and secondary.
3. Apply this consistently in cards and charts.
4. Clarify incremental yield versus total yield after op place.

## 8.bis Validator issuance / block rewards / APR / APY methodology audit
Status: TODO

Scope:
Validate and clarify the core validator yield methodology before further UX or parity work.

Main goals:
1. Verify the correct treatment of issuance in validator APR.
2. Make explicit that network inflation must be adjusted by the active staking ratio, rather than read as direct validator APR.
3. Consider adding active staking ratio as an explicit model input, with a sensible default around current network conditions.
4. Verify how issuance APR is converted into APY, using epoch based compounding rather than daily compounding.
5. Verify that block rewards are modeled correctly and clearly, including normal transaction flow, base fees, and priority fees.
6. Clarify the distinction between issuance, block rewards, and MEV in validator revenue.
7. Cross validate the resulting validator APR / APY against external references such as Marinade, Jito, Rakurai, or other reliable dashboards.
8. Identify whether any gap comes from inflation treatment, compounding cadence, reward perimeter, smoothing, or source mismatch.
9. Ensure the validator revenue UI and formulas reflect this methodology clearly once validated.

## 9. Validator specific setup module
Status: TODO

Scope:
Add a validator specific input module.

Main goals:
1. Let a validator input their own stake in SOL or as a share of total stake.
2. Show expected revenue with Raiku.
3. Show a clear breakdown across revenue types.
4. Show incremental APY and total APY.

## 10. JIT / validator share consistency
Status: TODO

Scope:
Formalize how Other JIT is derived when Raiku JIT does not use the full available share.

Main goals:
1. Clarify how Other JIT is calculated.
2. Ensure all JIT shares stay coherent with Raiku stake.
3. Reflect that logic clearly in the UI and formulas.

## 11. APY parity audit versus Jito / Rakurai references
Status: TODO

Scope:
Benchmark the validated internal methodology against external references.

Main goals:
1. Compare final APR / APY outputs against Jito / Rakurai / Marinade / Figment references.
2. Confirm whether remaining differences come from source selection, smoothing, update cadence, or reward scope.
3. Use this audit as an external validation step, not as the primary place to define internal methodology.

# Tab 3 — Block Simulation

## 12. Future customer module / customer economics simulator
Status: TODO

Scope:
Add a customer oriented simulation module, separate from the current block builder style setup.

Main goals:
1. Let a client input their own current execution profile.
2. Compare current execution without Raiku versus with Raiku.
3. Allow defaults by client type where useful, without forcing a one to one match with internal taxonomy.
4. Potentially capture parameters such as CU usage, fees paid, transaction count, bundle usage, block participation, and execution assumptions.
5. Design this as a separate major workstream before implementation.

## 13. Future congestion scenario workstream
Status: TODO

Scope:
Add explicit congestion scenario controls in Block Simulation later, not inside unrelated patches.

Main goals:
1. Keep congestion controls separate from baseline calibration.
2. Start with a version where congestion impacts fee per CU only.
3. Consider later whether block share or intraday effects should also be modeled.
4. Treat this as a distinct future task after current Revenue Model and Validator Revenue priorities.

# Tab 4 — Solana Market

## 14. Solana Market data / structure
Status: TODO

Scope:
Define later tasks for the Solana Market tab as the product direction becomes clearer.

Main goals:
1. Clarify which global market metrics should live there.
2. Avoid mixing these tasks with Revenue Model or Validator Revenue work.

# Shared / Cross-tab

## 15. Shared visual consistency
Status: TODO

Scope:
Keep colors, labels, badges, selected states, and metric hierarchy coherent across tabs.

Main goals:
1. Use consistent naming for Raiku JIT, Other JIT, AOT base, AOT bonus, total.
2. Keep APY / APR hierarchy consistent.
3. Keep selected / active button states coherent across tabs.
4. Avoid duplicative or contradictory labels.

## 16. Shared data-source clarity
Status: TODO

Scope:
Wherever a source is shown to the user, make it traceable and user facing.

Main goals:
1. Prefer real source names and real links.
2. Avoid vague labels like generic API names when a concrete source can be shown.
3. Keep methodology text readable for users, not written like backend notes.

## 17. Shared dynamic-value rule
Status: TODO

Scope:
Ensure dataset driven values are always treated as dynamic outputs.

Main goals:
1. Do not hardcode runtime outputs that should be recomputed from the active dataset.
2. When documenting logic, describe the mapping and computation rule, not temporary numeric outputs.
3. Recompute dynamic values when the underlying dataset refreshes.

## Recently Completed

1. Revenue Model recovered to a stable UI/runtime state after reverting the broken large JIT rollout.
2. Dynamic JIT calendar window computation was reintroduced in a minimal safe way.
3. JIT scenario presets were rewired to dynamic 6 month / 12 month / 24 month outputs from the active dataset.
4. JIT market share warning threshold was corrected to 100 percent of Raiku stake.
5. Hybrid slider precision and direct manual entry UX were added and stabilized.
6. Task 1 — JIT Market Assumption & Methodology cleanup: preset colors, window table, avg/CU column, source links, cross-check wording, methodology copy. Commits f79d7ab, fd95b3c, d6eefce, 4f7cbb5, 061032f.
7. Task 2 — Revenue Model bottom scroll / height alignment. Commit 134ac62.
8. Task 3 (IN PROGRESS) — AOT calibration source clarity: added source detail line, rule attribution lines per preset (commit 4fa03eb), and dedicated 30d AOT row in regime stats table that appears only when 30d scope is active (commit 9aab447). Awaiting user validation.
9. Task 4 (DONE) — Scenario preset UX: enlarged preset buttons (4-col grid, full width), active state now lime-colored coherent with UI, Long horizon default on load, sidebar independently scrollable so lower setup controls are reachable without scrolling through right panel.

## Validation Rule

A task is only marked VALIDATED after explicit user confirmation.

Allowed statuses:
1. TODO
2. IN PROGRESS
3. DONE
4. VALIDATED
5. BLOCKED