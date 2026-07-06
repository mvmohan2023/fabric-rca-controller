const PROFILE_LABELS = {
  hotspot_congestion_qmon: "Hotspot Congestion Monitoring",
};

const INTENT_LABELS = {
  hotspot_validation: "Hotspot Validation",
};

const state = {
  cases: [],
  currentRunId: null,
  currentCase: null,
  filteredEntities: [],
  showAllCosHotspots: false,
};

const DEBUG_UI = false;

function debugLog(...args) {
  if (DEBUG_UI) {
    console.log(...args);
  }
}

const els = {
  runSelect: document.getElementById("runSelect"),
  searchInput: document.getElementById("searchInput"),
  entityList: document.getElementById("entityList"),

  heroTitle: document.getElementById("heroTitle"),
  heroSub: document.getElementById("heroSub"),
  badgeSeverity: document.getElementById("badgeSeverity"),
  badgeConfidence: document.getElementById("badgeConfidence"),

  summaryBlock: document.getElementById("summaryBlock"),
  engineeringInvestigationBlock: document.getElementById("engineeringInvestigationBlock"),
  metadataBlock: document.getElementById("metadataBlock"),
  rcaSummaryBlock: document.getElementById("rcaSummaryBlock"),

  statCause: document.getElementById("statCause"),
  statConfidence: document.getElementById("statConfidence"),
  statTopScore: document.getElementById("statTopScore"),
  statTotalHotspots: document.getElementById("statTotalHotspots"),

  queueRcaSummaryBlock: document.getElementById("queueRcaSummaryBlock"),
  rcaNarrativeBlock: document.getElementById("rcaNarrativeBlock"),
  hotspotInterpretationBlock: document.getElementById("hotspotInterpretationBlock"),
  cosHotspotsTable: document.getElementById("cosHotspotsTable"),

  eventsBlock: document.getElementById("eventsBlock"),
  hotspotsTable: document.getElementById("hotspotsTable"),
  severityBlock: document.getElementById("severityBlock"),
  factorsBlock: document.getElementById("factorsBlock"),
  evidenceBlock: document.getElementById("evidenceBlock"),
  selectedEntityHint: document.getElementById("selectedEntityHint"),

  interfaceDropHealthBlock: document.getElementById("interfaceDropHealthBlock"),
  trafficHealthBlock: document.getElementById("trafficHealthBlock"),

  trafficExecSummaryBlock: document.getElementById("trafficExecSummaryBlock"),
  congestionOriginAnalysisBlock: document.getElementById("congestionOriginAnalysisBlock"),
  worstRxPortsBlock: document.getElementById("worstRxPortsBlock"),
  trafficRecoveryBlock: document.getElementById("trafficRecoveryBlock"),
  roceSeqerrorFlowsBlock: document.getElementById("roceSeqerrorFlowsBlock"),
  rocePostSeqerrorFlowsBlock: document.getElementById("rocePostSeqerrorFlowsBlock"),
  trafficFabricCorrelationBlock: document.getElementById("trafficFabricCorrelationBlock"),

  topologyViewLink: document.getElementById("topologyViewLink"),

  ecmpRecoverySummary: document.getElementById("ecmpRecoverySummary"),
  ecmpRecoveryVerdict: document.getElementById("ecmpRecoveryVerdict"),
  ecmpRecoveryTable: document.getElementById("ecmpRecoveryTable"),
  ecmpRecoveryDetailPanel: document.getElementById("ecmpRecoveryDetailPanel"),
};

function safe(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatPct(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function formatListOfPorts(rows) {
  if (!Array.isArray(rows) || !rows.length) {
    return `<div class="empty-state">No port ranking available</div>`;
  }

  return `
    <table class="data-table ecmp-mini-table">
      <thead>
        <tr>
          <th>Interface</th>
          <th>Value</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td class="mono-text">${escapeHtml(safe(row.interface))}</td>
            <td>${escapeHtml(formatDecimal(row.value, 4))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function formatNumber(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toLocaleString();
}

function formatDecimal(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

function formatSpreadWithTolerance(target, degradedSurvivor) {
  const targetSpread = targetSpeedSurvivorSpread(target, degradedSurvivor);

  const spread = targetSpread
    ? targetSpread.spread
    : degradedSurvivor && degradedSurvivor.worst_survivor_spread_pct != null
      ? Number(degradedSurvivor.worst_survivor_spread_pct)
      : null;

  if (spread == null || Number.isNaN(spread)) return "-";

  const tolerance = degradedSurvivor && degradedSurvivor.tolerance_fraction != null
    ? Number(degradedSurvivor.tolerance_fraction)
    : 0.15;

  const spreadText = `${(spread * 100).toFixed(1)}%`;
  const toleranceText = `${(tolerance * 100).toFixed(1)}%`;
  const speedText = targetSpread ? ` (${targetSpread.speed} group)` : " (all survivor groups)";

  return spread > tolerance
    ? `${spreadText} ⚠ Exceeds ${toleranceText}${speedText}`
    : `${spreadText} within ${toleranceText}${speedText}`;
}

function formatSharePct(value, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${(n * 100).toFixed(digits)}%`;
}

function formatConfidence(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function formatUtcTimestamp(value) {
  if (!value) return "-";

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  const ss = String(d.getUTCSeconds()).padStart(2, "0");

  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss} UTC`;
}

function formatUtcShort(value) {
  if (!value) return "";

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;

  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");

  return `${yyyy}-${mm}-${dd} ${hh}:${mi} UTC`;
}

function displayProfile(profile) {
  return PROFILE_LABELS[profile] || profile || "-";
}

function displayIntent(intent) {
  if (!intent) return "-";
  if (INTENT_LABELS[intent]) return INTENT_LABELS[intent];
  return intent
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function severityClass(severity) {
  const s = String(severity || "").toLowerCase();
  if (["critical"].includes(s)) return "badge badge-critical";
  if (["high", "severe"].includes(s)) return "badge badge-high";
  if (["medium", "moderate"].includes(s)) return "badge badge-medium";
  if (["low"].includes(s)) return "badge badge-low";
  return "badge badge-normal";
}

function normalizeSeverity(severity) {
  const s = String(severity || "").toLowerCase();
  if (["critical", "high", "medium", "low"].includes(s)) return s;
  if (["warning", "warn", "moderate"].includes(s)) return "medium";
  return "low";
}

function yesNo(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "-";
}

function renderEmpty(container, message) {
  container.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function renderKeyValueList(container, items) {
  if (!items.length) {
    renderEmpty(container, "No data available");
    return;
  }

  container.innerHTML = items
    .map(
      ([key, value]) => `
        <div class="kv-row">
          <div class="kv-key">${escapeHtml(key)}</div>
          <div class="kv-value">${escapeHtml(value)}</div>
        </div>
      `
    )
    .join("");
}

function classificationBadge(classification) {
  const cls = String(classification || "");
  if (!cls) {
    return `<span class="cos-chip cos-chip-neutral">unknown</span>`;
  }

  if (
    cls === "localized-lossy-mcast-pressure" ||
    cls === "unexpected-taildrop-on-lossless" ||
    cls === "queue-without-explicit-scheduler" ||
    cls === "needs-manual-review"
  ) {
    return `<span class="cos-chip cos-chip-suspicious">${escapeHtml(cls)}</span>`;
  }

  if (cls === "expected-ecn-pressure" ||
    cls === "expected-transient-control-impact") {
    return `<span class="cos-chip cos-chip-expected">${escapeHtml(cls)}</span>`;
  }

  return `<span class="cos-chip cos-chip-neutral">${escapeHtml(cls)}</span>`;
}

function formatRatio(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(2);
}

function eventOutcomeBadge(value) {
  const v = String(value || "unknown");
  const lower = v.toLowerCase();

  if (lower.includes("persistent")) {
    return `<span class="cos-chip cos-chip-suspicious">${escapeHtml(v)}</span>`;
  }
  if (lower.includes("lingering") || lower.includes("recovering")) {
    return `<span class="cos-chip cos-chip-neutral">${escapeHtml(v)}</span>`;
  }
  if (lower.includes("transient") || lower.includes("expected")) {
    return `<span class="cos-chip cos-chip-expected">${escapeHtml(v)}</span>`;
  }
  return `<span class="cos-chip cos-chip-neutral">${escapeHtml(v)}</span>`;
}

function trendBadge(value) {
  const v = String(value || "unknown");
  const lower = v.toLowerCase();

  if (lower === "increasing") {
    return `<span class="cos-chip cos-chip-suspicious">Increasing</span>`;
  }
  if (lower === "flat" || lower === "mixed") {
    return `<span class="cos-chip cos-chip-neutral">${escapeHtml(v)}</span>`;
  }
  if (lower === "decreasing" || lower === "cleared") {
    return `<span class="cos-chip cos-chip-expected">${escapeHtml(v)}</span>`;
  }
  return `<span class="cos-chip cos-chip-neutral">${escapeHtml(v)}</span>`;
}

function buildPhaseSeries(item) {
  const preSeries = Array.isArray(item.pre_tail_baseline_series)
    ? item.pre_tail_baseline_series.map((v) => Number(v ?? 0))
    : [];

  const riseTail = Number(item.rise_tail_dropped_packets ?? 0);

  const postSeries = Array.isArray(item.post_tail_linger_series)
    ? item.post_tail_linger_series.map((v) => Number(v ?? 0))
    : [];

  const lingerTail = Number(item.linger_tail_dropped_packets ?? 0);

  if (preSeries.length > 0 && postSeries.length > 0) {
    return [...preSeries, riseTail, ...postSeries];
  }

  if (preSeries.length > 0 && postSeries.length === 0) {
    return [...preSeries, riseTail, lingerTail];
  }

  if (preSeries.length === 0 && postSeries.length > 0) {
    return [0, riseTail, ...postSeries];
  }

  return [0, riseTail, lingerTail];
}

function getFlatGraphHint(values) {
  if (!Array.isArray(values) || values.length < 2) return null;

  const nums = values
    .map((v) => Number(v || 0))
    .filter((v) => Number.isFinite(v));

  if (nums.length < 2) return null;

  const max = Math.max(...nums);
  const min = Math.min(...nums);
  const range = max - min;

  if (max === 0) return "No measurable variation captured in this window.";

  if ((range / max) < 0.03) {
    return "Graph appears flat because the variation is small relative to the overall scale. Use Rise, Linger, and Persistence Ratio for interpretation.";
  }

  return null;
}

function renderSparkline(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return `<div class="sparkline-empty">-</div>`;
  }

  const nums = values.map((v) => Number(v || 0));
  const max = Math.max(...nums, 1);
  const width = 120;
  const height = 32;
  const step = nums.length > 1 ? width / (nums.length - 1) : width;

  const points = nums.map((v, i) => {
    const x = i * step;
    const y = height - (v / max) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(" ");

  return `
    <svg class="sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function renderHotspotType(row) {
  if (row.is_suspicious) {
    return `<span class="cos-chip cos-chip-suspicious">Suspicious</span>`;
  }
  if (row.is_expected_ecn) {
    return `<span class="cos-chip cos-chip-expected">Expected ECN</span>`;
  }
  return `<span class="cos-chip cos-chip-neutral">Info</span>`;
}

function renderEngineeringVerdictCard(report) {
  const er = report.engineering_reasoning || {};
  const exec = er.executive_assessment || {};
  const traffic = er.traffic_assessment || {};
  const verdict = er.engineering_verdict || {};
  const origin = exec.congestion_origin_candidate || {};
  const eventR = er.event_reasoning || {};
  const ecmpR = er.ecmp_reasoning || {};
  const queueR = er.queue_reasoning || {};
  const intfR = er.interface_reasoning || {};
  const roceR = er.roce_reasoning || {};
  const causalityR = er.causality_reasoning || {};
  const confidenceRows = er.confidence_breakdown || [];
  
  if (!er || Object.keys(er).length === 0) {
    return "";
  }

  const eventTargets = (exec.event_targets || []).join(", ") || "N/A";

  const originText = origin.node
    ? `${origin.node} / ${origin.interface || "unknown"} / q${origin.queue ?? "unknown"}`
    : "N/A";

  const impact = (traffic.impact_signals || [])
    .map(s => {
      if (typeof s === "string") return s;
      return `${s.signal || "Signal"} (${s.severity || "info"}${s.value !== null && s.value !== undefined ? `: ${s.value}` : ""})`;
    })
    .join(", ") || "N/A";

  return `
    <div class="summary-item full-row" style="border-left: 4px solid #38bdf8;">
      <div class="summary-label">Engineering Verdict</div>
      <div class="summary-value big-status">${escapeHtml(verdict.confidence || exec.engineering_confidence || "N/A")}</div>
      <div class="summary-subtext" style="margin-top:8px;">
        ${escapeHtml(verdict.summary || "No engineering verdict available.")}
      </div>

      <div class="summary-grid summary-grid-2" style="margin-top:12px;">
        <div class="summary-item">
          <div class="summary-label">Event Target</div>
          <div class="summary-value">${escapeHtml(eventTargets)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Congestion Origin Candidate</div>
          <div class="summary-value">${escapeHtml(originText)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Victim RoCEv2 Flow</div>
          <div class="summary-value">${escapeHtml(traffic.victim_flow || exec.victim_flow || "N/A")}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">TX / RX</div>
          <div class="summary-value">${escapeHtml(traffic.tx_port || "N/A")} → ${escapeHtml(traffic.rx_port || "N/A")}</div>
        </div>
        <div class="summary-item full-row">
          <div class="summary-label">RoCEv2 Impact Signals</div>
          <div class="summary-value">${escapeHtml(impact)}</div>
        </div>
        <div class="summary-item full-row">
          <div class="summary-label">Traffic Interpretation</div>
          <div class="summary-value">${escapeHtml(traffic.interpretation || "N/A")}</div>
        </div>
        <div class="summary-item full-row">
          <div class="summary-label">Confidence Reason</div>
          <div class="summary-value">${escapeHtml(verdict.confidence_reason || "N/A")}</div>
        </div>
	<div class="summary-item full-row">
           <div class="summary-label">Most Likely Cause</div>
           <div class="summary-value">
             ${escapeHtml(causalityR.most_likely_cause || "N/A")}
        </div>
	<div class="summary-item full-row">
           <div class="summary-label">Confidence Breakdown</div>
           <div class="summary-value">
             ${confidenceRows.map(r =>
             `${r.component}: ${r.confidence} — ${r.reason}`
             ).map(escapeHtml).join("<br>")}
           </div>
         </div>
      </div>
    </div>
       `;
}

function renderEngineeringInvestigation(report) {
    const er = report.engineering_reasoning || {};

    return `
    <div class="stack-card">

        <div class="stack-card-header">
            🧠 Engineering Investigation Report
        </div>

        <div class="stack-card-body">

            ${renderEventReasoning(er.event_reasoning || {})}

            ${renderECMPReasoning(er.ecmp_reasoning || {})}

            ${renderQueueReasoning(er.queue_reasoning || {})}

            ${renderInterfaceReasoning(er.interface_reasoning || {})}

            ${renderRoCEReasoning(er.roce_reasoning || {})}
	    
	    ${renderEvidenceReasoning(er.evidence_reasoning || {})}

            ${renderCausalityReasoning(er.causality_reasoning || {})}

            ${renderConfidenceBreakdown(er.confidence_breakdown || [])}

            ${renderFinalEngineeringVerdict(er.engineering_verdict || {})}

        </div>

    </div>
    `;
}


function renderEventReasoning(event) {

    if (!event || Object.keys(event).length === 0)
        return "";

    return `
    <div class="stack-card">

        <div class="stack-card-header">
            🟢 Event Investigation
        </div>

        <div class="stack-card-body">

            <table class="table">

                <tr>
                    <th>Scenario</th>
                    <td>${escapeHtml(event.scenario || "N/A")}</td>
                </tr>

                <tr>
                    <th>Status</th>
                    <td>${escapeHtml(event.status || "N/A")}</td>
                </tr>

                <tr>
                    <th>Execution</th>
                    <td>${escapeHtml(event.execution || "N/A")}</td>
                </tr>

                <tr>
                    <th>Recovery</th>
                    <td>${escapeHtml(event.recovery || "N/A")}</td>
                </tr>

                <tr>
                    <th>Targets</th>
                    <td>${escapeHtml((event.targets || []).join(", "))}</td>
                </tr>

            </table>

            <p>
                ${escapeHtml(event.interpretation || "")}
            </p>

        </div>

    </div>
    `;
}


function renderSummary(report) {
  const summary = report.summary || {};
  const rootCause = report.root_cause || {};

  const totalHotspots = Number(summary.total_hotspots || 0);
  const hasHotspots = totalHotspots > 0;

  const contributing =
    Array.isArray(rootCause.contributing_factors) && rootCause.contributing_factors.length
      ? rootCause.contributing_factors.slice(0, 3)
      : [];

  const primaryCause = hasHotspots
    ? safe(summary.primary_cause)
    : "No significant hotspot detected";

  const confidenceText = hasHotspots
    ? formatConfidence(summary.confidence)
    : "N/A";

  const severityText = hasHotspots
    ? safe(summary.severity)
    : "Normal";

  const topHotspot = hasHotspots
    ? [
        safe(summary.top_hotspot_node),
        safe(summary.top_hotspot_interface),
        summary.top_hotspot_queue === undefined || summary.top_hotspot_queue === null
          ? "-"
          : `q${summary.top_hotspot_queue}`,
      ].join(" / ")
    : "None detected";

  const recommendedAction = hasHotspots
    ? `Investigate ${safe(summary.top_hotspot_node)} ${safe(summary.top_hotspot_interface)} q${safe(summary.top_hotspot_queue)} for persistent queue impact and CoS behavior.`
    : "No immediate RCA action needed.";

  const findingsHtml =
    hasHotspots && contributing.length
      ? contributing.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
      : `<li>No queue-level congestion hotspot was identified in the selected run.</li>`;
  
  els.summaryBlock.innerHTML = renderExecutiveSummary(report);

  if (els.engineeringInvestigationBlock) {
    els.engineeringInvestigationBlock.innerHTML = renderEngineeringInvestigation(report);
  }
}

function renderStatusBadge(status) {
    const s = (status || "").toUpperCase();

    if (s === "PASS")
        return `<span class="badge badge-success">PASS</span>`;

    if (s === "FAIL")
        return `<span class="badge badge-danger">FAIL</span>`;

    if (s === "MEDIUM")
        return `<span class="badge badge-warning">MEDIUM</span>`;

    return `<span class="badge badge-neutral">${escapeHtml(status)}</span>`;
}

function renderExecutiveSummary(report) {
  const er = report.engineering_reasoning || {};
  const eventR = er.event_reasoning || {};
  const ecmpR = er.ecmp_reasoning || {};
  const queueR = er.queue_reasoning || {};
  const roceR = er.roce_reasoning || {};
  const verdict = er.engineering_verdict || {};
  const causality = er.causality_reasoning || {};
  const scenario =
    (eventR.scenario || "N/A")
        .replaceAll("_"," ")
        .replace(/\b\w/g, c => c.toUpperCase());
  const eventStatus = eventR.status === "Recovered" ? "PASS" : "WARN";
  const ecmpStatus = ecmpR.regression_detected ? "FAIL" : "PASS";
  const queueStatus = queueR.discard_signals && queueR.discard_signals.length ? "FAIL" : "PASS";
  const roceStatus = roceR.impact_signals && roceR.impact_signals.length ? "FAIL" : "PASS";
  return `
    <div class="summary-grid summary-grid-4">
      <div class="summary-item">
        <div class="summary-label">Scenario</div>
        <div class="summary-value big-status">${escapeHtml(scenario)}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Event</div>
        <div class="summary-value big-status">${renderStatusBadge(eventStatus)}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">ECMP</div>
        <div class="summary-value big-status">${renderStatusBadge(ecmpStatus)}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Queue</div>
        <div class="summary-value big-status">${renderStatusBadge(queueStatus)}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">RoCE</div>
        <div class="summary-value big-status">${renderStatusBadge(roceStatus)}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Causality</div>
        <div class="summary-value big-status">${renderStatusBadge(causality.causality_confidence || "N/A")}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Overall</div>
        <div class="summary-value big-status">${escapeHtml(causality.most_likely_cause || "N/A")}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Confidence</div>
        <div class="summary-value big-status">${renderStatusBadge(verdict.confidence || "N/A")}</div>
      </div>

      <div class="summary-item full-row">
        <div class="summary-label">Final Verdict</div>
        <div class="summary-value">${escapeHtml(verdict.summary || "N/A")}</div>
      </div>
    </div>
  `;
}

function renderECMPReasoning(ecmp) {
  if (!ecmp || Object.keys(ecmp).length === 0) return "";

  const reasonCodes = (ecmp.reason_codes || []).join(", ") || "N/A";

  return `
    <div class="stack-card">
      <div class="stack-card-header">🟢 ECMP Investigation</div>
      <div class="stack-card-body">
        <table class="table">
          <tr><th>Analysis Status</th><td>${escapeHtml(ecmp.analysis_status || "N/A")}</td></tr>
          <tr><th>Targets</th><td>${escapeHtml(String(ecmp.target_count ?? "N/A"))}</td></tr>
          <tr><th>Expected</th><td>${escapeHtml(String(ecmp.expected_count ?? "N/A"))}</td></tr>
          <tr><th>Defect Candidates</th><td>${escapeHtml(String(ecmp.defect_candidate_count ?? "N/A"))}</td></tr>
          <tr><th>Abnormal</th><td>${escapeHtml(String(ecmp.abnormal_count ?? "N/A"))}</td></tr>
          <tr><th>Regression Detected</th><td>${escapeHtml(String(ecmp.regression_detected ?? "N/A"))}</td></tr>
          <tr><th>Reason Codes</th><td>${escapeHtml(reasonCodes)}</td></tr>
        </table>
        <p>${escapeHtml(ecmp.interpretation || "")}</p>
      </div>
    </div>
  `;
}
function renderQueueReasoning(queue) {
  if (!queue || Object.keys(queue).length === 0) return "";

  const origin = queue.origin || {};
  const discardSignals = queue.discard_signals || [];

  const discardText = discardSignals.length
    ? discardSignals.map(s => `${s.signal}: ${s.value}`).map(escapeHtml).join("<br>")
    : "N/A";

  return `
    <div class="stack-card">
      <div class="stack-card-header">🟠 Queue / Discard Investigation</div>
      <div class="stack-card-body">
        <table class="table">
          <tr><th>Origin</th><td>${escapeHtml(origin.node || "N/A")} / ${escapeHtml(origin.interface || "N/A")} / q${escapeHtml(String(origin.queue ?? "N/A"))}</td></tr>
          <tr><th>Classification</th><td>${escapeHtml(queue.classification || "N/A")}</td></tr>
	  <tr>
            <th>Classification Explanation</th>
            <td>${escapeHtml(queue.classification_explanation || "N/A")}</td>
         </tr>
         <tr>
            <th>Trend Interpretation</th>
            <td>${escapeHtml(queue.trend_interpretation || "N/A")}</td>
          </tr>
          <tr><th>Severity</th><td>${escapeHtml(queue.severity || "N/A")}</td></tr>
          <tr><th>Forwarding Class</th><td>${escapeHtml(queue.forwarding_class || "N/A")}</td></tr>
          <tr><th>Event Delta</th><td>${escapeHtml(queue.event_delta_classification || "N/A")}</td></tr>
          <tr><th>Tail Linger Trend</th><td>${escapeHtml(queue.tail_linger_trend || "N/A")}</td></tr>
          <tr><th>Recovery Ratio</th><td>${escapeHtml(String(queue.recovery_ratio_tail ?? "N/A"))}</td></tr>
          <tr><th>Discard / Queue Signals</th><td>${discardText}</td></tr>
        </table>
        <p>${escapeHtml(queue.interpretation || "")}</p>
      </div>
    </div>
  `;
}
function renderEvidenceReasoning(evidence) {
  if (!evidence || !evidence.steps || evidence.steps.length === 0) return "";

  const rows = evidence.steps.map(s => `
    <div class="timeline-item">
      <div class="timeline-status">${escapeHtml(s.status || "INFO")}</div>
      <div class="timeline-content">
        <div class="summary-label">${escapeHtml(s.title || "Evidence Step")}</div>
        <div class="summary-value">${escapeHtml(s.evidence || "N/A")}</div>
      </div>
    </div>
  `).join("");

  return `
    <div class="stack-card">
      <div class="stack-card-header">🧩 Evidence Reasoning Chain</div>
      <div class="stack-card-body">
        ${rows}
      </div>
    </div>
  `;
}

function renderInterfaceReasoning(intf) {
  if (!intf || Object.keys(intf).length === 0) return "";

  const origin = intf.origin_interface || {};
  const signals = intf.physical_signals || [];

  const signalRows = signals.length
    ? signals.map(s => `
        <tr>
          <td>${escapeHtml(s.signal || "N/A")}</td>
          <td>${escapeHtml(String(s.value ?? "N/A"))}</td>
        </tr>
      `).join("")
    : `<tr><td colspan="2">N/A</td></tr>`;
  
  return `
    <div class="stack-card">
      <div class="stack-card-header">⚪ Interface / Physical Investigation</div>
      <div class="stack-card-body">
        <table class="table">
          <tr>
            <th>Origin Interface</th>
            <td>${escapeHtml(origin.node || "N/A")} / ${escapeHtml(origin.interface || "N/A")}</td>
          </tr>
          <tr>
            <th>Matched Rows</th>
            <td>${escapeHtml(String(intf.matched_rows ?? "N/A"))}</td>
          </tr>
          <tr>
            <th>Telemetry Status</th>
            <td>${escapeHtml(intf.telemetry_status || "N/A")}</td>
          </tr>
        </table>

        <table class="table">
          <thead>
            <tr>
              <th>Physical / Interface Signal</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            ${signalRows}
          </tbody>
        </table>

        <p>${escapeHtml(intf.interpretation || "")}</p>
      </div>
    </div>
  `;
}
function renderRoCEReasoning(roce) {
  if (!roce || Object.keys(roce).length === 0) return "";

  const signals = roce.impact_signals || [];

  const signalRows = signals.length
    ? signals.map(s => `
        <tr>
          <td>${escapeHtml(s.signal || "N/A")}</td>
          <td>${escapeHtml(s.severity || "N/A")}</td>
          <td>${escapeHtml(String(s.value ?? "N/A"))}</td>
        </tr>
      `).join("")
    : `<tr><td colspan="3">N/A</td></tr>`;

  return `
    <div class="stack-card">
      <div class="stack-card-header">🔴 RoCEv2 Investigation</div>
      <div class="stack-card-body">
        <table class="table">
          <tr><th>Victim Flow</th><td>${escapeHtml(roce.victim_flow || "N/A")}</td></tr>
          <tr><th>TX Port</th><td>${escapeHtml(roce.tx_port || "N/A")}</td></tr>
          <tr><th>RX Port</th><td>${escapeHtml(roce.rx_port || "N/A")}</td></tr>
        </table>

        <table class="table">
          <thead>
            <tr>
              <th>Signal</th>
              <th>Severity</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            ${signalRows}
          </tbody>
        </table>

        <p>${escapeHtml(roce.interpretation || "")}</p>
      </div>
    </div>
  `;
}
function renderCausalityReasoning(causality) {
  if (!causality || Object.keys(causality).length === 0) return "";

  const facts = causality.observed_facts || [];
  const alternatives = causality.alternative_explanations || [];

  const factRows = facts.length
    ? facts.map(f => `<li>${escapeHtml(f)}</li>`).join("")
    : "<li>N/A</li>";

  const altRows = alternatives.length
    ? alternatives.map(a => `
        <tr>
          <td>${escapeHtml(a.hypothesis || "N/A")}</td>
          <td>${escapeHtml(a.assessment || "N/A")}</td>
          <td>${escapeHtml(a.reason || "N/A")}</td>
        </tr>
      `).join("")
    : `<tr><td colspan="3">N/A</td></tr>`;

  return `
    <div class="stack-card">
      <div class="stack-card-header">🧠 Causality Analysis</div>
      <div class="stack-card-body">
        <table class="table">
          <tr><th>Most Likely Cause</th><td>${escapeHtml(causality.most_likely_cause || "N/A")}</td></tr>
          <tr><th>Causality Confidence</th><td>${escapeHtml(causality.causality_confidence || "N/A")}</td></tr>
        </table>

        <div class="summary-label">Observed Facts</div>
        <ul>
          ${factRows}
        </ul>

        <div class="summary-label">Alternative Explanations</div>
        <table class="table">
          <thead>
            <tr>
              <th>Hypothesis</th>
              <th>Assessment</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            ${altRows}
          </tbody>
        </table>
      </div>
    </div>
  `;
}
function renderConfidenceBreakdown(rows) {
  if (!rows || rows.length === 0) return "";

  const body = rows.map(r => `
    <tr>
      <td>${escapeHtml(r.component || "N/A")}</td>
      <td>${escapeHtml(r.confidence || "N/A")}</td>
      <td>${escapeHtml(r.reason || "N/A")}</td>
    </tr>
  `).join("");

  return `
    <div class="stack-card">
      <div class="stack-card-header">📊 Confidence Breakdown</div>
      <div class="stack-card-body">
        <table class="table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Confidence</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            ${body}
          </tbody>
        </table>
      </div>
    </div>
  `;
}
function renderFinalEngineeringVerdict(verdict) {
  if (!verdict || Object.keys(verdict).length === 0) return "";

  return `
    <div class="stack-card">
      <div class="stack-card-header">🏁 Final Engineering Verdict</div>
      <div class="stack-card-body">
        <table class="table">
          <tr><th>Confidence</th><td>${escapeHtml(verdict.confidence || "N/A")}</td></tr>
          <tr><th>Confidence Reason</th><td>${escapeHtml(verdict.confidence_reason || "N/A")}</td></tr>
        </table>
        <p>${escapeHtml(verdict.summary || "No final engineering verdict available.")}</p>
      </div>
    </div>
  `;
}

function renderMetadata(report) {
  const meta = report.run_metadata || {};
  const nodes = Array.isArray(meta.nodes) ? meta.nodes.join(", ") : safe(meta.nodes);

  renderKeyValueList(els.metadataBlock, [
    ["Generated", formatUtcTimestamp(meta.generated_at)],
    ["Run ID", safe(meta.run_id)],
    ["Intent", displayIntent(meta.intent_name)],
    ["Source", safe(meta.src)],
    ["Destination", safe(meta.dst)],
    ["Profile", displayProfile(meta.profile)],
    ["Nodes", nodes || "-"],
  ]);
}

function renderStats(report) {
  const summary = report.summary || {};
  const meta = report.run_metadata || {};

  const totalHotspots = Number(summary.total_hotspots || 0);
  const hasHotspots = totalHotspots > 0;

  els.statCause.textContent = hasHotspots
    ? safe(summary.primary_cause)
    : "No hotspot";

  els.statConfidence.textContent = hasHotspots
    ? formatConfidence(summary.confidence)
    : "N/A";

  els.statTopScore.textContent = hasHotspots
    ? formatDecimal(summary.top_hotspot_score || 0, 2)
    : "N/A";

  els.statTotalHotspots.textContent = formatNumber(totalHotspots);

  els.badgeSeverity.className = severityClass(hasHotspots ? summary.severity : "normal");
  els.badgeSeverity.textContent = `Severity: ${hasHotspots ? safe(summary.severity) : "normal"}`;

  els.badgeConfidence.className = "badge badge-neutral";
  els.badgeConfidence.textContent = `Confidence: ${hasHotspots ? formatConfidence(summary.confidence) : "N/A"}`;

  els.heroTitle.textContent = `${safe(meta.run_id)} — ${displayIntent(meta.intent_name)}`;
  els.heroSub.textContent = `${safe(meta.src)} → ${safe(meta.dst)} | ${displayProfile(meta.profile)} | ${formatUtcTimestamp(meta.generated_at)}`;
}

function renderQueueRcaSummary(report) {
  const summary = report.summary || {};
  const cosHealth = report.cos_health || {};

  const cards = [
    {
      label: "Suspicious CoS Hotspots",
      value: formatNumber(summary.suspicious_cos_hotspots || 0),
      subtext: "Needs RCA focus",
    },
    {
      label: "Expected ECN Hotspots",
      value: formatNumber(summary.expected_ecn_hotspots || 0),
      subtext: "Expected regulated congestion",
    },
    {
      label: "Top Affected Queue",
      value: safe(summary.top_affected_queue),
      subtext: "Highest interpreted queue",
    },
    {
      label: "Queue RCA Summary",
      value: safe(cosHealth.queue_rca_summary || summary.queue_rca_summary, "N/A"),
      subtext: "Suspicious vs expected split",
    },
  ];

  els.queueRcaSummaryBlock.innerHTML = `
    <div class="summary-grid summary-grid-2">
      ${cards.map((card) => `
        <div class="summary-item">
          <div class="summary-label">${escapeHtml(card.label)}</div>
          <div class="summary-value summary-value-large">${escapeHtml(card.value)}</div>
          <div class="summary-subtext">${escapeHtml(card.subtext)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderRcaNarrative(report) {
  const cosHealth = report.cos_health || {};
  const text = cosHealth.rca_interpretation || report.summary?.rca_interpretation;

  if (!text) {
    renderEmpty(els.rcaNarrativeBlock, "No CoS hotspot interpretation available");
    return;
  }

  els.rcaNarrativeBlock.innerHTML = `
    <div class="narrative-box">
      <div class="narrative-title">RCA Interpretation</div>
      <div class="narrative-body">${escapeHtml(text)}</div>
      <div class="summary-subtext" style="margin-top:8px;">
        Suspicious = queue behavior beyond normal ECN-regulated congestion.
        Expected ECN = congestion primarily managed through ECN marking and likely expected under load.
      </div>
    </div>
  `;
}

function renderHotspotInterpretation(report) {
  const top = report.cos_health?.top_cos_hotspot || {};
  const text = report.cos_health?.hotspot_interpretation || report.summary?.hotspot_interpretation;

  if (!top || !Object.keys(top).length) {
    renderEmpty(els.hotspotInterpretationBlock, "No hotspot interpretation available");
    return;
  }

  els.hotspotInterpretationBlock.innerHTML = `
    <div class="interpretation-wrap">
      <div class="interpretation-header">
        <div class="interpretation-title">Primary Queue Interpretation</div>
        <div>${classificationBadge(top.classification)}</div>
      </div>

      <div class="summary-subtext" style="margin-bottom:12px;">
        ${escapeHtml(safe(text, "No interpretation text available"))}
      </div>

      <div class="summary-grid summary-grid-2">
        <div class="summary-item">
          <div class="summary-label">Node / Interface / Queue</div>
          <div class="summary-value big-status">${escapeHtml(safe(top.node))} / <span class="mono-text">${escapeHtml(safe(top.interface))}</span> / q${escapeHtml(safe(top.queue))}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Forwarding Class</div>
          <div class="summary-value big-status">${escapeHtml(safe(top.forwarding_class))}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Confidence</div>
          <div class="summary-value big-status">${escapeHtml(formatConfidence(top.classification_confidence))}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Probable Cause</div>
          <div class="summary-value big-status">${escapeHtml(safe(top.probable_cause))}</div>
        </div>
      </div>
    </div>
  `;
}
function renderEvents(report) {
  const events = report.events || [];

  if (!events.length) {
    renderEmpty(els.eventsBlock, "No trigger events recorded");
    return;
  }

  els.eventsBlock.innerHTML = events
    .map((event) => {
      const details = event.details || {};
      return `
        <div class="stack-card">
          <div class="stack-card-title">${escapeHtml(safe(event.event_name))}</div>
          <div class="stack-card-meta">
            <span><strong>Type:</strong> ${escapeHtml(safe(event.event_type))}</span>
            <span><strong>Status:</strong> ${escapeHtml(safe(event.status))}</span>
          </div>
          <div class="stack-card-meta">
            <span><strong>Target:</strong> ${escapeHtml(safe(event.target_node))} / ${escapeHtml(safe(event.target_interface))}</span>
            <span><strong>Time:</strong> ${escapeHtml(formatUtcTimestamp(event.trigger_time))}</span>
          </div>
          <div class="stack-card-body">${escapeHtml(safe(event.summary))}</div>
          <details class="details-block">
            <summary>View execution details</summary>
            <div class="details-grid">
              <div><strong>Event Run ID:</strong> ${escapeHtml(safe(details.run_id))}</div>
              <div><strong>Iteration:</strong> ${escapeHtml(safe(details.iteration))}</div>
              <div><strong>Mode:</strong> ${escapeHtml(safe(details.stress_mode))}</div>
              <div><strong>Target Host:</strong> ${escapeHtml(safe(details.target_host))}</div>
              <div><strong>Disable Status:</strong> ${escapeHtml(safe(details.disable_status))}</div>
              <div><strong>Enable Status:</strong> ${escapeHtml(safe(details.enable_status))}</div>
              <div class="full-row"><strong>Disable Command:</strong> <code>${escapeHtml(safe(details.disable_command))}</code></div>
              <div class="full-row"><strong>Enable Command:</strong> <code>${escapeHtml(safe(details.enable_command))}</code></div>
            </div>
          </details>
        </div>
      `;
    })
    .join("");
}

function renderHotspots(report) {
  const hotspots = Array.isArray(report.hotspots) ? report.hotspots.slice(0, 3) : [];
  const total = Number(report.summary?.total_queue_hotspots_detected || report.summary?.total_hotspots || 0);

  if (!hotspots.length) {
    renderEmpty(els.hotspotsTable, "No hotspots available");
    return;
  }

  els.hotspotsTable.innerHTML = `
    <div class="table-note">
      Showing top 3 hotspot rows. Total queue hotspots detected: <strong>${escapeHtml(formatNumber(total))}</strong>.
      Use the CoS-correlated hotspot table below for interpreted RCA focus.
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Node</th>
          <th>Interface</th>
          <th>Queue</th>
          <th>Severity</th>
          <th>Score</th>
          <th>Cause</th>
        </tr>
      </thead>
      <tbody>
        ${hotspots
          .map(
            (h) => `
              <tr>
                <td>${escapeHtml(safe(h.node))}</td>
                <td class="mono-text">${escapeHtml(safe(h.interface))}</td>
                <td>${escapeHtml(safe(h.queue))}</td>
                <td>${escapeHtml(safe(h.severity))}</td>
                <td>${escapeHtml(formatDecimal(h.score || 0, 2))}</td>
                <td>${escapeHtml(safe(h.probable_cause))}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function getCosHotspotRows(report) {
  const cosHealth = report.cos_health || {};
  if (Array.isArray(cosHealth.all_hotspots) && cosHealth.all_hotspots.length) {
    return cosHealth.all_hotspots;
  }
  if (Array.isArray(cosHealth.hotspots) && cosHealth.hotspots.length) {
    return cosHealth.hotspots;
  }
  if (Array.isArray(cosHealth.top_hotspots) && cosHealth.top_hotspots.length) {
    return cosHealth.top_hotspots;
  }
  return [];
}

function renderCosHotspots(report) {
  const rows = getCosHotspotRows(report);
  const cosHealth = report.cos_health || null;

  if (!cosHealth) {
    renderEmpty(els.cosHotspotsTable, "CoS analysis was not available for this run");
    return;
  }

  if (!rows.length) {
    renderEmpty(els.cosHotspotsTable, "CoS analysis completed, but no correlated hotspots were detected");
    return;
  }

  const visibleRows = state.showAllCosHotspots ? rows : rows.slice(0, 10);

  els.cosHotspotsTable.innerHTML = `
    <div class="table-note">
      Showing <strong>${escapeHtml(formatNumber(visibleRows.length))}</strong> of
      <strong>${escapeHtml(formatNumber(rows.length))}</strong> CoS hotspot entries.
    </div>

    ${rows.length > 10 ? `
      <div class="table-note" style="margin-top:8px;">
        <button id="toggleCosHotspotsBtn" class="ghost-btn">
          ${state.showAllCosHotspots ? "Show less" : `Show all (${rows.length})`}
        </button>
      </div>
    ` : ""}

    <table class="data-table cos-table">
      <thead>
        <tr>
          <th>#</th>
          <th>Node</th>
          <th>Interface</th>
          <th>Queue</th>
          <th>FC</th>
          <th>Classification</th>
          <th>Event Outcome</th>
          <th>Trend</th>
          <th>Persistence</th>
          <th>Rise</th>
          <th>Linger</th>
          <th>Severity</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        ${visibleRows.map((r, index) => {
          const suspicious = !!r.is_suspicious;
          const expected = !!r.is_expected_ecn;
          const rowClass = suspicious ? "row-suspicious" : expected ? "row-expected" : "";

          return `
            <tr class="${rowClass}">
              <td>${index + 1}</td>
              <td>${escapeHtml(safe(r.node))}</td>
              <td class="mono-text">${escapeHtml(safe(r.interface))}</td>
              <td>${escapeHtml(safe(r.queue))}</td>
              <td>${escapeHtml(safe(r.forwarding_class))}</td>
              <td>${classificationBadge(r.classification)}</td>
              <td>${eventOutcomeBadge(r.event_delta_classification)}</td>
              <td>${trendBadge(r.tail_linger_trend)}</td>
              <td>${escapeHtml(formatRatio(r.recovery_ratio_tail))}</td>
              <td>${escapeHtml(formatNumber(r.rise_tail_dropped_packets))}</td>
              <td>${escapeHtml(formatNumber(r.linger_tail_dropped_packets))}</td>
              <td><span class="badge badge-${normalizeSeverity(r.severity)}">${escapeHtml(safe(r.severity))}</span></td>
              <td>${escapeHtml(formatConfidence(r.classification_confidence))}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;

  const toggleBtn = document.getElementById("toggleCosHotspotsBtn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      state.showAllCosHotspots = !state.showAllCosHotspots;
      renderCosHotspots(report);
    });
  }
}

function renderEcmpRecovery(view) {
  if (!els.ecmpRecoverySummary || !els.ecmpRecoveryVerdict || !els.ecmpRecoveryTable) {
    return;
  }

  if (!view) {
    els.ecmpRecoverySummary.innerHTML = `<div class="empty-state">No ECMP recovery data available</div>`;
    els.ecmpRecoveryVerdict.innerHTML = "";
    els.ecmpRecoveryTable.innerHTML = "";
    if (els.ecmpRecoveryDetailPanel) {
      els.ecmpRecoveryDetailPanel.innerHTML = "";
    }
    window._ecmpTargets = [];
    return;
  }

  const summary = view.summary || {};
  const targets = Array.isArray(view.targets) ? view.targets : [];

  els.ecmpRecoverySummary.innerHTML = `
    <div class="summary-grid summary-grid-4">
      <div class="summary-item">
        <div class="summary-label">Analysis Status</div>
        <div class="summary-value big-status">${escapeHtml(ecmpLabel("analysis_status", summary.analysis_status))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Targets</div>
        <div class="summary-value big-status">${escapeHtml(String(summary.target_count || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Expected</div>
        <div class="summary-value big-status">${escapeHtml(String(summary.expected_count || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Defect Candidates</div>
        <div class="summary-value big-status">${escapeHtml(String(summary.defect_candidate_count || 0))}</div>
      </div>
    </div>
  `;

  const verdictText = buildEcmpVerdictText(summary);
  els.ecmpRecoveryVerdict.innerHTML = `
    <div class="stack-card ecmp-verdict-card">
      <div class="stack-card-body">${escapeHtml(verdictText)}</div>
    </div>
  `;

  if (!targets.length) {
    els.ecmpRecoveryTable.innerHTML = `<div class="empty-state">No ECMP target rows available</div>`;
    if (els.ecmpRecoveryDetailPanel) {
      els.ecmpRecoveryDetailPanel.innerHTML = "";
    }
    window._ecmpTargets = [];
    return;
  }

  const sortedTargets = [...targets].sort((a, b) => {
    const rankDiff = ecmpVerdictRank(b.recovery_verdict) - ecmpVerdictRank(a.recovery_verdict);
    if (rankDiff !== 0) return rankDiff;
    return String(a.target_id || "").localeCompare(String(b.target_id || ""));
  });

  const groupSummaryText = safe(summary.group_summary_text || "");
  const groupReasonCodes = summary.group_reason_codes || [];
  
  els.ecmpRecoveryTable.innerHTML = `
    ${groupSummaryText ? `
      <div class="rca-summary-card">
        <div class="section-subtitle">ECMP Group Summary</div>
        <div class="summary-text">${escapeHtml(groupSummaryText)}</div>
        ${
          groupReasonCodes.length
            ? `<ul class="reason-code-list">
                ${groupReasonCodes.map(code => `<li>${escapeHtml(ecmpGroupReasonText(code))}</li>`).join("")}
              </ul>`
            : ""
        }
      </div>
    ` : ""}
  
    <table class="data-table">
      <thead>
        <tr>
          <th>Target</th>
          <th>Port Speed</th>
          <th>Baseline</th>
          <th>Recovery</th>
          <th>Speed Weighting</th>
          <th>Delta</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        ${sortedTargets.map((t, idx) => `
          <tr class="clickable-row ${ecmpRowClass(t.recovery_verdict)}" data-ecmp-index="${idx}">
	    <td class="mono-text">${escapeHtml(ecmpDisplayTarget(t.target_id))}</td>
            <td>${escapeHtml(safe(t.target_port_speed_label || "-"))}</td>
	    <td>${escapeHtml(ecmpBaselineLabel(t))}</td>
            <td>${escapeHtml(ecmpLabel("recovery_convergence_state", t.recovery_convergence_state))}</td>
            <td>${escapeHtml(ecmpLabel("speed_alignment_state", t.speed_alignment_state))}</td>
            <td>${escapeHtml(ecmpLabel("delta_outcome", t.delta_outcome))}</td>
            <td>${ecmpVerdictBadge(t.recovery_verdict)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  window._ecmpTargets = sortedTargets;

  els.ecmpRecoveryTable.querySelectorAll("[data-ecmp-index]").forEach((row) => {
    row.addEventListener("click", () => {
      const idx = Number(row.getAttribute("data-ecmp-index"));
      showEcmpDetail(idx);
    });
  });

  if (els.ecmpRecoveryDetailPanel) {
    els.ecmpRecoveryDetailPanel.innerHTML = "";
  }
}

function degradedStateBadge(state) {
  if (state === "pass") return "🟢 PASS";
  if (state === "warn") return "🟡 WARN";
  if (state === "fail") return "🔴 FAIL";
  return "⚪ UNKNOWN";
}

function ecmpDisplayTarget(targetId) {
  return String(targetId || "").replace(/~/g, ":");
}

function ecmpStatusBadge(value, label) {
  const raw = String(value || "").toLowerCase();
  const text = label || value || "-";

  let cls = "verdict-neutral";

  if (["pass", "converged", "no_event_regression", "expected", "healthy"].includes(raw)) {
    cls = "verdict-pass";
  } else if (["warn", "watch", "partial", "unchanged", "not_applicable", "none"].includes(raw)) {
    cls = "verdict-watch";
  } else if (["fail", "failed", "degraded", "worsened_vs_baseline", "defect_candidate", "abnormal"].includes(raw)) {
    cls = "verdict-fail";
  } else if (["unknown", ""].includes(raw)) {
    cls = "verdict-neutral";
  }

  return `<span class="verdict-badge ${cls}">${escapeHtml(text)}</span>`;
}

function ecmpTargetSummaryBanner(target, degradedState, degradedReason) {
  const verdict = String(target.recovery_verdict || "").toLowerCase();

  if (verdict === "no_event_regression" && degradedState === "pass") {
    return `
      <div class="rca-banner rca-banner-pass">
        🟢 Healthy: No event-induced ECMP regression detected. ${escapeHtml(degradedReason)}
      </div>
    `;
  }

  if (verdict === "no_event_regression" && degradedState === "warn") {
    return `
      <div class="rca-banner rca-banner-warn">
        🟡 Degraded hold warning: No event-induced ECMP regression detected, but ${escapeHtml(degradedReason)}
      </div>
    `;
  }

  if (verdict === "defect_candidate" || degradedState === "fail") {
    return `
      <div class="rca-banner rca-banner-fail">
        🔴 Action required: ECMP recovery or degraded hold behavior indicates a defect candidate.
      </div>
    `;
  }

  return `
    <div class="rca-banner rca-banner-neutral">
      ⚪ ECMP analysis completed. Review detailed RCA fields below.
    </div>
  `;
}

function degradedReasonLabel(reason, degradedSurvivor) {
  const spread = degradedSurvivor && degradedSurvivor.worst_survivor_spread_pct != null
    ? `${(Number(degradedSurvivor.worst_survivor_spread_pct) * 100).toFixed(1)}%`
    : null;

  const tolerance = degradedSurvivor && degradedSurvivor.tolerance_fraction != null
    ? `${(Number(degradedSurvivor.tolerance_fraction) * 100).toFixed(1)}%`
    : "15.0%";

  const map = {
    survivor_members_imbalanced: spread
      ? `Traffic shifted successfully, but survivor spread exceeded tolerance (${spread} > ${tolerance})`
      : "Traffic shifted successfully, but survivor spread exceeded configured tolerance",
    no_degraded_share_data: "No degraded-state telemetry available",
    no_disabled_members_identified: "Unable to identify disabled ECMP members",
    no_surviving_members_carried_traffic: "Traffic did not redistribute to surviving members",
    disabled_members_still_carry_traffic: "Disabled members continued carrying traffic",
    traffic_did_not_shift_to_survivors: "Traffic failed to shift to surviving members",
    surviving_members_carried_degraded_traffic_within_tolerance:
      "Traffic redistributed successfully within tolerance",
    insufficient_data: "Insufficient degraded-state validation data",
  };

  return map[reason] || reason || "-";
}
function targetDegradedState(target, degradedSurvivor) {
  const targetSpread = targetSpeedSurvivorSpread(target, degradedSurvivor);

  if (!targetSpread) {
    return degradedSurvivor.verdict || target.degraded_state_balance || "unknown";
  }

  const tolerance = degradedSurvivor && degradedSurvivor.tolerance_fraction != null
    ? Number(degradedSurvivor.tolerance_fraction)
    : 0.15;

  return targetSpread.spread > tolerance ? "warn" : "pass";
}

function targetDegradedReason(target, degradedSurvivor) {
  const targetSpread = targetSpeedSurvivorSpread(target, degradedSurvivor);

  if (!targetSpread) {
    return degradedReasonLabel(
      degradedSurvivor.reason || target.degraded_state_reason,
      degradedSurvivor
    );
  }

  const tolerance = degradedSurvivor && degradedSurvivor.tolerance_fraction != null
    ? Number(degradedSurvivor.tolerance_fraction)
    : 0.15;

  const spreadText = `${(targetSpread.spread * 100).toFixed(1)}%`;
  const toleranceText = `${(tolerance * 100).toFixed(1)}%`;

  if (targetSpread.spread > tolerance) {
    return `Traffic shifted successfully, but ${targetSpread.speed} survivor spread exceeded tolerance (${spreadText} > ${toleranceText})`;
  }

  return `Traffic shifted successfully; ${targetSpread.speed} survivor spread is within tolerance (${spreadText} <= ${toleranceText})`;
}

function showEcmpDetail(index) {
  if (!els.ecmpRecoveryDetailPanel) return;

  const target = (window._ecmpTargets || [])[index];

  const raw = target.raw_report || {};

  const degradedSurvivor =
    target.degraded_survivor_validation ||
    raw.degraded_survivor_validation ||
    {};
  
  const degradedState = targetDegradedState(target, degradedSurvivor);
  const degradedReason = targetDegradedReason(target, degradedSurvivor);

  if (!target) {
    els.ecmpRecoveryDetailPanel.innerHTML = "";
    return;
  }

  const reasons = Array.isArray(target.reason_codes) ? target.reason_codes : [];
  els.ecmpRecoveryDetailPanel.innerHTML = `
    <div class="evidence-grid">
      <div class="evidence-card full-width">
        <h4>ECMP Target Detail</h4>
	${ecmpTargetSummaryBanner(target, degradedState, degradedReason)}
        <div class="summary-grid summary-grid-3">
          <div class="summary-item">
            <div class="summary-label">Target</div>
            <div class="summary-value mono-text">${escapeHtml(ecmpDisplayTarget(target.target_id))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Verdict</div>
            <div class="summary-value big-status">${ecmpVerdictBadge(target.recovery_verdict)}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Confidence</div>
            <div class="summary-value big-status">${escapeHtml(safe(target.confidence))}</div>
          </div>
  
          <div class="summary-item">
            <div class="summary-label">Analysis Status</div>
            <div class="summary-value big-status">${escapeHtml(ecmpLabel("analysis_status", target.analysis_status))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Baseline</div>
	    <div class="summary-value big-status">${escapeHtml(ecmpBaselineLabel(target))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Recovery</div>
            <div class="summary-value big-status">${ecmpStatusBadge(target.recovery_convergence_state, ecmpLabel("recovery_convergence_state", target.recovery_convergence_state))}</div>
          </div>
  
          <div class="summary-item">
            <div class="summary-label">Speed Weighting</div>
            <div class="summary-value big-status">${ecmpStatusBadge(target.speed_alignment_state, ecmpLabel("speed_alignment_state", target.speed_alignment_state))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Dominant Port State</div>
            <div class="summary-value big-status">${escapeHtml(ecmpLabel("dominant_port_state", target.dominant_port_state))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Delta Outcome</div>
            <div class="summary-value big-status">${ecmpStatusBadge(target.delta_outcome, ecmpLabel("delta_outcome", target.delta_outcome))}</div>
          </div>
  	  <div class="summary-item">
            <div class="summary-label">Degraded Hold Validation</div>
            <div class="summary-value big-status">
             ${degradedStateBadge(degradedState)}
             </div>
           </div>
           <div class="summary-item">
             <div class="summary-label">Degraded Survivor Reason</div>
             <div class="summary-value mono-text">
	       ${escapeHtml(degradedReason)}
             </div>
           </div>
	   <div class="summary-item">
            <div class="summary-label">Survivor Members Share</div>
            <div class="summary-value">
	      ${formatSharePct(degradedSurvivor.survivor_share_pct, 1)}
            </div>
          </div>
          
          <div class="summary-item">
            <div class="summary-label">Disabled Members Residual Share</div>
            <div class="summary-value">
	      ${formatSharePct(degradedSurvivor.disabled_share_pct, 1)}
            </div>
          </div>
          
          <div class="summary-item">
            <div class="summary-label">Worst Survivor Spread</div>
            <div class="summary-value">
	      ${escapeHtml(formatSpreadWithTolerance(target, degradedSurvivor))}
            </div>
          </div>
          <div class="summary-item full-row">
	    <div class="summary-label">Capacity-Weighted Reference (Not Used)</div>
            <div class="summary-value mono-text">${escapeHtml(formatShareMap(target.expected_group_shares))}</div>
          </div>
          <div class="summary-item full-row">
	    <div class="summary-label">Observed Distribution — Baseline</div>
            <div class="summary-value mono-text">${escapeHtml(formatShareMap(target.baseline_group_shares))}</div>
          </div>
          <div class="summary-item full-row">
	    <div class="summary-label">Observed Distribution — Recovery</div>
            <div class="summary-value mono-text">${escapeHtml(formatShareMap(target.recovery_group_shares))}</div>
          </div>
  
          <div class="summary-item full-row">
            <div class="summary-label">Member Pressure Summary</div>
            <div class="summary-value big-status">${escapeHtml(ecmpMemberPressureLabel(target.member_pressure_summary))}</div>
          </div>

        </div>
      </div>
      ${renderMixedSpeedSpecValidationFromTarget(target)}
      ${renderDualDistributionValidation(target)}
      <div class="evidence-card full-width">
        <h4>Same-Speed Fairness — Baseline</h4>
        ${renderSameSpeedGroupTable(target.baseline_same_speed_group_view || [])}
      </div>
      <div class="evidence-card full-width">
        <h4>Same-Speed Fairness — Recovery</h4>
        ${renderSameSpeedGroupTable(target.recovery_same_speed_group_view || [])}
      </div>
      ${renderSameSpeedGroupMembers(target.baseline_same_speed_group_view || [], "Baseline")}
      ${renderSameSpeedGroupMembers(target.recovery_same_speed_group_view || [], "Recovery")}
      <div class="evidence-card full-width">
        <h4>Reason Codes</h4>
        ${
          reasons.length
            ? `<ul class="compact-list">${reasons.map((r) => `<li>${escapeHtml(ecmpReasonText ? ecmpReasonText(r) : r)}</li>`).join("")}</ul>`
            : `<div class="empty-state">No reason codes available</div>`
        }
      </div>
    </div>
  `;
}
function ecmpMemberPressureLabel(value) {
  const map = {
    no_member_pressure_evidence: "No congestion or dominant-member pressure observed",
    member_pressure_detected: "Member pressure detected",
    dominant_member_pressure: "Dominant-member pressure detected",
    unknown: "Unknown",
  };

  return map[value] || value || "-";
}
function targetSpeedSurvivorSpread(target, degradedSurvivor) {
  const speed = target.target_port_speed_label || "";
  const spreads = degradedSurvivor.same_speed_survivor_spreads || {};
  const item = spreads[speed] || null;

  if (!item || item.spread_pct == null) {
    return null;
  }

  return {
    speed,
    spread: Number(item.spread_pct),
    memberCount: item.member_count || 0,
  };
}

function formatShareMap(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return "-";
  return entries
    .map(([k, v]) => `${k}: ${(Number(v || 0) * 100).toFixed(1)}%`)
    .join(", ");
}

function renderSeverityRow(label, value, severityClassName = "") {
  return `
    <div class="severity-card">
      <div class="severity-top">
        <div class="severity-name">${escapeHtml(label)}</div>
        <div class="severity-count ${severityClassName}">${escapeHtml(formatNumber(value || 0))}</div>
      </div>
    </div>
  `;
}

function renderSeverity(report) {
  const cosSeverity = report.cos_health?.severity_distribution || null;

  if (cosSeverity) {
    const suspicious = cosSeverity.suspicious || {};
    const expected = cosSeverity.expected_ecn || {};
    const informational = cosSeverity.informational || {};

    els.severityBlock.innerHTML = `
      <div class="severity-groups">
        <div class="severity-group-card">
          <div class="severity-group-title">Suspicious Queue Symptoms</div>
          ${renderSeverityRow("Critical", suspicious.critical || 0, "sev-critical")}
          ${renderSeverityRow("High", suspicious.high || 0, "sev-high")}
          ${renderSeverityRow("Medium", suspicious.medium || 0, "sev-medium")}
          ${renderSeverityRow("Low", suspicious.low || 0, "sev-low")}
        </div>

        <div class="severity-group-card">
          <div class="severity-group-title">Expected ECN Congestion</div>
          ${renderSeverityRow("Critical", expected.critical || 0, "sev-critical")}
          ${renderSeverityRow("High", expected.high || 0, "sev-high")}
          ${renderSeverityRow("Medium", expected.medium || 0, "sev-medium")}
          ${renderSeverityRow("Low", expected.low || 0, "sev-low")}
        </div>

        <div class="severity-group-card">
          <div class="severity-group-title">Informational</div>
          ${renderSeverityRow("Entries", informational.count || 0, "sev-low")}
        </div>
      </div>
    `;
    return;
  }

  const severityCounts = report.severity_counts || {};
  const entries = Object.entries(severityCounts);

  if (!entries.length) {
    renderEmpty(els.severityBlock, "No severity distribution available");
    return;
  }

  const total = entries.reduce((acc, [, count]) => acc + Number(count || 0), 0);

  els.severityBlock.innerHTML = entries
    .map(([severity, count]) => {
      const pct = total > 0 ? Math.round((Number(count || 0) / total) * 100) : 0;
      return `
        <div class="severity-card">
          <div class="severity-top">
            <div class="severity-name">${escapeHtml(severity)}</div>
            <div class="severity-count">${formatNumber(count)} <span class="muted-inline">(${pct}%)</span></div>
          </div>
          <div class="severity-bar-wrap">
            <div class="severity-bar sev-${escapeHtml(String(severity).toLowerCase())}" style="width:${pct}%"></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderFactors(report) {
  const factors =
    report.root_cause?.contributing_factors ||
    report.summary?.contributing_factors ||
    [];

  if (!Array.isArray(factors) || !factors.length) {
    renderEmpty(els.factorsBlock, "No suggested investigation steps");
    return;
  }

  els.factorsBlock.innerHTML = factors
    .map(
      (factor) => `
        <div class="stack-card">
          <div class="stack-card-body">${escapeHtml(factor)}</div>
        </div>
      `
    )
    .join("");
}

function ecmpDisplayTarget(targetId) {
  return String(targetId || "").replace(/~/g, ":");
}

function formatPct(value) {
  const n = Number(value || 0);
  return `${(n * 100).toFixed(1)}%`;
}

function formatSpreadRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(2)}x`;
}

function sameSpeedFairnessLabel(v) {
  const map = {
    balanced: "Balanced",
    mild_skew: "Mild Skew",
    skewed: "Skewed",
    not_applicable: "N/A",
    unknown: "Unknown",
  };
  return map[v] || v || "Unknown";
}

function sameSpeedFairnessBadge(v) {
  const label = sameSpeedFairnessLabel(v);
  let cls = "badge-muted";
  if (v === "balanced") cls = "badge-ok";
  else if (v === "mild_skew") cls = "badge-warn";
  else if (v === "skewed") cls = "badge-bad";

  return `<span class="status-badge ${cls}">${escapeHtml(label)}</span>`;
}

function renderSameSpeedGroupTable(groups) {
  if (!groups || !groups.length) {
    return `<div class="empty-state">No same-speed fairness data available</div>`;
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>Speed Group</th>
          <th>Members</th>
          <th>Group Share</th>
          <th>Expected / Member</th>
          <th>Min</th>
          <th>Max</th>
          <th>Spread</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>
        ${groups.map((g, idx) => `
          <tr class="clickable-row" data-speed-group-index="${idx}">
            <td>${escapeHtml(g.speed_label || "unknown")}</td>
            <td>${escapeHtml(String(g.member_count || 0))}</td>
            <td>${escapeHtml(formatPct(g.group_total_share))}</td>
            <td>${escapeHtml(formatPct(g.expected_equal_member_share))}</td>
            <td>${escapeHtml(formatPct(g.min_member_share))}</td>
            <td>${escapeHtml(formatPct(g.max_member_share))}</td>
            <td>${escapeHtml(formatSpreadRatio(g.spread_ratio))}</td>
            <td>${sameSpeedFairnessBadge(g.fairness_verdict)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}


function renderSameSpeedGroupMembers(groups, phaseLabel = "") {
  if (!Array.isArray(groups) || !groups.length) return "";

  const toPct = (value) => {
    const num = Number(value || 0);
    return num <= 1.0 ? num * 100.0 : num;
  };

  return groups.map((group) => {
    const members = Array.isArray(group.members) ? group.members : [];
    if (!members.length) return "";

    const speedGroup =
      group.speed_group ||
      group.speed ||
      group.group_name ||
      group.group ||
      group.name ||
      group.speed_label ||
      "-";

    // Most reliable: derive expected/member from actual member shares.
    // This avoids dependency on backend key names.
    const memberShares = members.map((member) =>
      toPct(
        member.share ??
        member.share_pct ??
        member.member_share ??
        member.actual_share ??
        member.actual_share_pct ??
        0
      )
    );

    const totalMemberShare = memberShares.reduce((sum, value) => sum + value, 0);
    const expectedPerMember = members.length ? totalMemberShare / members.length : 0;

    return `
      <div class="evidence-card full-width">
        <h4>Members — ${escapeHtml(String(speedGroup))}${phaseLabel ? ` (${escapeHtml(phaseLabel)})` : ""}</h4>
        <table class="data-table compact-table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Share</th>
              <th>Deviation from Equal Share</th>
            </tr>
          </thead>
          <tbody>
            ${members.map((member, idx) => {
              const memberName =
                member.member ||
                member.interface ||
                member.name ||
                "-";

              const share = memberShares[idx] || 0;
	      
	      const deviation =
		expectedPerMember > 0 ? share - expectedPerMember : null;

	      const deviationText =
                deviation === null
                  ? "-"
                  : `${deviation >= 0 ? "+" : ""}${deviation.toFixed(1)}%`;

              return `
                <tr>
                  <td>${escapeHtml(String(memberName))}</td>
                  <td>${share.toFixed(1)}%</td>
		  <td>${deviationText}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  }).join("");
}

function renderDualDistributionValidation(target) {
  const dual = target.dual_distribution_validation || {};
  const capacity = dual.capacity_weighted_validation || target.capacity_weighted_validation || {};
  const equalMember = dual.equal_member_validation || target.equal_member_validation || {};
  const hasCapacityRows = Object.keys(capacity.group_validation || {}).length > 0;
  const hasEqualRows = Object.keys(equalMember.group_validation || {}).length > 0;

  if (!hasCapacityRows && !hasEqualRows) {
    return "";
  }
  const finalInterp =
    dual.final_distribution_interpretation ||
    target.final_distribution_interpretation ||
    "-";

  const fmt = (v) => {
    const n = Number(v || 0);
    return `${n.toFixed(1)}%`;
  };

  const renderRows = (validation) => {
    const rows = Array.isArray(validation.rows) ? validation.rows : [];
    if (!rows.length) {
      return `<tr><td colspan="6" class="empty-state">No validation data available</td></tr>`;
    }

    return rows.map((row) => {
      const status = row.status || "-";
      const statusText = status === "in_spec" ? "In spec" : "Out of spec";
      const badgeClass = status === "in_spec" ? "verdict-pass" : "verdict-fail";

      const deviation = Number(row.deviation_pct || 0);
      const deviationText = `${deviation >= 0 ? "+" : ""}${deviation.toFixed(1)}%`;

      return `
        <tr>
          <td>${escapeHtml(String(row.speed_group || "-"))}</td>
          <td>${fmt(row.expected_pct)}</td>
          <td>${fmt(row.actual_pct)}</td>
          <td>${fmt(row.allowed_min_pct)}–${fmt(row.allowed_max_pct)}</td>
          <td>${deviationText}</td>
          <td><span class="verdict-badge ${badgeClass}">${statusText}</span></td>
        </tr>
      `;
    }).join("");
  };

  const finalTextMap = {
    capacity_weighted_expected: "Capacity-weighted expected",
    design_aligned_equal_member_dlb: "Design-Aligned / Equal-Member DLB",
    defect_candidate: "Defect Candidate",
  };

  const finalText = finalTextMap[finalInterp] || finalInterp;

  return `
    <div class="evidence-card full-width">
      <h4>Dual ECMP Distribution Validation</h4>

      <div class="summary-grid summary-grid-3">
        <div class="summary-item">
          <div class="summary-label">Final Interpretation</div>
          <div class="summary-value">${escapeHtml(finalText)}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Capacity-Weighted Status</div>
          <div class="summary-value">${escapeHtml(capacity.overall_status || "-")}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">Equal-Member Status</div>
          <div class="summary-value">${escapeHtml(equalMember.overall_status || "-")}</div>
        </div>
      </div>

      <h5>Capacity-Weighted Validation</h5>
      <table class="data-table compact-table spec-validation-table">
        <thead>
          <tr>
            <th>Speed Group</th>
            <th>Expected</th>
            <th>Actual</th>
            <th>Allowed Range</th>
            <th>Deviation</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${renderRows(capacity)}</tbody>
      </table>

      <h5>Equal-Member Validation</h5>
      <table class="data-table compact-table spec-validation-table">
        <thead>
          <tr>
            <th>Speed Group</th>
            <th>Expected</th>
            <th>Actual</th>
            <th>Allowed Range</th>
            <th>Deviation</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${renderRows(equalMember)}</tbody>
      </table>

      <div class="spec-summary">
        ${
          finalInterp === "design_aligned_equal_member_dlb"
            ? "Observed distribution does not match capacity-weighted expectation, but closely matches equal-member DLB behavior. Under equal port-quality conditions, this is interpreted as design-aligned behavior rather than a defect candidate."
            : ""
        }
      </div>
    </div>
  `;
}

function ecmpVerdictRank(verdict) {
  const ranks = {
    defect_candidate: 5,
    abnormal: 4,
    watch: 3,
    acceptable: 2,
    expected: 1,
  };
  return ranks[String(verdict || "").toLowerCase()] || 0;
}

function ecmpVerdictBadge(verdict) {
  const v = String(verdict || "unknown").toLowerCase();

  if (v === "no_event_regression") {
    return '<span class="verdict-badge verdict-pass">🟢 No Event Regression</span>';
  }

  if (v === "defect_candidate") {
    return '<span class="verdict-badge verdict-fail">🔴 Defect Candidate</span>';
  }

  if (v === "abnormal") {
    return '<span class="verdict-badge verdict-watch">🟠 Abnormal</span>';
  }

  if (v === "watch") {
    return '<span class="verdict-badge verdict-watch">🟡 Watch</span>';
  }

  if (v === "acceptable" || v === "expected" || v === "design_aligned") {
    return `<span class="verdict-badge verdict-pass">🟢 ${escapeHtml(ecmpLabel("recovery_verdict", verdict))}</span>`;
  }

  return `<span class="verdict-badge verdict-neutral">${escapeHtml(ecmpLabel("recovery_verdict", verdict))}</span>`;
}

function ecmpRowClass(verdict) {
  const v = String(verdict || "").toLowerCase();
  if (v === "defect_candidate") return "row-ecmp-defect";
  if (v === "abnormal") return "row-ecmp-abnormal";
  if (v === "watch") return "row-ecmp-watch";
  if (v === "acceptable") return "row-ecmp-acceptable";
  if (v === "expected") return "row-ecmp-expected";
  return "";
}
function ecmpBaselineLabel(target) {
  if (target && target.ecmp_expected_mode === "equal_member") {
    return "Expected Equal-Score";
  }
  return ecmpLabel("baseline_state", target ? target.baseline_state : "");
}

function ecmpLabel(field, value) {
  const v = String(value || "");
  const maps = {
    baseline_state: {
      healthy_speed_weighted: "Healthy / Speed-weighted",
      healthy_minor_skew: "Healthy / Minor Skew",
      unhealthy_preexisting_skew: "Pre-existing Skew",
      unknown: "Unknown",
    },
    recovery_convergence_state: {
      converged: "Converged",
      partial: "Partially Converged",
      not_converged: "Not Converged",
      oscillating: "Oscillating",
      unknown: "Unknown",
    },
    speed_alignment_state: {
      aligned: "Speed Weighted",
      mildly_misaligned: "Partially Speed Weighted",
      misaligned: "Not Speed Weighted",
      not_applicable: "Not Used",
      unknown: "Unknown",
    },
    dominant_port_state: {
      none: "None",
      transient: "Transient",
      persistent: "Persistent",
      unknown: "Unknown",
    },
    delta_outcome: {
      improved: "Improved",
      unchanged: "Unchanged",
      degraded: "Degraded",
      recovered_from_event: "Recovered from Event",
      worsened_vs_baseline: "Worsened vs Baseline",
      unknown: "Unknown",
    },
    recovery_verdict: {
      expected: "Expected",
      acceptable: "Acceptable",
      watch: "Watch",
      abnormal: "Abnormal",
      defect_candidate: "Defect Candidate",
      design_aligned: "Design-Aligned",
    },
    analysis_status: {
      complete: "Complete",
      partial_data: "Partial Data",
      insufficient_data: "Insufficient Data",
    },
  };

  if (maps[field] && maps[field][v]) return maps[field][v];
  return v ? v.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "-";
}

function ecmpRatioStatusBadge(kind) {
  if (kind === "good") {
    return `<span class="status-mark status-good">✅ Expected</span>`;
  }
  if (kind === "warn") {
    return `<span class="status-mark status-warn">⚠ Mild Deviation</span>`;
  }
  return `<span class="status-mark status-bad">❌ Mismatch</span>`;
}

function ecmpRatioStatus(ratio) {
  const r = Number(ratio);
  if (Number.isNaN(r)) return "bad";
  if (r >= 0.85 && r <= 1.15) return "good";
  if ((r >= 0.70 && r < 0.85) || (r > 1.15 && r <= 1.50)) return "warn";
  return "bad";
}

function ecmpDeltaStatus(preValue, postValue, lowerIsBetter = true) {
  const pre = Number(preValue);
  const post = Number(postValue);
  if (Number.isNaN(pre) || Number.isNaN(post)) return "bad";

  if (lowerIsBetter) {
    if (post < pre) return "good";
    if (post === pre) return "warn";
    return "bad";
  }

  if (post > pre) return "good";
  if (post === pre) return "warn";
  return "bad";
}

function buildEventTargetSet(report) {
  const events = Array.isArray(report.events) ? report.events : [];
  const out = new Set();

  for (const ev of events) {
    const node = ev?.target_node;
    const intf = ev?.target_interface;
    if (node && intf) {
      out.add(`${node}|${intf}`);
    }
  }
  return out;
}

function deriveEventRelation(entity, report) {
  const entityId = String(entity?.entity_id || "");
  const node = String(entity?.node || "");
  const intf = String(entity?.interface || "");

  const targetSet = buildEventTargetSet(report);
  if (targetSet.has(`${node}|${intf}`) || targetSet.has(entityId)) {
    return "direct-event-target";
  }

  if (node) {
    for (const item of targetSet) {
      if (item.startsWith(`${node}|`)) return "same-node-as-event";
    }
  }

  return "non-event";
}

function eventRelationLabel(relation) {
  if (relation === "direct-event-target") return "Direct event target";
  if (relation === "same-node-as-event") return "Same node as event";
  return "Non-event context";
}

function hasPhaseDelta(entity) {
  if (!entity) return false;
  const rise = Number(entity.rise_tail_dropped_packets || 0);
  const linger = Number(entity.linger_tail_dropped_packets || 0);
  const pre = Array.isArray(entity.pre_tail_baseline_series) ? entity.pre_tail_baseline_series : [];
  const post = Array.isArray(entity.post_tail_linger_series) ? entity.post_tail_linger_series : [];
  return rise > 0 || linger > 0 || pre.length > 0 || post.length > 0;
}

function buildContextChips(entity) {
  const item = entity?.data || entity || {};
  const relation = entity?.relation || deriveEventRelation(item, state.currentCase || {});
  const chips = [];

  if (relation === "direct-event-target") {
    chips.push("Event target");
  } else if (relation === "same-node-as-event") {
    chips.push("Event node");
  }

  if (Number(item.queue) >= 8) {
    chips.push("Lossy (q8)");
  }

  if (
    item.is_suspicious ||
    String(item.classification || "").includes("unexpected") ||
    String(item.classification || "").includes("localized")
  ) {
    chips.push("Anomaly");
  }

  const trend = String(item.tail_linger_trend || "").toLowerCase();
  if (trend === "increasing") {
    chips.push("Worsening");
  } else if (trend === "flat") {
    chips.push("Stable");
  } else if (trend === "decreasing" || trend === "cleared") {
    chips.push("Recovered");
  }

  const rise = Number(item.rise_tail_dropped_packets || 0);
  const linger = Number(item.linger_tail_dropped_packets || 0);
  if (rise > 0 || linger > 0) {
    chips.push("Post-impact");
  }

  if (!chips.length) return "";
  return `<div class="context-chip-row">${chips.map((chip) => `<span class="cos-chip cos-chip-neutral">${escapeHtml(chip)}</span>`).join("")}</div>`;
}

function buildEntityList(report) {
  const evidence = report.evidence_index || {};
  const entities = Object.entries(evidence).map(([entityId, item]) => {
    const row = { entity_id: entityId, ...(item || {}) };
    const relation = deriveEventRelation(row, report);
    return {
      entity_id: entityId,
      relation,
      phaseDelta: hasPhaseDelta(row),
      label: `${safe(row.node)} / ${safe(row.interface)} / q${safe(row.queue)}`,
      data: row,
    };
  });

  return entities;
}

function pickDefaultEvidenceEntity(report, entities) {
  if (!Array.isArray(entities) || !entities.length) return null;

  const scored = entities.map((entity, idx) => {
    const data = entity.data || {};
    const relation = entity.relation;
    const severity = String(data.severity || "").toLowerCase();
    const score = Number(data.score || data.hotspot_score || 0);
    const hasCos = !!findCosHotspotByEntity(report, entity.entity_id);

    return {
      entity,
      idx,
      relationRank:
        relation === "direct-event-target" ? 100 :
        relation === "same-node-as-event" ? 50 : 10,
      criticalRank: severity === "critical" ? 2 : severity === "high" ? 1 : 0,
      score,
      cosRank: hasCos ? 1 : 0,
    };
  });

  scored.sort((a, b) =>
    b.relationRank - a.relationRank ||
    b.criticalRank - a.criticalRank ||
    b.score - a.score ||
    b.cosRank - a.cosRank ||
    a.idx - b.idx
  );

  return scored[0]?.entity || entities[0];
}

function renderEntityList(report, searchText = "") {
  const entities = buildEntityList(report);
  const needle = String(searchText || "").trim().toLowerCase();

  state.filteredEntities = needle
    ? entities.filter((entity) =>
        entity.entity_id.toLowerCase().includes(needle) ||
        entity.label.toLowerCase().includes(needle) ||
        eventRelationLabel(entity.relation).toLowerCase().includes(needle)
      )
    : entities;

  if (!state.filteredEntities.length) {
    renderEmpty(els.entityList, "No matching entities");
    renderEmpty(els.evidenceBlock, "No evidence available");
    if (els.selectedEntityHint) {
      els.selectedEntityHint.textContent = "";
    }
    return;
  }

  const defaultEntity = pickDefaultEvidenceEntity(report, state.filteredEntities) || state.filteredEntities[0];

  els.entityList.innerHTML = state.filteredEntities
    .map((entity) => {
      const active = entity.entity_id === defaultEntity.entity_id;
      const relationText = eventRelationLabel(entity.relation);
      const deltaText = entity.phaseDelta ? "Phase Delta" : "No Phase Delta";
      return `
        <button class="entity-btn ${active ? "active" : ""}" data-entity-id="${escapeHtml(entity.entity_id)}">
          <div>${escapeHtml(entity.label)}</div>
          <div class="summary-subtext">${escapeHtml(relationText)} • ${escapeHtml(deltaText)}</div>
          ${buildContextChips(entity)}
        </button>
      `;
    })
    .join("");

  if (els.selectedEntityHint) {
    els.selectedEntityHint.textContent = "Default entity is auto-selected based on event correlation, severity, and evidence strength.";
  }

  bindEntityClicks(report, defaultEntity.entity_id);
  renderEvidence(report, defaultEntity.entity_id);
}

function findCosHotspotByEntity(report, entityId) {
  const rows = getCosHotspotRows(report);
  return rows.find((row) => {
    const candidate = `${safe(row.node, "")}|${safe(row.interface, "")}|${safe(row.queue, "")}`;
    return candidate === entityId || `${safe(row.node, "")}|${safe(row.interface, "")}|q${safe(row.queue, "")}` === entityId;
  }) || null;
}

function buildPhaseLabels(item) {
  const labels = [];
  const phaseTs = item.phase_timestamps || {};
  const preSamples = Array.isArray(phaseTs.pre_samples) ? phaseTs.pre_samples : [];
  const postSamples = Array.isArray(phaseTs.post_samples) ? phaseTs.post_samples : [];

  const preSeries = Array.isArray(item.pre_tail_baseline_series) ? item.pre_tail_baseline_series : [];
  const postSeries = Array.isArray(item.post_tail_linger_series) ? item.post_tail_linger_series : [];

  for (let i = 0; i < preSeries.length; i += 1) {
    labels.push({
      label: `P${i + 1}`,
      time: formatPhaseTime(preSamples[i]),
    });
  }

  labels.push({
    label: "Evt",
    time: formatPhaseTime(phaseTs.event_window || phaseTs.event),
  });

  for (let i = 0; i < postSeries.length; i += 1) {
    labels.push({
      label: `R${i + 1}`,
      time: formatPhaseTime(postSamples[i]),
    });
  }

  if (!labels.length && (preSeries.length || postSeries.length || item.rise_tail_dropped_packets || item.linger_tail_dropped_packets)) {
    return [
      { label: "Pre", time: "" },
      { label: "Evt", time: "" },
      { label: "Post", time: "" },
    ];
  }

  return labels;
}

function renderAnnotatedSparkline(values, options = {}) {
  if (!Array.isArray(values) || !values.length) {
    return `<div class="empty-state">Trend graph unavailable</div>`;
  }

  const width = options.width || 620;
  const height = options.height || 160;
  const padLeft = 42;
  const padRight = 16;
  const padTop = 14;
  const padBottom = 36;
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;

  const maxVal = Math.max(0, ...values);
  const minVal = Math.min(0, ...values);

  const scaleX = (idx) => {
    if (values.length === 1) return padLeft + innerW / 2;
    return padLeft + (idx / (values.length - 1)) * innerW;
  };

  const scaleY = (val) => {
    const range = maxVal - minVal || 1;
    return padTop + innerH - ((val - minVal) / range) * innerH;
  };

  const points = values.map((v, i) => `${scaleX(i)},${scaleY(v)}`).join(" ");
  const baselineY = scaleY(0);
  const midVal = Math.round((maxVal + minVal) / 2);

  const preCount = Array.isArray(options.preSeries) ? options.preSeries.length : 0;
  const eventIdx = preCount > 0 ? preCount : Math.min(1, values.length - 1);
  const postCount = Math.max(0, values.length - eventIdx - 1);

  let labels = Array.isArray(options.phaseLabels) ? [...options.phaseLabels] : [];
  if (labels.length < values.length) {
    while (labels.length < values.length) {
      labels.push({ label: "", time: "" });
    }
  } else if (labels.length > values.length) {
    labels = labels.slice(0, values.length);
  }

  const stageMarkers = [
    { idx: 0, label: "Pre-Baseline" },
    { idx: eventIdx, label: "Event Window" },
  ];

  const uniqueStageMarkers = stageMarkers.filter(
    (m, i, arr) => arr.findIndex((x) => x.idx === m.idx) === i
  );

  const lastVal = values[values.length - 1];
  const prevVal = values.length > 1 ? values[values.length - 2] : values[0];

  let trendClass = "trend-state-neutral";
  let trendLabel = "Stable";
  if (lastVal > prevVal) {
    trendClass = "trend-state-worsening";
    trendLabel = "Worsening";
  } else if (lastVal < prevVal) {
    trendClass = "trend-state-recovering";
    trendLabel = "Recovering";
  }

  const lineSegments = uniqueStageMarkers
    .map((m) => {
      const x = scaleX(m.idx);
      return `<line x1="${x}" y1="${padTop}" x2="${x}" y2="${height - padBottom}" class="sparkline-stage-line" />`;
    })
    .join("");

  const pointDots = values
    .map((v, i) => {
      const x = scaleX(i);
      const y = scaleY(v);
      const isEvent = i === eventIdx;
      const isPost = i > eventIdx;
      const isLast = i === values.length - 1;

      const cls = isLast
        ? "sparkline-dot sparkline-dot-last"
        : isEvent
        ? "sparkline-dot sparkline-dot-event"
        : isPost
        ? "sparkline-dot sparkline-dot-post"
        : "sparkline-dot";

      const radius = isLast ? 4.5 : isPost ? 3.8 : 3.2;
      return `<circle cx="${x}" cy="${y}" r="${radius}" class="${cls}" />`;
    })
    .join("");

  const yAxisLabels = `
    <text x="${padLeft - 8}" y="${padTop + 4}" text-anchor="end" class="sparkline-axis-text">
      ${formatNumber(maxVal)}
    </text>
    <text x="${padLeft - 8}" y="${baselineY + 4}" text-anchor="end" class="sparkline-axis-text">
      0
    </text>
    ${
      minVal < 0
        ? `
      <text x="${padLeft - 8}" y="${height - padBottom + 4}" text-anchor="end" class="sparkline-axis-text">
        ${formatNumber(minVal)}
      </text>
    `
        : ""
    }
  `;

  const xAxisLabels = labels
    .map((entry, idx) => {
      const x = scaleX(idx);
      const label = entry && entry.label ? entry.label : "";
      const time = entry && entry.time ? entry.time : "";
      return `
        <text x="${x}" y="${height - 22}" text-anchor="middle" class="sparkline-stage-text">
          ${escapeHtml(label)}
        </text>
        <text x="${x}" y="${height - 8}" text-anchor="middle" class="sparkline-stage-time">
          ${escapeHtml(time)}
        </text>
      `;
    })
    .join("");

  const phaseLegend = `
    <div class="sparkline-phase-legend">
      <span class="sparkline-phase-pill">Pre-Baseline</span>
      <span class="sparkline-phase-pill">Event Window</span>
      ${postCount >= 1 ? `<span class="sparkline-phase-pill">Post-1</span>` : ""}
      ${postCount >= 2 ? `<span class="sparkline-phase-pill">Post-2</span>` : ""}
      ${postCount >= 3 ? `<span class="sparkline-phase-pill">Post-3</span>` : ""}
    </div>
  `;

  return `
    <div class="annotated-sparkline-card">
      <div class="annotated-sparkline-meta">
        <span class="annotated-sparkline-source">Pre-Baseline → Event Window → Post Recovery</span>
        <span class="annotated-sparkline-state ${trendClass}">${trendLabel}</span>
      </div>

      <svg class="annotated-sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Phase aware RCA trend">
        <line x1="${padLeft}" y1="${baselineY}" x2="${width - padRight}" y2="${baselineY}" class="sparkline-baseline-line" />
        <line x1="${padLeft}" y1="${padTop}" x2="${width - padRight}" y2="${padTop}" class="sparkline-guide-line" />
        <line x1="${padLeft}" y1="${scaleY(midVal)}" x2="${width - padRight}" y2="${scaleY(midVal)}" class="sparkline-guide-line" />
        ${
          minVal < 0
            ? `<line x1="${padLeft}" y1="${height - padBottom}" x2="${width - padRight}" y2="${height - padBottom}" class="sparkline-guide-line" />`
            : ""
        }
        ${yAxisLabels}
        ${lineSegments}
        <polyline fill="none" points="${points}" class="sparkline-polyline" />
        ${pointDots}
        ${xAxisLabels}
      </svg>

      ${phaseLegend}
    </div>
  `;
}
function renderEvidence(report, entityId) {
  const evidence = report.evidence_index || {};
  const baseItem = evidence[entityId] || {};
  const cosItem = findCosHotspotByEntity(report, entityId) || {};

  const item = {
    ...baseItem,
    ...cosItem,
  };

  if (
    Array.isArray(baseItem.pre_tail_baseline_series) &&
    baseItem.pre_tail_baseline_series.length > 0 &&
    (!Array.isArray(item.pre_tail_baseline_series) || item.pre_tail_baseline_series.length === 0)
  ) {
    item.pre_tail_baseline_series = baseItem.pre_tail_baseline_series;
  }

  if (
    Array.isArray(baseItem.post_tail_linger_series) &&
    baseItem.post_tail_linger_series.length > 0 &&
    (!Array.isArray(item.post_tail_linger_series) || item.post_tail_linger_series.length === 0)
  ) {
    item.post_tail_linger_series = baseItem.post_tail_linger_series;
  }

  if (
    baseItem.phase_timestamps &&
    (!item.phase_timestamps ||
      !Array.isArray(item.phase_timestamps.pre_samples) ||
      item.phase_timestamps.pre_samples.length === 0)
  ) {
    item.phase_timestamps = baseItem.phase_timestamps;
  }

  if (!item || !Object.keys(item).length) {
    renderEmpty(els.evidenceBlock, "No evidence available for selected entity");
    return;
  }

  const signals = item.signals || {};
  const deltaRunning = item.delta_running || {};
  const deltaPost = item.delta_post || {};
  const runningMetrics = item.running_metrics || {};
  const baselineMetrics = item.baseline_metrics || {};
  const postMetrics = item.post_metrics || {};
  const postSampleMetrics = item.post_sample_metrics || [];

  const runningTail = Number(deltaRunning["tail-drop-pkts"] || 0);
  const postTail = Number(deltaPost["tail-drop-pkts"] || 0);

  let postBehavior = "Recovered";
  if (postTail > runningTail) {
    postBehavior = "Worsening";
  } else if (postTail === runningTail && runningTail > 0) {
    postBehavior = "Lingering";
  }

  const riseTail = Number(item.rise_tail_dropped_packets || 0);
  const lingerTail = Number(item.linger_tail_dropped_packets || 0);

  const hasMeaningfulPhaseDelta =
    riseTail > 0 ||
    (Array.isArray(item.post_tail_linger_series) &&
      item.post_tail_linger_series.some((v) => Number(v || 0) !== 0));

  const noPhaseDeltaNote = !hasMeaningfulPhaseDelta
    ? `
      <div class="summary-subtext" style="margin-top:10px;">
        No phase-aware tail-drop increase observed for this entity in the selected run.
        The hotspot score may reflect absolute or pre-existing queue counters rather than event-time growth.
      </div>
    `
    : "";

  const recoveryRatio = item.recovery_ratio_tail;
  const trend = item.tail_linger_trend;
  const eventOutcome = item.event_delta_classification;

  const hasPreSeries =
    Array.isArray(item.pre_tail_baseline_series) &&
    item.pre_tail_baseline_series.length > 0;

  const hasPostSeries =
    Array.isArray(item.post_tail_linger_series) &&
    item.post_tail_linger_series.length > 0;

  const hasPhaseTrend =
    hasPreSeries ||
    hasPostSeries ||
    riseTail > 0 ||
    lingerTail > 0;

  const phaseSeries = hasPhaseTrend ? buildPhaseSeries(item) : [];
  const phaseLabels = hasPhaseTrend ? buildPhaseLabels(item) : [];
  const flatHint = hasPhaseTrend ? getFlatGraphHint(phaseSeries) : null;

  const trendGraphHtml = hasPhaseTrend
    ? `${renderAnnotatedSparkline(phaseSeries, {
        width: 620,
        height: 160,
        preSeries: item.pre_tail_baseline_series || [],
        phaseLabels,
      })}
      ${flatHint ? `<div class="flat-graph-note">${escapeHtml(flatHint)}</div>` : ""}`
    : `<div class="empty-state">Phase-aware trend not available for this entity</div>`;

  const interpretationText =
    !hasPhaseTrend
      ? "This entity does not currently have phase-aware pre-window, event-window, and post-window trend enrichment."
      : postBehavior === "Worsening"
      ? "Post-event queue impact continues increasing across recovery checkpoints, indicating worsening persistence after the stress event."
      : postBehavior === "Lingering"
      ? "Post-event queue impact remains elevated across recovery checkpoints and requires investigation."
      : "Post-event queue impact declines across recovery checkpoints, indicating recovery.";

  const relation = deriveEventRelation(item, report);

  els.evidenceBlock.innerHTML = `
    <div class="evidence-grid">
      <div class="evidence-card">
        <h4>Entity Summary</h4>
        <div class="evidence-line"><strong>Node:</strong> ${escapeHtml(safe(item.node))}</div>
        <div class="evidence-line"><strong>Interface:</strong> <span class="mono-text">${escapeHtml(safe(item.interface))}</span></div>
        <div class="evidence-line"><strong>Queue:</strong> ${escapeHtml(safe(item.queue))}</div>
        <div class="evidence-line"><strong>Severity:</strong> ${escapeHtml(safe(item.severity))}</div>
        <div class="evidence-line"><strong>Probable Cause:</strong> ${escapeHtml(safe(item.probable_cause))}</div>
        ${buildContextChips({ data: item, relation })}
      </div>

      <div class="evidence-card">
        <h4>Phase-Aware RCA</h4>
        <div class="evidence-line"><strong>Event Outcome:</strong> ${eventOutcomeBadge(eventOutcome)}</div>
        <div class="evidence-line"><strong>Recovery Trend:</strong> ${escapeHtml(postBehavior)}</div>
        <div class="evidence-line"><strong>Trend Classification:</strong> ${trendBadge(trend)}</div>
        <div class="evidence-line"><strong>Persistence Ratio:</strong> ${escapeHtml(formatRatio(recoveryRatio))}</div>
        <div class="evidence-line"><strong>Rise:</strong> ${escapeHtml(formatNumber(riseTail))}</div>
        <div class="evidence-line"><strong>Linger:</strong> ${escapeHtml(formatNumber(lingerTail))}</div>

        <div class="phase-trend-panel">
          <div class="phase-trend-title">Queue Recovery Trend (${postSampleMetrics.length || 0} post checkpoints)</div>
          ${trendGraphHtml}
          ${noPhaseDeltaNote}
          <div class="summary-subtext" style="margin-top:10px;">${escapeHtml(interpretationText)}</div>
          <div class="summary-subtext">
            Trend view shows pre-window baseline, event-window rise, and post-recovery checkpoints for quick RCA comparison.
          </div>
          <div class="summary-subtext">
            X-axis labels show phase checkpoints and timestamps when available.
          </div>
        </div>
      </div>

      <div class="evidence-card full-width">
        <h4>Key Signal Snapshot</h4>
        <div class="summary-grid summary-grid-3">
          <div class="summary-item">
            <div class="summary-label">Tail Drop Delta (Running)</div>
            <div class="summary-value big-status">${escapeHtml(formatNumber(deltaRunning["tail-drop-pkts"] || 0))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Tail Drop Delta (Post)</div>
            <div class="summary-value big-status">${escapeHtml(formatNumber(deltaPost["tail-drop-pkts"] || 0))}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Temporal Pattern</div>
            <div class="summary-value big-status">${escapeHtml(safe(item.temporal_pattern))}</div>
          </div>
        </div>
      </div>

      <div class="evidence-card full-width">
        <details class="details-block">
          <summary>View raw evidence details</summary>
          <div class="details-grid" style="margin-top:12px;">
            <div class="full-row"><strong>Signals</strong><pre>${escapeHtml(JSON.stringify(signals, null, 2))}</pre></div>
            <div><strong>Baseline Metrics</strong><pre>${escapeHtml(JSON.stringify(baselineMetrics, null, 2))}</pre></div>
            <div><strong>Running Metrics</strong><pre>${escapeHtml(JSON.stringify(runningMetrics, null, 2))}</pre></div>
            <div><strong>Post Metrics</strong><pre>${escapeHtml(JSON.stringify(postMetrics, null, 2))}</pre></div>
            <div><strong>Running Delta</strong><pre>${escapeHtml(JSON.stringify(deltaRunning, null, 2))}</pre></div>
            <div><strong>Post Delta</strong><pre>${escapeHtml(JSON.stringify(deltaPost, null, 2))}</pre></div>
            <div class="full-row"><strong>Post Sample Metrics</strong><pre>${escapeHtml(JSON.stringify(postSampleMetrics, null, 2))}</pre></div>
          </div>
        </details>
      </div>
    </div>
  `;
}

function buildEcmpVerdictText(summary) {
  if (!summary || !summary.analysis_status) {
    return "No ECMP recovery verdict available.";
  }

  const analysisStatus = ecmpLabel("analysis_status", summary.analysis_status);
  const targets = Number(summary.target_count || 0);
  const defects = Number(summary.defect_candidate_count || 0);
  const expected = Number(summary.expected_count || 0);

  return `${analysisStatus} — ${targets} targets analyzed, ${defects} defect candidate(s), ${expected} expected target(s).`;
}

function bindEntityClicks(report, selectedId) {
  const buttons = els.entityList.querySelectorAll(".entity-btn");
  buttons.forEach((btn) => {
    if (btn.dataset.entityId === selectedId) {
      btn.classList.add("active");
    }
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      renderEvidence(report, btn.dataset.entityId);
    });
  });
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function renderTopologyViewLink(report) {
  const runId = report?.run_metadata?.run_id || state.currentRunId;
  if (!runId || !els.topologyViewLink) {
    return;
  }

  const href = `/artifacts/campaigns/${encodeURIComponent(runId)}/topology_view.html`;
  els.topologyViewLink.href = href;
  els.topologyViewLink.textContent = "Open Topology View";
  els.topologyViewLink.style.pointerEvents = "auto";
  els.topologyViewLink.style.opacity = "1";
}

async function loadCases() {
  const data = await fetchJson("/api/rca/cases");
  state.cases = Array.isArray(data.cases) ? data.cases : [];

  if (!state.cases.length) {
    els.runSelect.innerHTML = `<option value="">No runs available</option>`;
    els.heroTitle.textContent = "No RCA cases found";
    els.heroSub.textContent = "Generate an RCA run to populate the dashboard";
    return;
  }

  els.runSelect.innerHTML = state.cases
    .map(
      (item) => `
        <option value="${escapeHtml(item.run_id)}">
         ${escapeHtml(item.run_id)} — ${escapeHtml(displayIntent(item.intent_name))} — ${escapeHtml(formatUtcShort(item.generated_at))}
        </option>
      `
    )
    .join("");

  state.currentRunId = state.cases[0].run_id;
  els.runSelect.value = state.currentRunId;
  await loadCase(state.currentRunId);
}

async function loadCase(runId) {
  state.currentRunId = runId;
  state.showAllCosHotspots = false;

  const report = await fetchJson(`/api/rca/cases/${encodeURIComponent(runId)}`);
  state.currentCase = report;
  
  renderStats(report);
  renderSummary(report);
  renderMetadata(report);
  renderRcaSummary(report);
  renderQueueRcaSummary(report);
  renderRcaNarrative(report);
  renderHotspotInterpretation(report);
  renderEvents(report);
  renderHotspots(report);
  renderCosHotspots(report);
  renderSeverity(report);
  renderFactors(report);
  renderEntityList(report, els.searchInput.value);
  renderInterfaceDropHealth(report);
  renderEcmpRecovery(report.ecmp_recovery_view);
  
  renderTrafficHealth(report);
  renderTrafficExecSummary(report);
  renderCongestionOriginAnalysis(report);
  renderWorstRxPorts(report);
  renderTrafficRecoveryInterpretation(report);
  renderRoceSeqerrorFlows(report);
  renderRocePostSeqerrorFlows(report);
  renderTrafficFabricCorrelation(report);
  
  renderTopologyViewLink(report);
}

function bindEvents() {
  els.runSelect.addEventListener("change", async (e) => {
    const runId = e.target.value;
    if (runId) {
      await loadCase(runId);
    }
  });

  els.searchInput.addEventListener("input", () => {
    if (state.currentCase) {
      renderEntityList(state.currentCase, els.searchInput.value);
    }
  });

  const toggleBtn = document.getElementById("toggleEcmpDetails");
  const detailsPanel = document.getElementById("ecmpRecoveryDetails");

  if (toggleBtn && detailsPanel) {
    toggleBtn.addEventListener("click", () => {
      const isHidden = detailsPanel.classList.contains("hidden");
      detailsPanel.classList.toggle("hidden");
      toggleBtn.textContent = isHidden
        ? "Hide ECMP Recovery Details"
        : "Show ECMP Recovery Details";
    });
  }
}

async function init() {
  try {
    bindEvents();
    await loadCases();
  } catch (err) {
    debugLog(err);
    els.heroTitle.textContent = "Failed to load dashboard";
    els.heroSub.textContent = err.message || "Unknown error";
    if (els.topologyViewLink) {
      els.topologyViewLink.href = "#";
      els.topologyViewLink.textContent = "Topology View Unavailable";
      els.topologyViewLink.style.pointerEvents = "none";
      els.topologyViewLink.style.opacity = "0.6";
    }
    renderEmpty(els.summaryBlock, "Unable to load RCA summary");
    renderEmpty(els.metadataBlock, "Unable to load run metadata");
    renderEmpty(els.queueRcaSummaryBlock, "Unable to load queue RCA summary");
    renderEmpty(els.rcaNarrativeBlock, "Unable to load RCA interpretation");
    renderEmpty(els.hotspotInterpretationBlock, "Unable to load hotspot interpretation");
    renderEmpty(els.eventsBlock, "Unable to load events");
    renderEmpty(els.hotspotsTable, "Unable to load hotspots");
    renderEmpty(els.cosHotspotsTable, "Unable to load CoS hotspots");
    renderEmpty(els.severityBlock, "Unable to load severity distribution");
    renderEmpty(els.factorsBlock, "Unable to load investigation factors");
    renderEmpty(els.entityList, "Unable to load entities");
    renderEmpty(els.evidenceBlock, "Unable to load evidence");
    renderEmpty(els.interfaceDropHealthBlock, "Unable to load interface drop/error health");
    renderEmpty(els.trafficHealthBlock, "Unable to load traffic / IXIA / RoCE health");
    if (els.ecmpRecoverySummary) {
      renderEmpty(els.ecmpRecoverySummary, "Unable to load ECMP recovery summary");
    }
    if (els.ecmpRecoveryVerdict) {
      renderEmpty(els.ecmpRecoveryVerdict, "Unable to load ECMP recovery verdict");
    }
    if (els.ecmpRecoveryTable) {
      renderEmpty(els.ecmpRecoveryTable, "Unable to load ECMP recovery table");
    }
    if (els.ecmpRecoveryDetailPanel) {
      renderEmpty(els.ecmpRecoveryDetailPanel, "Unable to load ECMP recovery details");
    }
  }
}

function renderInterfaceDropHealth(report) {
  const data = report.interface_drop_health || {};
  const totals = data.totals || {};
  const top = Array.isArray(data.top_impacted_interfaces) ? data.top_impacted_interfaces : [];

  const hasAny =
    Number(totals.in_discards || 0) > 0 ||
    Number(totals.out_discards || 0) > 0 ||
    Number(totals.in_errors || 0) > 0 ||
    Number(totals.out_errors || 0) > 0 ||
    Number(totals.carrier_transitions || 0) > 0;

  if (!hasAny && !top.length) {
    renderEmpty(els.interfaceDropHealthBlock, "No interface drop/error activity detected");
    return;
  }

  els.interfaceDropHealthBlock.innerHTML = `
    <div class="summary-grid summary-grid-3">
      <div class="summary-item">
        <div class="summary-label">Ingress Discards</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(totals.in_discards || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Egress Discards</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(totals.out_discards || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Carrier Transitions</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(totals.carrier_transitions || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">In Errors</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(totals.in_errors || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Out Errors</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(totals.out_errors || 0))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Status</div>
        <div class="summary-value summary-value-large">${escapeHtml(safe(data.status, "normal"))}</div>
      </div>
    </div>

    <div style="margin-top:14px;">
      <div class="table-note">Top impacted interfaces based on discards/errors/carrier transitions.</div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Node</th>
            <th>Interface</th>
            <th>In Discards</th>
            <th>Out Discards</th>
            <th>In Errors</th>
            <th>Out Errors</th>
            <th>Carrier Transitions</th>
          </tr>
        </thead>
        <tbody>
          ${top.map((r) => `
            <tr>
              <td>${escapeHtml(safe(r.node))}</td>
              <td class="mono-text">${escapeHtml(safe(r.interface))}</td>
              <td>${escapeHtml(formatNumber(r.in_discards || 0))}</td>
              <td>${escapeHtml(formatNumber(r.out_discards || 0))}</td>
              <td>${escapeHtml(formatNumber(r.in_errors || 0))}</td>
              <td>${escapeHtml(formatNumber(r.out_errors || 0))}</td>
              <td>${escapeHtml(formatNumber(r.carrier_transitions || 0))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTrafficHealth(report) {
  const data = report.traffic_health || {};
  const live = data.live_alert_summary || {};
  const worstRx = Array.isArray(data.worst_rx_ports) ? data.worst_rx_ports : [];
  const deepRx = Array.isArray(data.deep_rx_hotspots) ? data.deep_rx_hotspots : [];
  const topAlerts = Array.isArray(live.top_alerts) ? live.top_alerts : [];
  const rocev2Summary = data.rocev2_summary || {};
  const trafficSummary = data.traffic_summary || {};
  const rootCauseSummary = data.rocev2_root_cause_summary || {};

  const rootCauseSummaryHtml = rootCauseSummary.root_cause ? `
    <div class="summary-card" style="margin-top:14px;">
      <div class="summary-card-title">Detected Root Cause</div>
      <div><strong>${escapeHtml(safe(rootCauseSummary.root_cause))}</strong></div>
      <div>Confidence: ${escapeHtml(safe(rootCauseSummary.confidence || "-"))}</div>
      <div>Reason: ${escapeHtml(safe(rootCauseSummary.reason || "-"))}</div>
    </div>
  ` : "";

  els.trafficHealthBlock.innerHTML = `
    <div class="summary-grid summary-grid-3">
      <div class="summary-item">
        <div class="summary-label">Traffic Verdict</div>
        <div class="summary-value summary-value-large">${escapeHtml(safe(data.traffic_verdict, "unknown"))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">RoCEv2 Verdict</div>
        <div class="summary-value summary-value-large">${escapeHtml(safe(data.rocev2_verdict, "unknown"))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">IXIA Critical Alerts</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(live.critical_alerts || 0))}</div>
      </div>
    </div>
    ${rootCauseSummaryHtml}
    <div style="margin-top:14px;" class="table-wrap">
      <div class="table-note">Top IXIA live alerts</div>
      ${
        topAlerts.length ? `
        <table class="data-table">
          <thead>
            <tr>
              <th>Iteration</th>
              <th>Timestamp</th>
              <th>Severity</th>
              <th>Type</th>
              <th>RX Port</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            ${topAlerts.slice(0, 5).map(a => `
              <tr>
                <td>${escapeHtml(safe(a.iteration))}</td>
                <td>${escapeHtml(safe(a.timestamp))}</td>
                <td>${escapeHtml(safe(a.severity))}</td>
                <td>${escapeHtml(safe(a.type))}</td>
                <td>${escapeHtml(safe(a.rx_port))}</td>
                <td>${escapeHtml(formatNumber(a.value))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>` : `<div class="empty-state">No live IXIA alerts available</div>`
      }
    </div>

    <div style="margin-top:14px;" class="table-wrap">
      <div class="table-note">Worst RX ports</div>
      ${
        worstRx.length ? `
        <table class="data-table">
          <thead>
            <tr>
              <th>RX Port</th>
              <th>Switch</th>
              <th>Switch Port</th>
              <th>Flows</th>
              <th>Frame Delta</th>
              <th>Max Latency (ns)</th>
            </tr>
          </thead>
          <tbody>
            ${worstRx.slice(0, 5).map(r => `
              <tr>
                <td>${escapeHtml(safe(r.rx_port || r.port || r.name))}</td>
                <td>${escapeHtml(safe(r.switch))}</td>
                <td class="mono-text">${escapeHtml(safe(r.switch_interface))}</td>
                <td>${escapeHtml(formatNumber(r.flow_count || 0))}</td>
                <td>${escapeHtml(formatNumber(r.frame_delta || 0))}</td>
                <td>${escapeHtml(formatNumber(r.max_latency_ns || 0))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>` : `<div class="empty-state">No worst RX port data available</div>`
      }
    </div>

    <div style="margin-top:14px;" class="table-wrap">
      <div class="table-note">Deep RX hotspots</div>
      ${
        deepRx.length ? `
        <table class="data-table">
          <thead>
            <tr>
              <th>RX Port</th>
              <th>Switch</th>
              <th>Switch Port</th>
              <th>Flows</th>
              <th>ECN-CE RX</th>
              <th>Max Latency (ns)</th>
            </tr>
          </thead>
          <tbody>
            ${deepRx.slice(0, 5).map(r => `
              <tr>
                <td>${escapeHtml(safe(r.rx_port || r.port || r.name))}</td>
                <td>${escapeHtml(safe(r.switch))}</td>
                <td class="mono-text">${escapeHtml(safe(r.switch_interface))}</td>
		<td>${escapeHtml(formatNumber(r.flows ?? 0))}</td>
		<td>${escapeHtml(formatNumber(r.ecn ?? 0))}</td>
		<td>${escapeHtml(formatNumber(r.max_latency_ns ?? 0))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>` : `<div class="empty-state">No deep RX hotspot data available</div>`
      }
    </div>

    <div style="margin-top:14px;">
      <details class="details-block">
        <summary>View raw RoCE / traffic summary</summary>
        <pre>${escapeHtml(JSON.stringify({ rocev2_summary: rocev2Summary, traffic_summary: trafficSummary }, null, 2))}</pre>
      </details>
    </div>
  `;
}
function generateRcaSummary(report) {
  if (!report) return "No RCA data available.";

  const events = report.events || [];
  const hotspots = report.hotspots || [];
  const cosHotspots = report.cos_health?.hotspots || [];

  // --- Identify event targets ---
  const eventNodes = new Set(
    events.flatMap(e => e.nodes || []).map(n => String(n).toLowerCase())
  );

  // --- Find event-correlated entities ---
  const eventEntities = hotspots.filter(h =>
    eventNodes.has(String(h.node || "").toLowerCase())
  );

  // --- Find strongest non-event hotspot ---
  const nonEventHotspots = hotspots.filter(h =>
    !eventNodes.has(String(h.node || "").toLowerCase())
  );

  const topHotspot = nonEventHotspots.sort(
    (a, b) => (b.score || 0) - (a.score || 0)
  )[0];

  // --- Check if event target degraded ---
  const eventHasIssue = eventEntities.some(h =>
    (h.rise_tail_dropped_packets || 0) > 0 ||
    (h.linger_tail_dropped_packets || 0) > 0
  );

  // --- Build summary ---
  let summary = "";

  if (!eventHasIssue) {
    summary += "Event target interfaces show no degradation and recovered cleanly. ";
  } else {
    summary += "Event-correlated interfaces show degradation during the event window. ";
  }

  if (topHotspot) {
    summary += `However, a separate hotspot was detected on ${topHotspot.node} ${topHotspot.interface} q${topHotspot.queue}, `;
    summary += `showing persistent and worsening tail-drop (rise=${topHotspot.rise_tail_dropped_packets || 0}, `;
    summary += `linger=${topHotspot.linger_tail_dropped_packets || 0}). `;

    if ((topHotspot.persistence_ratio || 0) > 1) {
      summary += "This indicates a sustained congestion condition. ";
    }
  }

  if (!eventHasIssue && topHotspot) {
    summary += "This condition appears independent of the injected event and may indicate a localized queue-pressure issue.";
  }

  return summary.trim();
}
function renderRcaSummary(report) {
  if (!els.rcaSummaryBlock) return;

  const summary = generateRcaSummary(report);

  els.rcaSummaryBlock.innerHTML = `
    <div class="summary-text">
      ${escapeHtml(summary)}
    </div>
  `;
}
function formatPhaseTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";

  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} UTC`;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function topN(arr, n = 10) {
  return safeArray(arr).slice(0, n);
}

function parseRoceTextSections(text) {
  const raw = String(text || "");
  if (!raw) {
    return {
      topSeqerror: [],
      topPostSeqerrorIncrease: [],
    };
  }

  const lines = raw.split(/\r?\n/);
  const sections = {
    topSeqerror: [],
    topPostSeqerrorIncrease: [],
  };

  let mode = null;
  for (const line of lines) {
    const s = line.trim();
    if (!s) continue;

    if (s.includes("TOP FLOWS BY SEQERROR") && !s.includes("POST")) {
      mode = "topSeqerror";
      continue;
    }
    if (s.includes("TOP FLOWS BY POST SEQERROR INCREASE")) {
      mode = "topPostSeqerrorIncrease";
      continue;
    }

    if (mode) {
      sections[mode].push(s);
    }
  }

  return sections;
}

function classifyTrafficImpact(row) {
  const seq = Number(row.seqerror || row.seq_error || row.seqerror_delta || 0);
  const lat = Number(row.max_latency_ns || row.latency_ns || 0);
  const frame = Number(row.frame_delta || row.loss_frames || 0);
  const ecn = Number(row.ecn_ce_rx || row.sum_ecn_ce_rx || 0);

  const parts = [];
  if (seq > 0) parts.push("SeqError");
  if (lat > 0) parts.push("Latency");
  if (frame > 0) parts.push("Loss");
  if (ecn > 0) parts.push("ECN");

  return parts.length ? parts.join(" + ") : "No impact";
}

function classifyTrafficSeverity(row) {
  const seq = Number(row.seqerror || row.seq_error || row.seqerror_delta || 0);
  const lat = Number(row.max_latency_ns || row.latency_ns || 0);
  const frame = Number(row.frame_delta || row.loss_frames || 0);

  if (seq > 1000000 || lat > 10000 || frame > 100000) return "HIGH";
  if (seq > 10000 || lat > 2000 || frame > 1000) return "MEDIUM";
  if (seq > 0 || lat > 0 || frame > 0) return "LOW";
  return "NONE";
}

function trafficKeyMetric(row) {
  const seq = Number(row.seqerror || row.seq_error || row.seqerror_delta || 0);
  const lat = Number(row.max_latency_ns || row.latency_ns || 0);
  const frame = Number(row.frame_delta || row.loss_frames || 0);
  const ecn = Number(row.ecn_ce_rx || row.sum_ecn_ce_rx || 0);

  if (seq > 0) return `seqerr +${formatNumber(seq)}`;
  if (lat > 0) return `lat ${formatNumber(lat)} ns`;
  if (frame > 0) return `frames +${formatNumber(frame)}`;
  if (ecn > 0) return `ecn-ce ${formatNumber(ecn)}`;
  return "-";
}

function buildTrafficEntityId(row) {
  const node = safe(row.switch || row.node || "", "");
  const intf = safe(row.switch_interface || row.switch_port || row.interface || "", "");
  if (!node || !intf) return "";
  return `${node}|${intf}`;
}

function generateTrafficExecSummary(report) {
  const traffic = report.traffic_health || {};
  const worstRx = safeArray(traffic.worst_rx_ports);
  const deepRx = safeArray(traffic.deep_rx_hotspots);
  const rocev2 = traffic.rocev2_summary || {};
  const live = traffic.live_alert_summary || {};

  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveSource = safe(traffic.live_source, null);
  const liveError = safe(traffic.live_error, "");

  const trafficVerdict = safe(traffic.traffic_verdict, "unknown");
  const roceVerdict = safe(traffic.rocev2_verdict, "unknown");
  const affectedPorts = worstRx.length || deepRx.length || 0;
  const affectedFlows = Number(rocev2.total_findings || 0);

  const maxLatency = Math.max(
    0,
    ...worstRx.map((r) => Number(r.max_latency_ns || 0)),
    ...deepRx.map((r) => Number(r.max_latency_ns || 0))
  );

  const topPort = worstRx[0] || deepRx[0] || null;
  const criticalAlerts = Number(live.critical_alerts || 0);

  let narrative = "";

  if (liveRequested && !liveAvailable) {
    narrative = liveError
      ? `IXIA live statistics were requested but unavailable for this run (${liveError}). Traffic analysis is based on available RoCE pre/post and deep-inspection artifacts.`
      : "IXIA live statistics were requested but unavailable for this run. Traffic analysis is based on available RoCE pre/post and deep-inspection artifacts.";
  } else if (!liveRequested) {
    if (affectedFlows === 0 && affectedPorts === 0) {
      narrative = "Live IXIA statistics were disabled for this run. Traffic analysis is based on artifact-driven RoCE evidence, and no significant traffic-side degradation is visible in the available artifacts.";
    } else {
      narrative = "Live IXIA statistics were disabled for this run. Traffic analysis is based on artifact-driven RoCE evidence and should be correlated with CoS hotspots and ECMP recovery behavior.";
    }
  } else if (liveAvailable && affectedFlows === 0 && affectedPorts === 0 && criticalAlerts === 0) {
    narrative = liveSource
      ? `Live IXIA statistics are available from ${liveSource}. No significant traffic-side degradation is visible in the currently available live or artifact-based evidence.`
      : "Live IXIA statistics are available. No significant traffic-side degradation is visible in the currently available live or artifact-based evidence.";
  } else {
    narrative = "Traffic-side degradation was detected and should be correlated with CoS hotspots, ECMP recovery behavior, and RoCE deep-inspection artifacts.";
  }

  return {
    trafficVerdict,
    roceVerdict,
    affectedPorts,
    affectedFlows,
    maxLatency,
    topPort,
    criticalAlerts,
    liveRequested,
    liveAvailable,
    liveSource,
    liveError,
    narrative,
  };
}

function renderTrafficExecSummary(report) {
  if (!els.trafficExecSummaryBlock) return;

  const s = generateTrafficExecSummary(report);
  const traffic = report.traffic_health || {};

  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveSource = safe(traffic.live_source, "-");
  const liveError = safe(traffic.live_error, "");
  const rocev2TotalFindings = traffic.rocev2_total_findings ?? 0;
  const rocev2UniqueFlowCount = traffic.rocev2_unique_flow_count ?? 0;
  const topUniqueFlow = traffic.rocev2_top_unique_flow_summary || {};
  const rootCauseSummary = traffic.rocev2_root_cause_summary || {};
  const signalBreakdown = traffic.rocev2_signal_breakdown || {};
  const topUniqueFlows = Array.isArray(traffic.rocev2_top_unique_flows)
  ? traffic.rocev2_top_unique_flows
  : [];	

  let liveStateText = "Disabled";
  let liveStateClass = "cos-chip cos-chip-neutral";
  let liveDetailText = "Live IXIA statistics were not requested for this run.";

  if (liveRequested && liveAvailable) {
    liveStateText = "Available";
    liveStateClass = "cos-chip cos-chip-expected";
    liveDetailText = `Live IXIA statistics are available for this run. Source: ${liveSource}`;
  } else if (liveRequested && !liveAvailable) {
    liveStateText = "Unavailable";
    liveStateClass = "cos-chip cos-chip-suspicious";
    liveDetailText = liveError
      ? `Live IXIA statistics were requested but unavailable. Reason: ${liveError}`
      : "Live IXIA statistics were requested but unavailable for this run.";
  }

  const topUniqueFlowHtml = topUniqueFlow.flow_key ? `
    <div class="summary-card">
      <div class="summary-card-title">Most Impacted Unique RoCE Flow</div>
      <strong>${escapeHtml(safe(topUniqueFlow.flow_name || topUniqueFlow.flow_key))}</strong>
      <div>Tx Port: ${escapeHtml(safe(topUniqueFlow.tx_port || "-"))}</div>
      <div>Rx Port: ${escapeHtml(safe(topUniqueFlow.rx_port || "-"))}</div>
      <div>Src QP / Dest QP: ${escapeHtml(safe(topUniqueFlow.src_qp || "-"))} / ${escapeHtml(safe(topUniqueFlow.dest_qp || "-"))}</div>
      <div>Findings: ${escapeHtml(formatNumber(topUniqueFlow.findings || 0))}</div>
    </div>
  ` : "";
   
  const rootCauseSummaryHtml = rootCauseSummary.root_cause ? `
    <div class="summary-card">
      <div class="summary-card-title">Detected Root Cause</div>
      <strong>${escapeHtml(safe(rootCauseSummary.root_cause))}</strong>
      <div>Confidence: ${escapeHtml(safe(rootCauseSummary.confidence || "-"))}</div>
      <div>Reason: ${escapeHtml(safe(rootCauseSummary.reason || "-"))}</div>
    </div>
  ` : "";
  const signalBreakdownHtml = Object.keys(signalBreakdown).length ? `
    <div class="summary-card">
      <div class="summary-card-title">RoCE Signal Breakdown</div>
      <div>Flows with Loss: ${escapeHtml(formatNumber(signalBreakdown.loss || 0))}</div>
      <div>Flows with Retransmission: ${escapeHtml(formatNumber(signalBreakdown.retx || 0))}</div>
      <div>Flows with SeqError: ${escapeHtml(formatNumber(signalBreakdown.seqerror || 0))}</div>
      <div>Flows with Message Failed: ${escapeHtml(formatNumber(signalBreakdown.message_failed || 0))}</div>
      <div>Flows with ECN Pressure: ${escapeHtml(formatNumber(signalBreakdown.ecn_pressure || 0))}</div>
      <div>Flows with CNP Pressure: ${escapeHtml(formatNumber(signalBreakdown.cnp_pressure || 0))}</div>
      <div>Flows with Latency: ${escapeHtml(formatNumber(signalBreakdown.latency || 0))}</div>
    </div>
  ` : ""; 

  const topUniqueFlowsHtml = topUniqueFlows.length ? `
  <div style="margin-top:14px;" class="table-wrap">
    <div class="table-note">Top Impacted Unique RoCE Flows</div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Flow Name</th>
          <th>Tx Port</th>
          <th>Rx Port</th>
          <th>Src / Dest QP</th>
          <th>Findings</th>
          <th>ECN-CE RX</th>
          <th>Max Latency (ns)</th>
        </tr>
      </thead>
      <tbody>
        ${topUniqueFlows.map((r) => `
          <tr>
            <td>${escapeHtml(safe(r.flow_name || r.flow_key))}</td>
            <td>${escapeHtml(safe(r.tx_port))}</td>
            <td>${escapeHtml(safe(r.rx_port))}</td>
            <td>${escapeHtml(`${safe(r.src_qp, "-")} / ${safe(r.dest_qp, "-")}`)}</td>
            <td>${escapeHtml(formatNumber(r.findings ?? 0))}</td>
            <td>${escapeHtml(formatNumber(r.ecn ?? 0))}</td>
            <td>${escapeHtml(formatNumber(r.max_latency_ns ?? 0))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  </div>
` : "";
  els.trafficExecSummaryBlock.innerHTML = `
    <div class="summary-grid summary-grid-3">
      <div class="summary-item">
        <div class="summary-label">Traffic Verdict</div>
        <div class="summary-value summary-value-large">${escapeHtml(s.trafficVerdict)}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">RoCEv2 Verdict</div>
        <div class="summary-value summary-value-large">${escapeHtml(s.roceVerdict)}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Critical Alerts</div>
        <div class="summary-value summary-value-large">${escapeHtml(formatNumber(s.criticalAlerts))}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Affected Fabric Interfaces</div>
        <div class="summary-value big-status">${escapeHtml(formatNumber(s.affectedPorts))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Affected Unique RoCE Flows</div>
        <div class="summary-value big-status">${escapeHtml(formatNumber(rocev2UniqueFlowCount))}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">Affected RoCE Findings</div>
        <div class="summary-value big-status">${escapeHtml(formatNumber(rocev2TotalFindings))}</div>
      </div> 
      <div class="summary-item">
        <div class="summary-label">Max Latency (ns)</div>
        <div class="summary-value big-status">${escapeHtml(formatNumber(s.maxLatency))}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Live IXIA Stats</div>
        <div class="summary-value big-status">
          <span class="${liveStateClass}">${escapeHtml(liveStateText)}</span>
        </div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Live Source</div>
        <div class="summary-value big-status">${escapeHtml(liveAvailable ? liveSource : "-")}</div>
      </div>

      <div class="summary-item">
        <div class="summary-label">Live Stats Requested</div>
        <div class="summary-value big-status">${escapeHtml(liveRequested ? "Yes" : "No")}</div>
      </div>

      <div class="summary-item full-row">
        <div class="summary-label">Most Impacted Fabric Mapping</div>
        <div class="summary-value big-status">
          ${s.topPort
            ? escapeHtml(`${safe(s.topPort.switch || s.topPort.node)} / ${safe(s.topPort.switch_interface || s.topPort.switch_port || s.topPort.interface)}`)
            : "No impacted fabric interface ranking available"}
        </div>
      </div>

      <div class="summary-item full-row">
        <div class="summary-label">Live Visibility Status</div>
        <div class="summary-value big-status">${escapeHtml(liveDetailText)}</div>
      </div>

      <div class="summary-item full-row">
        <div class="summary-label">Interpretation</div>
        <div class="summary-value big-status">${escapeHtml(s.narrative)}</div>
      </div>
    </div>
    <div class="exec-summary-extensions">
      ${topUniqueFlowHtml}
      ${rootCauseSummaryHtml}
      ${signalBreakdownHtml}
    </div>
    ${topUniqueFlowsHtml}
  `;
}

function renderCongestionOriginAnalysis(report) {
  const origin = report.congestion_origin_analysis || {};
  const primary = origin.primary_origin_candidate || {};
  const victims = origin.victim_flows || [];
  const topVictim = victims.length ? victims[0] : {};
  const secondary = origin.secondary_hotspots || [];
  const stress = origin.stress_classification || {};
  const causality = origin.causality_assessment || {};
  const baselineCmp = causality.victim_flow_baseline_comparison || {};
  const preCmp = baselineCmp.pre || {};
  const postCmp = baselineCmp.post || {};
  const deltaCmp = baselineCmp.delta || {};

  if (!els.congestionOriginAnalysisBlock) return;

  const fmt = (v) => {
    if (v === undefined || v === null || v === "") return "-";
    if (typeof v === "number") return v.toLocaleString();
    return v;
  };


  const deltaClass = (v) => {
    if (v > 0) return "delta-bad";
    if (v < 0) return "delta-good";
    return "delta-neutral";
  };
  
  const deltaIcon = (v) => {
    if (v > 0) return "🔴";
    if (v < 0) return "🟢";
    return "⚪";
  };
  const confidenceLabel =
    causality.confidence === "high"
      ? "🔴 HIGH (Event caused issue)"
      : causality.confidence === "medium"
      ? "🟡 MEDIUM (Event amplified issue)"
      : causality.confidence === "low"
      ? "🟢 LOW"
      : "-";

  const baselineLabel =
    causality.baseline_gate === "strong"
      ? "🔴 Clean before event → degraded after event"
      : causality.baseline_gate === "moderate"
      ? "🟡 Pre-existing issue → worsened after event"
      : causality.baseline_gate === "weak"
      ? "🟢 Pre-existing issue without clear worsening"
      : "-";
  const secondaryRows = secondary.length
    ? `
      <table class="origin-table">
        <thead>
          <tr>
            <th>Node</th>
            <th>Interface</th>
            <th>Queue</th>
            <th>Classification</th>
            <th>Forwarding Class</th>
          </tr>
        </thead>
        <tbody>
          ${secondary.map(item => `
            <tr>
              <td>${item.node || "-"}</td>
              <td>${item.interface || "-"}</td>
              <td>${item.queue ?? "-"}</td>
              <td>${item.classification || "-"}</td>
              <td>${item.forwarding_class || "-"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `
    : `<div class="origin-text">No secondary hotspots available.</div>`;

  els.congestionOriginAnalysisBlock.innerHTML = `
    <div class="origin-section">
      <div class="origin-grid">
        <div class="origin-kv">
          <div><strong>Event Nodes:</strong> ${(origin.event_nodes || []).join(", ") || "-"}</div>
          <div><strong>Event Target Count:</strong> ${origin.event_target_count ?? "-"}</div>
          <div><strong>Impact Scope:</strong> ${origin.impact_scope || "-"}</div>
        </div>
        <div class="origin-kv">
          <div><strong>Stress Classification:</strong> <span class="origin-badge">${stress.classification || "-"}</span></div>
          <div><strong>Reason:</strong> ${stress.reason || "-"}</div>
        </div>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Causality Assessment</h4>
        <div class="origin-grid">
          <div class="origin-kv">
            <div><strong>Confidence:</strong> ${confidenceLabel}</div>
            <div><strong>Baseline:</strong> ${baselineLabel}</div>
            <div><strong>Score:</strong> ${causality.score ?? "-"}</div>
          </div>
          <div class="origin-kv">
            <div><strong>Reason:</strong> ${causality.reason || "-"}</div>
          </div>
        </div>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Victim Flow Impact (Pre vs Post)</h4>
        <table class="origin-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Pre</th>
              <th>Post</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Loss</td>
              <td>${fmt(preCmp.loss)}</td>
              <td>${fmt(postCmp.loss)}</td>
	      <td class="${deltaClass(deltaCmp.loss)}">${deltaIcon(deltaCmp.loss)} ${fmt(deltaCmp.loss)}</td>
            </tr>
            <tr>
              <td>Message Failed</td>
              <td>${fmt(preCmp.message_failed)}</td>
              <td>${fmt(postCmp.message_failed)}</td>
              <td class="${deltaClass(deltaCmp.message_failed)}">${fmt(deltaCmp.message_failed)}</td>
            </tr>
            <tr>
              <td>ECN Pressure</td>
              <td>${fmt(preCmp.ecn_pressure)}</td>
              <td>${fmt(postCmp.ecn_pressure)}</td>
              <td class="${deltaClass(deltaCmp.ecn_pressure)}">${fmt(deltaCmp.ecn_pressure)}</td>
            </tr>
            <tr>
              <td>CNP Pressure</td>
              <td>${fmt(preCmp.cnp_pressure)}</td>
              <td>${fmt(postCmp.cnp_pressure)}</td>
              <td class="${deltaClass(deltaCmp.cnp_pressure)}">${fmt(deltaCmp.cnp_pressure)}</td>
            </tr>
            <tr>
              <td>Latency (ns)</td>
              <td>${fmt(preCmp.latency)}</td>
              <td>${fmt(postCmp.latency)}</td>
              <td class="${deltaClass(deltaCmp.latency)}">${fmt(deltaCmp.latency)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Primary Origin Candidate</h4>
        <div class="origin-grid">
          <div class="origin-kv">
            <div><strong>Node:</strong> ${primary.node || "-"}</div>
            <div><strong>Interface:</strong> ${primary.interface || "-"}</div>
            <div><strong>Queue:</strong> ${primary.queue ?? "-"}</div>
            <div><strong>Classification:</strong> ${primary.classification || "-"}</div>
          </div>
          <div class="origin-kv">
            <div><strong>Confidence:</strong> ${primary.confidence ?? "-"}</div>
            <div><strong>Event Outcome:</strong> ${primary.event_outcome || "-"}</div>
            <div><strong>Recovery Trend:</strong> ${primary.recovery_trend || "-"}</div>
            <div><strong>Persistence Ratio:</strong> ${primary.persistence_ratio ?? "-"}</div>
          </div>
        </div>
        <div class="origin-text"><strong>Reason:</strong> ${primary.reason || "-"}</div>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Top Victim Flow</h4>
        <div class="origin-grid">
          <div class="origin-kv">
            <div><strong>TX:</strong> ${topVictim.tx_switch || "-"} / ${topVictim.tx_switch_interface || "-"}</div>
            <div><strong>RX:</strong> ${topVictim.rx_switch || "-"} / ${topVictim.rx_switch_interface || "-"}</div>
          </div>
          <div class="origin-kv">
            <div><strong>Flow:</strong> ${topVictim.flow_name || "-"}</div>
            <div><strong>Observed At:</strong> ${topVictim.observed_at || "-"}</div>
            <div><strong>Findings:</strong> ${topVictim.finding_count ?? "-"}</div>
          </div>
        </div>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Secondary Hotspots</h4>
        <div class="origin-table-wrap">
          ${secondaryRows}
        </div>
      </div>

      <hr />

      <div class="origin-block">
        <h4>Propagation Hypothesis</h4>
        <div class="origin-text">${origin.propagation_hypothesis || "-"}</div>
      </div>
    </div>
  `;
}

function renderWorstRxPorts(report) {
  if (!els.worstRxPortsBlock) return;

  const traffic = report.traffic_health || {};
  const rows = topN(traffic.worst_rx_ports, 10);

  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveError = safe(traffic.live_error, "");

  const artifactSeqerror =
    safeArray(traffic.rocev2_top_seqerror_flows).length ||
    safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror).length ||
    safeArray(report.rocev2_deep_inspection?.top_by_seqerror).length;

  const artifactPostIncrease =
    safeArray(traffic.rocev2_top_post_seqerror_increase_flows).length ||
    safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror_increase).length ||
    safeArray(report.rocev2_deep_inspection?.top_by_seqerror_increase).length;

  if (!rows.length) {
    let message = "No impacted fabric interfaces were derived from live traffic evidence.";

    if (liveRequested && !liveAvailable) {
      message = liveError
        ? `Live IXIA statistics were unavailable (${liveError}). No impacted fabric interfaces could be derived from live traffic views for this run.`
        : "Live IXIA statistics were unavailable. No impacted fabric interfaces could be derived from live traffic views for this run.";
    } else if (!liveRequested) {
      message = "Live IXIA statistics were disabled for this run. Impacted fabric interface ranking is not available from live traffic views.";
    } else if (artifactSeqerror || artifactPostIncrease) {
      message = "No impacted fabric interfaces were derived from live traffic views. Use the RoCE SeqError and post-SeqError panels for artifact-backed flow-level evidence.";
    }

    els.worstRxPortsBlock.innerHTML = `
      <div class="empty-state">${escapeHtml(message)}</div>
    `;
    return;
  }

  els.worstRxPortsBlock.innerHTML = `
    <div class="table-note">
      Fabric-first traffic view showing which switch interfaces appear most impacted from live IXIA / RoCE evidence.
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Node</th>
          <th>Interface</th>
          <th>RX Port</th>
          <th>Impact</th>
          <th>Severity</th>
          <th>Key Metric</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => {
          const entityKey = buildTrafficEntityId(row);
          return `
            <tr class="clickable-row" data-traffic-entity="${escapeHtml(entityKey)}">
              <td>${escapeHtml(safe(row.switch || row.node))}</td>
              <td class="mono-text">${escapeHtml(safe(row.switch_interface || row.switch_port || row.interface))}</td>
              <td>${escapeHtml(safe(row.rx_port || row.port || row.name))}</td>
              <td>${escapeHtml(classifyTrafficImpact(row))}</td>
              <td>${escapeHtml(classifyTrafficSeverity(row))}</td>
              <td>${escapeHtml(trafficKeyMetric(row))}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;

  els.worstRxPortsBlock.querySelectorAll("[data-traffic-entity]").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      const entityPrefix = rowEl.getAttribute("data-traffic-entity");
      if (!entityPrefix) return;

      const matched = state.filteredEntities.find((entity) => {
        const data = entity.data || {};
        return `${safe(data.node, "")}|${safe(data.interface, "")}` === entityPrefix;
      });

      if (!matched) return;

      const buttons = els.entityList.querySelectorAll(".entity-btn");
      buttons.forEach((btn) => {
        const active = btn.dataset.entityId === matched.entity_id;
        btn.classList.toggle("active", active);
      });

      renderEvidence(report, matched.entity_id);

      const evidenceCard = document.getElementById("evidenceBlock");
      if (evidenceCard) {
        evidenceCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}
function generateTrafficRecoveryInterpretation(report) {
  const traffic = report.traffic_health || {};
  const worstRx = safeArray(traffic.worst_rx_ports);
  const deepRx = safeArray(traffic.deep_rx_hotspots);
  const trafficVerdict = String(traffic.traffic_verdict || "unknown").toLowerCase();
  const roceVerdict = String(traffic.rocev2_verdict || "unknown").toLowerCase();

  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveError = safe(traffic.live_error, "");

  const structuredSeqerror =
    safeArray(traffic.rocev2_top_seqerror_flows).length ||
    safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror).length ||
    safeArray(report.rocev2_deep_inspection?.top_by_seqerror).length;

  const structuredPostIncrease =
    safeArray(traffic.rocev2_top_post_seqerror_increase_flows).length ||
    safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror_increase).length ||
    safeArray(report.rocev2_deep_inspection?.top_by_seqerror_increase).length;

  const hasArtifactTrafficEvidence =
    structuredSeqerror > 0 ||
    structuredPostIncrease > 0 ||
    Number((traffic.rocev2_summary || {}).total_findings || 0) > 0;

  const hasLiveEvidence = worstRx.length > 0 || deepRx.length > 0;

  if (liveRequested && !liveAvailable) {
    if (hasArtifactTrafficEvidence) {
      return liveError
        ? `Live IXIA statistics were unavailable (${liveError}). Recovery interpretation is based on RoCE pre/post and deep-inspection artifacts rather than real-time IXIA visibility.`
        : "Live IXIA statistics were unavailable. Recovery interpretation is based on RoCE pre/post and deep-inspection artifacts rather than real-time IXIA visibility.";
    }

    return liveError
      ? `Live IXIA statistics were unavailable (${liveError}), and no strong artifact-backed traffic degradation signal was found for this run.`
      : "Live IXIA statistics were unavailable, and no strong artifact-backed traffic degradation signal was found for this run.";
  }

  if (!liveRequested) {
    if (hasArtifactTrafficEvidence) {
      return "Live IXIA statistics were disabled for this run. Recovery interpretation is based on artifact-backed RoCE analysis and should be correlated with CoS hotspots and ECMP recovery behavior.";
    }

    return "Live IXIA statistics were disabled for this run. No strong artifact-backed traffic degradation signal was found in the available RoCE analysis.";
  }

  if (hasLiveEvidence) {
    if (trafficVerdict === "pass" || trafficVerdict === "clean") {
      return "Live IXIA evidence is available and traffic appears recovered with no material persistent RX-side degradation.";
    }

    if (trafficVerdict === "warning") {
      return "Live IXIA evidence shows localized or transient degradation. Validate whether the impact persists into post-recovery before treating it as a defect.";
    }

    if (trafficVerdict === "fail") {
      return "Live IXIA evidence shows persistent degradation and should be treated as a strong bug candidate when aligned with CoS or ECMP evidence.";
    }

    return "Live IXIA evidence is partially available. Use it together with RoCE deep-inspection artifacts to determine whether recovery is complete or degraded.";
  }

  if (hasArtifactTrafficEvidence) {
    if (roceVerdict === "pass") {
      return "RoCE artifact analysis completed and does not indicate a strong persistent post-event traffic failure, but live IXIA visibility is limited.";
    }

    return "RoCE artifact analysis indicates traffic-side degradation and should be correlated with CoS hotspots, ECMP recovery behavior, and root-cause correlation output.";
  }

  return "Traffic recovery could not be strongly characterized from the currently available live or artifact-backed traffic evidence.";
}

function renderTrafficRecoveryInterpretation(report) {
  if (!els.trafficRecoveryBlock) return;
  els.trafficRecoveryBlock.innerHTML = `
    <div class="summary-text">
      ${escapeHtml(generateTrafficRecoveryInterpretation(report))}
    </div>
  `;
}

function renderRoceSeqerrorFlows(report) {
  if (!els.roceSeqerrorFlowsBlock) return;

  const traffic = report.traffic_health || {};
  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveError = safe(traffic.live_error, "");

  // Prefer structured artifact-backed rows first
  const structured =
    topN(
      traffic.rocev2_top_seqerror_flows ||
      traffic.rocev2_deep_inspection?.top_by_seqerror ||
      report.rocev2_deep_inspection?.top_by_seqerror,
      10
    );

  const parsed = parseRoceTextSections(
    traffic.rocev2_deep_inspection_text ||
    report.rocev2_deep_inspection_text ||
    ""
  );

  if (structured.length) {
    els.roceSeqerrorFlowsBlock.innerHTML = `
      <div class="table-note">
        Top RoCEv2 flows ranked by sequence-error evidence from artifact-backed analysis.
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Flow</th>
            <th>RX Port</th>
            <th>SeqError</th>
            <th>Max Latency (ns)</th>
            <th>ECN-CE RX</th>
          </tr>
        </thead>
        <tbody>
          ${structured.map((r) => `
            <tr>
              <td>${escapeHtml(safe(r.flow_name || r.flow_id || r.flow_key))}</td>
              <td>${escapeHtml(safe(r.rx_port))}</td>
              <td>${escapeHtml(formatNumber(
                r.frames_seqerror || r.seqerror || r.seq_error || 0
              ))}</td>
              <td>${escapeHtml(formatNumber(r.max_latency_ns || 0))}</td>
              <td>${escapeHtml(formatNumber(r.ecn ?? 0))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
    return;
  }

  if (parsed.topSeqerror.length) {
    els.roceSeqerrorFlowsBlock.innerHTML = `
      <div class="table-note">
        Structured flow rows are unavailable; showing parsed RoCE deep-inspection text.
      </div>
      <pre>${escapeHtml(parsed.topSeqerror.join("\n"))}</pre>
    `;
    return;
  }

  let message = "No packet reordering or corruption indicators were detected.";

  if (liveRequested && !liveAvailable) {
    message = liveError
      ? `Live IXIA statistics were unavailable (${liveError}). No artifact-backed SeqError flow details were found for this run.`
      : "Live IXIA statistics were unavailable. No artifact-backed SeqError flow details were found for this run.";
  }

  els.roceSeqerrorFlowsBlock.innerHTML = `
    <div class="empty-state">${escapeHtml(message)}</div>
  `;
}

function renderRocePostSeqerrorFlows(report) {
  if (!els.rocePostSeqerrorFlowsBlock) return;

  const traffic = report.traffic_health || {};
  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveError = safe(traffic.live_error, "");

  // Prefer structured artifact-backed rows first
  const structured =
    topN(
      traffic.rocev2_top_post_seqerror_increase_flows ||
      traffic.rocev2_deep_inspection?.top_by_seqerror_increase ||
      report.rocev2_deep_inspection?.top_by_seqerror_increase,
      10
    );

  const parsed = parseRoceTextSections(
    traffic.rocev2_deep_inspection_text ||
    report.rocev2_deep_inspection_text ||
    ""
  );

  if (structured.length) {
    els.rocePostSeqerrorFlowsBlock.innerHTML = `
      <div class="table-note">
        Top RoCEv2 flows ranked by post-event sequence-error increase from artifact-backed analysis.
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>Flow</th>
            <th>RX Port</th>
            <th>Post SeqError Increase</th>
            <th>Max Latency (ns)</th>
            <th>ECN-CE RX</th>
          </tr>
        </thead>
        <tbody>
          ${structured.map((r) => `
            <tr>
              <td>${escapeHtml(safe(r.flow_name || r.flow_id || r.flow_key))}</td>
              <td>${escapeHtml(safe(r.rx_port))}</td>
              <td>${escapeHtml(formatNumber(
                r.post_seqerror_increase ||
                r.seqerror_increase ||
                r.frames_seqerror_increase ||
                0
              ))}</td>
              <td>${escapeHtml(formatNumber(r.max_latency_ns || 0))}</td>
              <td>${escapeHtml(formatNumber(r.ecn ?? 0))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
    return;
  }

  if (parsed.topPostSeqerrorIncrease.length) {
    els.rocePostSeqerrorFlowsBlock.innerHTML = `
      <div class="table-note">
        Structured flow rows are unavailable; showing parsed RoCE deep-inspection text.
      </div>
      <pre>${escapeHtml(parsed.topPostSeqerrorIncrease.join("\n"))}</pre>
    `;
    return;
  }

  let message = "No post-event SeqError increase was detected.";

  if (liveRequested && !liveAvailable) {
    message = liveError
      ? `Live IXIA statistics were unavailable (${liveError}). No artifact-backed post-SeqError increase details were found for this run.`
      : "Live IXIA statistics were unavailable. No artifact-backed post-SeqError increase details were found for this run.";
  }

  els.rocePostSeqerrorFlowsBlock.innerHTML = `
    <div class="empty-state">${escapeHtml(message)}</div>
  `;
}

function generateTrafficFabricCorrelation(report) {
  const traffic = report.traffic_health || {};
  const topCos = report.cos_health?.top_cos_hotspot || null;

  const worstRx = safeArray(traffic.worst_rx_ports);
  const liveRequested = !!traffic.live_requested;
  const liveAvailable = !!traffic.live_available;
  const liveError = safe(traffic.live_error, "");

  const roceVerdict = safe(traffic.rocev2_verdict, "unknown");
  const trafficVerdict = safe(traffic.traffic_verdict, "unknown");

  const topSeqerror =
    safeArray(traffic.rocev2_top_seqerror_flows).length
      ? safeArray(traffic.rocev2_top_seqerror_flows)
      : safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror).length
      ? safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror)
      : safeArray(report.rocev2_deep_inspection?.top_by_seqerror);

  const topPostIncrease =
    safeArray(traffic.rocev2_top_post_seqerror_increase_flows).length
      ? safeArray(traffic.rocev2_top_post_seqerror_increase_flows)
      : safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror_increase).length
      ? safeArray(traffic.rocev2_deep_inspection?.top_by_seqerror_increase)
      : safeArray(report.rocev2_deep_inspection?.top_by_seqerror_increase);

  const topRoceFlow = topSeqerror[0] || topPostIncrease[0] || null;

  if (!topCos && !worstRx.length && !topRoceFlow) {
    return "No strong traffic-to-fabric correlation could be established from the available evidence.";
  }

  let text = "";

  if (topCos) {
    text += `Top fabric hotspot is ${topCos.node} ${topCos.interface} q${topCos.queue}`;
    if (topCos.classification) {
      text += ` (${topCos.classification})`;
    }
    text += ". ";
  }

  if (worstRx.length) {
    const p = worstRx[0];
    text += `Top impacted fabric interface from live traffic evidence is ${safe(p.switch || p.node)} ${safe(p.switch_interface || p.switch_port || p.interface)}. `;
  } else if (topRoceFlow) {
    text += `Top RoCE artifact signal is associated with flow ${safe(topRoceFlow.flow_name || topRoceFlow.flow_id || topRoceFlow.flow_key)} on RX port ${safe(topRoceFlow.rx_port)}. `;
  }

  text += `Traffic verdict is ${trafficVerdict} and RoCEv2 verdict is ${roceVerdict}. `;

  if (liveRequested && !liveAvailable) {
    text += liveError
      ? `Correlation confidence is based primarily on artifact-backed RoCE evidence because live IXIA statistics were unavailable (${liveError}).`
      : "Correlation confidence is based primarily on artifact-backed RoCE evidence because live IXIA statistics were unavailable.";
  } else if (!liveRequested) {
    text += "Correlation confidence is based primarily on artifact-backed RoCE evidence because live IXIA statistics were disabled for this run.";
  } else if (String(trafficVerdict).toLowerCase() === "unknown") {
    text += "Correlation confidence is limited because live traffic detail is incomplete.";
  } else {
    text += "Use this alignment to determine whether queue-pressure evidence is reflected in traffic-side degradation.";
  }

  return text.trim();
}

function renderTrafficFabricCorrelation(report) {
  if (!els.trafficFabricCorrelationBlock) return;
  els.trafficFabricCorrelationBlock.innerHTML = `
    <div class="summary-text">
      ${escapeHtml(generateTrafficFabricCorrelation(report))}
    </div>
  `;
}

function ecmpGroupReasonText(code) {
  const map = {
    group_baseline_preexisting_skew: "Baseline skew already existed across the ECMP group",
    group_recovery_stable: "Post-event distribution is stable across the group",
    group_persistent_mixed_speed_skew: "Capacity-weighted 400G/100G mismatch is informational under equal-score ECMP mode",
    group_no_post_recovery_improvement: "No event-induced ECMP regression detected; distribution remained stable",
    group_recovered_cleanly: "ECMP group recovered cleanly after the event",
    group_speed_aligned_after_recovery: "Post-recovery distribution matches speed-weighted expectation",
    group_contains_abnormal_targets: "Some ECMP targets still show abnormal recovery behavior",
    group_equal_score_expected: "ECMP distribution follows equal-score member behavior",
    group_capacity_weight_informational: "Capacity-weighted 400G/100G comparison is informational only",
    group_degraded_warn: "Degraded hold completed, but survivor spread exceeded tolerance",

    persistent_ecmp_misalignment: "Persistent ECMP imbalance remains after recovery",
    persistent_ecmp_misalignment_with_pressure: "Persistent ECMP imbalance is correlated with congestion pressure",

  };
  return map[code] || code;
}

function renderMixedSpeedSpecValidationFromTarget(target) {
  const expected = target.expected_group_shares || {};
  const actual = target.recovery_group_shares || {};

  const speedGroups = Object.keys(expected);
  if (!speedGroups.length) return "";

  const tolerancePct = 15.0;

  const toPct = (value) => {
    const num = Number(value || 0);
    return num <= 1.0 ? num * 100.0 : num;
  };

  const mixedSpec = target.mixed_speed_spec_validation_ui || {};
  const isInformational =
    mixedSpec.overall_status === "informational" ||
    mixedSpec.status === "informational";

  const specTitle = mixedSpec.title || "Mixed-Speed ECMP Spec Validation";
  const specInterpretation = mixedSpec.interpretation || "";

  const overallOutOfSpec = speedGroups.some((speed) => {
    const exp = toPct(expected[speed]);
    const act = toPct(actual[speed]);
    return (
      act < Math.max(0, exp - tolerancePct) ||
      act > Math.min(100, exp + tolerancePct)
    );
  });

  const specSummaryText = specInterpretation || (
    overallOutOfSpec
      ? "Recovery converged, but mixed-speed distribution remains out of spec relative to expected capacity weighting."
      : "Recovery converged and mixed-speed distribution is within the configured tolerance band."
  );

  const rows = speedGroups.map((speed) => {
    const exp = toPct(expected[speed]);
    const act = toPct(actual[speed]);
    const min = Math.max(0, exp - tolerancePct);
    const max = Math.min(100, exp + tolerancePct);
    const deviation = act - exp;
    const inSpec = act >= min && act <= max;

    const statusBadge = inSpec
      ? '<span class="verdict-badge verdict-pass">In spec</span>'
      : isInformational
        ? '<span class="verdict-badge verdict-watch">Informational mismatch</span>'
        : '<span class="verdict-badge verdict-fail">Out of spec</span>';

    return `
      <tr>
        <td>${escapeHtml(speed)}</td>
        <td>${exp.toFixed(1)}%</td>
        <td>${act.toFixed(1)}%</td>
        <td class="range-cell">${min.toFixed(1)}–${max.toFixed(1)}%</td>
        <td class="${Math.abs(deviation) > tolerancePct ? "deviation-bad" : "deviation-ok"}">
          ${deviation > 0 ? "+" : ""}${deviation.toFixed(1)}%
        </td>
        <td>${statusBadge}</td>
      </tr>
    `;
  }).join("");

  const overallBadge = isInformational
    ? '<span class="verdict-badge verdict-watch">informational</span>'
    : overallOutOfSpec
      ? '<span class="verdict-badge verdict-fail">out_of_spec</span>'
      : '<span class="verdict-badge verdict-pass">in_spec</span>';

  return `
    <div class="evidence-card full-width">
      <h4>${escapeHtml(specTitle)}</h4>
      <div class="spec-validation-wrap">
        <div class="summary-grid summary-grid-3">
          <div class="summary-item">
            <div class="summary-label">Overall Status</div>
            <div class="summary-value">${overallBadge}</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Tolerance</div>
            <div class="summary-value">±${tolerancePct.toFixed(1)}%</div>
          </div>
          <div class="summary-item">
            <div class="summary-label">Traffic Start Mode</div>
            <div class="summary-value">all_at_once</div>
          </div>
        </div>

        <table class="data-table compact-table spec-validation-table">
          <thead>
            <tr>
              <th>Speed Group</th>
              <th>Expected</th>
              <th>Actual</th>
              <th>Allowed Range</th>
              <th>Deviation</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>

        <div class="spec-summary">${escapeHtml(specSummaryText)}</div>
      </div>
    </div>
  `;
}

function ecmpReasonText(code) {
  const map = {
    baseline_already_skewed: "Baseline ECMP distribution was already imbalanced",
    recovery_distribution_stable: "Post-event distribution is stable (no oscillation)",
    persistent_mixed_speed_skew: "Traffic remains misaligned across mixed-speed links",
    no_dominant_member: "No single link is overloaded or dominant",
    baseline_remained_problematic: "Recovery did not improve the pre-existing imbalance",
    recovery_abnormal_but_not_strong_enough: "Recovery is abnormal, but not strong enough for the old defect rule",
    persistent_ecmp_misalignment: "Persistent ECMP imbalance remains after recovery",
    persistent_ecmp_misalignment_with_pressure: "Persistent ECMP imbalance is correlated with congestion pressure",

    group_baseline_preexisting_skew: "Baseline skew already existed across the ECMP group",
    group_recovery_stable: "Post-event distribution is stable across the group",
    group_persistent_mixed_speed_skew: "Traffic remains misaligned across mixed-speed links",
    group_no_post_recovery_improvement: "Recovery did not improve the pre-existing imbalance",
    group_recovered_cleanly: "ECMP group recovered cleanly after the event",
    group_speed_aligned_after_recovery: "Post-recovery distribution matches speed-weighted expectation",
    group_contains_abnormal_targets: "Some ECMP targets still show abnormal recovery behavior",
  };
  return map[code] || code;
}

init();
