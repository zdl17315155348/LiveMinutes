"""Shared project paths, independent of the process working directory."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
MODELS_DIR = DATA_DIR / 'models'
RECORDINGS_DIR = DATA_DIR / 'recordings'
TEST_OUTPUT_DIR = DATA_DIR / 'test-output'
MINUTES_DIR = DATA_DIR / 'minutes'
