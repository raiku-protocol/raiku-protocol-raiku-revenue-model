---
name: Windows console encoding for validator names
description: Print statements fail on Windows cp1252 when validator names contain emoji or non-ASCII characters
type: feedback
---

Use a `_safe()` helper in any script that prints validator names to stdout. Define it in the helpers block (before first use):

```python
def _safe(name, width=35):
    """ASCII-safe validator name for Windows console printing (strips emoji)."""
    s = name.encode("ascii", "replace").decode("ascii")
    return s[:width].ljust(width)
```

**Why:** Windows shell uses cp1252 by default. Validator names like "Staking Facilities | MEV 🔥" or "Moutai Validator 🚀" cause `UnicodeEncodeError: 'charmap' codec can't encode character` at runtime, even though the data itself is fine.

**How to apply:** Any script that prints validator names (or other user-supplied strings) to console on this machine must either use `_safe()` or encode with `errors='replace'`. The data in CSV/JSON outputs is unaffected — only print statements need the guard.

Also: avoid em-dash `—` in print strings; use `-` instead. Same cp1252 issue.

Also: matplotlib 3.9+ renamed `labels=` to `tick_labels=` in `boxplot()`. Use `tick_labels=` to avoid DeprecationWarning (will become error in 3.11).
