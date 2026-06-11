"use client";
import React from "react";

export function Tag({ children, tone = "muted" }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    muted: "text-muted border-line",
    accent: "text-accent border-accent/30 bg-accentSoft",
    amber: "text-amber border-amber/30 bg-amber/5",
    rust: "text-rust border-rust/30 bg-rust/5",
  };
  return <span className={`tag inline-block px-2 py-0.5 border rounded-sm ${tones[tone]}`}>{children}</span>;
}

export function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, [string, string]> = {
    auto_approved: ["auto-approved", "accent"], auto_routed: ["auto-routed", "accent"],
    approved: ["approved", "accent"], corrected: ["corrected", "amber"],
    pending: ["needs review", "amber"], needs_review: ["needs review", "amber"],
    high: ["high", "rust"], medium: ["medium", "amber"], low: ["low", "muted"],
  };
  const [label, tone] = map[status || "pending"] || [status, "muted"];
  return <Tag tone={tone}>{label}</Tag>;
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card p-5 rise">
      <div className="tag text-muted">{label}</div>
      <div className="num text-3xl mt-2 text-ink">{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

export function SectionTitle({ kicker, title, desc }: { kicker?: string; title: string; desc?: string }) {
  return (
    <div className="mb-6">
      {kicker && <div className="tag text-accent mb-1">{kicker}</div>}
      <h2 className="font-display text-2xl text-ink">{title}</h2>
      {desc && <p className="text-sm text-muted mt-1 max-w-2xl">{desc}</p>}
    </div>
  );
}

export function Meter({ value, tone = "accent" }: { value: number; tone?: string }) {
  const c: Record<string, string> = { accent: "bg-accent", amber: "bg-amber", rust: "bg-rust" };
  return (
    <div className="h-1.5 w-full bg-line rounded-full overflow-hidden">
      <div className={`h-full ${c[tone]} rounded-full transition-all`} style={{ width: `${Math.min(100, value * 100)}%` }} />
    </div>
  );
}
