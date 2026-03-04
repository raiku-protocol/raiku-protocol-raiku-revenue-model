"""
RAIKU Revenue Estimation — Master Pipeline Orchestrator
========================================================
Runs: Extract → Transform → Model → Output

Usage:
    python run_pipeline.py              # Incremental (only new data)
    python run_pipeline.py --full       # Full re-extraction
    python run_pipeline.py --model-only # Skip extraction, only run model
"""

import argparse
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "01_extract"))
sys.path.insert(0, str(Path(__file__).parent / "02_transform"))
sys.path.insert(0, str(Path(__file__).parent / "03_model"))


def run_step(name: str, func, *args):
    """Run a pipeline step with timing."""
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")
    start = time.time()
    try:
        func(*args)
        elapsed = time.time() - start
        print(f"\n  ✓ {name} completed in {elapsed:.1f}s")
        return True
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ {name} FAILED after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="RAIKU Revenue Estimation Pipeline")
    parser.add_argument("--full", action="store_true", help="Full re-extraction (all epochs)")
    parser.add_argument("--model-only", action="store_true", help="Skip extraction, run models only")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  RAIKU Revenue Estimation Pipeline")
    print("="*60)

    total_start = time.time()
    steps_ok = 0
    steps_total = 0

    if not args.model_only:
        # ── Phase 1: Extract ──
        from extract_trillium import extract as extract_trillium
        steps_total += 1
        if run_step("Extract Trillium Data", extract_trillium, args.full):
            steps_ok += 1

        # CoinGecko (optional refresh)
        try:
            from coingecko_prices import extract as extract_coingecko
            steps_total += 1
            if run_step("Extract CoinGecko Prices", extract_coingecko):
                steps_ok += 1
        except Exception:
            print("  (Skipping CoinGecko — existing data will be used)")

        # ── Phase 1: Transform ──
        from build_database import build as build_db
        steps_total += 1
        if run_step("Build Epoch Database", build_db):
            steps_ok += 1
    else:
        print("\n  --model-only: Skipping extraction & transform steps")

    # ── Phase 3: Models ──
    from jit_revenue import model as jit_model
    steps_total += 1
    if run_step("JIT Revenue Model", jit_model):
        steps_ok += 1

    from aot_revenue import model as aot_model
    steps_total += 1
    if run_step("AOT Revenue Model", aot_model):
        steps_ok += 1

    # ── Summary ──
    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE: {steps_ok}/{steps_total} steps succeeded in {total_elapsed:.1f}s")
    print(f"{'='*60}")

    # List output files
    from config import DATA_PROCESSED
    if DATA_PROCESSED.exists():
        print(f"\n  Output files in {DATA_PROCESSED}:")
        for f in sorted(DATA_PROCESSED.glob("*.csv")):
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
