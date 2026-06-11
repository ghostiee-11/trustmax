"""Seed a self-contained demo into the slug at build time (cloud deploys).

Generates a small labeled corpus, builds the embedded NetworkX knowledge graph, runs the coding
flywheel (mock provider) so categorizations + learned facts exist, and runs the routing and anomaly
scans so the dashboard is fully populated on first load. Persists data/trustmax.db + data/graph.pkl.

Run: `python -m app.deploy_seed`
"""
from __future__ import annotations

import os

os.environ.setdefault("GRAPH_BACKEND", "networkx")  # no external Neo4j in the cloud
os.environ.setdefault("LLM_PROVIDER", "mock")        # deterministic, no key needed at build
os.environ.setdefault("DATA_SCALE", "cloud")

from . import db                                      # noqa: E402
from .datagen.generate import Generator               # noqa: E402
from .kg import build as kgbuild                       # noqa: E402
from .kg.store import get_store                         # noqa: E402
from .evals import code_eval                             # noqa: E402
from .agents.anomaly_agent import run_firm as flag        # noqa: E402
from .agents.router_agent import run_firm as route         # noqa: E402


def main() -> None:
    scale = os.environ.get("DATA_SCALE", "cloud")
    print(f"[seed] generating corpus (scale={scale}) ...")
    db.reset_db()
    counts = Generator(scale).generate()
    print(f"[seed] {counts}")

    print("[seed] building knowledge graph ...")
    kgbuild.build(reset=True)

    print("[seed] running coding flywheel on firm00 ...")
    code_eval.run("firm00")

    print("[seed] routing + anomaly scans on firm00 ...")
    route("firm00")
    flag("firm00")

    store = get_store()
    if hasattr(store, "save"):
        store.save()  # persist the NetworkX graph (with learned facts) into the slug
    print("[seed] done. stats:", store.stats())


if __name__ == "__main__":
    main()
