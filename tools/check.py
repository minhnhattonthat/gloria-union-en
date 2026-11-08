"""check.py: the repo's one-command check (the pre-commit hook runs it). Tests, plus the text lint (batches.py check)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lint = subprocess.call([sys.executable, "-X", "utf8", "tools/batches.py", "check"], cwd=ROOT)
tests = subprocess.call([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests"], cwd=ROOT)
sys.exit(lint or tests)
