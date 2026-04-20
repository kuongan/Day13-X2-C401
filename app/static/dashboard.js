const state = {
  autoRefresh: true,
  timer: null,
  loadedRecords: [],
  isRunningQueries: false,
  execution: {
    executed: 0,
    success: 0,
    failed: 0,
    avgLatencyMs: 0,
  },
};

const chartConfig = {
  width: 640,
  height: 240,
  padding: { top: 18, right: 18, bottom: 36, left: 52 },
};

const el = {
  windowInput: document.getElementById("windowInput"),
  bucketInput: document.getElementById("bucketInput"),
  refreshBtn: document.getElementById("refreshBtn"),
  autoRefreshBtn: document.getElementById("autoRefreshBtn"),
  runQueriesBtn: document.getElementById("runQueriesBtn"),
  windowLabel: document.getElementById("windowLabel"),
  generatedAt: document.getElementById("generatedAt"),
  trafficValue: document.getElementById("trafficValue"),
  latencyValue: document.getElementById("latencyValue"),
  errorRateValue: document.getElementById("errorRateValue"),
  costValue: document.getElementById("costValue"),
  fileInput: document.getElementById("fileInput"),
  fileStatus: document.getElementById("fileStatus"),
  runStatus: document.getElementById("runStatus"),
  recordsCount: document.getElementById("recordsCount"),
  usersCount: document.getElementById("usersCount"),
  sessionsCount: document.getElementById("sessionsCount"),
  messageLength: document.getElementById("messageLength"),
  executedCount: document.getElementById("executedCount"),
  successCount: document.getElementById("successCount"),
  failedCount: document.getElementById("failedCount"),
  avgResponseTime: document.getElementById("avgResponseTime"),
  featureBars: document.getElementById("featureBars"),
  previewBody: document.getElementById("previewBody"),
  latencyChart: document.getElementById("latencyChart"),
  trafficChart: document.getElementById("trafficChart"),
  errorChart: document.getElementById("errorChart"),
  costChart: document.getElementById("costChart"),
  tokensChart: document.getElementById("tokensChart"),
  qualityChart: document.getElementById("qualityChart"),
};

function formatNumber(value, digits = 0) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(Number.isFinite(value) ? value : 0);
}

function formatCurrency(value) {
  return `$${formatNumber(value, 4)}`;
}

function formatPercent(value) {
  return `${formatNumber(value, 2)}%`;
}

function formatMs(value) {
  return `${formatNumber(value, 1)} ms`;
}

function formatDateLabel(iso) {
  const date = new Date(iso);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function loadDashboard() {
  const windowMinutes = Math.max(1, Number(el.windowInput.value) || 60);
  const bucketSeconds = Math.max(10, Number(el.bucketInput.value) || 60);
  const response = await fetch(`/metrics/dashboard?window_minutes=${windowMinutes}&bucket_seconds=${bucketSeconds}`);
  if (!response.ok) {
    throw new Error(`Failed to load dashboard: ${response.status}`);
  }
  const data = await response.json();
  renderDashboard(data);
}

function renderDashboard(data) {
  el.windowLabel.textContent = `${data.window_minutes} minutes`;
  el.generatedAt.textContent = new Date(data.generated_at).toLocaleString();
  el.trafficValue.textContent = formatNumber(data.summary.traffic);
  el.latencyValue.textContent = `${formatNumber(data.summary.latency_p95, 1)} ms`;
  el.errorRateValue.textContent = formatPercent(data.summary.error_rate_pct);
  el.costValue.textContent = formatCurrency(data.summary.total_cost_usd);

  renderLineChart(el.latencyChart, data.panels.latency, [
    { key: "p50_ms", color: "#2057d4", label: "P50" },
    { key: "p95_ms", color: "#cb5a2e", label: "P95" },
    { key: "p99_ms", color: "#b42318", label: "P99" },
  ], { threshold: data.slo_lines.latency_p95_ms, formatter: (v) => `${formatNumber(v, 0)} ms` });

  renderLineChart(el.trafficChart, data.panels.traffic, [
    { key: "requests", color: "#137a63", label: "Requests" },
    { key: "qps", color: "#2057d4", label: "QPS" },
  ], { formatter: (v) => formatNumber(v, 2) });

  renderLineChart(el.errorChart, data.panels.error_rate, [
    { key: "error_rate_pct", color: "#b42318", label: "Error rate" },
  ], { threshold: data.slo_lines.error_rate_pct, formatter: (v) => `${formatNumber(v, 2)}%` });

  renderLineChart(el.costChart, data.panels.cost, [
    { key: "cost_usd", color: "#cb5a2e", label: "Cost" },
    { key: "cost_usd_per_hour", color: "#2057d4", label: "Cost / hour" },
  ], { threshold: data.slo_lines.cost_usd_per_hour, formatter: (v) => formatCurrency(v) });

  renderLineChart(el.tokensChart, data.panels.tokens, [
    { key: "tokens_in", color: "#137a63", label: "Tokens in" },
    { key: "tokens_out", color: "#cc8a11", label: "Tokens out" },
  ], { formatter: (v) => formatNumber(v, 0) });

  renderLineChart(el.qualityChart, data.panels.quality, [
    { key: "quality_avg", color: "#137a63", label: "Quality avg" },
    { key: "hallucination_pct", color: "#b42318", label: "Hallucination %" },
  ], { threshold: data.slo_lines.hallucination_pct, formatter: (v) => formatNumber(v, 2) });
}

function renderLineChart(svg, points, series, options = {}) {
  const { width, height, padding } = chartConfig;
  svg.innerHTML = "";

  if (!Array.isArray(points) || points.length === 0) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#6b5b4a" font-size="14">No data yet</text>`;
    return;
  }

  const values = [];
  points.forEach((point) => {
    series.forEach((item) => values.push(Number(point[item.key] ?? 0)));
  });
  if (Number.isFinite(options.threshold)) {
    values.push(options.threshold);
  }

  const maxValue = Math.max(...values, 1);
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const x = (index) => padding.left + (chartWidth * index) / Math.max(points.length - 1, 1);
  const y = (value) => padding.top + chartHeight - (value / maxValue) * chartHeight;

  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const value = (maxValue / ticks) * (ticks - i);
    const lineY = padding.top + (chartHeight / ticks) * i;
    svg.appendChild(makeLine(padding.left, lineY, width - padding.right, lineY, "rgba(78,61,45,0.12)", 1));
    svg.appendChild(makeText(padding.left - 10, lineY + 4, options.formatter ? options.formatter(value) : formatNumber(value), "#6b5b4a", "11", "end"));
  }

  svg.appendChild(makeLine(padding.left, padding.top, padding.left, height - padding.bottom, "rgba(78,61,45,0.24)", 1.25));
  svg.appendChild(makeLine(padding.left, height - padding.bottom, width - padding.right, height - padding.bottom, "rgba(78,61,45,0.24)", 1.25));

  if (Number.isFinite(options.threshold)) {
    const thresholdY = y(options.threshold);
    const threshold = makeLine(padding.left, thresholdY, width - padding.right, thresholdY, "rgba(180,35,24,0.55)", 2);
    threshold.setAttribute("stroke-dasharray", "6 6");
    svg.appendChild(threshold);
  }

  series.forEach((item) => {
    const path = points.map((point, index) => {
      const value = Number(point[item.key] ?? 0);
      return `${index === 0 ? "M" : "L"} ${x(index)} ${y(value)}`;
    }).join(" ");

    const pathNode = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pathNode.setAttribute("d", path);
    pathNode.setAttribute("fill", "none");
    pathNode.setAttribute("stroke", item.color);
    pathNode.setAttribute("stroke-width", "3");
    pathNode.setAttribute("stroke-linecap", "round");
    pathNode.setAttribute("stroke-linejoin", "round");
    svg.appendChild(pathNode);

    points.forEach((point, index) => {
      const value = Number(point[item.key] ?? 0);
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", x(index));
      circle.setAttribute("cy", y(value));
      circle.setAttribute("r", "3.5");
      circle.setAttribute("fill", item.color);
      svg.appendChild(circle);
    });
  });

  const tickIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  tickIndexes.forEach((index) => {
    svg.appendChild(makeText(x(index), height - 10, formatDateLabel(points[index].ts), "#6b5b4a", "11", "middle"));
  });
}

function makeLine(x1, y1, x2, y2, stroke, width) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", x1);
  line.setAttribute("y1", y1);
  line.setAttribute("x2", x2);
  line.setAttribute("y2", y2);
  line.setAttribute("stroke", stroke);
  line.setAttribute("stroke-width", width);
  return line;
}

function makeText(x, y, text, fill, size, anchor = "start") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "text");
  node.setAttribute("x", x);
  node.setAttribute("y", y);
  node.setAttribute("fill", fill);
  node.setAttribute("font-size", size);
  node.setAttribute("text-anchor", anchor);
  node.textContent = text;
  return node;
}

function parseUploadedRecords(rawText, fileName) {
  if (fileName.toLowerCase().endsWith(".jsonl")) {
    return rawText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  }

  const parsed = JSON.parse(rawText);
  return Array.isArray(parsed) ? parsed : [parsed];
}

function isValidSampleQuery(record) {
  return Boolean(
    record
    && typeof record.user_id === "string"
    && typeof record.session_id === "string"
    && typeof record.feature === "string"
    && typeof record.message === "string"
  );
}

function renderUploadedRecords(records, fileName) {
  const validRecords = records.filter(isValidSampleQuery);
  const invalidCount = records.length - validRecords.length;
  state.loadedRecords = validRecords;

  el.fileStatus.textContent = `${fileName}: loaded ${validRecords.length} valid record(s)` +
    (invalidCount ? `, skipped ${invalidCount} invalid record(s).` : ".");

  const uniqueUsers = new Set(validRecords.map((item) => item.user_id));
  const uniqueSessions = new Set(validRecords.map((item) => item.session_id));
  const avgLength = validRecords.length
    ? validRecords.reduce((sum, item) => sum + item.message.length, 0) / validRecords.length
    : 0;

  el.recordsCount.textContent = formatNumber(validRecords.length);
  el.usersCount.textContent = formatNumber(uniqueUsers.size);
  el.sessionsCount.textContent = formatNumber(uniqueSessions.size);
  el.messageLength.textContent = formatNumber(avgLength, 1);
  el.runQueriesBtn.disabled = validRecords.length === 0;

  resetExecutionSummary();
  renderFeatureBars(validRecords);
  renderPreview(validRecords);
}

function renderFeatureBars(records) {
  if (!records.length) {
    el.featureBars.innerHTML = "No valid records to visualize.";
    el.featureBars.className = "bars-empty";
    return;
  }

  const counts = records.reduce((acc, item) => {
    acc[item.feature] = (acc[item.feature] || 0) + 1;
    return acc;
  }, {});

  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const maxCount = entries[0][1];

  el.featureBars.className = "feature-list";
  el.featureBars.innerHTML = entries.map(([feature, count]) => `
    <div class="feature-row">
      <header>
        <span>${escapeHtml(feature)}</span>
        <strong>${count}</strong>
      </header>
      <div class="feature-track">
        <div class="feature-fill" style="width: ${(count / maxCount) * 100}%"></div>
      </div>
    </div>
  `).join("");
}

function renderPreview(records) {
  if (!records.length) {
    el.previewBody.innerHTML = `<tr><td colspan="4" class="empty-cell">No valid records loaded.</td></tr>`;
    return;
  }

  el.previewBody.innerHTML = records.slice(0, 8).map((record) => `
    <tr>
      <td>${escapeHtml(record.user_id)}</td>
      <td>${escapeHtml(record.session_id)}</td>
      <td>${escapeHtml(record.feature)}</td>
      <td class="message-cell">${escapeHtml(record.message)}</td>
    </tr>
  `).join("");
}

function resetExecutionSummary() {
  state.execution = {
    executed: 0,
    success: 0,
    failed: 0,
    avgLatencyMs: 0,
  };
  syncExecutionSummary();
  el.runStatus.textContent = "Queries have not been executed yet.";
}

function syncExecutionSummary() {
  el.executedCount.textContent = formatNumber(state.execution.executed);
  el.successCount.textContent = formatNumber(state.execution.success);
  el.failedCount.textContent = formatNumber(state.execution.failed);
  el.avgResponseTime.textContent = formatMs(state.execution.avgLatencyMs);
}

async function runLoadedQueries() {
  if (!state.loadedRecords.length || state.isRunningQueries) {
    return;
  }

  state.isRunningQueries = true;
  el.runQueriesBtn.disabled = true;
  el.runStatus.textContent = `Running ${state.loadedRecords.length} query(s) through /chat...`;

  let totalLatency = 0;

  for (let index = 0; index < state.loadedRecords.length; index += 1) {
    const payload = state.loadedRecords[index];
    const startedAt = performance.now();

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const latency = performance.now() - startedAt;
      totalLatency += latency;
      state.execution.executed += 1;

      if (response.ok) {
        state.execution.success += 1;
      } else {
        state.execution.failed += 1;
      }

      state.execution.avgLatencyMs = totalLatency / state.execution.executed;
      syncExecutionSummary();
      el.runStatus.textContent = `Executed ${index + 1}/${state.loadedRecords.length} query(s)...`;
    } catch (error) {
      const latency = performance.now() - startedAt;
      totalLatency += latency;
      state.execution.executed += 1;
      state.execution.failed += 1;
      state.execution.avgLatencyMs = totalLatency / state.execution.executed;
      syncExecutionSummary();
      el.runStatus.textContent = `Stopped on query ${index + 1}: ${error.message}`;
    }
  }

  state.isRunningQueries = false;
  el.runQueriesBtn.disabled = state.loadedRecords.length === 0;
  el.runStatus.textContent = `Finished ${state.execution.executed} query(s): ${state.execution.success} success, ${state.execution.failed} failed. Refreshing dashboard...`;
  await runDashboardRefresh();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toggleAutoRefresh() {
  state.autoRefresh = !state.autoRefresh;
  el.autoRefreshBtn.textContent = state.autoRefresh ? "Pause auto refresh" : "Resume auto refresh";
  window.clearInterval(state.timer);
  if (state.autoRefresh) {
    state.timer = window.setInterval(runDashboardRefresh, 15000);
  }
}

async function runDashboardRefresh() {
  try {
    await loadDashboard();
  } catch (error) {
    el.generatedAt.textContent = "Failed to load";
    console.error(error);
  }
}

el.refreshBtn.addEventListener("click", runDashboardRefresh);
el.autoRefreshBtn.addEventListener("click", toggleAutoRefresh);
el.runQueriesBtn.addEventListener("click", runLoadedQueries);
el.fileInput.addEventListener("change", async (event) => {
  const [file] = event.target.files || [];
  if (!file) {
    return;
  }

  try {
    const content = await file.text();
    const records = parseUploadedRecords(content, file.name);
    renderUploadedRecords(records, file.name);
  } catch (error) {
    state.loadedRecords = [];
    el.runQueriesBtn.disabled = true;
    el.fileStatus.textContent = `Could not parse ${file.name}. Please use valid JSON or JSONL.`;
    console.error(error);
  }
});

state.timer = window.setInterval(runDashboardRefresh, 15000);
resetExecutionSummary();
runDashboardRefresh();
