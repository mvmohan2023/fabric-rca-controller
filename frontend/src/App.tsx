import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Cable,
  ChevronRight,
  Clock3,
  Eye,
  FileJson,
  Filter,
  Gauge,
  Network,
  Search,
  ShieldAlert,
  Waves,
  Zap,
} from "lucide-react";
import { fetchCase, fetchCases, type RCAReport, type Severity } from "./api";

type View = "overview" | "fabric" | "timeline" | "evidence";
type Hotspot = RCAReport["hotspots"][number];
type DeltaEntry = RCAReport["deltas"][number];

const severityMap: Record<Exclude<Severity, "none">, string> = {
  critical: "bg-rose-500/15 text-rose-300 ring-1 ring-inset ring-rose-400/30",
  high: "bg-orange-500/15 text-orange-300 ring-1 ring-inset ring-orange-400/30",
  medium: "bg-amber-500/15 text-amber-300 ring-1 ring-inset ring-amber-400/30",
  low: "bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-400/30",
  normal: "bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-400/30",
};

function classNames(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

function normalizeSeverity(value?: string): Exclude<Severity, "none"> {
  if (
    value === "critical" ||
    value === "high" ||
    value === "medium" ||
    value === "low" ||
    value === "normal"
  ) {
    return value;
  }
  return "normal";
}

function severityFromScore(score: number): Exclude<Severity, "none"> {
  if (score >= 300) return "critical";
  if (score >= 200) return "high";
  if (score >= 100) return "medium";
  if (score > 0) return "low";
  return "normal";
}

function shortCause(cause: string) {
  return cause.replaceAll("-", " ");
}

function formatNumber(value: number) {
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return `${value}`;
}

function Badge({
  children,
  severity = "normal",
}: {
  children: React.ReactNode;
  severity?: Exclude<Severity, "none">;
}) {
  return (
    <span
      className={classNames(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
        severityMap[severity]
      )}
    >
      {children}
    </span>
  );
}

function SectionCard({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] shadow-2xl shadow-black/20 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4">
        <div>
          <h3 className="text-sm font-semibold tracking-wide text-white">{title}</h3>
          {subtitle ? <p className="mt-1 text-xs text-slate-400">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  footnote,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  footnote?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
      <div className="flex items-center justify-between">
        <div className="rounded-2xl bg-white/5 p-2 text-slate-300">{icon}</div>
        <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">RCA</span>
      </div>
      <div className="mt-4 text-xs uppercase tracking-[0.18em] text-slate-400">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      {footnote ? <div className="mt-1 text-xs text-slate-400">{footnote}</div> : null}
    </div>
  );
}

function MiniBar({
  value,
  max = 100,
  severity = "low",
}: {
  value: number;
  max?: number;
  severity?: Exclude<Severity, "none">;
}) {
  const width = Math.max(6, Math.min(100, (value / max) * 100));
  const barClass = {
    critical: "bg-rose-400",
    high: "bg-orange-400",
    medium: "bg-amber-400",
    low: "bg-sky-400",
    normal: "bg-emerald-400",
  }[severity];

  return (
    <div className="h-2 w-full rounded-full bg-white/5">
      <div className={classNames("h-2 rounded-full", barClass)} style={{ width: `${width}%` }} />
    </div>
  );
}

function buildNodeInventory(hotspots: Hotspot[]) {
  const grouped = new Map<
    string,
    {
      node: string;
      maxScore: number;
      severity: Exclude<Severity, "none">;
      queues: number;
      interfaces: Set<string>;
    }
  >();

  hotspots.forEach((item) => {
    const current = grouped.get(item.node);
    if (!current) {
      grouped.set(item.node, {
        node: item.node,
        maxScore: item.score,
        severity: normalizeSeverity(item.severity),
        queues: 1,
        interfaces: new Set([item.interface]),
      });
      return;
    }
    current.maxScore = Math.max(current.maxScore, item.score);
    current.severity = severityFromScore(current.maxScore);
    current.queues += 1;
    current.interfaces.add(item.interface);
  });

  return Array.from(grouped.values())
    .map((entry) => ({ ...entry, interfaceCount: entry.interfaces.size }))
    .sort((a, b) => b.maxScore - a.maxScore);
}

function TopNav({
  view,
  setView,
}: {
  view: View;
  setView: (view: View) => void;
}) {
  const items: Array<{ id: View; label: string; icon: React.ReactNode }> = [
    { id: "overview", label: "Overview", icon: <BarChart3 className="h-4 w-4" /> },
    { id: "fabric", label: "Fabric Hotspots", icon: <Network className="h-4 w-4" /> },
    { id: "timeline", label: "Contributing Factors", icon: <Clock3 className="h-4 w-4" /> },
    { id: "evidence", label: "Evidence", icon: <FileJson className="h-4 w-4" /> },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => setView(item.id)}
          className={classNames(
            "inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm transition-all",
            view === item.id
              ? "bg-white text-slate-950 shadow-lg"
              : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white"
          )}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

function Sidebar({
  report,
  nodeInventory,
  search,
  setSearch,
  selectedEntity,
  setSelectedEntity,
}: {
  report: RCAReport;
  nodeInventory: Array<{
    node: string;
    maxScore: number;
    severity: Exclude<Severity, "none">;
    queues: number;
    interfaceCount: number;
  }>;
  search: string;
  setSearch: (v: string) => void;
  selectedEntity: string;
  setSelectedEntity: (v: string) => void;
}) {
  const entities = [...nodeInventory.map((n) => n.node), ...report.hotspots.map((h) => h.entity_id)];
  const filtered = entities.filter((e) => e.toLowerCase().includes(search.toLowerCase()));

  return (
    <aside className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="rounded-2xl bg-white/5 p-2 text-slate-300">
          <Search className="h-4 w-4" />
        </div>
        <div>
          <div className="text-sm font-semibold text-white">Run Navigator</div>
          <div className="text-xs text-slate-400">Hotspot RCA exploration</div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 px-3 py-2">
        <div className="flex items-center gap-2 text-slate-400">
          <Search className="h-4 w-4" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
            placeholder="Search node, interface, or queue"
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Run ID</div>
          <div className="mt-2 text-sm font-semibold text-white">{report.run_metadata.run_id}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">Profile</div>
          <div className="mt-2 text-sm font-semibold text-white">{report.run_metadata.profile}</div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-500">
        <Filter className="h-3.5 w-3.5" />
        Entities
      </div>
      <div className="mt-2 space-y-2 max-h-[58vh] overflow-auto pr-1">
        {filtered.map((entity) => (
          <button
            key={entity}
            onClick={() => setSelectedEntity(entity)}
            className={classNames(
              "flex w-full items-center justify-between rounded-2xl border px-3 py-2 text-left text-sm transition-all",
              selectedEntity === entity
                ? "border-sky-400/40 bg-sky-400/10 text-white"
                : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white"
            )}
          >
            <span className="truncate pr-3">{entity}</span>
            <ChevronRight className="h-4 w-4 shrink-0 opacity-70" />
          </button>
        ))}
      </div>
    </aside>
  );
}

function OverviewPage({
  report,
  setSelectedEntity,
}: {
  report: RCAReport;
  setSelectedEntity: (id: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={<ShieldAlert className="h-5 w-5" />}
          label="Primary Cause"
          value={shortCause(report.summary.primary_cause)}
          footnote="Dominant queue signature"
        />
        <StatCard
          icon={<Gauge className="h-5 w-5" />}
          label="Confidence"
          value={`${Math.round(report.summary.confidence * 100)}%`}
          footnote="From top hotspot score"
        />
        <StatCard
          icon={<Waves className="h-5 w-5" />}
          label="Top Hotspot Score"
          value={report.summary.top_hotspot_score}
          footnote={`${report.summary.top_hotspot_node} q${report.summary.top_hotspot_queue}`}
        />
        <StatCard
          icon={<Activity className="h-5 w-5" />}
          label="Total Hotspots"
          value={report.summary.total_hotspots}
          footnote="Running snapshot"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.35fr_0.95fr]">
        <SectionCard
          title="RCA Verdict"
          subtitle="Normalized from hotspot ranking, congestion analysis, and delta evidence."
          action={<Badge severity={normalizeSeverity(report.summary.severity)}>{report.summary.severity}</Badge>}
        >
          <div className="rounded-2xl border border-rose-400/20 bg-rose-400/5 p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-rose-200/70">Final Conclusion</div>
                <div className="mt-2 max-w-3xl text-lg font-semibold text-white">
                  {shortCause(report.summary.primary_cause)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-400">Confidence</div>
                <div className="mt-2 text-3xl font-semibold text-white">
                  {Math.round(report.summary.confidence * 100)}%
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
                <div className="text-xs text-slate-400">Top hotspot node</div>
                <button
                  onClick={() => setSelectedEntity(report.summary.top_hotspot_node)}
                  className="mt-2 text-left text-sm font-semibold text-sky-300 hover:text-sky-200"
                >
                  {report.summary.top_hotspot_node}
                </button>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
                <div className="text-xs text-slate-400">Top queue entity</div>
                <button
                  onClick={() => setSelectedEntity(report.hotspots[0]?.entity_id ?? "")}
                  className="mt-2 break-all text-left text-sm font-semibold text-sky-300 hover:text-sky-200"
                >
                  {report.hotspots[0]?.entity_id ?? "-"}
                </button>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-3">
                <div className="text-xs text-slate-400">Profile</div>
                <div className="mt-2 text-sm font-semibold text-white">{report.run_metadata.profile}</div>
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Run Snapshot" subtitle="Case-level metadata used by the backend normalizer.">
          <dl className="grid grid-cols-1 gap-3 text-sm">
            {[
              ["Intent", report.run_metadata.intent_name],
              ["Source", report.run_metadata.src],
              ["Destination", report.run_metadata.dst],
              ["Profile", report.run_metadata.profile],
              ["Generated", report.run_metadata.generated_at],
              ["Nodes", report.run_metadata.nodes.join(", ")],
            ].map(([k, v]) => (
              <div
                key={k}
                className="flex items-start justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/40 px-3 py-2.5"
              >
                <dt className="text-slate-400">{k}</dt>
                <dd className="text-right font-medium text-white">{v}</dd>
              </div>
            ))}
          </dl>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.05fr_1.25fr]">
        <SectionCard title="Top Queue Hotspots" subtitle="Highest-scoring queue entities from the running snapshot.">
          <div className="space-y-3">
            {report.hotspots.map((item, index) => (
              <button
                key={item.entity_id}
                onClick={() => setSelectedEntity(item.entity_id)}
                className="w-full rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-left transition hover:border-white/20 hover:bg-white/5"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Rank #{index + 1}</div>
                    <div className="mt-1 break-all font-semibold text-white">{item.entity_id}</div>
                    <div className="mt-1 text-sm text-slate-400">{shortCause(item.probable_cause)}</div>
                  </div>
                  <div className="w-24 text-right">
                    <div className="text-sm font-semibold text-white">{item.score}</div>
                    <div className="mt-2">
                      <MiniBar value={item.score} max={450} severity={normalizeSeverity(item.severity)} />
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Severity Distribution" subtitle="Normalized counts from the hotspot summary file.">
          <div className="space-y-4">
            {Object.entries(report.summary.severity_counts).map(([key, count]) => (
              <div key={key}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <div className="capitalize text-white">{key}</div>
                  <div className="text-slate-400">{count}</div>
                </div>
                <MiniBar
                  value={count}
                  max={report.summary.total_hotspots}
                  severity={normalizeSeverity(key)}
                />
              </div>
            ))}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

function NodePill({
  id,
  severity,
  selected,
  score,
  onClick,
}: {
  id: string;
  severity: Exclude<Severity, "none">;
  selected: boolean;
  score: number;
  onClick: () => void;
}) {
  const accent = {
    critical: "border-rose-400/40 bg-rose-400/10",
    high: "border-orange-400/40 bg-orange-400/10",
    medium: "border-amber-400/40 bg-amber-400/10",
    low: "border-sky-400/40 bg-sky-400/10",
    normal: "border-emerald-400/40 bg-emerald-400/10",
  }[severity];

  return (
    <button
      onClick={onClick}
      className={classNames(
        "rounded-2xl border px-4 py-3 text-left shadow-lg transition hover:scale-[1.01]",
        selected ? `${accent} ring-2 ring-white/30` : "border-white/10 bg-slate-950/50 hover:bg-white/10"
      )}
    >
      <div className="text-sm font-semibold text-white">{id}</div>
      <div className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
        Top queue score {score}
      </div>
    </button>
  );
}

function HotspotRow({
  hotspot,
  selected,
  onClick,
}: {
  hotspot: Hotspot;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={classNames(
        "w-full rounded-2xl border p-4 text-left transition",
        selected ? "border-sky-400/40 bg-sky-400/10" : "border-white/10 bg-slate-950/40 hover:bg-white/5"
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="break-all font-semibold text-white">{hotspot.entity_id}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span>{hotspot.node}</span>
            <Cable className="h-3 w-3" />
            <span>{hotspot.interface}</span>
            <Badge severity={normalizeSeverity(hotspot.severity)}>q{hotspot.queue}</Badge>
          </div>
        </div>
        <Badge severity={normalizeSeverity(hotspot.severity)}>{hotspot.severity}</Badge>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div>
          <div className="text-slate-500">Score</div>
          <div className="mt-1 font-semibold text-white">{hotspot.score}</div>
        </div>
        <div>
          <div className="text-slate-500">Tail Drop</div>
          <div className="mt-1 font-semibold text-white">{formatNumber(hotspot.signals.tail_drop_pkts)}</div>
        </div>
        <div>
          <div className="text-slate-500">ECN Marks</div>
          <div className="mt-1 font-semibold text-white">{formatNumber(hotspot.signals.ecn_marked_pkts)}</div>
        </div>
      </div>
    </button>
  );
}

function FabricMapPage({
  report,
  nodeInventory,
  selectedEntity,
  setSelectedEntity,
}: {
  report: RCAReport;
  nodeInventory: Array<{
    node: string;
    maxScore: number;
    severity: Exclude<Severity, "none">;
    queues: number;
    interfaceCount: number;
  }>;
  selectedEntity: string;
  setSelectedEntity: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.2fr_0.95fr]">
      <SectionCard title="Hotspot Concentration Map" subtitle="Node-centric view derived from running hotspot analysis.">
        <div className="rounded-[28px] border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.10),_transparent_30%),linear-gradient(to_bottom,rgba(15,23,42,0.85),rgba(2,6,23,0.85))] p-6">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {nodeInventory.map((node) => (
              <NodePill
                key={node.node}
                id={node.node}
                score={node.maxScore}
                severity={node.severity}
                selected={selectedEntity === node.node}
                onClick={() => setSelectedEntity(node.node)}
              />
            ))}
          </div>

          <div className="mt-8 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-500">
              <Eye className="h-3.5 w-3.5" /> Top queue entities
            </div>
            <div className="mt-4 space-y-3">
              {report.hotspots.map((hotspot) => (
                <div key={hotspot.entity_id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex items-center justify-between gap-4">
                    <button
                      onClick={() => setSelectedEntity(hotspot.entity_id)}
                      className="break-all text-left font-medium text-white hover:text-sky-300"
                    >
                      {hotspot.node} → {hotspot.interface} → q{hotspot.queue}
                    </button>
                    <div className="flex items-center gap-2">
                      <Badge severity={normalizeSeverity(hotspot.severity)}>
                        {shortCause(hotspot.probable_cause)}
                      </Badge>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-3">
                    <div>
                      <div className="mb-1 text-xs text-slate-500">Peak buffer</div>
                      <MiniBar
                        value={hotspot.signals.peak_buffer_occupancy_percent}
                        severity={normalizeSeverity(hotspot.severity)}
                      />
                      <div className="mt-2 text-sm text-white">
                        {hotspot.signals.peak_buffer_occupancy_percent}%
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-slate-500">PFC activity</div>
                      <MiniBar
                        value={Math.min(100, hotspot.signals.pfc_activity > 0 ? 100 : 0)}
                        severity={normalizeSeverity(hotspot.severity)}
                      />
                      <div className="mt-2 text-sm text-white">{formatNumber(hotspot.signals.pfc_activity)}</div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs text-slate-500">FEC corrected</div>
                      <MiniBar
                        value={Math.min(100, hotspot.signals.fec_corrected_words > 0 ? 100 : 0)}
                        severity={hotspot.signals.fec_uncorrectable_words > 0 ? "high" : "low"}
                      />
                      <div className="mt-2 text-sm text-white">
                        {formatNumber(hotspot.signals.fec_corrected_words)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Hotspot Inventory" subtitle="Entity drill-down synchronized with evidence view.">
        <div className="space-y-3">
          {report.hotspots.map((hotspot) => (
            <HotspotRow
              key={hotspot.entity_id}
              hotspot={hotspot}
              selected={selectedEntity === hotspot.entity_id}
              onClick={() => setSelectedEntity(hotspot.entity_id)}
            />
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

function TimelinePage({
  report,
  setSelectedEntity,
}: {
  report: RCAReport;
  setSelectedEntity: (id: string) => void;
}) {
  return (
    <SectionCard title="Contributing Factor Timeline" subtitle="Ranked supporting factors that shaped the final RCA decision.">
      <div className="space-y-3">
        {report.summary.contributing_factors.map((factor, index) => {
          const relatedEntity = report.hotspots[index]?.entity_id ?? report.hotspots[0]?.entity_id ?? "";
          return (
            <button
              key={`${factor}-${index}`}
              onClick={() => setSelectedEntity(relatedEntity)}
              className="flex w-full gap-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-left transition hover:bg-white/5"
            >
              <div className="w-20 shrink-0">
                <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Rank</div>
                <div className="mt-1 font-semibold text-white">#{index + 1}</div>
              </div>
              <div className="mt-6 h-3 w-3 shrink-0 rounded-full bg-rose-400" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-semibold text-white">{factor}</div>
                  <Badge severity={normalizeSeverity(report.hotspots[index]?.severity)}>Evidence</Badge>
                </div>
                <div className="mt-1 break-all text-sm text-slate-400">{relatedEntity}</div>
              </div>
            </button>
          );
        })}
      </div>
    </SectionCard>
  );
}

function EvidencePage({
  report,
  nodeInventory,
  deltaMap,
  selectedEntity,
  setSelectedEntity,
}: {
  report: RCAReport;
  nodeInventory: Array<{
    node: string;
    maxScore: number;
    severity: Exclude<Severity, "none">;
    queues: number;
    interfaceCount: number;
  }>;
  deltaMap: Map<string, DeltaEntry>;
  selectedEntity: string;
  setSelectedEntity: (id: string) => void;
}) {
  const hotspot = report.hotspots.find((item) => item.entity_id === selectedEntity);
  const delta = deltaMap.get(selectedEntity);
  const nodeSummary = nodeInventory.find((node) => node.node === selectedEntity);

  if (!hotspot && nodeSummary) {
    const related = report.hotspots.filter((item) => item.node === nodeSummary.node);
    return (
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SectionCard title="Evidence Explorer" subtitle="Node-level RCA view synthesized from queue hotspots.">
          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="text-lg font-semibold text-white">{selectedEntity}</div>
              <Badge severity={nodeSummary.severity}>node</Badge>
              <Badge severity={nodeSummary.severity}>{nodeSummary.severity}</Badge>
            </div>
            <ul className="mt-5 space-y-3 text-sm text-slate-300">
              <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                Top queue score reached {nodeSummary.maxScore} on this node.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                {nodeSummary.queues} hotspot queues detected across {nodeSummary.interfaceCount} interfaces.
              </li>
              <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                Primary local patterns include {related.slice(0, 3).map((r) => shortCause(r.probable_cause)).join(", ")}.
              </li>
            </ul>
          </div>
        </SectionCard>

        <SectionCard title="Related Queue Entities" subtitle="Highest scoring queues on the selected node.">
          <div className="space-y-3">
            {related.map((item) => (
              <button
                key={item.entity_id}
                onClick={() => setSelectedEntity(item.entity_id)}
                className="w-full rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-left"
              >
                <div className="break-all text-sm font-semibold text-white">{item.entity_id}</div>
                <div className="mt-1 text-sm text-slate-400">{shortCause(item.probable_cause)}</div>
              </button>
            ))}
          </div>
        </SectionCard>
      </div>
    );
  }

  if (!hotspot) {
    return (
      <SectionCard title="Evidence Explorer" subtitle="No direct entity evidence available.">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-6 text-slate-300">
          Select a hotspot entity from the navigator to inspect queue-level evidence.
        </div>
      </SectionCard>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <SectionCard title="Evidence Explorer" subtitle="Queue-level supporting metrics from the UI-normalized RCA report.">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="break-all text-lg font-semibold text-white">{selectedEntity}</div>
            <Badge severity={normalizeSeverity(hotspot.severity)}>queue entity</Badge>
            <Badge severity={normalizeSeverity(hotspot.severity)}>{hotspot.severity}</Badge>
          </div>
          <div className="mt-5 text-sm font-semibold text-white">Why this entity is suspicious</div>
          <ul className="mt-3 space-y-3 text-sm text-slate-300">
            <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
              Probable cause ranked as {shortCause(hotspot.probable_cause)}.
            </li>
            <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
              Queue score reached {hotspot.score} on {hotspot.node} {hotspot.interface} queue {hotspot.queue}.
            </li>
            <li className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
              Tail-drop, ECN, FEC, and PFC counters were used as supporting congestion indicators.
            </li>
          </ul>
        </div>
      </SectionCard>

      <SectionCard title="Metrics Snapshot" subtitle="Signal, running metric, and delta evidence for the selected entity.">
        <div className="space-y-3">
          {[
            {
              name: "Peak buffer occupancy",
              value: `${hotspot.signals.peak_buffer_occupancy_percent}%`,
              baseline: "running snapshot",
              delta: delta?.delta_running?.peak_buffer_occupancy_percent ?? "n/a",
            },
            {
              name: "Tail drop packets",
              value: formatNumber(hotspot.signals.tail_drop_pkts),
              baseline: "running snapshot",
              delta: delta?.delta_running?.tail_drop_pkts ?? "n/a",
            },
            {
              name: "ECN marked packets",
              value: formatNumber(hotspot.signals.ecn_marked_pkts),
              baseline: "running snapshot",
              delta: delta?.delta_running?.ecn_marked_pkts ?? "n/a",
            },
            {
              name: "PFC activity",
              value: formatNumber(hotspot.signals.pfc_activity),
              baseline: "running snapshot",
              delta: "signal",
            },
            {
              name: "FEC corrected words",
              value: formatNumber(hotspot.signals.fec_corrected_words),
              baseline: "running snapshot",
              delta: "signal",
            },
          ].map((metric) => (
            <div key={metric.name} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-white">{metric.name}</div>
                  <div className="mt-1 text-xs text-slate-500">Evidence metric</div>
                </div>
                <Badge severity={normalizeSeverity(hotspot.severity)}>{String(metric.delta)}</Badge>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div className="text-slate-500">Current</div>
                  <div className="mt-1 font-semibold text-white">{metric.value}</div>
                </div>
                <div>
                  <div className="text-slate-500">Reference</div>
                  <div className="mt-1 font-semibold text-white">{metric.baseline}</div>
                </div>
                <div>
                  <div className="text-slate-500">Delta</div>
                  <div className="mt-1 font-semibold text-white">{String(metric.delta)}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

function EvidenceDrawer({
  report,
  nodeInventory,
  deltaMap,
  selectedEntity,
  setSelectedEntity,
}: {
  report: RCAReport;
  nodeInventory: Array<{
    node: string;
    maxScore: number;
    severity: Exclude<Severity, "none">;
    queues: number;
    interfaceCount: number;
  }>;
  deltaMap: Map<string, DeltaEntry>;
  selectedEntity: string;
  setSelectedEntity: (id: string) => void;
}) {
  const hotspot = report.hotspots.find((item) => item.entity_id === selectedEntity);
  const nodeSummary = nodeInventory.find((item) => item.node === selectedEntity);
  const delta = deltaMap.get(selectedEntity);

  const summaryRows = useMemo(() => {
    if (hotspot) {
      return [
        ["Entity Type", "queue hotspot"],
        ["Node", hotspot.node],
        ["Interface", hotspot.interface],
        ["Queue", `q${hotspot.queue}`],
        ["Severity", hotspot.severity],
        ["Score", String(hotspot.score)],
      ];
    }
    if (nodeSummary) {
      return [
        ["Entity Type", "node"],
        ["Severity", nodeSummary.severity],
        ["Max Score", String(nodeSummary.maxScore)],
        ["Hotspot Queues", String(nodeSummary.queues)],
        ["Interfaces", String(nodeSummary.interfaceCount)],
      ];
    }
    return [["Entity Type", "unknown"]];
  }, [hotspot, nodeSummary]);

  const severity = normalizeSeverity(hotspot?.severity || nodeSummary?.severity || "normal");

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-white">Evidence Drawer</div>
          <div className="mt-1 text-xs text-slate-400">Selected entity details and RCA support</div>
        </div>
        <Badge severity={severity}>{severity}</Badge>
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/50 p-4">
        <div className="break-all text-sm font-semibold text-white">{selectedEntity}</div>
        <div className="mt-3 space-y-2">
          {summaryRows.map(([k, v]) => (
            <div key={k} className="flex items-start justify-between gap-3 text-sm">
              <div className="text-slate-500">{k}</div>
              <div className="text-right font-medium text-white">{v}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
          <div className="text-sm font-semibold text-white">Top reasons</div>
          <div className="mt-3 space-y-2 text-sm text-slate-300">
            {hotspot ? (
              <>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  {shortCause(hotspot.probable_cause)} is the dominant pattern on this queue.
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  Score {hotspot.score} places this entity among the highest-ranked hotspots in the case.
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  Running delta evidence {delta ? "is available" : "is not available"} for this entity.
                </div>
              </>
            ) : nodeSummary ? (
              <>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  This node aggregates multiple hotspot queues.
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  Highest local queue score is {nodeSummary.maxScore}.
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  Use queue entity selection for deeper interface-level drill-down.
                </div>
              </>
            ) : (
              <div className="text-slate-500">No expanded evidence available for this entity.</div>
            )}
          </div>
        </div>

        {nodeSummary ? (
          <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <div className="text-sm font-semibold text-white">Node queues</div>
            <div className="mt-3 space-y-2">
              {report.hotspots
                .filter((item) => item.node === nodeSummary.node)
                .map((item) => (
                  <button
                    key={item.entity_id}
                    onClick={() => setSelectedEntity(item.entity_id)}
                    className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-left text-sm text-slate-300 hover:bg-white/10"
                  >
                    {item.interface} · q{item.queue} · {item.score}
                  </button>
                ))}
            </div>
          </div>
        ) : null}

        <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
          <div className="text-sm font-semibold text-white">Final RCA reasoning</div>
          <div className="mt-3 text-sm leading-6 text-slate-300">
            The platform correlates queue score, cause classification, severity distribution, and running delta movement to prioritize this entity inside the normalized RCA verdict.
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [search, setSearch] = useState("");
  const [runIds, setRunIds] = useState<string[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [report, setReport] = useState<RCAReport | null>(null);
  const [selectedEntity, setSelectedEntity] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const init = async () => {
      try {
        setLoading(true);
        const cases = await fetchCases();
        const ids = cases.map((c) => c.run_id);
        setRunIds(ids);

        if (ids.length > 0) {
          const firstRun = ids[0];
          setSelectedRunId(firstRun);
          const loaded = await fetchCase(firstRun);
          setReport(loaded);
          setSelectedEntity(loaded.hotspots?.[0]?.entity_id ?? loaded.run_metadata.nodes?.[0] ?? "");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    };

    init();
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;

    const load = async () => {
      try {
        setLoading(true);
        setError("");
        const loaded = await fetchCase(selectedRunId);
        setReport(loaded);
        setSelectedEntity(loaded.hotspots?.[0]?.entity_id ?? loaded.run_metadata.nodes?.[0] ?? "");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [selectedRunId]);

  const nodeInventory = useMemo(() => {
    if (!report) return [];
    return buildNodeInventory(report.hotspots);
  }, [report]);

  const deltaMap = useMemo(() => {
    if (!report) return new Map<string, DeltaEntry>();
    return new Map(report.deltas.map((item) => [item.entity_id, item]));
  }, [report]);

  if (loading && !report) {
    return <div className="min-h-screen bg-slate-950 p-8 text-white">Loading RCA UI...</div>;
  }

  if (error && !report) {
    return <div className="min-h-screen bg-slate-950 p-8 text-rose-300">Failed to load RCA UI: {error}</div>;
  }

  if (!report) {
    return <div className="min-h-screen bg-slate-950 p-8 text-white">No RCA reports found.</div>;
  }

  return (
    <div className="min-h-screen bg-[linear-gradient(to_bottom_right,#020617,#0f172a,#111827)] text-slate-200">
      <div className="mx-auto max-w-[1700px] p-5 lg:p-7">
        <div className="mb-6 rounded-[28px] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.18),_transparent_25%),radial-gradient(circle_at_top_right,_rgba(249,115,22,0.12),_transparent_24%),rgba(255,255,255,0.04)] p-6 shadow-2xl shadow-black/30 backdrop-blur-xl">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.22em] text-sky-300">
                <Zap className="h-3.5 w-3.5" /> Fabric RCA Visualization
              </div>
              <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white md:text-4xl">
                Professional UI foundation aligned to your real RCA artifacts
              </h1>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-300 md:text-base">
                Built against the normalized <span className="font-semibold text-white">rca_ui_report.json</span> generated from your case manifest, congestion analysis, hotspot summary, and delta evidence files.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Badge severity={normalizeSeverity(report.summary.severity)}>
                Verdict: {shortCause(report.summary.primary_cause)}
              </Badge>
              <Badge severity="medium">Run: {report.run_metadata.run_id}</Badge>
              <Badge severity="high">Top Score: {report.summary.top_hotspot_score}</Badge>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <TopNav view={view} setView={setView} />
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
              <select
                value={selectedRunId}
                onChange={(e) => setSelectedRunId(e.target.value)}
                className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-white outline-none"
              >
                {runIds.map((runId) => (
                  <option key={runId} value={runId} className="bg-slate-900">
                    {runId}
                  </option>
                ))}
              </select>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2">
                Intent: <span className="font-semibold text-white">{report.run_metadata.intent_name}</span>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2">
                Path: <span className="font-semibold text-white">{report.run_metadata.src} → {report.run_metadata.dst}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
          <Sidebar
            report={report}
            nodeInventory={nodeInventory}
            search={search}
            setSearch={setSearch}
            selectedEntity={selectedEntity}
            setSelectedEntity={setSelectedEntity}
          />

          <main className="min-w-0">
            {view === "overview" && (
              <OverviewPage report={report} setSelectedEntity={setSelectedEntity} />
            )}
            {view === "fabric" && (
              <FabricMapPage
                report={report}
                nodeInventory={nodeInventory}
                selectedEntity={selectedEntity}
                setSelectedEntity={setSelectedEntity}
              />
            )}
            {view === "timeline" && (
              <TimelinePage report={report} setSelectedEntity={setSelectedEntity} />
            )}
            {view === "evidence" && (
              <EvidencePage
                report={report}
                nodeInventory={nodeInventory}
                deltaMap={deltaMap}
                selectedEntity={selectedEntity}
                setSelectedEntity={setSelectedEntity}
              />
            )}
          </main>

          <EvidenceDrawer
            report={report}
            nodeInventory={nodeInventory}
            deltaMap={deltaMap}
            selectedEntity={selectedEntity}
            setSelectedEntity={setSelectedEntity}
          />
        </div>
      </div>
    </div>
  );
}
