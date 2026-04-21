export type Severity = "critical" | "high" | "medium" | "low" | "normal" | "none";

export type Hotspot = {
  entity_id: string;
  node: string;
  interface: string;
  queue: number;
  severity: Severity;
  score: number;
  probable_cause: string;
  signals: {
    peak_buffer_occupancy_percent: number;
    tail_drop_pkts: number;
    red_drop_pkts: number;
    ecn_marked_pkts: number;
    in_resource_drops?: number;
    out_ecn_ce_marked_pkts?: number;
    fec_corrected_words?: number;
    fec_uncorrectable_words?: number;
    pfc_activity?: number;
  };
};

export type DeltaEntry = {
  entity_id: string;
  node: string;
  interface: string;
  queue: number;
  delta_running: Record<string, number>;
  delta_post: Record<string, number>;
  running_metrics: Record<string, number>;
};

export type RCAReport = {
  run_metadata: {
    generated_at: string;
    run_id: string;
    intent_name: string;
    src: string;
    dst: string;
    profile: string;
    nodes: string[];
  };
  summary: {
    primary_cause: string;
    confidence: number;
    severity: Severity;
    top_hotspot_node: string;
    top_hotspot_interface: string;
    top_hotspot_queue: number;
    top_hotspot_score: number;
    total_hotspots: number;
    severity_counts: Record<string, number>;
    contributing_factors: string[];
  };
  hotspots: Hotspot[];
  deltas: DeltaEntry[];
};

export type RCACaseListItem = {
  run_id: string;
  intent_name: string;
  profile: string;
  generated_at: string;
  primary_cause: string;
  severity: Severity;
  confidence: number;
};

export async function fetchCases(): Promise<RCACaseListItem[]> {
  const res = await fetch("/api/rca/cases");
  if (!res.ok) {
    throw new Error(`Failed to load cases: ${res.status}`);
  }
  const data = await res.json();
  return data.cases ?? [];
}

export async function fetchCase(runId: string): Promise<RCAReport> {
  const res = await fetch(`/api/rca/cases/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to load case ${runId}: ${res.status}`);
  }
  return res.json();
}
