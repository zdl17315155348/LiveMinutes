"""Shared project paths, independent of the process working directory."""
from pathlib import Path
import sys

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
ASSETS_DIR = Path(getattr(sys, '_MEIPASS', ROOT)) / 'assets'
DATA_DIR = ROOT / 'data'
MODELS_DIR = DATA_DIR / 'models'
RECORDINGS_DIR = DATA_DIR / 'recordings'
TEST_OUTPUT_DIR = DATA_DIR / 'test-output'
MINUTES_DIR = DATA_DIR / 'minutes'
