"""Compatibility entry point; implementation lives in the original Gate 4 path."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gate4_1000_tap_suite as implementation
if __name__ == "__main__":
    raise SystemExit(implementation.main())
sys.modules[__name__] = implementation
