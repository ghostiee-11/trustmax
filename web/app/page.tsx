"use client";
import React, { useEffect, useRef, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api, fmtNum, fmtUSD, pct } from "../lib/api";
import { Stat, Tag, StatusBadge, SectionTitle, Meter, Chip, Select, Rail } from "../components/ui";
import { I } from "../components/icons";

// never surface a raw model id in the UI; show a clean label instead
const genLabel = (g?: string) => (!g ? "" : /llama|groq|gpt|claude|mistral|\//i.test(g) ? "model phrased" : g);

/* ------------------------------------------------------------------ */
/* app shell                                                            */
/* ------------------------------------------------------------------ */

const NAV_GROUPS: { label: string | null; items: { id: string; label: string; icon: string }[] }[] = [
  { label: null, items: [{ id: "overview", label: "Overview", icon: "overview" }] },
  {
    label: "Max · Back office",
    items: [
      { id: "ingest", label: "Live Ingest", icon: "upload" },
      { id: "coding", label: "Coding & Flywheel", icon: "flywheel" },
      { id: "routing", label: "Document Routing", icon: "route" },
      { id: "recon", label: "Reconciliation", icon: "balance" },
      { id: "flux", label: "Flux & Variance", icon: "trend" },
      { id: "close", label: "Close & Collect", icon: "clipboard" },
      { id: "alerts", label: "Anomaly Flags", icon: "flag" },
    ],
  },
  { label: "Ed · Clients", items: [{ id: "ask", label: "Ask Ed", icon: "chat" }] },
  { label: "Trust", items: [{ id: "trust", label: "Trust & Security", icon: "shield" }] },
];

const PAGE_META: Record<string, { kicker: string; title: string }> = {
  overview: { kicker: "Workspace", title: "Overview" },
  ingest: { kicker: "Max · Back office", title: "Live Ingest" },
  coding: { kicker: "Max · Back office", title: "Coding & Flywheel" },
  routing: { kicker: "Max · Back office", title: "Document Routing" },
  recon: { kicker: "Max · Back office", title: "Reconciliation" },
  flux: { kicker: "Max · Back office", title: "Flux & Variance" },
  close: { kicker: "Max · Back office", title: "Close & Collect" },
  alerts: { kicker: "Max · Back office", title: "Anomaly Flags" },
  ask: { kicker: "Ed · Client-facing", title: "Ask Ed" },
  trust: { kicker: "Trust spine", title: "Trust & Security" },
};

function BrandMark() {
  return (
    <div className="w-9 h-9 shrink-0 rounded-[10px] bg-gradient-to-br from-accent to-accentDeep flex items-center justify-center shadow-[0_2px_6px_rgba(14,77,50,0.35),inset_0_1px_0_rgba(255,255,255,0.18)]">
      <svg viewBox="0 0 20 20" width="19" height="19" fill="none" stroke="#FFFFFF" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M4 5h12" />
        <path d="M4 9h6" />
        <path d="M4 13h3.5" />
        <path d="m10.5 13.5 3 3 5-6" />
      </svg>
    </div>
  );
}

function FirmSwitcher({ firms, firm, onChange }: { firms: any[]; firm: string; onChange: (id: string) => void }) {
  const current = firms.find((f) => f.id === firm);
  const initials = (current?.name || "")
    .split(/\s+/)
    .map((w: string) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="p-3 border-t border-line">
      <div className="tag text-faint px-1.5 mb-1.5">Firm workspace</div>
      <div className="relative flex items-center gap-2.5 rounded-xl border border-line bg-card p-2.5 shadow-card hover:border-lineStrong transition-colors">
        <div className="w-8 h-8 shrink-0 rounded-lg bg-accentSoft border border-accent/20 text-accent font-display text-[13px] flex items-center justify-center">
          {initials || <I name="building" size={14} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium text-ink truncate">{current?.name || "Select a firm"}</div>
          <div className="tag text-faint truncate">{firm || "connecting"}</div>
        </div>
        <I name="chevronsUpDown" size={14} className="text-faint shrink-0" />
        <select
          value={firm}
          onChange={(e) => onChange(e.target.value)}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          aria-label="Switch firm"
        >
          {firms.map((f) => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function Page() {
  const [firms, setFirms] = useState<any[]>([]);
  const [firm, setFirm] = useState<string>("");
  const [tab, setTab] = useState("overview");
  const [meta, setMeta] = useState<any>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    api("/firms").then((f) => { setFirms(f); setFirm(f[0]?.id); }).catch(() => {});
    api("/meta").then(setMeta).catch(() => {});
  }, []);

  const firmName = firms.find((f) => f.id === firm)?.name;
  const pageMeta = PAGE_META[tab] || { kicker: "", title: "" };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[264px_1fr]">
      <div
        className={`fixed inset-0 z-40 bg-ink/40 transition-opacity duration-200 lg:hidden ${sidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none"}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden="true"
      />
      <aside
        className={`fixed top-0 left-0 z-50 h-screen w-[264px] flex flex-col border-r border-line bg-shell shadow-pop transition-transform duration-200 ease-out ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        } lg:sticky lg:z-auto lg:w-auto lg:translate-x-0 lg:bg-shell/70 lg:shadow-none lg:transition-none`}
      >
        <div className="px-5 pt-6 pb-4 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <BrandMark />
            <div className="min-w-0">
              <div className="font-display text-[19px] tracking-tight leading-none text-ink">Trustmax</div>
              <div className="tag text-faint mt-1.5">Graph-native trust layer</div>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden shrink-0 -mr-1 p-1.5 rounded-lg text-muted hover:text-ink hover:bg-ink/5"
            aria-label="Close navigation"
          >
            <I name="x" size={16} />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {NAV_GROUPS.map((g, gi) => (
            <div key={gi}>
              {g.label ? <div className="nav-group">{g.label}</div> : <div className="h-2" />}
              {g.items.map((it) => (
                <button
                  key={it.id}
                  onClick={() => { setTab(it.id); setSidebarOpen(false); }}
                  data-active={tab === it.id}
                  className="nav-item mb-0.5"
                >
                  <I name={it.icon} size={16} className="nav-ico" strokeWidth={1.7} />
                  {it.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <FirmSwitcher firms={firms} firm={firm} onChange={setFirm} />
      </aside>

      <div className="flex flex-col min-w-0">
        <header className="sticky top-0 z-30 h-[58px] px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-3 border-b border-line bg-paper/85 backdrop-blur">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden shrink-0 -ml-1 p-1.5 rounded-lg text-muted hover:text-ink hover:bg-ink/5"
              aria-label="Open navigation"
            >
              <I name="menu" size={18} />
            </button>
            <div className="min-w-0">
              <div className="tag text-faint leading-none">{pageMeta.kicker}</div>
              <div className="font-display text-[16px] text-ink leading-tight mt-0.5 truncate">{pageMeta.title}</div>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accentSoft px-2.5 py-[5px] text-[11px] font-medium text-accent">
              <span className="w-1.5 h-1.5 rounded-full bg-accent pulse-dot" />
              {meta?.live ? "Live" : "Connecting"}
            </span>
          </div>
        </header>

        <main className="px-4 sm:px-6 lg:px-8 py-6 lg:py-9">
          <div className="mx-auto max-w-[1120px]">
            {firm && (
              <div key={`${tab}:${firm}`}>
                {tab === "overview" && <Overview firm={firm} firmName={firmName} />}
                {tab === "ingest" && <Ingest firm={firm} />}
                {tab === "coding" && <Coding firm={firm} />}
                {tab === "routing" && <Routing firm={firm} />}
                {tab === "recon" && <Recon firm={firm} />}
                {tab === "flux" && <Flux firm={firm} />}
                {tab === "close" && <Close firm={firm} />}
                {tab === "alerts" && <Alerts firm={firm} />}
                {tab === "ask" && <AskEd firm={firm} />}
                {tab === "trust" && <Trust firm={firm} />}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* shared loading pieces                                                */
/* ------------------------------------------------------------------ */

function SkelStats({ n, className = "" }: { n: number; className?: string }) {
  const cols =
    n === 4 ? "grid-cols-2 lg:grid-cols-4"
    : n === 3 ? "grid-cols-1 sm:grid-cols-3"
    : n === 2 ? "grid-cols-1 md:grid-cols-2"
    : "grid-cols-1";
  return (
    <div className={`grid gap-3 ${cols} ${className}`}>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="skel h-[108px]" />
      ))}
    </div>
  );
}

function SkelRows({ n = 5 }: { n?: number }) {
  return (
    <div className="px-5 py-4 space-y-3">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="skel h-9" style={{ opacity: Math.max(0.25, 1 - i * 0.16) }} />
      ))}
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-2">
      <div className="tag text-faint">{label}</div>
      <div className="num text-[13px] text-ink mt-1">{value}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* overview                                                             */
/* ------------------------------------------------------------------ */

const PRINCIPLES = [
  { icon: "graph", title: "Grounded coding", desc: "Every GL code is grounded in a knowledge-graph fact and carries a reasoning path you can inspect." },
  { icon: "route", title: "Near-certain routing", desc: "Documents only auto-route to a client at near-certain confidence. A misroute is treated as a breach." },
  { icon: "chat", title: "Computed answers", desc: "Client answers are computed by query, validated, and cited. Never generated numbers." },
  { icon: "shield", title: "Tamper-evident audit", desc: "Every action is written to a hash-chained audit log that proves nothing was quietly altered." },
];

function Overview({ firm, firmName }: { firm: string; firmName?: string }) {
  const [ov, setOv] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    setOv(null);
    api(`/firms/${firm}/overview`).then(setOv).catch(() => {});
    api(`/stats`).then(setStats).catch(() => {});
  }, [firm]);
  const kg = stats?.knowledge_graph || {};
  return (
    <div className="stagger">
      <SectionTitle
        kicker="Firm overview"
        title={ov?.firm?.name || firmName || "Firm"}
        desc="One AI operating layer for the back office and client comms, with every decision learned, cited, and auditable."
      />

      {!ov ? (
        <SkelStats n={4} className="mb-3" />
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <Stat label="Clients" value={fmtNum(ov.clients)} />
          <Stat label="Transactions" value={fmtNum(ov.transactions)} />
          <Stat label="Documents" value={fmtNum(ov.documents)} />
          <Stat
            label="Auto-approved"
            value={fmtNum(ov.auto_approved)}
            sub={`of ${fmtNum(ov.categorized)} categorized`}
            meter={ov.categorized ? ov.auto_approved / ov.categorized : 0}
          />
        </div>
      )}

      <div className="panel-pine p-7 mb-3">
        <svg className="absolute inset-y-0 right-0 h-full w-[46%] pointer-events-none" viewBox="0 0 420 200" fill="none" aria-hidden="true">
          <g stroke="#FFFFFF" strokeOpacity="0.09" strokeWidth="1">
            <path d="M40 160 150 60M150 60 270 120M270 120 390 40M150 60 320 30M270 120 200 185M320 30 390 40M40 160 200 185" />
          </g>
          <g fill="#FFFFFF" fillOpacity="0.16">
            <circle cx="40" cy="160" r="4" /><circle cx="150" cy="60" r="5" /><circle cx="270" cy="120" r="4" />
            <circle cx="390" cy="40" r="5" /><circle cx="320" cy="30" r="3.5" /><circle cx="200" cy="185" r="3.5" />
          </g>
        </svg>
        <div className="relative flex flex-wrap items-center justify-between gap-8">
          <div className="max-w-md">
            <div className="tag text-[#9CC4AA] mb-2">Knowledge graph · shared memory</div>
            <div className="font-display text-[22px] leading-snug">Every decision is grounded in the graph</div>
            <p className="text-[13px] leading-relaxed text-[#BFD6C6] mt-2">
              Vendors, accounts, clients, and learned facts form one connected memory across the firm. Each human approval makes the next decision safer.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-10 gap-y-4 pr-2">
            <div>
              <div className="num text-[26px] font-medium text-white leading-tight">{fmtNum(kg.nodes)}</div>
              <div className="tag text-[#9CC4AA] mt-1.5">Nodes · all firms</div>
            </div>
            <div>
              <div className="num text-[26px] font-medium text-white leading-tight">{fmtNum(kg.edges)}</div>
              <div className="tag text-[#9CC4AA] mt-1.5">Edges</div>
            </div>
            <div>
              <div className="num text-[26px] font-medium text-white leading-tight">{fmtNum(kg.open_coded_to)}</div>
              <div className="tag text-[#9CC4AA] mt-1.5">Learned facts</div>
              <div className="text-[11px] text-[#9CC4AA]/80 mt-0.5">vendor to account, per client</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {PRINCIPLES.map((p) => (
          <div key={p.title} className="card card-hover p-5 flex items-start gap-3.5">
            <div className="w-9 h-9 shrink-0 rounded-lg bg-accentSoft border border-accent/15 text-accent flex items-center justify-center">
              <I name={p.icon} size={16} strokeWidth={1.7} />
            </div>
            <div>
              <div className="text-[13.5px] font-semibold text-ink">{p.title}</div>
              <p className="text-xs text-muted leading-relaxed mt-1">{p.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* coding & flywheel                                                    */
/* ------------------------------------------------------------------ */

function Coding({ firm }: { firm: string }) {
  const [score, setScore] = useState<any[]>([]);
  const [txns, setTxns] = useState<any[]>([]);
  useEffect(() => {
    setScore([]); setTxns([]);
    api(`/firms/${firm}/scorecard`).then((s) => {
      setScore(s);
      const last = s[s.length - 1]?.batch_id; // newest batch = the learned state (data-driven)
      api(`/firms/${firm}/transactions?limit=40${last ? `&batch_id=${last}` : ""}`).then(setTxns).catch(() => {});
    }).catch(() => { api(`/firms/${firm}/transactions?limit=40`).then(setTxns).catch(() => {}); });
  }, [firm]);
  const data = score.map((r) => ({
    batch: r.batch_id?.slice(5),
    accuracy: +(r.accuracy * 100).toFixed(1),
    auto: +(r.auto_approve_rate * 100).toFixed(1),
  }));
  const latest = score[score.length - 1];
  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Back office"
        title="Coding flywheel"
        desc="Each human approval writes a fact into the graph. Accuracy and safe autonomy climb over time while the auto-approved error rate stays near zero. Trust is earned."
      />

      {!latest ? (
        <SkelStats n={4} className="mb-3" />
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <Stat label="Accuracy" value={`${(latest.accuracy * 100).toFixed(1)}%`} meter={latest.accuracy} sub={`latest batch ${latest.batch_id}`} />
          <Stat label="Auto-approve rate" value={`${(latest.auto_approve_rate * 100).toFixed(1)}%`} meter={latest.auto_approve_rate} tone="amber" sub="earned autonomy" />
          <Stat label="Auto-approved errors" value={`${(latest.auto_approved_error_rate * 100).toFixed(1)}%`} sub="held near zero by design" />
          <Stat label="Graph-grounded" value={`${(latest.graph_grounded_rate * 100).toFixed(0)}%`} sub="decisions backed by a learned fact" />
        </div>
      )}

      <div className="card card-hover p-6 mb-3">
        <div className="flex flex-wrap justify-between items-baseline gap-x-4 gap-y-2 mb-5">
          <div className="font-display text-[17px] text-ink">Accuracy and autonomy over time</div>
          <div className="flex gap-4 text-xs text-muted">
            <span className="flex items-center gap-1.5"><i className="w-3 h-[3px] rounded-full bg-accent inline-block" />accuracy</span>
            <span className="flex items-center gap-1.5"><i className="w-3 h-[3px] rounded-full bg-amber inline-block" />auto-approve</span>
          </div>
        </div>
        {data.length ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data} margin={{ left: -16, right: 8, top: 4 }}>
              <CartesianGrid stroke="#ECE8DB" strokeDasharray="3 5" vertical={false} />
              <XAxis dataKey="batch" stroke="#9C9786" fontSize={11} tickLine={false} axisLine={{ stroke: "#E7E3D5" }} tickMargin={8} fontFamily="var(--font-mono)" />
              <YAxis domain={[0, 100]} stroke="#9C9786" fontSize={11} tickLine={false} axisLine={false} unit="%" fontFamily="var(--font-mono)" />
              <Tooltip
                contentStyle={{
                  fontSize: 12, borderRadius: 10, border: "1px solid #E7E3D5", background: "#FFFFFF",
                  boxShadow: "0 12px 32px -16px rgba(27,26,20,0.25)", fontFamily: "var(--font-mono)", padding: "8px 12px",
                }}
                labelStyle={{ color: "#6E6A5B", marginBottom: 4 }}
                formatter={(v: any) => `${v}%`}
                cursor={{ stroke: "#D7D2C0", strokeDasharray: "3 4" }}
              />
              <Line type="monotone" dataKey="accuracy" stroke="#156B45" strokeWidth={2.2} dot={{ r: 2.5, strokeWidth: 0, fill: "#156B45" }} activeDot={{ r: 4.5, strokeWidth: 0 }} />
              <Line type="monotone" dataKey="auto" stroke="#A8731D" strokeWidth={2.2} dot={{ r: 2.5, strokeWidth: 0, fill: "#A8731D" }} activeDot={{ r: 4.5, strokeWidth: 0 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="skel h-[250px]" />
        )}
      </div>

      <div className="card card-hover overflow-hidden mb-3">
        <div className="px-5 py-3 rule flex items-center justify-between">
          <span className="font-display text-[15px] text-ink">Flywheel by month</span>
          <span className="tag text-faint">{score.length} batches</span>
        </div>
        <div className="overflow-x-auto">
          <div className="min-w-[640px]">
            <div className="px-5 py-2 rule thead grid grid-cols-[86px_1fr_1fr_104px_104px] gap-4 bg-paper/50">
              <span>Batch</span><span>Accuracy</span><span>Auto-approve</span>
              <span className="text-right">Auto-errors</span><span className="text-right">Grounded</span>
            </div>
            {score.map((r) => (
              <div key={r.batch_id} className="ledger-row px-5 py-2.5 grid grid-cols-[86px_1fr_1fr_104px_104px] gap-4 items-center text-xs">
                <span className="num text-ink">{r.batch_id}</span>
                <span className="flex items-center gap-2.5">
                  <span className="num text-accent w-12 shrink-0">{(r.accuracy * 100).toFixed(1)}%</span>
                  <span className="flex-1 max-w-[110px]"><Meter value={r.accuracy} /></span>
                </span>
                <span className="flex items-center gap-2.5">
                  <span className="num text-amber w-12 shrink-0">{(r.auto_approve_rate * 100).toFixed(1)}%</span>
                  <span className="flex-1 max-w-[110px]"><Meter value={r.auto_approve_rate} tone="amber" /></span>
                </span>
                <span className="num text-right text-muted">{(r.auto_approved_error_rate * 100).toFixed(1)}%</span>
                <span className="num text-right text-muted">{(r.graph_grounded_rate * 100).toFixed(0)}%</span>
              </div>
            ))}
            {!score.length && <SkelRows n={4} />}
          </div>
        </div>
      </div>

      <div className="card card-hover overflow-hidden">
        <div className="px-5 py-3 rule flex items-center justify-between">
          <span className="font-display text-[15px] text-ink">Recent transactions</span>
          <span className="tag text-faint">Expand a row to see why</span>
        </div>
        <div className="overflow-x-auto">
          <div className="min-w-[680px]">
            <div className="px-5 py-2 rule thead grid grid-cols-[14px_1fr_110px_64px_104px_120px] gap-4 bg-paper/50">
              <span />
              <span>Vendor · client</span>
              <span className="text-right">Amount</span>
              <span className="text-right">Code</span>
              <span>Grounding</span>
              <span className="text-right">Status</span>
            </div>
            {txns.map((t) => <CodingRow key={t.id} t={t} />)}
            {!txns.length && <SkelRows n={6} />}
          </div>
        </div>
      </div>
    </div>
  );
}

function CodingRow({ t }: { t: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ledger-row">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-2.5 grid grid-cols-[14px_1fr_110px_64px_104px_120px] items-center gap-4 text-sm text-left"
        aria-expanded={open}
      >
        <I name="chevronRight" size={12} className={`text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
        <div className="truncate">
          <span className="text-ink">{t.vendor_raw}</span>
          <span className="text-faint text-xs"> · {t.client_id}</span>
        </div>
        <div className="num text-muted text-right text-[13px]">{fmtUSD(t.amount)}</div>
        <div className="num text-accent text-right text-[13px]">{t.predicted_code || "-"}</div>
        <div><Tag tone={t.graph_support > 0 ? "accent" : "muted"}>{t.graph_support > 0 ? "grounded" : "cold"}</Tag></div>
        <div className="text-right"><StatusBadge status={t.status} /></div>
      </button>
      {open && (
        <div className="unfold border-t border-line bg-paper/60 px-5 py-4">
          <div className="grid grid-cols-3 gap-3 mb-3 max-w-2xl">
            <MiniMetric label="Vendor match" value={t.er_method || "-"} />
            <MiniMetric label="Graph support" value={t.graph_support != null ? `${(t.graph_support * 100).toFixed(0)}%` : "-"} />
            <MiniMetric label="Calibrated confidence" value={t.calibrated_confidence != null ? `${(t.calibrated_confidence * 100).toFixed(0)}%` : "-"} />
          </div>
          {t.anomaly_flags?.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber mb-3">
              <I name="flag" size={12} /> flags: {t.anomaly_flags.join(", ")}
            </div>
          )}
          <div className="tag text-faint mb-2">Reasoning path</div>
          <Rail
            items={t.reasoning_path || []}
            empty="Coded from the chart of accounts; no learned graph fact yet."
          />
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* document routing                                                     */
/* ------------------------------------------------------------------ */

function Routing({ firm }: { firm: string }) {
  const [sum, setSum] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    setSum(null); setDocs([]);
    api(`/firms/${firm}/route/run`, { method: "POST" }).then(setSum).catch(() => {});
    api(`/firms/${firm}/routing`).then(setDocs).catch(() => {});
  }, [firm]);
  const counts = {
    all: docs.length,
    auto_routed: docs.filter((d) => d.status === "auto_routed").length,
    needs_review: docs.filter((d) => d.status === "needs_review").length,
  };
  const shown = docs.filter((d) => filter === "all" || d.status === filter);
  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Document intake"
        title="Route to the right client"
        desc="Each incoming document is entity-linked to a client via deterministic keys and the graph. Expand any document to see the matching signals. It only auto-routes when near-certain, because misrouting to the wrong client is a breach."
      />

      {!sum ? (
        <SkelStats n={3} className="mb-3" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <Stat label="Documents" value={fmtNum(sum.documents)} />
          <Stat label="Auto-routed" value={fmtNum(sum.auto_routed)} sub={pct(sum.auto_routed / sum.documents)} meter={sum.documents ? sum.auto_routed / sum.documents : 0} />
          <Stat label="To human review" value={fmtNum(sum.needs_review)} sub="ambiguous, escalated" />
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 mb-3">
        {[["all", "All"], ["auto_routed", "Auto-routed"], ["needs_review", "Needs review"]].map(([id, label]) => (
          <Chip key={id} active={filter === id} onClick={() => setFilter(id)} count={(counts as any)[id]}>
            {label}
          </Chip>
        ))}
      </div>

      <div className="card card-hover overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[680px]">
            <div className="px-5 py-2 rule thead grid grid-cols-[14px_1fr_170px_72px_120px] gap-4 bg-paper/50">
              <span />
              <span>Document</span>
              <span>Sender</span>
              <span className="text-right">Conf.</span>
              <span className="text-right">Status</span>
            </div>
            {shown.map((d) => <RoutingRow key={d.id} d={d} firm={firm} />)}
            {!shown.length && <SkelRows n={6} />}
          </div>
        </div>
      </div>
    </div>
  );
}

function RoutingRow({ d, firm }: { d: any; firm: string }) {
  const [open, setOpen] = useState(false);
  const [ext, setExt] = useState<any>(null);
  const toggle = () => {
    const next = !open; setOpen(next);
    if (next && !ext) api(`/firms/${firm}/documents/${d.id}/extract`).then(setExt).catch(() => {});
  };
  return (
    <div className="ledger-row">
      <button
        onClick={toggle}
        className="w-full px-5 py-2.5 grid grid-cols-[14px_1fr_170px_72px_120px] items-center gap-4 text-sm text-left"
        aria-expanded={open}
      >
        <I name="chevronRight" size={12} className={`text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
        <div className="flex items-center gap-2 min-w-0">
          <I name="file" size={14} className="text-faint shrink-0" />
          <span className="text-ink truncate">{d.filename}</span>
          <span className="text-faint text-xs whitespace-nowrap">· {d.doc_type}</span>
        </div>
        <div className="num text-muted text-xs truncate">{d.sender_domain}</div>
        <div className="num text-muted text-xs text-right">{d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : ""}</div>
        <div className="text-right"><StatusBadge status={d.status} /></div>
      </button>
      {open && (
        <div className="unfold border-t border-line bg-paper/60 px-5 py-4 grid md:grid-cols-2 gap-6 text-xs">
          <div>
            {d.status === "auto_routed" ? (
              <div className="mb-3 flex items-center gap-1.5">
                <I name="check" size={13} className="text-accent" />
                <span className="text-muted">
                  Routed to <span className="text-accent font-medium">{d.routed_client_name}</span> at{" "}
                  <span className="num text-ink">{(d.confidence * 100).toFixed(0)}%</span> confidence
                </span>
              </div>
            ) : (
              <div className="mb-3 flex items-center gap-1.5 text-amber">
                <I name="flag" size={12} />
                Ambiguous. Escalated to a human: which client?
              </div>
            )}
            <div className="tag text-faint mb-2">Matching signals on the graph</div>
            <ul className="space-y-1.5">
              {(d.evidence || []).map((e: string, i: number) => (
                <li key={i} className="flex items-start gap-2 text-ink leading-relaxed">
                  <I name="check" size={12} className="text-accent mt-[2px] shrink-0" />
                  {e}
                </li>
              ))}
              {(!d.evidence || !d.evidence.length) && (
                <li className="text-muted">No strong identifier matched, so a human decides.</li>
              )}
            </ul>
          </div>
          <div>
            <div className="tag text-faint mb-2">Extracted from the document · with provenance</div>
            {ext ? (
              <div className="space-y-0.5">
                {ext.fields.map((f: any, i: number) => (
                  <div key={i} className="flex justify-between gap-4 py-[3px] border-b border-line/70 last:border-0">
                    <span className="text-muted">{f.name}</span>
                    <span className="num text-ink text-right">{f.value}</span>
                  </div>
                ))}
                {!ext.fields.length && <div className="text-muted">No fields found.</div>}
              </div>
            ) : (
              <div className="space-y-2 pt-1">
                <div className="skel h-4" /><div className="skel h-4 w-4/5" /><div className="skel h-4 w-3/5" />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* anomaly flags                                                        */
/* ------------------------------------------------------------------ */

const ALERT_LABELS: Record<string, string> = {
  duplicate: "Duplicate payment",
  unusual_amount: "Unusual amount",
  missing_category: "Missing category",
};

function Alerts({ firm }: { firm: string }) {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  useEffect(() => { setAlerts([]); api(`/firms/${firm}/alerts`).then(setAlerts).catch(() => {}); }, [firm]);
  const counts: any = { all: alerts.length };
  ["duplicate", "unusual_amount", "missing_category"].forEach((t) => (counts[t] = alerts.filter((a) => a.type === t).length));
  const shown = alerts.filter((a) => filter === "all" || a.type === filter).slice(0, 60);
  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Real-time"
        title="Anomaly flags"
        desc="Duplicates, unusual amounts, and missing categories, each with the evidence that justifies it. Expand an alert to inspect the evidence and confirm or dismiss it."
      />

      <div className="flex flex-wrap gap-1.5 mb-4">
        {[["all", "All"], ["duplicate", "Duplicates"], ["unusual_amount", "Unusual amounts"], ["missing_category", "Missing category"]].map(([id, label]) => (
          <Chip key={id} active={filter === id} onClick={() => setFilter(id)} count={counts[id] ?? 0}>
            {label}
          </Chip>
        ))}
      </div>

      <div className="space-y-2">
        {shown.map((a, i) => <AlertRow key={a.id || i} a={a} />)}
        {!shown.length && (
          <div className="card overflow-hidden"><SkelRows n={6} /></div>
        )}
      </div>
    </div>
  );
}

function AlertRow({ a }: { a: any }) {
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<string | null>(null);
  return (
    <div className="card card-hover overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full px-5 py-3 flex items-center gap-4 text-left" aria-expanded={open}>
        <StatusBadge status={a.severity} />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-ink font-medium">{ALERT_LABELS[a.type] || a.type}</div>
          <div className="text-xs text-muted truncate">{a.evidence?.note}</div>
        </div>
        {decision && <Tag tone={decision === "confirmed" ? "rust" : "muted"}>{decision}</Tag>}
        <div className="num text-xs text-faint hidden md:block">{a.transaction_id}</div>
        <I name="chevronRight" size={12} className={`text-faint shrink-0 transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="unfold px-5 pb-4 pt-3 border-t border-line bg-paper/60 text-xs">
          <div className="tag text-faint mb-2">Evidence</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 num text-muted mb-4 max-w-xl">
            {Object.entries(a.evidence || {}).filter(([k]) => k !== "note").map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-line/70 py-[3px]">
                <span>{k.replace(/_/g, " ")}</span>
                <span className="text-ink text-right">{String(v)}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setDecision("confirmed")}
              className="btn-ghost !text-rust !border-rust/30 hover:!bg-rustSoft"
            >
              <I name="flag" size={12} /> Confirm issue
            </button>
            <button onClick={() => setDecision("dismissed")} className="btn-ghost">
              <I name="x" size={12} /> Dismiss as false positive
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* ask ed                                                               */
/* ------------------------------------------------------------------ */

const THINKING = ["scoping to client", "planning a constrained query", "querying the graph + ledger", "computing from the ledger", "validating against evidence", "composing with the model"];

function EdMark({ size = 28 }: { size?: number }) {
  return (
    <div
      className="shrink-0 rounded-lg bg-pine text-[#CFE3D2] flex items-center justify-center shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]"
      style={{ width: size, height: size }}
    >
      <I name="spark" size={Math.round(size * 0.5)} strokeWidth={1.7} />
    </div>
  );
}

function AskEd({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [q, setQ] = useState("");
  const [msgs, setMsgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const ctxRef = useRef<any>(null); // conversation memory (last resolved query)
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
    <div className="stagger">
      <SectionTitle
        kicker="Ed · Client-facing"
        title="Ask Ed"
        desc="Ed answers from this client's own ledger. Numbers are computed by query and validated, the model only phrases the reply, and Ed abstains and escalates when it cannot ground an answer."
      />

      <div className="grid lg:grid-cols-[1fr_300px] gap-4 items-start">
        <div className="card overflow-hidden flex flex-col h-[520px] sm:h-[600px]">
          <div className="px-5 py-3 border-b border-line flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex items-center gap-2.5 min-w-0">
              <EdMark size={30} />
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-ink leading-tight">Ed</div>
                <div className="tag text-faint">Answers from the ledger only</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="tag text-faint">Client</span>
              <Select value={client} onChange={(e) => setClient(e.target.value)} ariaLabel="Select client">
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 flex flex-col gap-5 bg-paper/40">
            {msgs.length === 0 && !loading && (
              <div className="m-auto text-center max-w-sm">
                <div className="mx-auto mb-3 w-fit"><EdMark size={40} /></div>
                <div className="font-display text-[17px] text-ink">Ask about this client's books</div>
                <p className="text-xs text-muted leading-relaxed mt-1.5">
                  Spend, totals, vendors, or transaction counts. Try an advisory question to watch Ed abstain and escalate.
                </p>
              </div>
            )}
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="rise self-end max-w-[78%] bg-accent text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed shadow-card">
                  {m.text}
                </div>
              ) : (
                <EdMessage key={i} m={m} />
              )
            )}
            {loading && (
              <div className="self-start flex items-center gap-2.5">
                <EdMark size={26} />
                <div className="flex items-center gap-2 text-sm text-muted bg-card border border-line rounded-2xl rounded-tl-md px-4 py-2.5">
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

          <div className="px-4 py-3 border-t border-line bg-card">
            <div className="flex items-center gap-2 rounded-xl border border-line bg-paper px-3 py-1 transition-shadow focus-within:border-accent/50 focus-within:shadow-[0_0_0_3px_rgba(21,107,69,0.08)]">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                placeholder="Ask Ed about this client's books…"
                className="flex-1 bg-transparent py-2 text-sm outline-none placeholder:text-faint"
              />
              <button onClick={() => ask()} disabled={loading} className="btn-primary !px-3 !py-2" aria-label="Send">
                <I name="send" size={14} />
              </button>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="card p-4">
            <div className="tag text-accent mb-2.5">Try asking</div>
            <div className="-mx-1.5">
              {samples.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="w-full text-left text-xs text-muted leading-snug rounded-lg px-2.5 py-2 flex items-start gap-2 hover:bg-accentSoft/60 hover:text-accentDeep transition-colors"
                >
                  <I name="arrowRight" size={11} className="mt-[2px] shrink-0 text-faint" />
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div className="card p-4">
            <div className="tag text-faint mb-2.5">How Ed stays honest</div>
            <ul className="space-y-2 text-xs text-muted leading-relaxed">
              <li className="flex gap-2"><I name="check" size={12} className="text-accent mt-[2px] shrink-0" />Numbers come from constrained queries over the ledger, never from generation.</li>
              <li className="flex gap-2"><I name="check" size={12} className="text-accent mt-[2px] shrink-0" />Every answer is validated against evidence and cited.</li>
              <li className="flex gap-2"><I name="check" size={12} className="text-accent mt-[2px] shrink-0" />When Ed cannot ground an answer, it abstains and escalates to your accountant.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function AnswerTable({ table }: { table: any }) {
  const rows = table.rows || [];
  const collapsible = table.type === "transactions";
  const [open, setOpen] = useState(!collapsible);
  return (
    <div className="mt-2">
      {collapsible && (
        <button onClick={() => setOpen(!open)} className="tag text-muted hover:text-accent mb-1.5 inline-flex items-center gap-1">
          <I name="chevronRight" size={10} className={`transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
          {open ? "Hide transactions" : `View ${rows.length} transactions`}
        </button>
      )}
      {open && (
        <div className="card overflow-hidden unfold">
          <div className="max-h-56 overflow-auto">
            <div className="min-w-[420px]">
            {table.type === "transactions" && (
              <div className="px-3 py-1.5 rule thead grid grid-cols-[78px_1fr_92px_44px] gap-3 bg-paper sticky top-0 z-10">
                <span>Date</span><span>Vendor</span><span className="text-right">Amount</span><span className="text-right">Code</span>
              </div>
            )}
            {table.type === "transactions" && rows.map((r: any, i: number) => (
              <div key={i} className="ledger-row px-3 py-1.5 grid grid-cols-[78px_1fr_92px_44px] gap-3 items-center text-xs">
                <span className="num text-muted">{r.date}</span>
                <span className="text-ink truncate">{r.vendor}</span>
                <span className="num text-ink text-right">{fmtUSD(r.amount)}</span>
                <span className="num text-accent text-right">{r.code}</span>
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
              <div key={i} className="ledger-row px-3 py-1.5 grid grid-cols-[44px_1fr_auto] gap-3 items-center text-xs">
                <span className="num text-accent">{r.code}</span>
                <span className="text-ink truncate">{r.name}</span>
                <span className="num text-ink text-right w-20">{fmtUSD(r.total)}</span>
              </div>
            ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EdMessage({ m }: { m: any }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="rise self-start max-w-[85%]">
      <div className="flex items-center gap-2 mb-1.5">
        <EdMark size={20} />
        {m.abstained ? (
          <Tag tone="amber">escalated to accountant</Tag>
        ) : (
          <>
            <Tag tone="accent">grounded</Tag>
            <span className="tag text-faint">{genLabel(m.generated_by)}</span>
          </>
        )}
        {!m.abstained && m.citations && <span className="tag text-faint">{m.citations.length} citations</span>}
      </div>
      <p className="font-display text-[17px] text-ink leading-snug bg-card border border-line rounded-2xl rounded-tl-md px-4 py-3 shadow-card">
        {m.answer}
      </p>
      {m.table && <AnswerTable table={m.table} />}
      {m.trace?.length > 0 && (
        <div className="mt-2">
          <button onClick={() => setOpen(!open)} className="tag text-muted hover:text-accent inline-flex items-center gap-1">
            <I name="chevronRight" size={10} className={`transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
            {open ? "Hide agent trace" : "Show agent trace"}
          </button>
          {open && (
            <ol className="unfold mt-2 relative border-l border-accent/25 pl-4 space-y-2">
              {m.trace.map((s: any, i: number) => (
                <li key={i} className="relative text-xs">
                  <span className={`absolute -left-[21px] top-[3px] w-2 h-2 rounded-full ${s.ok ? "bg-accent" : "bg-rust"}`} />
                  <span className="text-ink font-medium">{s.label}</span>
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

/* ------------------------------------------------------------------ */
/* close & collect                                                      */
/* ------------------------------------------------------------------ */

const STEP_TONE: Record<string, string> = {
  done: "accent", waiting_on_client: "amber", needs_review: "amber", needs_approval: "amber", pending: "muted",
};

function StepIcon({ status }: { status: string }) {
  if (status === "done") {
    return (
      <span className="w-6 h-6 rounded-full bg-accentSoft border border-accent/30 text-accent flex items-center justify-center">
        <I name="check" size={12} strokeWidth={2} />
      </span>
    );
  }
  if (status === "pending") {
    return (
      <span className="w-6 h-6 rounded-full border border-line bg-card flex items-center justify-center">
        <span className="w-1.5 h-1.5 rounded-full bg-faint" />
      </span>
    );
  }
  return (
    <span className="w-6 h-6 rounded-full bg-amberSoft border border-amber/30 text-amber flex items-center justify-center">
      <I name="clock" size={12} />
    </span>
  );
}

function CloseStep({ s, last }: { s: any; last: boolean }) {
  const [open, setOpen] = useState(false);
  const d = s.data || {};
  const hasData = (d.alerts && d.alerts.length) || (d.sample && d.sample.length) || d.pbc;
  return (
    <li className="grid grid-cols-[24px_1fr] gap-x-4">
      <div className="flex flex-col items-center">
        <StepIcon status={s.status} />
        {!last && <span className="w-px flex-1 bg-line my-1" />}
      </div>
      <div className={last ? "pb-1" : "pb-6"}>
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="text-sm text-ink font-medium">{s.step}</span>
          <Tag tone={STEP_TONE[s.status] || "muted"}>{s.status.replace(/_/g, " ")}</Tag>
          {hasData && (
            <button onClick={() => setOpen(!open)} className="tag text-muted hover:text-accent ml-auto inline-flex items-center gap-1">
              <I name="chevronRight" size={10} className={`transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
              {open ? "Hide data" : "See data"}
            </button>
          )}
        </div>
        <div className="text-xs text-muted mt-1 leading-relaxed">{s.detail}</div>
        {d.reminder?.body && (
          <div className="mt-2 rounded-lg border border-amber/25 bg-amberSoft px-3.5 py-2.5 text-xs text-ink leading-relaxed">
            <div className="tag text-amber mb-1">Draft reminder · approve to send</div>
            {d.reminder.body}
          </div>
        )}
        {d.message?.body && (
          <div className="mt-2 rounded-lg border border-accent/20 bg-accentSoft/60 px-3.5 py-2.5 text-xs text-ink leading-relaxed">
            <div className="tag text-accent mb-1">Draft client update · approve to send</div>
            {d.message.body}
          </div>
        )}
        {open && hasData && (
          <div className="unfold mt-2 rounded-lg border border-line bg-paper/70 px-3.5 py-2.5 text-xs text-muted space-y-1">
            {d.pbc && (
              <>
                <div>received: <span className="text-ink">{d.pbc.received.join(", ") || "none"}</span></div>
                {d.pbc.missing.length > 0 && <div>missing: <span className="text-amber">{d.pbc.missing.join(", ")}</span></div>}
              </>
            )}
            {(d.alerts || []).map((a: any, i: number) => (
              <div key={i}><span className="text-ink">{a.type}</span>: {a.evidence?.note}</div>
            ))}
            {(d.sample || []).map((e: any, i: number) => (
              <div key={i}>
                <span className="num text-ink">{e.document_id}</span>: {e.fields.map((f: any) => `${f.name}=${f.value}`).join(", ")}
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

function Close({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [pbc, setPbc] = useState<any>(null);
  const [close, setClose] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [csv, setCsv] = useState("");
  const [imp, setImp] = useState<any>(null);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    setClose(null); setImp(null);
    api(`/firms/${firm}/clients`).then((c) => { setClients(c); setClient(c[0]?.id); }).catch(() => {});
    api(`/firms/${firm}/pbc`).then(setPbc).catch(() => {});
    api(`/import/sample`).then((d) => setCsv(d.csv)).catch(() => {});
  }, [firm]);

  const runCloseFor = async (cid: string) => {
    if (!cid) return;
    setRunning(true); setClose(null);
    try { setClose(await api(`/close`, { method: "POST", body: JSON.stringify({ firm_id: firm, client_id: cid, period: "2026-01" }) })); }
    finally { setRunning(false); }
  };
  useEffect(() => { if (client) runCloseFor(client); }, [client]); // auto-run so the workflow shows immediately
  const runImport = async () => {
    setImporting(true);
    try { setImp(await api(`/import`, { method: "POST", body: JSON.stringify({ firm_id: firm, client_id: client, csv }) })); }
    finally { setImporting(false); }
  };

  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · The close"
        title="Run the close, end to end"
        desc="One orchestrated workflow: collect missing documents from the client, route what came in, extract the fields, code the transactions, flag anomalies, and draft the client update, with your approval at every gate."
      />

      {!pbc ? (
        <SkelStats n={3} className="mb-3" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <Stat label="Clients" value={fmtNum(pbc.summary.total)} />
          <Stat label="Docs complete" value={fmtNum(pbc.summary.complete)} />
          <Stat label="Waiting on documents" value={fmtNum(pbc.summary.waiting_on_docs)} sub="Ed will chase these" />
        </div>
      )}

      <div className="card card-hover p-6 mb-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="font-display text-[17px] text-ink">Close orchestrator</span>
            <Tag tone="muted"><I name="calendar" size={10} /> period 2026-01</Tag>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="tag text-faint">Client</span>
            <Select value={client} onChange={(e) => setClient(e.target.value)} ariaLabel="Select client">
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <button onClick={() => runCloseFor(client)} disabled={running} className="btn-primary">
              <I name="flywheel" size={13} className={running ? "animate-spin" : ""} />
              {running ? "Running…" : "Re-run close"}
            </button>
          </div>
        </div>
        {running && !close && (
          <div className="mt-5 space-y-3">
            <div className="skel h-10" /><div className="skel h-10 w-5/6" /><div className="skel h-10 w-4/6" />
          </div>
        )}
        {close && (
          <ol className="mt-6">
            {close.steps.map((s: any, i: number) => (
              <CloseStep key={i} s={s} last={i === close.steps.length - 1} />
            ))}
          </ol>
        )}
      </div>

      <div className="card card-hover p-6">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-3">
          <div className="flex items-start gap-3.5">
            <div className="w-9 h-9 shrink-0 rounded-lg bg-accentSoft border border-accent/15 text-accent flex items-center justify-center">
              <I name="upload" size={15} />
            </div>
            <div>
              <div className="text-[13.5px] font-semibold text-ink">Import from QuickBooks or a bank export</div>
              <div className="text-xs text-muted mt-0.5 leading-relaxed">Paste a CSV export and Trustmax ingests and codes it on the way in.</div>
            </div>
          </div>
          <button onClick={runImport} disabled={importing} className="btn-ghost shrink-0">
            <I name="play" size={11} />
            {importing ? "Coding…" : "Import & code"}
          </button>
        </div>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          rows={4}
          spellCheck={false}
          className="field w-full !bg-paper num text-[11px] leading-relaxed resize-y"
        />
        {imp && (
          <div className="mt-3 card overflow-hidden unfold">
            <div className="overflow-x-auto">
              <div className="min-w-[600px]">
                <div className="px-4 py-2 rule thead grid grid-cols-[1fr_110px_56px_130px] gap-3 bg-paper/50">
                  <span>Vendor</span><span className="text-right">Amount</span><span className="text-right">Code</span><span className="text-right">Status</span>
                </div>
                {imp.coded.map((c: any, i: number) => (
                  <div key={i} className="ledger-row px-4 py-2 grid grid-cols-[1fr_110px_56px_130px] gap-3 items-center text-xs">
                    <span className="text-ink truncate">{c.vendor}</span>
                    <span className="num text-muted text-right">{fmtUSD(c.amount)}</span>
                    <span className="num text-accent text-right">{c.code}</span>
                    <div className="text-right"><StatusBadge status={c.status} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* live ingest                                                          */
/* ------------------------------------------------------------------ */

function KgDelta({ before, after, delta }: { before: any; after: any; delta: any }) {
  const rows = [
    { label: "Graph nodes", after: after.nodes, before: before.nodes, d: delta.nodes },
    { label: "Graph edges", after: after.edges, before: before.edges, d: delta.edges },
    { label: "Learned facts", after: after.facts, before: before.facts, d: delta.facts },
  ];
  return (
    <div className="panel-pine p-6">
      <div className="relative">
        <div className="tag text-[#9CC4AA] mb-1">Autonomous update</div>
        <div className="font-display text-[19px] mb-5">The knowledge graph updated itself</div>
        <div className="grid grid-cols-3 gap-4 sm:gap-6">
          {rows.map((r) => (
            <div key={r.label}>
              <div className="flex items-baseline gap-2">
                <span className="num text-[24px] font-medium text-white leading-none">{fmtNum(r.after)}</span>
                {r.d > 0 && <span className="num text-[13px] text-[#86E0AA]">+{fmtNum(r.d)}</span>}
              </div>
              <div className="tag text-[#9CC4AA] mt-2">{r.label}</div>
              <div className="text-[11px] text-[#9CC4AA]/70 mt-0.5">was {fmtNum(r.before)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TraceTimeline({ trace }: { trace: any[] }) {
  return (
    <ol>
      {trace.map((s, i) => (
        <li key={i} className="grid grid-cols-[24px_1fr] gap-x-3">
          <div className="flex flex-col items-center">
            <span className="w-6 h-6 rounded-full bg-accentSoft border border-accent/30 text-accent flex items-center justify-center">
              <I name="check" size={12} strokeWidth={2} />
            </span>
            {i < trace.length - 1 && <span className="w-px flex-1 bg-line my-1" />}
          </div>
          <div className={i < trace.length - 1 ? "pb-4" : ""}>
            <div className="text-sm text-ink font-medium">{s.label}</div>
            <div className="text-xs text-muted mt-0.5 num">{s.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function IngestItemRow({ it }: { it: any }) {
  const [open, setOpen] = useState(false);
  const has = (it.reasoning_path && it.reasoning_path.length) || (it.flags && it.flags.length);
  return (
    <div className="ledger-row">
      <button onClick={() => has && setOpen(!open)} className="w-full px-4 py-2 grid grid-cols-[14px_1fr_100px_56px_104px_120px] items-center gap-3 text-xs text-left">
        <I name="chevronRight" size={11} className={`text-faint transition-transform duration-200 ${open ? "rotate-90" : ""} ${has ? "" : "opacity-0"}`} />
        <span className="text-ink truncate">{it.vendor}</span>
        <span className="num text-muted text-right">{fmtUSD(it.amount)}</span>
        <span className="num text-accent text-right">{it.code || "-"}</span>
        <span><Tag tone={it.grounded ? "accent" : "muted"}>{it.grounded ? "grounded" : "cold"}</Tag></span>
        <span className="text-right"><StatusBadge status={it.status} /></span>
      </button>
      {open && has && (
        <div className="unfold border-t border-line bg-paper/60 px-4 py-3">
          {it.flags?.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber mb-2"><I name="flag" size={12} /> {it.flags.join(", ")}</div>
          )}
          <Rail items={it.reasoning_path || []} empty="Coded from the chart of accounts; no learned fact yet." />
        </div>
      )}
    </div>
  );
}

function Ingest({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [mode, setMode] = useState<"feed" | "document">("feed");
  const [samples, setSamples] = useState<any>(null);
  const [text, setText] = useState("");
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState("");
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api(`/firms/${firm}/clients`).then((c) => { setClients(c); setClient(c[0]?.id); }).catch(() => {});
    api(`/ingest/sample`).then((d) => { setSamples(d); setText(d.feed); }).catch(() => {});
  }, [firm]);
  useEffect(() => { setRes(null); }, [client, firm]);

  const switchMode = (m: "feed" | "document") => {
    setMode(m); setRes(null); setFileName("");
    if (samples) setText(m === "feed" ? samples.feed : samples.invoice);
  };
  const loadFile = (file?: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setRes(null);
      setText(String(reader.result || ""));
      setFileName(file.name);
      const name = file.name.toLowerCase();
      if (name.endsWith(".csv") || name.endsWith(".tsv")) setMode("feed");
      else if (name.includes("invoice") || name.includes("receipt") || name.includes("bill")) setMode("document");
    };
    reader.readAsText(file);
  };
  const run = async () => {
    if (!text.trim() || loading) return;
    setLoading(true); setRes(null);
    try { setRes(await api(`/ingest`, { method: "POST", body: JSON.stringify({ firm_id: firm, client_id: client, kind: mode, text }) })); }
    catch { setRes({ error: "Ingest failed. Check the input and try again." }); }
    finally { setLoading(false); }
  };

  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Live ingest"
        title="Drop data in, watch the graph grow"
        desc="Paste a bank feed or a document. Max resolves the vendors on the graph, codes every line against the chart and the learned facts, flags anything odd, and writes the new transactions and facts straight into the knowledge graph. The flywheel turns on live input."
      />

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <div className="card p-5">
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <div className="flex gap-1.5">
              <Chip active={mode === "feed"} onClick={() => switchMode("feed")}>Bank feed</Chip>
              <Chip active={mode === "document"} onClick={() => switchMode("document")}>Document</Chip>
            </div>
            <div className="flex items-center gap-2">
              <span className="tag text-faint">Client</span>
              <Select value={client} onChange={(e) => setClient(e.target.value)} ariaLabel="Client">
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </div>
          </div>
          <div
            onDrop={(e) => { e.preventDefault(); setDrag(false); loadFile(e.dataTransfer.files?.[0]); }}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            className={`relative rounded-xl border border-dashed transition-colors ${drag ? "border-accent bg-accentSoft/40" : "border-line"}`}
          >
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={mode === "feed" ? 9 : 8}
              spellCheck={false}
              placeholder={mode === "feed" ? "date,description,amount" : "Paste an invoice or receipt"}
              className="w-full bg-transparent num text-[11px] leading-relaxed resize-y px-3 py-2.5 outline-none"
            />
            {drag && (
              <div className="absolute inset-0 flex items-center justify-center text-xs text-accent font-medium pointer-events-none">
                Drop the file to load it
              </div>
            )}
          </div>
          <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,.text,text/*" className="hidden"
            onChange={(e) => loadFile(e.target.files?.[0])} />
          <div className="flex items-center justify-between gap-3 mt-3 flex-wrap">
            <div className="flex items-center gap-2 min-w-0">
              <button onClick={() => fileRef.current?.click()} className="btn-ghost shrink-0">
                <I name="file" size={11} /> Upload file
              </button>
              <span className="text-xs text-muted truncate">
                {fileName ? `loaded ${fileName}` : (mode === "feed" ? "drop a CSV or paste lines" : "drop or paste an invoice")}
              </span>
            </div>
            <button onClick={run} disabled={loading} className="btn-primary shrink-0">
              <I name="upload" size={13} className={loading ? "animate-pulse" : ""} />
              {loading ? "Processing…" : "Ingest & process"}
            </button>
          </div>
        </div>

        <div>
          {!res && !loading && (
            <div className="card p-7 h-full flex flex-col items-center justify-center text-center">
              <div className="w-11 h-11 rounded-xl bg-accentSoft border border-accent/20 text-accent flex items-center justify-center mb-3"><I name="graph" size={19} /></div>
              <div className="font-display text-[16px] text-ink">Nothing ingested yet</div>
              <p className="text-xs text-muted mt-1.5 max-w-xs leading-relaxed">Run an ingest to watch the pipeline execute and the knowledge graph grow in real time.</p>
            </div>
          )}
          {loading && <div className="space-y-3"><div className="skel h-[156px]" /><div className="skel h-10" /><div className="skel h-10 w-5/6" /></div>}
          {res?.error && <div className="card p-5 text-sm text-rust">{res.error}</div>}
          {res && !res.error && (
            <div className="space-y-3">
              <KgDelta before={res.before} after={res.after} delta={res.delta} />
              <div className="card p-5">
                <div className="tag text-faint mb-3">Pipeline</div>
                <TraceTimeline trace={res.trace} />
              </div>
            </div>
          )}
        </div>
      </div>

      {res && !res.error && res.kind === "feed" && (
        <div className="card overflow-hidden mt-4">
          <div className="px-4 py-3 rule flex items-center justify-between">
            <span className="font-display text-[15px] text-ink">Coded on the way in</span>
            <span className="tag text-faint">{res.counts.ingested} lines · {res.counts.auto_approved} auto-approved · +{res.counts.facts_learned} facts</span>
          </div>
          <div className="overflow-x-auto">
            <div className="min-w-[640px]">
              <div className="px-4 py-2 rule thead grid grid-cols-[14px_1fr_100px_56px_104px_120px] gap-3 bg-paper/50">
                <span /><span>Vendor</span><span className="text-right">Amount</span><span className="text-right">Code</span><span>Grounding</span><span className="text-right">Status</span>
              </div>
              {res.items.map((it: any, i: number) => <IngestItemRow key={i} it={it} />)}
            </div>
          </div>
        </div>
      )}

      {res && !res.error && res.kind === "document" && (
        <div className="grid md:grid-cols-3 gap-3 mt-4">
          <div className="card p-5">
            <div className="tag text-accent mb-2">Routed to client</div>
            <div className="text-sm text-ink font-medium">{res.routing.client_name}</div>
            <div className="num text-xs text-muted mt-0.5">{Math.round((res.routing.confidence || 0) * 100)}% confidence · {res.routing.auto ? "auto-routed" : "needs review"}</div>
            <ul className="mt-3 space-y-1.5">
              {(res.routing.evidence || []).map((e: string, i: number) => (
                <li key={i} className="flex items-start gap-2 text-xs text-ink leading-relaxed"><I name="check" size={12} className="text-accent mt-[2px] shrink-0" />{e}</li>
              ))}
              {!res.routing.evidence?.length && <li className="text-xs text-muted">No strong identifier; routed to the selected client.</li>}
            </ul>
          </div>
          <div className="card p-5">
            <div className="tag text-faint mb-2">Extracted fields · with provenance</div>
            <div className="space-y-0.5">
              {res.fields.map((f: any, i: number) => (
                <div key={i} className="flex justify-between gap-4 py-[3px] border-b border-line/70 last:border-0 text-xs">
                  <span className="text-muted">{f.name}</span><span className="num text-ink text-right">{String(f.value)}</span>
                </div>
              ))}
              {!res.fields.length && <div className="text-xs text-muted">No fields found.</div>}
            </div>
          </div>
          <div className="card p-5">
            <div className="tag text-accent mb-2">Coded</div>
            <div className="text-sm"><span className="text-ink font-medium">{res.coded.vendor}</span> <span className="num text-muted">{fmtUSD(res.coded.amount)}</span></div>
            <div className="num text-accent text-sm mt-1">{res.coded.code} {res.coded.account}</div>
            <div className="mt-2"><StatusBadge status={res.coded.status} /></div>
            <div className="mt-3"><Rail items={res.coded.reasoning_path || []} empty="Coded from the chart of accounts." /></div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* reconciliation                                                       */
/* ------------------------------------------------------------------ */

const RECON_LABELS: Record<string, string> = {
  in_bank_not_books: "On statement, not in books",
  in_books_not_bank: "In books, not cleared",
  amount_mismatch: "Amount mismatch",
  timing: "Timing difference",
};
const RECON_TONE: Record<string, string> = {
  in_bank_not_books: "rust", amount_mismatch: "rust", in_books_not_bank: "amber", timing: "amber",
};

function Recon({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [period, setPeriod] = useState("2026-01");
  const [data, setData] = useState<any>(null);
  const [filter, setFilter] = useState("all");
  const [showMatches, setShowMatches] = useState(false);

  useEffect(() => { api(`/firms/${firm}/clients`).then((c) => { setClients(c); setClient(c[0]?.id); }).catch(() => {}); }, [firm]);
  useEffect(() => {
    if (!client) return;
    setData(null); setFilter("all"); setShowMatches(false);
    api(`/firms/${firm}/recon?client_id=${client}&period=${period}`).then(setData).catch(() => {});
  }, [client, period, firm]);

  const s = data?.summary;
  const exc = data?.exceptions || [];
  const counts: any = { all: exc.length };
  ["in_bank_not_books", "amount_mismatch", "in_books_not_bank", "timing"].forEach((t) => (counts[t] = exc.filter((e: any) => e.type === t).length));
  const shown = exc.filter((e: any) => filter === "all" || e.type === filter);

  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Reconciliation"
        title="Reconcile the bank, review only the breaks"
        desc="The biggest time sink in a firm. Trustmax matches the statement to the ledger on amount, date, and payee, then surfaces only the exceptions that do not tie, each with the reason and a suggested fix. Hours of ticking become minutes of judgement."
      >
        <div className="flex items-center gap-2">
          <Select value={client} onChange={(e) => setClient(e.target.value)} ariaLabel="Client">
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select value={period} onChange={(e) => setPeriod(e.target.value)} ariaLabel="Period">
            {["2026-01", "2026-02", "2026-03"].map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
        </div>
      </SectionTitle>

      {!s ? <SkelStats n={4} className="mb-3" /> : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <Stat label="Auto-matched" value={`${(s.match_rate * 100).toFixed(0)}%`} meter={s.match_rate} sub={`${s.matched} of ${s.bank_lines} bank lines`} />
          <Stat label="Reconciled" value={fmtUSD(s.reconciled_amount)} sub="tied to the ledger" />
          <Stat label="Exceptions" value={fmtNum(s.exceptions)} tone="amber" sub="need a human look" />
          <Stat label="In exceptions" value={fmtUSD(s.exceptions_amount)} sub="value under review" />
        </div>
      )}

      {s && (
        <>
          <div className="flex gap-1.5 mb-3 flex-wrap">
            {[["all", "All"], ["in_bank_not_books", "On statement only"], ["amount_mismatch", "Amount mismatch"], ["in_books_not_bank", "Outstanding"], ["timing", "Timing"]].map(([id, label]) => (
              <Chip key={id} active={filter === id} onClick={() => setFilter(id)} count={counts[id] ?? 0}>{label}</Chip>
            ))}
          </div>
          <div className="card overflow-hidden">
            <div className="px-5 py-3 rule flex items-center justify-between">
              <span className="font-display text-[15px] text-ink">Exceptions</span>
              <span className="tag text-faint">{shown.length} shown</span>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[600px]">
                {shown.map((e: any, i: number) => (
                  <div key={i} className="ledger-row px-5 py-3 flex items-start gap-3">
                    <Tag tone={RECON_TONE[e.type] || "muted"}>{RECON_LABELS[e.type] || e.type}</Tag>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-ink leading-snug">{e.detail}</div>
                      <div className="text-xs text-muted mt-0.5 leading-relaxed">{e.suggestion}</div>
                    </div>
                    <div className="num text-sm text-ink shrink-0">{fmtUSD(Math.abs(e.amount))}</div>
                  </div>
                ))}
                {!shown.length && <div className="px-5 py-7 text-sm text-muted text-center">Nothing in this category. Clean.</div>}
              </div>
            </div>
          </div>

          {data.matches?.length > 0 && (
            <>
              <button onClick={() => setShowMatches(!showMatches)} className="tag text-muted hover:text-accent mt-3 inline-flex items-center gap-1">
                <I name="chevronRight" size={10} className={`transition-transform duration-200 ${showMatches ? "rotate-90" : ""}`} />
                {showMatches ? "Hide" : "Show"} {data.matches.length} auto-matched lines
              </button>
              {showMatches && (
                <div className="card overflow-hidden mt-2 unfold">
                  <div className="overflow-x-auto">
                    <div className="min-w-[620px]">
                      <div className="px-4 py-2 rule thead grid grid-cols-[1fr_88px_1fr_88px_64px] gap-3 bg-paper/50">
                        <span>Bank payee</span><span className="text-right">Bank</span><span>Ledger</span><span className="text-right">Books</span><span className="text-right">Conf.</span>
                      </div>
                      <div className="max-h-72 overflow-y-auto">
                        {data.matches.map((m: any, i: number) => (
                          <div key={i} className="ledger-row px-4 py-2 grid grid-cols-[1fr_88px_1fr_88px_64px] gap-3 items-center text-xs">
                            <span className="text-ink truncate">{m.bank.payee}</span>
                            <span className="num text-muted text-right">{fmtUSD(m.bank.amount)}</span>
                            <span className="text-muted truncate">{m.book.vendor}</span>
                            <span className="num text-ink text-right">{fmtUSD(m.book.amount)}</span>
                            <span className="num text-accent text-right">{Math.round(m.confidence * 100)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* flux & variance                                                      */
/* ------------------------------------------------------------------ */

function FluxBar({ value, max }: { value: number; max: number }) {
  const w = max ? Math.min(100, (Math.abs(value) / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full bg-line rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${value > 0 ? "bg-rust" : "bg-accent"}`} style={{ width: `${w}%` }} />
    </div>
  );
}

function FluxDriver({ d }: { d: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ledger-row">
      <button onClick={() => setOpen(!open)} className="w-full px-5 py-2.5 grid grid-cols-[14px_1fr_120px] items-center gap-3 text-sm text-left">
        <I name="chevronRight" size={12} className={`text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`} />
        <span className="text-ink truncate"><span className="num text-faint">{d.code}</span> {d.name}</span>
        <span className={`num text-right ${d.delta > 0 ? "text-rust" : "text-accent"}`}>{d.delta > 0 ? "+" : ""}{fmtUSD(d.delta)}</span>
      </button>
      {open && (
        <div className="unfold border-t border-line bg-paper/60 px-5 py-3">
          <div className="tag text-faint mb-2">Driving transactions</div>
          <div className="space-y-1">
            {d.txns.map((t: any, i: number) => (
              <div key={i} className="grid grid-cols-[80px_1fr_90px] gap-3 text-xs items-center">
                <span className="num text-muted">{t.date}</span>
                <span className="text-ink truncate">{t.vendor}</span>
                <span className="num text-ink text-right">{fmtUSD(t.amount)}</span>
              </div>
            ))}
            {!d.txns.length && <div className="text-xs text-muted">No transactions in this category this period.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function Flux({ firm }: { firm: string }) {
  const [clients, setClients] = useState<any[]>([]);
  const [client, setClient] = useState("");
  const [data, setData] = useState<any>(null);

  useEffect(() => { api(`/firms/${firm}/clients`).then((c) => { setClients(c); setClient(c[0]?.id); }).catch(() => {}); }, [firm]);
  useEffect(() => {
    if (!client) return;
    setData(null);
    api(`/firms/${firm}/flux?client_id=${client}`).then(setData).catch(() => setData({ error: true }));
  }, [client, firm]);

  const rows = (data?.rows || []).filter((r: any) => r.current || r.prior);
  const maxDelta = rows.reduce((m: number, r: any) => Math.max(m, Math.abs(r.delta)), 0);

  return (
    <div className="stagger">
      <SectionTitle
        kicker="Max · Flux & variance"
        title="What moved, and exactly why"
        desc="Month over month variance, computed from the ledger and never generated. Every swing is traced to the transactions driving it, so the narrative is one you can drill into and defend."
      >
        <Select value={client} onChange={(e) => setClient(e.target.value)} ariaLabel="Client">
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </SectionTitle>

      {!data ? (
        <div className="space-y-3"><div className="skel h-24" /><SkelStats n={3} /></div>
      ) : data.error ? (
        <div className="card p-6 text-sm text-muted">Need at least two periods of data for this client to compute a variance.</div>
      ) : (
        <>
          <div className="card p-6 mb-3">
            <div className="flex items-center gap-2 mb-2.5 flex-wrap">
              <div className="w-7 h-7 rounded-lg bg-accentSoft border border-accent/20 text-accent flex items-center justify-center"><I name="spark" size={13} /></div>
              <div className="tag text-faint">Flux note · {data.prior} to {data.period}</div>
              <span className="tag text-muted ml-auto">{genLabel(data.generated_by)}</span>
            </div>
            <p className="font-display text-[18px] text-ink leading-snug">{data.narrative}</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <Stat label={`Spend ${data.period}`} value={fmtUSD(data.total.current)} />
            <Stat label={`Spend ${data.prior}`} value={fmtUSD(data.total.prior)} />
            <Stat label="Net change" value={`${data.total.delta > 0 ? "+" : ""}${fmtUSD(data.total.delta)}`} tone={data.total.delta > 0 ? "amber" : "accent"}
              sub={data.total.pct != null ? `${(data.total.pct * 100).toFixed(1)}% vs prior` : "new period"} />
          </div>

          <div className="card overflow-hidden mb-3">
            <div className="px-5 py-3 rule flex items-center justify-between">
              <span className="font-display text-[15px] text-ink">Variance by category</span>
              <span className="tag text-faint">sorted by movement</span>
            </div>
            <div className="overflow-x-auto">
              <div className="min-w-[680px]">
                <div className="px-5 py-2 rule thead grid grid-cols-[1fr_96px_96px_104px_120px] gap-3 bg-paper/50">
                  <span>Category</span>
                  <span className="text-right">{data.prior}</span>
                  <span className="text-right">{data.period}</span>
                  <span className="text-right">Change</span>
                  <span>Movement</span>
                </div>
                {rows.map((r: any) => (
                  <div key={r.code} className="ledger-row px-5 py-2.5 grid grid-cols-[1fr_96px_96px_104px_120px] gap-3 items-center text-xs">
                    <span className="text-ink truncate"><span className="num text-faint">{r.code}</span> {r.name}</span>
                    <span className="num text-muted text-right">{fmtUSD(r.prior)}</span>
                    <span className="num text-ink text-right">{fmtUSD(r.current)}</span>
                    <span className={`num text-right ${r.delta > 0 ? "text-rust" : r.delta < 0 ? "text-accent" : "text-faint"}`}>{r.delta > 0 ? "+" : ""}{fmtUSD(r.delta)}</span>
                    <span><FluxBar value={r.delta} max={maxDelta} /></span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {data.drivers?.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-5 py-3 rule flex items-center justify-between">
                <span className="font-display text-[15px] text-ink">Top movers</span>
                <span className="tag text-faint">expand to see the transactions</span>
              </div>
              <div className="overflow-x-auto">
                <div className="min-w-[520px]">
                  {data.drivers.map((d: any, i: number) => <FluxDriver key={i} d={d} />)}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* trust & security                                                     */
/* ------------------------------------------------------------------ */

const SCENARIOS = [
  { id: "tamper", icon: "hash", threat: "Someone edits a posted transaction to hide activity", endpoint: "/security/demo/tamper" },
  { id: "cross_tenant", icon: "building", threat: "One firm's staff tries to open another firm's client file", endpoint: "/security/demo/cross_tenant" },
  { id: "rbac", icon: "key", threat: "A junior associate tries to export the audit trail", endpoint: "/security/demo/rbac" },
  { id: "encrypt", icon: "lock", threat: "A database row leaks: can anyone read the client's EIN?", endpoint: "/security/demo/encrypt" },
  { id: "pii", icon: "eyeOff", threat: "A client message accidentally contains an SSN and bank account", endpoint: "/security/demo/pii" },
];

function ScenarioCard({ s }: { s: any }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const run = async () => { setLoading(true); try { setData(await api(s.endpoint)); } finally { setLoading(false); } };
  const safe = data && (data.tampered?.valid === false || data.blocked || data.other_firm_decrypt === "could not decrypt" || s.id === "rbac" || (s.id === "pii" && data.clean === false));
  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-9 h-9 shrink-0 rounded-lg bg-paper border border-line text-muted flex items-center justify-center">
            <I name={s.icon} size={15} />
          </div>
          <div className="min-w-0">
            <div className="tag text-rust mb-1">Threat scenario</div>
            <div className="text-sm text-ink leading-snug">{s.threat}</div>
          </div>
        </div>
        <button onClick={run} disabled={loading} className="btn-ghost shrink-0">
          <I name="play" size={11} />
          {loading ? "Running…" : data ? "Re-run" : "Simulate"}
        </button>
      </div>
      {data && (
        <div className="unfold mt-4 pt-4 border-t border-line">
          <div className="mb-3">
            <span className={`tag inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 border ${safe ? "bg-accentSoft text-accent border-accent/25" : "bg-rustSoft text-rust border-rust/25"}`}>
              <I name={safe ? "shield" : "x"} size={11} />
              {safe ? "Stopped" : "Exposed"}
            </span>
          </div>
          {s.id === "tamper" && (
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between gap-3">
                <span className="text-muted">Clean chain</span>
                <span className="num text-accent">verified · {data.clean?.rows} rows</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted">After the edit</span>
                <span className="num text-rust">broken at row {data.tampered?.broken_at}</span>
              </div>
            </div>
          )}
          {s.id === "cross_tenant" && (
            <div className={`num text-xs ${data.blocked ? "text-accent" : "text-rust"}`}>
              {data.blocked ? "ACCESS DENIED, blocked and logged" : "leaked"}
            </div>
          )}
          {s.id === "rbac" && (
            <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-5 gap-y-1 text-[11px] items-center">
              <span />
              <span className="tag text-faint text-center">approve</span>
              <span className="tag text-faint text-center">message</span>
              <span className="tag text-faint text-center">export</span>
              {["partner", "manager", "associate"].map((r) => (
                <React.Fragment key={r}>
                  <span className="text-muted capitalize">{r}</span>
                  {["approve", "send_message", "export_audit"].map((a) => {
                    const ok = data.matrix?.find((m: any) => m.role === r && m.action === a)?.allowed;
                    return (
                      <span key={a} className={`flex justify-center ${ok ? "text-accent" : "text-rust"}`}>
                        <I name={ok ? "check" : "x"} size={12} strokeWidth={2} />
                      </span>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          )}
          {s.id === "encrypt" && (
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between gap-3 min-w-0">
                <span className="text-muted shrink-0">At rest</span>
                <span className="num text-ink truncate">{data.ciphertext_at_rest}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted">Another firm's key</span>
                <span className="num text-accent">{data.other_firm_decrypt}</span>
              </div>
            </div>
          )}
          {s.id === "pii" && (
            <div className="text-xs space-y-1.5">
              <div className="text-rust">caught: {(data.findings || []).map((f: any) => f.type).join(", ")}</div>
              <div className="num text-ink rounded-lg border border-line bg-paper px-2.5 py-1.5">{data.redacted}</div>
            </div>
          )}
          <div className="text-xs text-muted mt-3 pt-3 border-t border-line leading-relaxed">
            <span className="text-accent font-medium">How Trustmax stops it. </span>
            {data.solution}
          </div>
        </div>
      )}
    </div>
  );
}

function ComplianceCard({ firm }: { firm: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const run = async () => { setLoading(true); try { setData(await api(`/firms/${firm}/compliance`)); } finally { setLoading(false); } };
  useEffect(() => { setData(null); api(`/firms/${firm}/compliance`).then(setData).catch(() => {}); }, [firm]);
  const tone: Record<string, string> = { high: "rust", medium: "amber", low: "muted" };
  return (
    <div className="card card-hover p-6 mt-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-9 h-9 shrink-0 rounded-lg bg-accentSoft border border-accent/15 text-accent flex items-center justify-center">
            <I name="scan" size={15} />
          </div>
          <div>
            <div className="text-[13.5px] font-semibold text-ink">Compliance agent</div>
            <div className="text-xs text-muted mt-0.5 max-w-xl leading-relaxed">
              A background reviewer that watches the firm for governance risk: high-value auto-approvals, self-approval, approval concentration, unresolved high-severity alerts, and vendors with a high correction rate.
            </div>
          </div>
        </div>
        <button onClick={run} disabled={loading} className="btn-ghost shrink-0">
          <I name="flywheel" size={12} className={loading ? "animate-spin" : ""} />
          {loading ? "Scanning…" : data ? "Re-scan" : "Run scan"}
        </button>
      </div>
      {data && (
        <div className="unfold mt-4 pt-4 border-t border-line">
          <div className="flex flex-wrap gap-2 mb-3">
            <Tag tone="muted"><span className="num">{data.summary.total}</span> findings</Tag>
            <Tag tone={data.summary.high > 0 ? "rust" : "muted"}><span className="num">{data.summary.high}</span> high</Tag>
            <Tag tone={data.summary.sod_clean ? "accent" : "rust"}>SoD {data.summary.sod_clean ? "clean" : "violation"}</Tag>
            <Tag tone="muted"><span className="num">{fmtNum(data.summary.scanned_events)}</span> events scanned</Tag>
          </div>
          <div className="space-y-2.5">
            {data.findings.map((f: any, i: number) => (
              <div key={i} className="flex items-start gap-3 text-xs">
                <Tag tone={tone[f.severity]}>{f.severity}</Tag>
                <div className="flex-1 leading-relaxed">
                  <div className="text-ink">{f.detail}</div>
                  <div className="text-muted">Recommend: {f.recommendation}</div>
                </div>
              </div>
            ))}
            {!data.findings.length && (
              <div className="text-xs text-accent flex items-center gap-1.5">
                <I name="check" size={12} /> No governance issues found.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Trust({ firm }: { firm: string }) {
  const [health, setHealth] = useState<any>(null);
  const [txns, setTxns] = useState<any[]>([]);
  const [txId, setTxId] = useState("");
  const [explain, setExplain] = useState<any>(null);
  const [narr, setNarr] = useState<any>(null);
  const [narrLoading, setNarrLoading] = useState(false);
  const load = (id: string) => {
    setExplain(null); setNarr(null); setTxId(id);
    api(`/firms/${firm}/explain/${id}`).then(setExplain).catch(() => {});
  };
  useEffect(() => {
    setHealth(null); setExplain(null); setNarr(null); setTxId(""); setTxns([]);
    api(`/firms/${firm}/trust/health`).then(setHealth).catch(() => {});
    // load coded transactions so any number can be picked and traced; default to a rich one
    api(`/firms/${firm}/transactions?limit=80`).then((ts: any[]) => {
      const coded = ts.filter((t) => t.predicted_code);
      setTxns(coded);
      const good = coded.find((t) => t.graph_support > 0 && t.reasoning_path?.length)
        || coded.find((t) => t.reasoning_path?.length) || coded[0];
      if (good) load(good.id);
    }).catch(() => {});
  }, [firm]);
  const narrate = async () => { setNarrLoading(true); try { setNarr(await api(`/firms/${firm}/explain/${txId}/narrate`)); } finally { setNarrLoading(false); } };
  return (
    <div className="stagger">
      <SectionTitle
        kicker="Trust spine"
        title="Trust and security"
        desc="A compliance agent watches the firm, an explainability agent narrates any number, and each threat below shows what could go wrong and how Trustmax stops it."
      />

      {!health ? (
        <SkelStats n={4} className="mb-3" />
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
          <Stat label="Audit chain" value={health?.audit_chain_valid ? "Verified" : "Broken"} sub={`${fmtNum(health?.audit_events)} events, hash-chained`} />
          <Stat label="Security checks" value={health?.security_checks || "-"} />
          <Stat label="Compliance findings" value={fmtNum(health?.compliance_findings)} sub={`${health?.compliance_high || 0} high severity`} />
          <Stat label="Segregation of duties" value={health?.sod_clean ? "Clean" : "Violation"} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {SCENARIOS.map((s) => <ScenarioCard key={s.id} s={s} />)}
      </div>

      <ComplianceCard firm={firm} />

      {txns.length > 0 && (
        <div className="card card-hover p-6 mt-3">
          <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
            <div className="flex items-start gap-3.5">
              <div className="w-9 h-9 shrink-0 rounded-lg bg-accentSoft border border-accent/15 text-accent flex items-center justify-center">
                <I name="graph" size={15} />
              </div>
              <div>
                <div className="text-[13.5px] font-semibold text-ink">Explain this number</div>
                <div className="text-xs text-muted mt-0.5">Pick any transaction to trace its full decision path.</div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={txId} onChange={(e) => load(e.target.value)} ariaLabel="Transaction to explain" className="max-w-[230px] sm:max-w-none">
                {txns.map((t) => (
                  <option key={t.id} value={t.id}>{t.vendor_raw} · {fmtUSD(t.amount)}</option>
                ))}
              </Select>
              <button onClick={narrate} disabled={narrLoading || !explain?.decision?.code} className="btn-ghost shrink-0">
                <I name="chat" size={12} />
                {narrLoading ? "Narrating…" : "Narrate"}
              </button>
            </div>
          </div>
          {!explain ? (
            <div className="space-y-2"><div className="skel h-9 w-2/3" /><div className="skel h-4 w-1/2" /></div>
          ) : explain.decision?.code ? (
            <div className="view-enter">
              <div className="rounded-lg border border-line bg-paper px-3.5 py-2.5 text-sm mb-4 inline-flex items-center gap-2 flex-wrap">
                <span className="text-ink font-medium">{explain.transaction?.vendor_raw}</span>
                <span className="num text-muted">{fmtUSD(explain.transaction?.amount)}</span>
                <I name="arrowRight" size={12} className="text-faint" />
                <span className="num text-accent">{explain.decision.code} {explain.decision.account}</span>
                {explain.decision.grounded && <Tag tone="accent">grounded</Tag>}
              </div>
              {narr && (
                <p className="unfold font-display text-[15.5px] text-ink mb-4 bg-accentSoft/60 border border-accent/20 rounded-lg px-4 py-3 leading-snug">
                  {narr.narrative} <span className="tag text-muted">{genLabel(narr.generated_by)}</span>
                </p>
              )}
              <div className="tag text-faint mb-2">Reasoning path</div>
              <Rail items={explain.reasoning_path || []} empty="Coded from the chart of accounts; no learned fact yet." />
              <div className="mt-4 pt-3 border-t border-line text-xs text-muted flex items-center gap-1.5">
                <I name="shield" size={12} className="text-accent" />
                {fmtNum(explain.audit_trail?.length)} audit events recorded for this transaction.
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted">No coding decision recorded for this transaction yet. Pick another.</div>
          )}
        </div>
      )}
    </div>
  );
}
