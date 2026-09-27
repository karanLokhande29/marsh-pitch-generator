"""Central configuration. Values can be overridden with environment variables or a .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "pitchgen" / "data"
POLICY_DIR = ROOT / "policies"
OUTPUT_DIR = ROOT / "outputs"
CACHE_DIR = ROOT / ".cache"

def _secret(name: str, default: str = "") -> str:
    """Environment / .env first, then Streamlit Cloud secrets (never shipped in the repo)."""
    val = os.getenv(name, "").strip()
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


GROQ_API_KEY = _secret("GROQ_API_KEY")
SERVER_HAS_KEY = bool(GROQ_API_KEY)
# Cap LLM-backed generations per browser session on the public deployment (protects the free Groq quota).
MAX_RUNS_PER_SESSION = int(_secret("MAX_RUNS_PER_SESSION", "15") or 15)
# Primary model for generation and auditing; fallback is used on rate limits (Groq free tier).
GROQ_MODEL = _secret("GROQ_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = _secret("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b") or "openai/gpt-oss-20b"

# Audit thresholds
PASS_SCORE = float(os.getenv("AUDIT_PASS_SCORE", "90"))

USER_AGENT = "MarshPitchGenerator/1.0 (NMIMS internship case study)"

for d in (OUTPUT_DIR, CACHE_DIR):
    d.mkdir(parents=True, exist_ok=True)
