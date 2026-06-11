"""GraphStore: the knowledge graph behind Trustmax.

Primary backend is Neo4j (the user's choice, production target). A NetworkX backend is the embedded
fallback so tests and CI run with zero services. Both share one small domain-specific API rather than
raw Cypher, so the rest of the app is backend-agnostic.

The defining feature is the bi-temporal, provenance-bearing fact:
    (Vendor)-[:CODED_TO {client_id, valid_from, valid_to, confidence, source}]->(GLAccount)
"why is this vendor coded to this account for this client". New approvals invalidate the prior open
fact (set valid_to) instead of deleting it, giving an audit-grade history (Graphiti-inspired).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from .. import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphStore(ABC):
    backend: str = "base"

    @abstractmethod
    def reset(self) -> None: ...
    @abstractmethod
    def add_node(self, label: str, firm_id: str, key: str, props: dict) -> None: ...
    @abstractmethod
    def add_edge(self, rel: str, firm_id: str, src_label: str, src_key: str,
                 dst_label: str, dst_key: str, props: dict | None = None) -> None: ...
    @abstractmethod
    def set_coded_to(self, firm_id: str, vendor_key: str, client_id: str, gl_code: str,
                     confidence: float, source: str) -> None: ...
    @abstractmethod
    def get_current_code(self, firm_id: str, vendor_key: str, client_id: str) -> Optional[dict]: ...
    @abstractmethod
    def coded_to_history(self, firm_id: str, vendor_key: str, client_id: str) -> list[dict]: ...
    @abstractmethod
    def siblings_on_account(self, firm_id: str, gl_code: str, limit: int = 5) -> list[str]: ...
    @abstractmethod
    def reasoning_path(self, firm_id: str, transaction_key: str) -> dict: ...
    @abstractmethod
    def stats(self) -> dict: ...

    # Bulk helpers (default to looping; backends may override for speed).
    def add_nodes(self, label: str, firm_id: str, rows: list[tuple[str, dict]]) -> None:
        for key, props in rows:
            self.add_node(label, firm_id, key, props)

    def add_edges(self, rel: str, firm_id: str,
                  triples: list[tuple[str, str, str, str, dict]]) -> None:
        for src_label, src_key, dst_label, dst_key, props in triples:
            self.add_edge(rel, firm_id, src_label, src_key, dst_label, dst_key, props)


# ----------------------------------------------------------------------- Neo4j
class Neo4jStore(GraphStore):
    backend = "neo4j"

    def __init__(self):
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(
            config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            notifications_min_severity="OFF")
        self._driver.verify_connectivity()
        self._ensure_constraints()

    def _run(self, cypher: str, **params):
        with self._driver.session() as s:
            return list(s.run(cypher, **params))

    def _ensure_constraints(self) -> None:
        for label in ["Firm", "Client", "Engagement", "Vendor", "GLAccount", "Transaction",
                      "Document", "Employee"]:
            try:
                self._run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE (n.firm_id, n.key) IS UNIQUE")
            except Exception:
                pass

    def reset(self) -> None:
        self._run("MATCH (n) DETACH DELETE n")

    def add_node(self, label: str, firm_id: str, key: str, props: dict) -> None:
        self._run(
            f"MERGE (n:{label} {{firm_id:$firm_id, key:$key}}) SET n += $props",
            firm_id=firm_id, key=key, props={k: v for k, v in props.items() if v is not None})

    def add_edge(self, rel: str, firm_id: str, src_label: str, src_key: str,
                 dst_label: str, dst_key: str, props: dict | None = None) -> None:
        self._run(
            f"""MATCH (a:{src_label} {{firm_id:$firm_id, key:$src_key}})
                MATCH (b:{dst_label} {{firm_id:$firm_id, key:$dst_key}})
                MERGE (a)-[r:{rel}]->(b) SET r += $props""",
            firm_id=firm_id, src_key=src_key, dst_key=dst_key, props=props or {})

    def add_nodes(self, label: str, firm_id: str, rows: list[tuple[str, dict]]) -> None:
        payload = [{"key": k, "props": {kk: vv for kk, vv in p.items() if vv is not None}} for k, p in rows]
        for i in range(0, len(payload), 5000):
            self._run(
                f"""UNWIND $rows AS row
                    MERGE (n:{label} {{firm_id:$firm_id, key:row.key}}) SET n += row.props""",
                firm_id=firm_id, rows=payload[i:i + 5000])

    def add_edges(self, rel: str, firm_id: str,
                  triples: list[tuple[str, str, str, str, dict]]) -> None:
        # group by (src_label, dst_label) so labels are static per query
        groups: dict[tuple, list[dict]] = {}
        for src_label, src_key, dst_label, dst_key, props in triples:
            groups.setdefault((src_label, dst_label), []).append(
                {"sk": src_key, "dk": dst_key, "props": props or {}})
        for (src_label, dst_label), rows in groups.items():
            for i in range(0, len(rows), 5000):
                self._run(
                    f"""UNWIND $rows AS row
                        MATCH (a:{src_label} {{firm_id:$firm_id, key:row.sk}})
                        MATCH (b:{dst_label} {{firm_id:$firm_id, key:row.dk}})
                        MERGE (a)-[r:{rel}]->(b) SET r += row.props""",
                    firm_id=firm_id, rows=rows[i:i + 5000])

    def set_coded_to(self, firm_id: str, vendor_key: str, client_id: str, gl_code: str,
                     confidence: float, source: str) -> None:
        now = _now()
        # invalidate prior open facts for this (vendor, client) pointing elsewhere
        self._run(
            """MATCH (v:Vendor {firm_id:$firm_id, key:$vk})-[r:CODED_TO]->(g:GLAccount)
               WHERE r.client_id=$cid AND r.valid_to IS NULL AND g.key <> $glkey
               SET r.valid_to=$now""",
            firm_id=firm_id, vk=vendor_key, cid=client_id, glkey=gl_code, now=now)
        # upsert the current fact (idempotent if same code already open)
        self._run(
            """MATCH (v:Vendor {firm_id:$firm_id, key:$vk})
               MATCH (g:GLAccount {firm_id:$firm_id, key:$glkey})
               MERGE (v)-[r:CODED_TO {client_id:$cid, valid_to_marker:'open'}]->(g)
               ON CREATE SET r.valid_from=$now, r.valid_to=null, r.confidence=$conf, r.source=$src
               SET r.confidence=$conf, r.source=$src""",
            firm_id=firm_id, vk=vendor_key, glkey=gl_code, cid=client_id,
            now=now, conf=confidence, src=source)

    def get_current_code(self, firm_id: str, vendor_key: str, client_id: str) -> Optional[dict]:
        rows = self._run(
            """MATCH (v:Vendor {firm_id:$firm_id, key:$vk})-[r:CODED_TO]->(g:GLAccount)
               WHERE r.client_id=$cid AND r.valid_to IS NULL
               RETURN g.key AS code, g.name AS name, r.confidence AS confidence, r.source AS source
               ORDER BY r.valid_from DESC LIMIT 1""",
            firm_id=firm_id, vk=vendor_key, cid=client_id)
        return dict(rows[0]) if rows else None

    def coded_to_history(self, firm_id: str, vendor_key: str, client_id: str) -> list[dict]:
        rows = self._run(
            """MATCH (v:Vendor {firm_id:$firm_id, key:$vk})-[r:CODED_TO]->(g:GLAccount)
               WHERE r.client_id=$cid
               RETURN g.key AS code, r.valid_from AS valid_from, r.valid_to AS valid_to,
                      r.confidence AS confidence, r.source AS source
               ORDER BY r.valid_from""",
            firm_id=firm_id, vk=vendor_key, cid=client_id)
        return [dict(r) for r in rows]

    def siblings_on_account(self, firm_id: str, gl_code: str, limit: int = 5) -> list[str]:
        rows = self._run(
            """MATCH (v:Vendor {firm_id:$firm_id})-[r:CODED_TO]->(g:GLAccount {firm_id:$firm_id, key:$glkey})
               WHERE r.valid_to IS NULL RETURN DISTINCT v.canonical_name AS name LIMIT $lim""",
            firm_id=firm_id, glkey=gl_code, lim=limit)
        return [r["name"] for r in rows]

    def vendor_open_facts(self, firm_id: str, vendor_key: str) -> list[dict]:
        rows = self._run(
            """MATCH (v:Vendor {firm_id:$firm_id, key:$vk})-[r:CODED_TO]->(g:GLAccount)
               WHERE r.valid_to IS NULL
               RETURN r.client_id AS client_id, g.key AS code, r.confidence AS confidence, r.source AS source""",
            firm_id=firm_id, vk=vendor_key)
        return [dict(r) for r in rows]

    def clear_coded_to(self, firm_id: str) -> None:
        self._run("MATCH (:Vendor {firm_id:$firm_id})-[r:CODED_TO]->() DELETE r", firm_id=firm_id)

    def reasoning_path(self, firm_id: str, transaction_key: str) -> dict:
        rows = self._run(
            """MATCH (t:Transaction {firm_id:$firm_id, key:$tk})
               OPTIONAL MATCH (t)-[:REFERENCES]->(v:Vendor)
               OPTIONAL MATCH (t)-[tc:CODED_TO]->(tg:GLAccount)
               OPTIONAL MATCH (v)-[vc:CODED_TO]->(vg:GLAccount)
                 WHERE vc.client_id=t.client_id AND vc.valid_to IS NULL
               RETURN t, v.canonical_name AS vendor, tc.confidence AS decision_conf,
                      tg.key AS decision_code, vg.key AS history_code, vc.confidence AS history_conf,
                      vc.source AS history_source""",
            firm_id=firm_id, tk=transaction_key)
        if not rows:
            return {}
        r = rows[0]
        t = dict(r["t"])
        return {
            "transaction": {"key": t.get("key"), "vendor_raw": t.get("vendor_raw"),
                            "amount": t.get("amount"), "client_id": t.get("client_id")},
            "vendor": r["vendor"],
            "decision": {"code": r["decision_code"], "confidence": r["decision_conf"]},
            "graph_fact": {"code": r["history_code"], "confidence": r["history_conf"],
                           "source": r["history_source"]},
        }

    def stats(self) -> dict:
        nodes = self._run("MATCH (n) RETURN count(n) AS c")[0]["c"]
        edges = self._run("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        coded = self._run("MATCH ()-[r:CODED_TO]->() WHERE r.valid_to IS NULL RETURN count(r) AS c")[0]["c"]
        return {"backend": "neo4j", "nodes": nodes, "edges": edges, "open_coded_to": coded}

    def close(self) -> None:
        self._driver.close()


# -------------------------------------------------------------------- NetworkX
class NetworkXStore(GraphStore):
    """Embedded fallback. Keeps the same API using a MultiDiGraph + dict indexes."""
    backend = "networkx"

    def __init__(self):
        import networkx as nx
        self._nx = nx
        self.g = nx.MultiDiGraph()
        # coded_to facts: (firm_id, vendor_key, client_id) -> list of {code, valid_from, valid_to, confidence, source}
        self.coded: dict[tuple, list[dict]] = {}
        if config.GRAPH_PICKLE.exists():
            self._load()

    def _nid(self, label, firm_id, key):
        return f"{label}:{firm_id}:{key}"

    def reset(self) -> None:
        self.g.clear(); self.coded.clear()

    def add_node(self, label, firm_id, key, props):
        self.g.add_node(self._nid(label, firm_id, key), label=label, firm_id=firm_id, key=key, **props)

    def add_edge(self, rel, firm_id, src_label, src_key, dst_label, dst_key, props=None):
        self.g.add_edge(self._nid(src_label, firm_id, src_key), self._nid(dst_label, firm_id, dst_key),
                        key=rel, rel=rel, **(props or {}))

    def set_coded_to(self, firm_id, vendor_key, client_id, gl_code, confidence, source):
        k = (firm_id, vendor_key, client_id)
        facts = self.coded.setdefault(k, [])
        for f in facts:
            if f["valid_to"] is None and f["code"] != gl_code:
                f["valid_to"] = _now()
        open_same = [f for f in facts if f["valid_to"] is None and f["code"] == gl_code]
        if open_same:
            open_same[0].update(confidence=confidence, source=source)
        else:
            facts.append({"code": gl_code, "valid_from": _now(), "valid_to": None,
                          "confidence": confidence, "source": source})

    def get_current_code(self, firm_id, vendor_key, client_id):
        for f in reversed(self.coded.get((firm_id, vendor_key, client_id), [])):
            if f["valid_to"] is None:
                return {"code": f["code"], "confidence": f["confidence"], "source": f["source"]}
        return None

    def coded_to_history(self, firm_id, vendor_key, client_id):
        return list(self.coded.get((firm_id, vendor_key, client_id), []))

    def siblings_on_account(self, firm_id, gl_code, limit=5):
        names = []
        for (fid, vk, cid), facts in self.coded.items():
            if fid != firm_id:
                continue
            if any(f["valid_to"] is None and f["code"] == gl_code for f in facts):
                node = self.g.nodes.get(self._nid("Vendor", firm_id, vk), {})
                if node.get("canonical_name"):
                    names.append(node["canonical_name"])
            if len(names) >= limit:
                break
        return names[:limit]

    def vendor_open_facts(self, firm_id, vendor_key):
        out = []
        for (fid, vk, cid), facts in self.coded.items():
            if fid != firm_id or vk != vendor_key:
                continue
            for f in facts:
                if f["valid_to"] is None:
                    out.append({"client_id": cid, "code": f["code"],
                                "confidence": f["confidence"], "source": f["source"]})
        return out

    def clear_coded_to(self, firm_id):
        for k in [k for k in self.coded if k[0] == firm_id]:
            del self.coded[k]

    def reasoning_path(self, firm_id, transaction_key):
        node = self.g.nodes.get(self._nid("Transaction", firm_id, transaction_key))
        if not node:
            return {}
        return {"transaction": {"key": transaction_key, "vendor_raw": node.get("vendor_raw"),
                                "amount": node.get("amount"), "client_id": node.get("client_id")}}

    def stats(self):
        open_ct = sum(1 for facts in self.coded.values() for f in facts if f["valid_to"] is None)
        return {"backend": "networkx", "nodes": self.g.number_of_nodes(),
                "edges": self.g.number_of_edges(), "open_coded_to": open_ct}

    def save(self):
        import pickle
        with open(config.GRAPH_PICKLE, "wb") as f:
            pickle.dump({"g": self.g, "coded": self.coded}, f)

    def _load(self):
        import pickle
        with open(config.GRAPH_PICKLE, "rb") as f:
            d = pickle.load(f)
        self.g, self.coded = d["g"], d["coded"]


_STORE: Optional[GraphStore] = None


def get_store() -> GraphStore:
    global _STORE
    if _STORE is not None:
        return _STORE
    if config.GRAPH_BACKEND == "neo4j":
        try:
            _STORE = Neo4jStore()
        except Exception as e:
            print(f"[kg] Neo4j unavailable ({e}); using NetworkX fallback")
            _STORE = NetworkXStore()
    else:
        _STORE = NetworkXStore()
    return _STORE


def reset_store() -> None:
    global _STORE
    _STORE = None
