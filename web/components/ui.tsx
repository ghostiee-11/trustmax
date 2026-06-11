"use client";
import React from "react";
import { I } from "./icons";

export function Tag({ children, tone = "muted" }: { children: React.ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    muted: "text-muted border-line bg-paper",
    accent: "text-accent border-accent/25 bg-accentSoft",
    amber: "text-amber border-amber/25 bg-amberSoft",
    rust: "text-rust border-rust/25 bg-rustSoft",
  };
  return (
    <span className={`tag inline-flex items-center gap-1.5 px-2 py-[3px] border rounded-md whitespace-nowrap ${tones[tone] || tones.muted}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, [string, string]> = {
    auto_approved: ["auto-approved", "accent"], auto_routed: ["auto-routed", "accent"],
    approved: ["approved", "accent"], corrected: ["corrected", "amber"],
    pending: ["needs review", "amber"], needs_review: ["needs review", "amber"],
    high: ["high", "rust"], medium: ["medium", "amber"], low: ["low", "muted"],
  };
  const [label, tone] = map[status || "pending"] || [status, "muted"];
  const dot: Record<string, string> = { accent: "bg-accent", amber: "bg-amber", rust: "bg-rust", muted: "bg-faint" };
  return (
    <Tag tone={tone}>
      <span className={`w-1 h-1 rounded-full ${dot[tone] || dot.muted}`} />
      {label}
    </Tag>
  );
}

export function Stat({
  label, value, sub, meter, tone = "accent",
}: {
  label: string; value: React.ReactNode; sub?: string; meter?: number; tone?: string;
}) {
  return (
    <div className="card card-hover p-5">
      <div className="tag text-faint">{label}</div>
      <div className="num text-[26px] font-medium leading-tight mt-2.5 text-ink">{value}</div>
      {typeof meter === "number" && Number.isFinite(meter) && (
        <div className="mt-3"><Meter value={meter} tone={tone} /></div>
      )}
      {sub && <div className="text-xs text-muted mt-1.5">{sub}</div>}
    </div>
  );
}

export function SectionTitle({
  kicker, title, desc, children,
}: {
  kicker?: string; title: string; desc?: string; children?: React.ReactNode;
}) {
  return (
    <div className="mb-7 flex items-end justify-between gap-6">
      <div className="min-w-0">
        {kicker && <div className="tag text-accent mb-1.5">{kicker}</div>}
        <h2 className="font-display text-[28px] leading-tight tracking-tight text-ink">{title}</h2>
        {desc && <p className="text-sm text-muted mt-2 max-w-2xl leading-relaxed">{desc}</p>}
      </div>
      {children && <div className="shrink-0 pb-1">{children}</div>}
    </div>
  );
}

export function Meter({ value, tone = "accent" }: { value: number; tone?: string }) {
  const c: Record<string, string> = { accent: "bg-accent", amber: "bg-amber", rust: "bg-rust" };
  return (
    <div className="h-1.5 w-full bg-line rounded-full overflow-hidden">
      <div
        className={`h-full ${c[tone] || c.accent} rounded-full transition-all duration-500`}
        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }}
      />
    </div>
  );
}

export function Chip({
  active, onClick, children, count,
}: {
  active?: boolean; onClick?: () => void; children: React.ReactNode; count?: number;
}) {
  return (
    <button onClick={onClick} data-active={!!active} className="chip">
      {children}
      {count != null && <span className="chip-count">{count}</span>}
    </button>
  );
}

export function Select({
  value, onChange, children, className = "", ariaLabel,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  children: React.ReactNode;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <span className={`relative inline-flex ${className}`}>
      <select value={value} onChange={onChange} aria-label={ariaLabel} className="field appearance-none pr-7 num w-full cursor-pointer">
        {children}
      </select>
      <span className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-faint">
        <I name="chevronDown" size={12} />
      </span>
    </span>
  );
}

export function Rail({ items, empty }: { items: string[]; empty?: string }) {
  if (!items.length) {
    return <div className="text-xs text-muted">{empty || "Nothing recorded yet."}</div>;
  }
  return (
    <ol className="relative border-l border-accent/25 pl-4 space-y-2">
      {items.map((r, i) => (
        <li key={i} className="relative text-xs text-muted leading-relaxed">
          <span className="absolute -left-[21px] top-[3px] w-2 h-2 rounded-full bg-accentSoft border border-accent/50" />
          {r}
        </li>
      ))}
    </ol>
  );
}
