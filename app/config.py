"""Central configuration. Everything is env-driven so the stack stays model-agnostic."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
FIXTURES_DIR = ROOT / "fixtures"
SEEDS_DIR = DATA_DIR / "seeds"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("TRUSTMAX_DB_PATH") or (DATA_DIR / "trustmax.db"))
FAISS_PATH = DATA_DIR / "memory.faiss"
MEMORY_META_PATH = DATA_DIR / "memory_meta.json"
CALIBRATOR_PATH = DATA_DIR / "calibrator.pkl"

# Relational backend: sqlite (default) | postgres (Supabase/Postgres via DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL", "")  # e.g. postgresql://... (Supabase). Empty => SQLite.

# Knowledge graph backend: neo4j (default if reachable) | networkx (embedded fallback)
GRAPH_BACKEND = os.getenv("GRAPH_BACKEND", "neo4j").lower()
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "trustmax123")
GRAPH_PICKLE = DATA_DIR / "graph.pkl"  # NetworkX fallback persistence

# Synthetic data scale: test | demo | showcase
DATA_SCALE = os.getenv("DATA_SCALE", "demo").lower()

# Routing auto-route confidence threshold (misroute-safe; wrong client = breach)
AUTO_ROUTE_THRESHOLD = float(os.getenv("AUTO_ROUTE_THRESHOLD", "0.90"))

# Per-tenant field encryption master key (demo only; use a real KMS in production)
MASTER_ENCRYPTION_KEY = os.getenv("MASTER_ENCRYPTION_KEY", "trustmax-demo-master-key-change-me")

# LLM provider: groq (default) | openai | anthropic | mock
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "auto")  # auto (fastembed, fallback hash) | hash

AUTO_APPROVE_THRESHOLD = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.85"))

# Seconds of human review saved per auto-approved transaction (used for the "minutes saved" metric).
SECONDS_PER_TXN = 25


def effective_provider() -> str:
    """Fall back to the offline mock model when the chosen provider has no key configured.

    This keeps the whole flywheel runnable (and the demo reproducible) without any network access.
    """
    if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        return "mock"
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        return "mock"
    if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        return "mock"
    return LLM_PROVIDER
