import os
import sys
from pathlib import Path

# Run from repo root so core/ (config/AGENTS.md, skills/) resolves.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Unit tests must never build the real agent or need API keys.
os.environ["EAGER_INIT"] = "false"
