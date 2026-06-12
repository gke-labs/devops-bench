// =============================================================================
// devops-bench leaderboard — SETUP DETAIL PAGE (detail.html).
//
// Renders one (model × harness) setup in depth. Routing is query-based:
//   detail.html?id=<setup.id>&metric=<pass1|pass5|passMax>
// `id` selects the setup from the shared `setups` array (data.js, loaded first);
// `metric` pre-selects the Pass@N view so it carries over from the leaderboard.
//
// Sections (top -> bottom): identity hero + Pass@N toggle, summary stat cards,
// sortable per-task breakdown, and a single-setup score-over-time chart.
// =============================================================================

const METRIC_LABELS = { pass1: "Pass@1", pass5: "Pass@5", passMax: "Pass^5" };

let detailMetric = "pass1";
let detailSort = { key: "score", dir: "desc" };   // task-table sort state
let currentSetup = null;
let setupTrendChartInstance = null;

// --- small utilities ---------------------------------------------------------
function getQueryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
}

function median(nums) {
    const s = [...nums].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// --- rendering ---------------------------------------------------------------
function renderHero(setup) {
    const model = models[setup.model];
    const harness = harnesses[setup.harness];
    const score = setupScore(setup, detailMetric);

    const tagsHtml = setupTags(setup).map(tag =>
        `<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${tag.cls}">${tag.text}</span>`
    ).join('');
    const typeChip = `<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wide" style="color: ${harness.accent}; background-color: ${harness.accent}1a;">${HARNESS_TYPES[harness.type]}</span>`;

    const metricBtns = ["pass1", "pass5", "passMax"].map(m => {
        const active = m === detailMetric;
        const cls = active
            ? "bg-white text-slate-800 shadow-sm"
            : "text-slate-600 hover:text-slate-800";
        return `<button type="button" onclick="switchDetailMetric('${m}')" aria-pressed="${active}"
                    class="px-2.5 py-1 font-medium rounded-md transition-all duration-200 ${cls} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">
                    ${METRIC_LABELS[m]}
                </button>`;
    }).join('');

    return `
        <div class="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6 flex flex-col lg:flex-row lg:items-center gap-6 justify-between">
            <!-- Pairing identity -->
            <div class="flex items-center gap-3 sm:gap-4 min-w-0">
                <!-- Model entity -->
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="p-1.5 bg-white rounded-lg shadow-sm border border-slate-100 flex-shrink-0 scale-125 origin-left">
                        ${brandLogos[model.logo] || ''}
                    </div>
                    <div class="flex flex-col min-w-0 pl-1">
                        <span class="text-slate-900 font-bold text-base sm:text-lg truncate">${model.name}</span>
                        <span class="text-xs text-slate-400 font-normal truncate">${model.provider}</span>
                    </div>
                </div>
                <!-- Connector -->
                <div aria-hidden="true" class="flex items-center justify-center gap-1.5 shrink-0">
                    <span class="hidden sm:block h-px w-4 bg-gradient-to-r from-transparent to-slate-300"></span>
                    <span class="flex items-center justify-center w-6 h-6 rounded-md text-slate-400 text-base font-medium leading-none ring-1 ring-slate-200/70 bg-slate-50">×</span>
                    <span class="hidden sm:block h-px w-4 bg-gradient-to-l from-transparent to-slate-300"></span>
                </div>
                <!-- Harness entity -->
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="p-1.5 rounded-lg shadow-sm flex-shrink-0 scale-125 origin-left" style="background-color: ${harness.accent}1a; border: 1px solid ${harness.accent}33;">
                        ${harnessIcon(harness)}
                    </div>
                    <div class="flex flex-col min-w-0 pl-1 gap-1">
                        <span class="text-slate-900 font-bold text-base sm:text-lg truncate">${harness.name}</span>
                        <div class="flex flex-wrap items-center gap-1.5">${typeChip}${tagsHtml}</div>
                    </div>
                </div>
            </div>

            <!-- Headline score + metric toggle -->
            <div class="flex flex-col items-start lg:items-end gap-2 shrink-0">
                <div class="flex items-baseline gap-1.5">
                    <span class="text-4xl font-bold text-slate-900">${score.toFixed(1)}<span class="text-2xl">%</span></span>
                    <span class="text-xs font-medium text-slate-400 uppercase tracking-wide">${METRIC_LABELS[detailMetric]}</span>
                </div>
                <div class="inline-flex p-0.5 bg-slate-100 rounded-lg text-[11px]">${metricBtns}</div>
            </div>
        </div>`;
}

function statCard(label, value, sub) {
    return `
        <div class="bg-white rounded-xl border border-slate-200/80 shadow-sm p-4 flex flex-col gap-1">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">${label}</span>
            <span class="text-xl font-bold text-slate-900">${value}</span>
            ${sub ? `<span class="text-[10px] text-slate-400">${sub}</span>` : ''}
        </div>`;
}

function renderSummary(setup) {
    const vals = setup.tasks.map(t => t.scores[detailMetric]);
    const best = Math.max(...vals);
    const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
    const med = median(vals);
    // Cost/Speed deliberately N/A — latency/token capture isn't normalized yet.
    return `
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 w-full">
            ${statCard("Best Task", `${best.toFixed(1)}%`, METRIC_LABELS[detailMetric])}
            ${statCard("Average", `${avg.toFixed(1)}%`, `over ${vals.length} tasks`)}
            ${statCard("Median", `${med.toFixed(1)}%`, METRIC_LABELS[detailMetric])}
            ${statCard("Avg Cost", "N/A", "not captured yet")}
            ${statCard("Avg Speed", "N/A", "not captured yet")}
        </div>`;
}

function renderTaskTable(setup) {
    const color = setup.color;
    const tasks = [...setup.tasks].sort((a, b) => {
        const dir = detailSort.dir === "asc" ? 1 : -1;
        if (detailSort.key === "name") return dir * a.name.localeCompare(b.name);
        return dir * (a.scores[detailMetric] - b.scores[detailMetric]);
    });

    const arrow = (key) => detailSort.key === key
        ? `<span class="text-indigo-500">${detailSort.dir === "asc" ? "▲" : "▼"}</span>`
        : `<span class="text-slate-300">↕</span>`;

    const rows = tasks.map(task => {
        const s = task.scores[detailMetric];
        return `
            <tr class="border-t border-slate-100">
                <td class="py-3 pr-4">
                    <div class="flex flex-col">
                        <span class="font-semibold text-slate-700 text-sm">${task.name}</span>
                        <span class="text-[10px] font-mono text-slate-400 mt-0.5">${task.folder}/</span>
                    </div>
                </td>
                <td class="py-3 pr-4 w-1/2">
                    <div class="flex items-center gap-3">
                        <div class="flex-grow bg-slate-100 h-2 rounded-full overflow-hidden">
                            <div class="progress-bar-fill h-full rounded-full" style="width: ${s}%; background-color: ${color};"></div>
                        </div>
                        <span class="text-sm font-semibold text-slate-700 w-12 text-right shrink-0">${s}%</span>
                    </div>
                </td>
            </tr>`;
    }).join('');

    return `
        <div class="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-6">
            <div class="mb-3 font-semibold text-slate-500 tracking-wider uppercase text-xs">Granular Task Breakdown</div>
            <table class="w-full text-left">
                <thead>
                    <tr class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 select-none">
                        <th class="pb-2 pr-4 cursor-pointer" onclick="sortTasks('name')">Task ${arrow("name")}</th>
                        <th class="pb-2 pr-4 cursor-pointer" onclick="sortTasks('score')">Score (${METRIC_LABELS[detailMetric]}) ${arrow("score")}</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function renderNotFound(id) {
    document.getElementById('detail-content').innerHTML = `
        <div class="w-full bg-white rounded-2xl border border-slate-200/80 shadow-xl shadow-slate-100 p-10 flex flex-col items-center text-center gap-3">
            <svg class="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <p class="text-sm font-medium text-slate-600">No setup found for <span class="font-mono text-slate-800">${id || "(missing id)"}</span>.</p>
            <a href="index.html" class="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">Return to the leaderboard</a>
        </div>`;
}

// Re-render the metric-dependent sections (hero + summary + table).
function renderDetail() {
    document.getElementById('detail-content').innerHTML =
        renderHero(currentSetup) + renderSummary(currentSetup) + renderTaskTable(currentSetup);
}

// --- interactions ------------------------------------------------------------
function switchDetailMetric(metric) {
    detailMetric = metric;
    renderDetail();
    updateSetupChart();
}

function sortTasks(key) {
    if (detailSort.key === key) {
        detailSort.dir = detailSort.dir === "asc" ? "desc" : "asc";
    } else {
        detailSort.key = key;
        detailSort.dir = key === "name" ? "asc" : "desc";
    }
    renderDetail();
}

// --- single-setup trend chart ------------------------------------------------
function initSetupChart() {
    const canvas = document.getElementById('setupTrendChart');
    if (!canvas || typeof Chart === "undefined") return;
    const ctx = canvas.getContext('2d');

    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = "#64748b";
    Chart.defaults.plugins.tooltip.backgroundColor = "#0f172a";
    Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
    Chart.defaults.plugins.tooltip.bodyColor = "#cbd5e1";
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;

    setupTrendChartInstance = new Chart(ctx, {
        type: 'line',
        data: { datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'nearest', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => items.length ? formatRunDate(items[0].parsed.x) : '',
                        label: (ctx) => ` ${METRIC_LABELS[detailMetric]}: ${ctx.parsed.y.toFixed(1)}%`
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    bounds: 'data',
                    // Real time axis: ticks land on this setup's actual run dates.
                    afterBuildTicks: (axis) => {
                        axis.ticks = (currentSetup ? currentSetup.history : []).map(h => ({ value: Date.parse(h.t) }));
                    },
                    grid: { display: false },
                    ticks: { callback: (v) => formatRunDate(v), maxRotation: 0, autoSkip: false, padding: 8 }
                },
                y: {
                    min: 60, max: 100,
                    border: { display: false },
                    grid: { color: "#f1f5f9" },
                    ticks: { callback: (v) => v + '%', stepSize: 10, padding: 8 }
                }
            },
            elements: {
                line: { tension: 0.35, borderWidth: 3 },
                point: { radius: 3, hitRadius: 12, hoverRadius: 6, hoverBackgroundColor: '#ffffff', hoverBorderWidth: 3 }
            }
        }
    });
    updateSetupChart();
}

function updateSetupChart() {
    if (!setupTrendChartInstance || !currentSetup) return;
    const color = currentSetup.color;
    setupTrendChartInstance.data.datasets = [{
        label: setupLabel(currentSetup),
        data: setupHistory(currentSetup, detailMetric),
        borderColor: color,
        backgroundColor: `${color}1a`,
        pointBorderColor: color,
        pointBackgroundColor: color,
        fill: true
    }];
    setupTrendChartInstance.update();

    const table = document.getElementById('setup-trend-table');
    if (table) {
        const hist = currentSetup.history;
        table.innerHTML = `
            <caption>Score trend for ${setupLabel(currentSetup)} (metric: ${detailMetric})</caption>
            <thead><tr><th scope="col">Setup</th>${hist.map(h => `<th scope="col">${formatRunDate(h.t)}</th>`).join('')}</tr></thead>
            <tbody><tr><th scope="row">${setupLabel(currentSetup)}</th>${hist.map(h => `<td>${h.scores[detailMetric].toFixed(1)}%</td>`).join('')}</tr></tbody>`;
    }
}

// --- init --------------------------------------------------------------------
window.onload = function() {
    const id = getQueryParam('id');
    const metric = getQueryParam('metric');
    if (metric && METRIC_LABELS[metric]) detailMetric = metric;

    currentSetup = setups.find(s => s.id === id) || null;

    if (!currentSetup) {
        renderNotFound(id);
        return;
    }

    document.title = `${setupLabel(currentSetup)} · Agent DevOps Benchmark`;
    renderDetail();

    // Reveal + populate the trend chart now that we have a valid setup.
    const section = document.getElementById('trend-section');
    if (section) {
        section.classList.remove('hidden');
        section.classList.add('flex');
    }
    initSetupChart();
};
