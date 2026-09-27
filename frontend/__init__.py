# Corpus AI - Frontend Package
import sys
from pathlib import Path

# Ensure root directory is always on sys.path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
