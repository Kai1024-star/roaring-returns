"""Launch with: python -m streamlit run demo_app.py"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent/"src"))
from roaring_returns.app import main

main()
