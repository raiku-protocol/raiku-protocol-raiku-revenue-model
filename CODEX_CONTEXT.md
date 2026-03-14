# RAIKU Revenue Model — Codex Context

## Repo roles

- `raiku-revenue-model` is the upstream source-of-truth for data extraction, taxonomy, processed datasets, model outputs, and simulator input artifacts.
- `raiku-simulator` is the active HTML UI repo. Its current entrypoint is `index.html`.

## Active upstream flow

1. Raw extracts are produced in `01_extract/` and `scripts/download_dune_daily_C.py`
2. Consolidated datasets are built in `02_transform/`
3. Scenario/model outputs are built in `03_model/`
4. Simulator-facing AOT artifact is prepared from upstream outputs via `scripts/build_aot_programs_artifact.py`
5. Active simulator consumes the generated artifact as `raiku-simulator/data/aot_programs.v1.js`

## Key upstream files

- `run_pipeline.py`
- `scripts/build_aot_programs_artifact.py`
- `scripts/build_daily_temporal.py`
- `scripts/classify_programs.py`
- `data/mapping/program_categories.csv`
- `data/processed/program_database.csv`
- `data/processed/program_conditions.csv`

## Current simulator boundary

- Do not treat `raiku_revenue_simulator.html` in this repo as the active product surface.
- It is a legacy inline-data snapshot kept for auditability.
- Current simulator UX work should land in the separate `raiku-simulator` repo unless the task is explicitly about upstream artifact generation or historical lineage.
