"""check.py: the repo's one-command check (the pre-commit hook runs it). Tests, plus the text lint once script/ exists."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "pytest", "-q", "tests"], cwd=ROOT))
