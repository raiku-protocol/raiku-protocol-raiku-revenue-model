"""Full extraction of Solana Compass + Jito MEV for all epochs."""
import sys, os, time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

log = open("_full_extract.log", "w", encoding="utf-8")

class Tee:
    def __init__(self, *files):
        self.files = files
        self.encoding = "utf-8"
    def write(self, text):
        for f in self.files:
            f.write(text)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()
    def reconfigure(self, **kwargs):
        pass

sys.stdout = Tee(log)
sys.stderr = Tee(log)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── 1. Jito MEV (faster, lighter responses) ──────────────
print("=" * 60)
print("PHASE 1: Jito Foundation MEV — Full extraction")
print("=" * 60)
t0 = time.time()
from importlib import import_module
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "01_extract"))
import extract_jito_mev
extract_jito_mev.extract(full=True)
print(f"\nJito MEV done in {time.time()-t0:.0f}s\n")

# ── 2. Solana Compass (heavier, per-validator data) ──────
print("=" * 60)
print("PHASE 2: Solana Compass — Full extraction")
print("=" * 60)
t1 = time.time()
import extract_solana_compass
extract_solana_compass.extract(full=True)
print(f"\nSolana Compass done in {time.time()-t1:.0f}s\n")

# ── 3. Rebuild database ──────────────────────────────────
print("=" * 60)
print("PHASE 3: Rebuild merged database")
print("=" * 60)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "02_transform"))
import build_database
build_database.build()

total = time.time() - t0
print(f"\n{'=' * 60}")
print(f"ALL DONE — total time: {total:.0f}s ({total/60:.1f} min)")
print(f"{'=' * 60}")
log.close()
