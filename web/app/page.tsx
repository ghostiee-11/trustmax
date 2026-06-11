"use client";
import React, { useEffect, useRef, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api, fmtNum, fmtUSD, pct } from "../lib/api";
import { Stat, Tag, StatusBadge, SectionTitle } from "../components/ui";

const TABS = [
  ["overview", "Overview"], ["coding", "Coding & Flywheel"], ["routing", "Document Routing"],
  ["alerts", "Anomaly Flags"], ["ask", "Ask Ed"], ["trust", "Trust & Security"],
];

export default function Page() {
  const [firms, setFirms] = useState<any[]>([]);
  const [firm, setFirm] = useState<string>("");
  const [tab, setTab] = useState("overview");
  const [meta, setMeta] = useState<any>(null);

  useEffect(() => {
    api("/firms").then((f) => { setFirms(f); setFirm(f[0]?.id); }).catch(() => {});
    api("/meta").then(setMeta).catch(() => {});
  }, []);

  const firmName = firms.find((f) => f.id === firm)?.name;

  return (
    <div className="min-h-screen grid grid-cols-[248px_1fr]">
      <aside className="border-r border-line bg-card/60 flex flex-col sticky top-0 h-screen">
        <div className="px-6 py-6 rule">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-sm bg-accent flex items-center justify-center text-white font-display text-sm">T</div>
            <span className="font-display text-xl tracking-tight">Trustmax</span>
          </div>
          <div className="tag text-muted mt-2">graph-native trust layer</div>
        </div>
        <nav className="px-3 py-4 flex-1">
          {TABS.map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)}
              className={`w-full text-left px-3 py-2 rounded-sm text-sm mb-0.5 transition-colors ${tab === id ? "bg-accentSoft text-accent font-medium" : "text-muted hover:text-ink hover:bg-line/40"}`}>
              {label}
            </button>
          ))}
        </nav>
        <div className="px-6 py-4 rule border-t text-xs text-muted">
          <div className="tag mb-1">tenant</div>
          <select value={firm} onChange={(e) => setFirm(e.target.value)}
            className="w-full bg-paper border border-line rounded-sm px-2 py-1.5 text-ink num text-xs">
            {firms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
      </aside>

      <div className="flex flex-col">
        {/* live header */}
        <header className="rule px-10 py-3 flex items-center justify-between bg-paper/80 backdrop-blur sticky top-0 z-10">
          <div className="text-sm text-muted">{firmName || " "}</div>
          <div className="flex items-center gap-3">
            {meta?.live && (
              <span className="flex items-center gap-1.5 text-xs text-muted">
                <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" /> live
              </span>
            )}
            <span className="tag text-muted border border-line rounded-sm px-2 py-1">
              {meta ? `${meta.provider} · ${meta.model}` : "connecting"}
            </span>
          </div>
        </header>
        <main className="px-10 py-8 max-w-[1100px]">
          {firm && (
            <>
              {tab === "overview" && <Overview firm={firm} />}
              {tab === "coding" && <Coding firm={firm} />}
              {tab === "routing" && <Routing firm={firm} />}
              {tab === "alerts" && <Alerts firm={firm} />}
              {tab === "ask" && <AskEd firm={firm} />}
              {tab === "trust" && <Trust firm={firm} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Skeleton({ h = 80, n = 1 }: { h?: number; n?: number }) {
  return <div className="grid grid-cols-4 gap-3">{Array.from({ length: n }).map((_, i) =>
    <div key={i} className="card animate-pulse" style={{ height: h }} />)}</div>;
}

function Overview({ firm }: { firm: string }) {
  const [ov, setOv] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    setOv(null);
    api(`/firms/${firm}/overview`).then(setOv).catch(() => {});
    api(`/stats`).then(setStats).catch(() => {});
  }, [firm]);
  const kg = stats?.knowledge_graph || {};
  return (
    <div>
      <SectionTitle kicker="firm overview" title={ov?.firm?.name || "Firm"}
        desc="One AI operating layer for the back office and client comms, with every decision learned, cited, and auditable." />
      {!ov ? <Skeleton n={4} /> : (
        <>
          <div className="grid grid-cols-4 gap-3 mb-3">
            <Stat label="clients" value={fmtNum(ov.clients)} />
            <Stat label="transactions" value={fmtNum(ov.transactions)} />
            <Stat label="documents" value={fmtNum(ov.documents)} />
            <Stat label="auto-approved" value={fmtNum(ov.auto_approved)} sub={`of ${fmtNum(ov.categorized)} categorized`} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="KG nodes (all firms)" value={fmtNum(kg.nodes)} />
            <Stat label="KG edges" value={fmtNum(kg.edges)} />
            <Stat label="learned facts" value={fmtNum(kg.open_coded_to)} sub="vendor to account, per client" />
          </div>
        </>
      )}
      <div className="card p-6 mt-3 rise">
        <div className="tag text-accent mb-2">how trust is enforced</div>
        <ul className="text-sm text-muted space-y-1.5">
          <li>Every GL code is grounded in a knowledge-graph fact and carries a reasoning path.</li>
          <li>Documents only auto-route to a client at near-certain confidence (0% misroute).</li>
          <li>Client answers are computed by query, validated, and cited, never generated numbers.</li>
          <li>Every action is written to a tamper-evident, hash-chained audit log.</li>
        </ul>
      </div>
    </div>
  );
}

function Coding({ firm }: { firm: string }) {
  const [score, setScore] = useState<any[]>([]);
  const [txns, setTxns] = useState<any[]>([]);
  useEffect(() => {
    setTxns([]);
    api(`/firms/${firm}/scorecard`).then((s) => {
      setScore(s);
      const last = s[s.length - 1]?.batch_id;  // newest batch = the learned state (data-driven)
      api(`/firms/${firm}/transactions?limit=40${last ? `&batch_id=${last}` : ""}`).then(setTxns).catch(() => {});
    }).catch(() => { api(`/firms/${firm}/transactions?limit=40`).then(setTxns).catch(() => {}); });
  }, [firm]);
  const data = score.map((r) => ({ batch: r.batch_id?.slice(5), accuracy: +(r.accuracy * 100).toFixed(1), auto: +(r.auto_approve_rate * 100).toFixed(1) }));
  return (
    <div>
      <SectionTitle kicker="max · back office" title="Coding flywheel"
        desc="Each human approval writes a fact into the graph. Accuracy and safe autonomy climb over time while the auto-approved error rate stays near zero. Trust is earned." />
      <div className="card p-6 mb-3 rise">
        <div className="flex justify-between items-baseline mb-4">
          <div className="font-display text-lg">Accuracy and autonomy over time</div>
          <div className="flex gap-4 text-xs">
            <span className="flex items-center gap-1.5"><i className="w-3 h-0.5 bg-accent inline-block" />accuracy</span>
            <span className="flex items-center gap-1.5"><i className="w-3 h-0.5 bg-amber inline-block" />auto-approve</span>
          </div>
        </div>
        {data.length ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data} margin={{ left: -18, right: 8, top: 4 }}>
              <CartesianGrid stroke="#E6E2D6" vertical={false} />
              <XAxis dataKey="batch" stroke="#6E6A5C" fontSize={11} tickLine={false} />
              <YAxis domain={[0, 100]} stroke="#6E6A5C" fontSize={11} tickLine={false} unit="%" />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #E6E2D6", fontFamily: "var(--font-mono)" }} />
              <Line type="monotone" dataKey="accuracy" stroke="#12734A" strokeWidth={2.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="auto" stroke="#B7791F" strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : <div className="h-[240px] animate-pulse bg-line/30 rounded" />}
      </div>
      <div className="card rise mb-3">
        <div className="px-5 py-2.5 rule tag text-muted">flywheel by month</div>
        {score.map((r) => (
          <div key={r.batch_id} className="ledger-row px-5 py-2 grid grid-cols-[auto_1fr_1fr_1fr_1fr] gap-4 text-xs items-center">
            <span className="num text-ink w-16">{r.batch_id}</span>
            <span className="num"><span className="text-muted">acc </span><span className="text-accent">{(r.accuracy * 100).toFixed(1)}%</span></span>
            <span className="num"><span className="text-muted">auto </span><span className="text-amber">{(r.auto_approve_rate * 100).toFixed(1)}%</span></span>
            <span className="num"><span className="text-muted">auto-err </span>{(r.auto_approved_error_rate * 100).toFixed(1)}%</span>
            <span className="num"><span className="text-muted">grounded </span>{(r.graph_grounded_rate * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
      <div className="card rise">
        <div className="px-5 py-2.5 rule flex justify-between text-xs tag text-muted">
          <span>recent transactions, click to see why</span><span>graph-grounded coding</span>
        </div>
        {txns.map((t) => <CodingRow key={t.id} t={t} />)}
      </div>
    </div>
  );
}

function CodingRow({ t }: { t: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rule">
      <button onClick={() => setOpen(!open)} className="w-full ledger-row px-5 py-2.5 grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 text-sm text-left">
        <div className="truncate"><span className="text-ink">{t.vendor_raw}</span> <span className="text-muted text-xs">· {t.client_id}</span></div>
        <div className="num text-muted">{fmtUSD(t.amount)}</div>
        <div className="num text-accent w-10 text-right">{t.predicted_code || "-"}</div>
        <Tag tone={t.graph_support > 0 ? "accent" : "muted"}>{t.graph_support > 0 ? "grounded" : "cold"}</Tag>
        <div className="w-28 text-right"><StatusBadge status={t.status} /></div>
      </button>
      {open && (
        <div className="px-5 pb-4 text-xs">
          <div className="grid grid-cols-3 gap-3 mb-2 num text-muted">
            <span>vendor match: <span className="text-ink">{t.er_method || "-"}</span></span>
            <span>graph support: <span className="text-ink">{t.graph_support != null ? `${(t.graph_support * 100).toFixed(0)}%` : "-"}</span></span>
            <span>confidence: <span className="text-ink">{t.calibrated_confidence != null ? `${(t.calibrated_confidence * 100).toFixed(0)}%` : "-"}</span></span>
          </div>
          {t.anomaly_flags?.length > 0 && <div className="text-amber mb-2">flags: {t.anomaly_flags.join(", ")}</div>}
          <ol className="border-l-2 border-accent/25 pl-4 space-y-1">
            {(t.reasoning_path || []).map((r: string, i: number) => (
              <li key={i} className="relative text-muted"><span className="absolute -left-[21px] top-1 w-1.5 h-1.5 rounded-full bg-accent/40" />{r}</li>
            ))}
            {(!t.reasoning_path || !t.reasoning_path.length) && <li className="text-muted">Coded from the chart of accounts; no learned graph fact yet.</li>}
          </ol>
        </div>
      )}
    </div>
  );
}

function Routing({ firm }: { firm: string }) {
  const [sum, setSum] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    setSum(null); setDocs([]);
    api(`/firms/${firm}/route/run`, { method: "POST" }).then(setSum).catch(() => {});
    api(`/firms/${firm}/routing`).then(setDocs).catch(() => {});
  }, [firm]);
  const counts = { all: docs.length, auto_routed: docs.filter((d) => d.status === "auto_routed").length, needs_review: docs.filter((d) => d.status === "needs_review").length };
  const shown = docs.filter((d) => filter === "all" || d.status === filter);
  return (
    <div>
      <SectionTitle kicker="max · document intake" title="Route to the right client"
        desc="Each incoming document is entity-linked to a client via deterministic keys and the graph. Click any document to see the matching signals. It only auto-routes when near-certain, because misrouting to the wrong client is a breach." />
      {!sum ? <Skeleton n={3} /> : (
        <div className="grid grid-cols-3 gap-3 mb-3">
          <Stat label="documents" value={fmtNum(sum.documents)} />
          <Stat label="auto-routed" value={fmtNum(sum.auto_routed)} sub={pct(sum.auto_routed / sum.documents)} />
          <Stat label="to human review" value={fmtNum(sum.needs_review)} sub="ambiguous, escalated" />
        </div>
      )}
      <div className="flex gap-1.5 mb-3">
        {[["all", "all"], ["auto_routed", "auto-routed"], ["needs_review", "needs review"]].map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)}
            className={`text-xs rounded-full px-3 py-1 border ${filter === id ? "border-accent text-accent bg-accentSoft" : "border-line text-muted"}`}>
            {label} <span className="num">{(counts as any)[id]}</span>
          </button>
        ))}
      </div>
      <div className="card rise">
        {shown.map((d) => <RoutingRow key={d.id} d={d} />)}
        {!shown.length && <div className="px-5 py-6 text-sm text-muted text-center">loading documents…</div>}
      </div>
    </div>
  );
}

function RoutingRow({ d }: { d: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rule">
      <button onClick={() => setOpen(!open)} className="w-full ledger-row px-5 py-2.5 grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 text-sm text-left">
        <div className="truncate"><span className="text-ink">{d.filename}</span> <span className="text-muted text-xs">· {d.doc_type}</span></div>
        <div className="num text-muted text-xs hidden md:block">{d.sender_domain}</div>
        <div className="num text-muted text-xs w-12 text-right">{d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : ""}</div>
        <div className="w-28 text-right"><StatusBadge status={d.status} /></div>
      </button>
      {open && (
        <div className="px-5 pb-4 text-xs">
          <div className="mb-2">
            {d.status === "auto_routed"
              ? <span className="text-muted">routed to <span className="text-accent">{d.routed_client_name}</span> at {(d.confidence * 100).toFixed(0)}% confidence</span>
              : <span className="text-amber">ambiguous, escalated to a human: which client?</span>}
          </div>
          <div className="text-muted mb-1">matching signals on the graph:</div>
          <ul className="space-y-0.5">
            {(d.evidence || []).map((e: string, i: number) => <li key={i} className="text-ink">· {e}</li>)}
            {(!d.evidence || !d.evidence.length) && <li className="text-muted">no strong identifier matched, so a human decides.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

const ALERT_LABELS: Record<string, string> = { duplicate: "Duplicate payment", unusual_amount: "Unusual amount", missing_category: "Missing category" };

function Alerts({ firm }: { firm: string }) {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  useEffect(() => { setAlerts([]); api(`/firms/${firm}/alerts`).then(setAlerts).catch(() => {}); }, [firm]);
  const counts: any = { all: alerts.length };
  ["duplicate", "unusual_amount", "missing_category"].forEach((t) => counts[t] = alerts.filter((a) => a.type === t).length);
  const shown = alerts.filter((a) => filter === "all" || a.type === filter).slice(0, 60);
  return (
    <div>
      <SectionTitle kicker="max · real-time" title="Anomaly flags"
        desc="Duplicates, unusual amounts, and missing categories, each with the evidence that justifies it. Click an alert to inspect the evidence and confirm or dismiss it." />
      <div className="flex gap-1.5 mb-3">
        {[["all", "all"], ["duplicate", "duplicates"], ["unusual_amount", "unusual amounts"], ["missing_category", "missing category"]].map(([id, label]) => (
          <button key={id} onClick={() => setFilter(id)}
            className={`text-xs rounded-full px-3 py-1 border ${filter === id ? "border-accent text-accent bg-accentSoft" : "border-line text-muted"}`}>
            {label} <span className="num">{counts[id] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {shown.map((a, i) => <AlertRow key={a.id || i} a={a} />)}
        {!shown.length && <div className="card px-5 py-6 text-sm text-muted text-center">scanning…</div>}
      </div>
    </div>
  );
}

function AlertRow({ a }: { a: any }) {
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<string | null>(null);
  return (
    <div className="card rise">
      <button onClick={() => setOpen(!open)} className="w-full px-5 py-3 flex items-center gap-4 text-left">
        <StatusBadge status={a.severity} />
        <div className="flex-1">
          <div className="text-sm text-ink">{ALERT_LABELS[a.type] || a.type}</div>
          <div className="text-xs text-muted">{a.evidence?.note}</div>
        </div>
        {decision && <Tag tone={decision === "confirmed" ? "rust" : "muted"}>{decision}</Tag>}
        <div className="num text-xs text-muted hidden md:block">{a.transaction_id}</div>
      </button>
      {open && (
        <div className="px-5 pb-4 pt-3 border-t border-line text-xs">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 num text-muted mb-3">
            {Object.entries(a.evidence || {}).filter(([k]) => k !== "note").map(([k, v]) => (
              <div key={k}><span>{k.replace(/_/g, " ")}: </span><span className="text-ink">{String(v)}</span></div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setDecision("confirmed")} className="text-xs border border-rust/40 text-rust rounded-sm px-3 py-1 hover:bg-rust/5">confirm issue</button>
            <button onClick={() => setDecision("dismissed")} className="text-xs border border-line text-muted rounded-sm px-3 py-1 hover:border-ink">dismiss (false positive)</button>
          </div>
        </div>
      )}
    </div>
  );
}

const THINKING = ["scoping to client", "planning a constrained query", "querying the graph + ledger", "computing from the ledger", "validating against evidence", "composing with the model"];

function AskEd({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const ctxRef = useRef<any>(null);   // conversation memory (last resolved query)
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api(`/firms/${firm}/clients`).then((c) => { setClients(c); setClient(c[0]?.id); }).catch(() => {}); }, [firm]);
  // changing the client (or firm) starts a fresh conversation
  useEffect(() => { setMsgs([]); ctxRef.current = null; }, [client, firm]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9, behavior: "smooth" }); }, [msgs, loading]);
  useEffect(() => {
    if (!loading) return;
    const t = setInterval(() => setStep((s) => (s + 1) % THINKING.length), 550);
    return () => clearInterval(t);
  }, [loading]);

  const ask = async (question?: string) => {
    const text = (question ?? q).trim();
    if (!text || loading) return;
    setQ(""); setStep(0);
    const history = msgs.map((m) => ({ role: m.role === "user" ? "user" : "ed", text: m.role === "user" ? m.text : m.answer }));
    setMsgs((m) => [...m, { role: "user", text }]);
    setLoading(true);
    try {
      const r = await api(`/ask`, { method: "POST", body: JSON.stringify({ firm_id: firm, client_id: client, question: text, context: ctxRef.current, history }) });
      if (r.context) ctxRef.current = r.context;
      setMsgs((m) => [...m, { role: "ed", ...r }]);
    } catch {
      setMsgs((m) => [...m, { role: "ed", answer: "Something went wrong reaching the ledger.", abstained: true, trace: [] }]);
    } finally { setLoading(false); }
  };

  const samples = [
    "How much did we spend on Software Subscriptions in January 2026?",
    "Who is our biggest vendor in 2026?",
    "What was our largest expense in January 2026?",
    "Break down our spending by category in January 2026",
    "How much did we spend with Amazon Web Services in 2026?",
    "Show me all our Travel transactions in January 2026",
    "What were our total expenses in Q1 2026?",
    "How many transactions did we have in January 2026?",
    "Should I convert my LLC to an S-corp?",
  ];

  return (
    <div>
      <SectionTitle kicker="ed · client-facing" title="Ask Ed"
        desc="Ed answers from this client's own ledger. Numbers are computed by query and validated, the model only phrases the reply, and Ed abstains and escalates when it cannot ground an answer." />

      <div className="flex items-center gap-2 mb-3">
        <span className="tag text-muted">client</span>
        <select value={client} onChange={(e) => setClient(e.target.value)} className="bg-paper border border-line rounded-sm px-2 py-1.5 text-xs num">
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      <div ref={scrollRef} className="card rise p-5 h-[440px] overflow-y-auto flex flex-col gap-4">
        {msgs.length === 0 && !loading && (
          <div className="text-sm text-muted m-auto text-center max-w-sm">
            Ask about this client's spend, totals, or transaction counts. Try an advisory question to watch Ed abstain.
          </div>
        )}
        {msgs.map((m, i) => m.role === "user" ? (
          <div key={i} className="self-end max-w-[80%] bg-accent text-white rounded-lg rounded-br-sm px-4 py-2.5 text-sm">{m.text}</div>
        ) : (
          <EdMessage key={i} m={m} />
        ))}
        {loading && (
          <div className="self-start max-w-[80%]">
            <div className="flex items-center gap-2 text-sm text-muted">
              <span className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: "120ms" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: "240ms" }} />
              </span>
              <span className="num text-xs">{THINKING[step]}…</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2 mt-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Ask Ed about this client's books…"
          className="flex-1 bg-card border border-line rounded-sm px-3 py-2.5 text-sm" />
        <button onClick={() => ask()} disabled={loading} className="bg-accent text-white px-6 rounded-sm text-sm font-medium disabled:opacity-50">Send</button>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {samples.map((s) => <button key={s} onClick={() => ask(s)} className="text-xs text-muted border border-line rounded-full px-3 py-1 hover:border-accent hover:text-accent">{s}</button>)}
      </div>
    </div>
  );
}

function AnswerTable({ table }: { table: any }) {
  const rows = table.rows || [];
  return (
    <div className="mt-2 card overflow-hidden">
      <div className="max-h-56 overflow-y-auto">
        {table.type === "transactions" && rows.map((r: any, i: number) => (
          <div key={i} className="ledger-row px-3 py-1.5 grid grid-cols-[auto_1fr_auto_auto] gap-3 items-center text-xs">
            <span className="num text-muted">{r.date}</span>
            <span className="text-ink truncate">{r.vendor}</span>
            <span className="num text-ink text-right">{fmtUSD(r.amount)}</span>
            <span className="num text-accent w-8 text-right">{r.code}</span>
          </div>
        ))}
        {table.type === "vendors" && rows.map((r: any, i: number) => (
          <div key={i} className="ledger-row px-3 py-1.5 grid grid-cols-[1fr_auto_auto] gap-3 items-center text-xs">
            <span className="text-ink truncate">{r.vendor}</span>
            <span className="num text-muted">{r.count} txns</span>
            <span className="num text-ink text-right w-20">{fmtUSD(r.total)}</span>
          </div>
        ))}
        {table.type === "breakdown" && rows.map((r: any, i: number) => (
          <div key={i} className="ledger-row px-3 py-1.5 grid grid-cols-[auto_1fr_auto] gap-3 items-center text-xs">
            <span className="num text-accent w-8">{r.code}</span>
            <span className="text-ink truncate">{r.name}</span>
            <span className="num text-ink text-right w-20">{fmtUSD(r.total)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EdMessage({ m }: { m: any }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="self-start max-w-[85%]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <div className="w-5 h-5 rounded-sm bg-ink text-white flex items-center justify-center text-[10px] font-display">E</div>
        {m.abstained ? <Tag tone="amber">escalated to accountant</Tag>
          : <><Tag tone="accent">grounded</Tag><span className="tag text-muted">{m.generated_by}</span></>}
        {!m.abstained && m.citations && <span className="tag text-muted">{m.citations.length} citations</span>}
      </div>
      <p className="font-display text-lg text-ink leading-snug bg-card border border-line rounded-lg rounded-tl-sm px-4 py-3">{m.answer}</p>
      {m.table && <AnswerTable table={m.table} />}
      {m.trace?.length > 0 && (
        <div className="mt-1.5">
          <button onClick={() => setOpen(!open)} className="tag text-muted hover:text-accent">{open ? "hide" : "show"} agent trace</button>
          {open && (
            <ol className="mt-2 border-l-2 border-accent/25 pl-4 space-y-1.5">
              {m.trace.map((s: any, i: number) => (
                <li key={i} className="relative text-xs">
                  <span className={`absolute -left-[21px] top-1 w-2 h-2 rounded-full ${s.ok ? "bg-accent" : "bg-rust"}`} />
                  <span className="text-ink">{s.label}</span>
                  {s.detail && <span className="text-muted num"> · {s.detail}</span>}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

const SCENARIOS = [
  { id: "tamper", threat: "Someone edits a posted transaction to hide activity", endpoint: "/security/demo/tamper" },
  { id: "cross_tenant", threat: "One firm's staff tries to open another firm's client file", endpoint: "/security/demo/cross_tenant" },
  { id: "rbac", threat: "A junior associate tries to export the audit trail", endpoint: "/security/demo/rbac" },
  { id: "encrypt", threat: "A database row leaks: can anyone read the client's EIN?", endpoint: "/security/demo/encrypt" },
  { id: "pii", threat: "A client message accidentally contains an SSN and bank account", endpoint: "/security/demo/pii" },
];

function ScenarioCard({ s }: { s: any }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const run = async () => { setLoading(true); try { setData(await api(s.endpoint)); } finally { setLoading(false); } };
  const safe = data && (data.tampered?.valid === false || data.blocked || data.other_firm_decrypt === "could not decrypt" || s.id === "rbac" || (s.id === "pii" && data.clean === false));
  return (
    <div className="card p-5 rise">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="tag text-rust mb-1">threat</div>
          <div className="text-sm text-ink">{s.threat}</div>
        </div>
        <button onClick={run} disabled={loading}
          className="shrink-0 text-xs border border-line rounded-sm px-3 py-1.5 hover:border-accent hover:text-accent disabled:opacity-50">
          {loading ? "running…" : data ? "re-run" : "simulate"}
        </button>
      </div>
      {data && (
        <div className="mt-3 pt-3 border-t border-line">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${safe ? "bg-accent" : "bg-rust"}`} />
            <span className={`tag ${safe ? "text-accent" : "text-rust"}`}>{safe ? "stopped" : "exposed"}</span>
          </div>
          {s.id === "tamper" && (
            <div className="text-xs space-y-1">
              <div className="flex justify-between"><span className="text-muted">clean chain</span><span className="num text-accent">verified, {data.clean?.rows} rows</span></div>
              <div className="flex justify-between"><span className="text-muted">after the edit</span><span className="num text-rust">BROKEN at row {data.tampered?.broken_at}</span></div>
            </div>
          )}
          {s.id === "cross_tenant" && <div className="num text-xs text-rust">{data.blocked ? "ACCESS DENIED" : "leaked"}</div>}
          {s.id === "rbac" && (
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 gap-y-0.5 text-[11px]">
              <span /><span className="tag text-muted">approve</span><span className="tag text-muted">message</span><span className="tag text-muted">export</span>
              {["partner", "manager", "associate"].map((r) => (
                <React.Fragment key={r}>
                  <span className="text-muted">{r}</span>
                  {["approve", "send_message", "export_audit"].map((a) => {
                    const ok = data.matrix?.find((m: any) => m.role === r && m.action === a)?.allowed;
                    return <span key={a} className={`num text-center ${ok ? "text-accent" : "text-rust"}`}>{ok ? "✓" : "✕"}</span>;
                  })}
                </React.Fragment>
              ))}
            </div>
          )}
          {s.id === "encrypt" && (
            <div className="text-xs space-y-1">
              <div className="flex justify-between"><span className="text-muted">at rest</span><span className="num text-ink truncate ml-3">{data.ciphertext_at_rest}</span></div>
              <div className="flex justify-between"><span className="text-muted">another firm's key</span><span className="num text-accent">{data.other_firm_decrypt}</span></div>
            </div>
          )}
          {s.id === "pii" && (
            <div className="text-xs space-y-1">
              <div className="text-rust">caught: {(data.findings || []).map((f: any) => f.type).join(", ")}</div>
              <div className="num text-ink">{data.redacted}</div>
            </div>
          )}
          <div className="text-xs text-muted mt-2 pt-2 border-t border-line"><span className="text-accent">how we solve it. </span>{data.solution}</div>
        </div>
      )}
    </div>
  );
}

function ComplianceCard({ firm }: { firm: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const run = async () => { setLoading(true); try { setData(await api(`/firms/${firm}/compliance`)); } finally { setLoading(false); } };
  const tone: Record<string, string> = { high: "rust", medium: "amber", low: "muted" };
  return (
    <div className="card p-5 mt-3 rise">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="tag text-accent mb-1">compliance agent</div>
          <div className="text-sm text-ink max-w-xl">A background reviewer that watches the firm for governance risk: high-value auto-approvals, self-approval, approval concentration, unresolved high-severity alerts, and vendors with a high correction rate.</div>
        </div>
        <button onClick={run} disabled={loading} className="shrink-0 text-xs border border-line rounded-sm px-3 py-1.5 hover:border-accent hover:text-accent disabled:opacity-50">{loading ? "scanning…" : data ? "re-scan" : "run scan"}</button>
      </div>
      {data && (
        <div className="mt-3 pt-3 border-t border-line space-y-2">
          <div className="tag text-muted">{data.summary.total} findings · {data.summary.high} high · SoD {data.summary.sod_clean ? "clean" : "violation"} · {fmtNum(data.summary.scanned_events)} events scanned</div>
          {data.findings.map((f: any, i: number) => (
            <div key={i} className="flex items-start gap-3 text-xs pt-1">
              <Tag tone={tone[f.severity]}>{f.severity}</Tag>
              <div className="flex-1">
                <div className="text-ink">{f.detail}</div>
                <div className="text-muted">recommend: {f.recommendation}</div>
              </div>
            </div>
          ))}
          {!data.findings.length && <div className="text-xs text-accent">No governance issues found.</div>}
        </div>
      )}
    </div>
  );
}

function Trust({ firm }: { firm: string }) {
  const [health, setHealth] = useState<any>(null);
  const [explain, setExplain] = useState<any>(null);
  const [txId, setTxId] = useState("");
  const [narr, setNarr] = useState<any>(null);
  const [narrLoading, setNarrLoading] = useState(false);
  useEffect(() => {
    setHealth(null); setExplain(null); setNarr(null);
    api(`/firms/${firm}/trust/health`).then(setHealth).catch(() => {});
    api(`/firms/${firm}/transactions?limit=1`).then((t) => {
      if (t[0]) { setTxId(t[0].id); api(`/firms/${firm}/explain/${t[0].id}`).then(setExplain).catch(() => {}); }
    }).catch(() => {});
  }, [firm]);
  const narrate = async () => { setNarrLoading(true); try { setNarr(await api(`/firms/${firm}/explain/${txId}/narrate`)); } finally { setNarrLoading(false); } };
  return (
    <div>
      <SectionTitle kicker="trust spine" title="Trust and security"
        desc="A compliance agent watches the firm, an explainability agent narrates any number, and each threat below shows what could go wrong and how Trustmax stops it." />
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="audit chain" value={health?.audit_chain_valid ? "verified" : "broken"} sub={`${fmtNum(health?.audit_events)} events`} />
        <Stat label="security checks" value={health?.security_checks || "—"} />
        <Stat label="compliance findings" value={fmtNum(health?.compliance_findings)} sub={`${health?.compliance_high || 0} high`} />
        <Stat label="segregation of duties" value={health?.sod_clean ? "clean" : "violation"} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {SCENARIOS.map((s) => <ScenarioCard key={s.id} s={s} />)}
      </div>
      <ComplianceCard firm={firm} />
      {explain && !explain.error && (
        <div className="card p-6 mt-3 rise">
          <div className="flex items-center justify-between mb-2">
            <div className="tag text-accent">explain this number</div>
            <button onClick={narrate} disabled={narrLoading || !txId} className="text-xs border border-line rounded-sm px-3 py-1 hover:border-accent hover:text-accent disabled:opacity-50">{narrLoading ? "…" : "narrate in plain English"}</button>
          </div>
          <div className="text-sm mb-3">
            <span className="text-ink">{explain.transaction?.vendor_raw}</span>
            <span className="num text-muted"> · {fmtUSD(explain.transaction?.amount)}</span>
            <span className="num text-accent"> to {explain.decision?.code}</span>
          </div>
          {narr && (
            <p className="font-display text-base text-ink mb-3 bg-accentSoft/50 border border-accent/20 rounded-sm px-3 py-2 leading-snug">
              {narr.narrative} <span className="tag text-muted">via {narr.generated_by}</span>
            </p>
          )}
          <ol className="border-l-2 border-accent/30 pl-4 space-y-2">
            {(explain.reasoning_path || []).map((r: string, i: number) => (
              <li key={i} className="text-sm text-muted relative">
                <span className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-accent/40" />{r}
              </li>
            ))}
          </ol>
          <div className="mt-4 pt-3 border-t border-line text-xs text-muted">
            {fmtNum(explain.audit_trail?.length)} audit events recorded for this transaction.
          </div>
        </div>
      )}
    </div>
  );
}
