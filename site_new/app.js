// =============================================================================
// devops-bench leaderboard — LEADERBOARD PAGE (index.html).
//
// The data model, derived accessors, and shared logos live in data.js, which
// MUST be loaded before this file. This file is purely the leaderboard view:
//   1. FILTERING ...... faceted multi-select over the setup dimensions
//   2. RENDERING ...... leaderboard rows (each LINKS to detail.html)
//   3. TREND CHART .... Chart.js line chart of score-over-time
//
// Rows no longer expand inline — clicking a row navigates to a dedicated
// detail page (detail.html?id=<setup.id>) so the leaderboard stays uncluttered.
// =============================================================================

let currentMetric = 'pass1';
let trendChartInstance = null;

// --- 1. FILTERING ------------------------------------------------------------
//
// Faceted multi-select filter over the setup dimensions. Each group holds a Set
// of selected values; WITHIN a group the selected values are OR'd, ACROSS groups
// they are AND'd (standard faceted behavior). An empty group means "no filter"
// for that dimension. getFilteredSetups() is the single source the leaderboard
// AND the trend chart both read from, so any selection change is reflected
// everywhere via filterAndRender() + updateTrendChart().

const filterState = {
    model: new Set(),
    harness: new Set(),
    augmentation: new Set(),
    mcp: new Set()        // values: "mcp" | "nomcp"
};

// Group definitions, including how to read the matching value off a setup and a
// `tier`: "primary" facets are the co-equal first-class axes (model, harness);
// "secondary" facets are the modifier layer (augmentation, mcp), rendered more
// quietly. `options()` is derived from the live `setups` so it stays correct
// when real data drops in (e.g. an unused harness simply won't show a chip).
const FILTER_GROUPS = [
    {
        key: "model", label: "Model", tier: "primary",
        valueOf: s => s.model,
        options: () => Object.keys(models)
            .filter(id => setups.some(s => s.model === id))
            .map(id => ({ value: id, text: models[id].name }))
    },
    {
        key: "harness", label: "Harness", tier: "primary",
        valueOf: s => s.harness,
        options: () => Object.keys(harnesses)
            .filter(id => setups.some(s => s.harness === id))
            .map(id => ({ value: id, text: harnesses[id].name }))
    },
    {
        key: "augmentation", label: "Augment", tier: "secondary",
        valueOf: s => s.augmentation,
        options: () => Object.keys(AUGMENTATIONS)
            .filter(a => setups.some(s => s.augmentation === a))
            .map(a => ({ value: a, text: AUGMENTATIONS[a] }))
    },
    {
        key: "mcp", label: "MCP", tier: "secondary",
        valueOf: s => (s.mcp ? "mcp" : "nomcp"),
        options: () => {
            const opts = [];
            if (setups.some(s => s.mcp)) opts.push({ value: "mcp", text: "MCP" });
            if (setups.some(s => !s.mcp)) opts.push({ value: "nomcp", text: "No MCP" });
            return opts;
        }
    }
];

// The setups passing every active facet. Empty facet = match all.
function getFilteredSetups() {
    return setups.filter(setup =>
        FILTER_GROUPS.every(group => {
            const selected = filterState[group.key];
            return selected.size === 0 || selected.has(group.valueOf(setup));
        })
    );
}

function anyFilterActive() {
    return FILTER_GROUPS.some(g => filterState[g.key].size > 0);
}

function toggleFilter(groupKey, value) {
    const set = filterState[groupKey];
    if (set.has(value)) set.delete(value);
    else set.add(value);
    renderFilters();
    filterAndRender();
    updateTrendChart();
}

function clearFilters() {
    FILTER_GROUPS.forEach(g => filterState[g.key].clear());
    renderFilters();
    filterAndRender();
    updateTrendChart();
}

// Renders one filter group (label + chips). `tier` controls weight: primary
// facets (model/harness) get bolder labels and indigo active chips; secondary
// facets (modifiers) get quieter labels and a softer slate active state.
function renderFilterGroup(group) {
    const opts = group.options();
    if (opts.length === 0) return '';
    const primary = group.tier === 'primary';
    const chips = opts.map(opt => {
        const active = filterState[group.key].has(opt.value);
        let cls;
        if (active) {
            cls = primary
                ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                : 'bg-slate-700 text-white border-slate-700 shadow-sm';
        } else {
            cls = 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50';
        }
        const size = primary ? 'px-3 py-1 text-xs' : 'px-2.5 py-0.5 text-[11px]';
        return `<button type="button"
                    onclick="toggleFilter('${group.key}', '${opt.value}')"
                    aria-pressed="${active}"
                    class="${size} rounded-full border font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 ${cls}">
                    ${opt.text}
                </button>`;
    }).join('');
    const labelCls = primary
        ? 'text-[11px] font-bold tracking-wide uppercase text-slate-600'
        : 'text-[10px] font-semibold tracking-wider uppercase text-slate-400';
    return `
        <div class="flex flex-wrap items-center gap-1.5">
            <span class="${labelCls} w-16 shrink-0">${group.label}</span>
            ${chips}
        </div>`;
}

// Renders the two-tier filter bar: the first-class axes (Model × Harness) up
// top, then a divider, then the secondary modifier facets.
function renderFilters() {
    const bar = document.getElementById('filter-bar');
    if (!bar) return;

    const primaryHtml = FILTER_GROUPS.filter(g => g.tier === 'primary')
        .map(renderFilterGroup).join('');
    const secondaryHtml = FILTER_GROUPS.filter(g => g.tier === 'secondary')
        .map(renderFilterGroup).join('');

    const total = setups.length;
    const shown = getFilteredSetups().length;
    const clearBtn = anyFilterActive()
        ? `<button type="button" onclick="clearFilters()"
               class="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded">
               Clear all
           </button>`
        : '';

    bar.innerHTML = `
        <div class="flex items-start justify-between gap-4">
            <div class="flex flex-col gap-2 flex-grow">${primaryHtml}</div>
            <div class="flex items-center gap-3 shrink-0 pt-0.5">
                <span class="text-[11px] text-slate-400 whitespace-nowrap">${shown} of ${total}</span>
                ${clearBtn}
            </div>
        </div>
        <div class="flex items-center gap-2 pt-1 mt-1 border-t border-slate-100">
            <span class="text-[9px] font-semibold tracking-wider uppercase text-slate-300 shrink-0">Modifiers</span>
            <div class="flex flex-col sm:flex-row sm:flex-wrap gap-x-4 gap-y-1 flex-grow pl-1">${secondaryHtml}</div>
        </div>`;
}

// --- 2. RENDERING ------------------------------------------------------------
function switchMetric(metric) {
    currentMetric = metric;
    ['pass1', 'pass5', 'passMax'].forEach(m => {
        const btn = document.getElementById(`btn-${m}`);
        if (btn) {
            if (m === metric) {
                btn.classList.add('bg-white', 'text-slate-800', 'shadow-sm');
                btn.classList.remove('text-slate-600', 'hover:text-slate-800');
                btn.setAttribute('aria-pressed', 'true');
            } else {
                btn.classList.remove('bg-white', 'text-slate-800', 'shadow-sm');
                btn.classList.add('text-slate-600', 'hover:text-slate-800');
                btn.setAttribute('aria-pressed', 'false');
            }
        }
    });
    filterAndRender();
    updateTrendChart();
}

function filterAndRender() {
    const container = document.getElementById('leaderboard-rows');
    if (!container) return;

    // Sort the FILTERED setups by their aggregated score under the selected metric.
    const sortedData = getFilteredSetups()
        .sort((a, b) => setupScore(b, currentMetric) - setupScore(a, currentMetric));

    if (sortedData.length === 0) {
        container.innerHTML = `
            <div class="px-6 py-12 flex flex-col items-center justify-center text-center gap-2">
                <svg class="w-8 h-8 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                </svg>
                <p class="text-sm font-medium text-slate-500">No setups match the selected filters.</p>
                <button type="button" onclick="clearFilters()" class="text-xs font-medium text-indigo-600 hover:text-indigo-800 hover:underline">Clear all filters</button>
            </div>`;
        return;
    }

    container.innerHTML = sortedData.map(setup => {
        const model = models[setup.model];
        const harness = harnesses[setup.harness];
        const color = setup.color;
        const scoreValue = setupScore(setup, currentMetric);

        // The harness configures these — render them nested UNDER the harness:
        // the CLI/API type chip (accent-tinted) followed by the augmentation + MCP modifiers.
        const tagsHtml = setupTags(setup).map(tag =>
            `<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${tag.cls}">${tag.text}</span>`
        ).join('');
        const typeChip = `<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide" style="color: ${harness.accent}; background-color: ${harness.accent}1a;">${HARNESS_TYPES[harness.type]}</span>`;
        const harnessConfigHtml = typeChip + tagsHtml;

        // Each row LINKS to the dedicated detail page (carrying the active metric).
        const href = `detail.html?id=${encodeURIComponent(setup.id)}&metric=${encodeURIComponent(currentMetric)}`;

        return `
            <a href="${href}"
               aria-label="View details for ${setupLabel(setup)}"
               class="relative px-6 py-4 flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 items-start sm:items-center hover:bg-slate-50/70 cursor-pointer transition-colors group select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-inset">

                <!-- Benchmark subject: model × harness pairing (co-equal first-class).
                     Fixed 1fr_auto_1fr sub-grid so the operator and harness align across rows.
                     Harness config (type + augmentation + MCP) nests beneath the harness. -->
                <div class="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2 w-full sm:w-auto pr-6 sm:pr-0">
                    <!-- Model entity -->
                    <div class="flex items-center gap-2 min-w-0">
                        <div class="p-1 bg-white rounded-md shadow-sm border border-slate-100 flex-shrink-0 group-hover:scale-105 transition-transform">
                            ${brandLogos[model.logo] || ''}
                        </div>
                        <div class="flex flex-col gap-0.5 min-w-0">
                            <span class="text-slate-900 font-semibold text-sm truncate">${model.name}</span>
                            <span class="text-[10px] text-slate-400 font-normal truncate">${model.provider}</span>
                        </div>
                    </div>

                    <!-- Pairing connector: hairlines + a multiplication glyph reading "model combined with harness" -->
                    <div aria-hidden="true" class="flex items-center justify-center gap-1 px-0.5 sm:px-1 select-none shrink-0">
                        <span class="hidden sm:block h-px w-2.5 bg-gradient-to-r from-transparent to-slate-300"></span>
                        <span class="flex items-center justify-center w-5 h-5 rounded-md text-slate-400 text-sm font-medium leading-none ring-1 ring-slate-200/70 bg-slate-50 group-hover:text-indigo-500 group-hover:ring-indigo-200 transition-colors">×</span>
                        <span class="hidden sm:block h-px w-2.5 bg-gradient-to-l from-transparent to-slate-300"></span>
                    </div>

                    <!-- Harness entity -->
                    <div class="flex items-center gap-2 min-w-0">
                        <div class="p-1 rounded-md shadow-sm flex-shrink-0 group-hover:scale-105 transition-transform" style="background-color: ${harness.accent}1a; border: 1px solid ${harness.accent}33;">
                            ${harnessIcon(harness)}
                        </div>
                        <div class="flex flex-col gap-1 min-w-0">
                            <span class="text-slate-900 font-semibold text-sm truncate">${harness.name}</span>
                            <div class="flex flex-wrap items-center gap-1">${harnessConfigHtml}</div>
                        </div>
                    </div>
                </div>

                <!-- Score progression meter -->
                <div class="col-span-4 sm:col-span-4 flex items-center gap-3 w-full sm:w-auto mt-2 sm:mt-0">
                    <span class="text-sm font-semibold text-slate-900 w-12 min-w-[48px]">
                        ${scoreValue.toFixed(1)}%
                    </span>
                    <div class="w-full bg-slate-100 h-2 rounded-full overflow-hidden relative">
                        <div class="progress-bar-fill h-full rounded-full"
                             style="width: ${scoreValue}%; background-color: ${color};">
                        </div>
                    </div>
                </div>

                <!-- View-details affordance (replaces the old expand caret) -->
                <div class="absolute right-6 top-5 sm:relative sm:right-auto sm:top-auto col-span-1 sm:col-span-1 flex items-center justify-end">
                    <svg aria-hidden="true" class="w-4 h-4 text-slate-300 group-hover:text-indigo-500 group-hover:translate-x-0.5 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                    </svg>
                </div>
            </a>
        `;
    }).join('');
}

function setupTooltip() {
    const trigger = document.getElementById('tooltip-trigger');
    if (trigger) {
        trigger.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                trigger.blur(); // Dismisses tooltip
            }
        });
    }
}

// --- 3. TREND CHART ----------------------------------------------------------
// Score-over-time line chart: one line per setup, x = iterations, y = score for
// the selected metric. Data comes from setupHistory() (currently [MOCK]).
function initTrendChart() {
    const canvas = document.getElementById('trendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Set custom Chart.js defaults matching Inter font and Slate styling
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = "#64748b"; // slate-500
    Chart.defaults.plugins.tooltip.backgroundColor = "#0f172a"; // slate-900
    Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
    Chart.defaults.plugins.tooltip.bodyColor = "#cbd5e1";
    Chart.defaults.plugins.tooltip.padding = 12;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.borderColor = "#334155"; // slate-700

    trendChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'nearest',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8,
                        padding: 20,
                        font: {
                            size: 11,
                            weight: '500'
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        title: function(items) {
                            return items.length ? formatRunDate(items[0].parsed.x) : '';
                        },
                        label: function(context) {
                            return ` ${context.dataset.label}: ${context.parsed.y.toFixed(1)}%`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    bounds: 'data',
                    // Real time axis: ticks land exactly on run dates, spaced
                    // proportionally to elapsed time (not evenly-spaced labels).
                    afterBuildTicks: function(axis) {
                        axis.ticks = allRunDates(setups).map(t => ({ value: Date.parse(t) }));
                    },
                    grid: {
                        display: false
                    },
                    ticks: {
                        callback: function(value) { return formatRunDate(value); },
                        maxRotation: 0,
                        autoSkip: false,
                        padding: 8
                    }
                },
                y: {
                    min: 60,
                    max: 100,
                    border: {
                        display: false
                    },
                    grid: {
                        color: "#f1f5f9"
                    },
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        },
                        stepSize: 10,
                        padding: 8
                    }
                }
            },
            elements: {
                line: {
                    tension: 0.35,
                    borderWidth: 3
                },
                point: {
                    radius: 3,
                    hitRadius: 12,
                    hoverRadius: 6,
                    hoverBackgroundColor: '#ffffff',
                    hoverBorderWidth: 3
                }
            }
        }
    });

    updateTrendChart();
}

function updateTrendChart() {
    if (!trendChartInstance) return;

    // One line per FILTERED setup, colored by the setup's own color.
    const visibleSetups = getFilteredSetups();
    const datasets = visibleSetups.map(setup => ({
        label: setupLabel(setup),
        data: setupHistory(setup, currentMetric),
        borderColor: setup.color,
        backgroundColor: `${setup.color}1a`, // 10% opacity shading (1a = 10%)
        pointBorderColor: setup.color,
        pointBackgroundColor: setup.color,
        fill: false
    }));

    trendChartInstance.data.datasets = datasets;
    trendChartInstance.update();

    // Accessibility data table — shared columns = union of run dates; a setup
    // missing a given run shows a blank ("—"), never a 0.
    const table = document.getElementById('trend-chart-table');
    if (table) {
        const dates = allRunDates(visibleSetups);
        table.innerHTML = `
            <caption>Score trend over time data summary (selected metric: ${currentMetric})</caption>
            <thead>
                <tr>
                    <th scope="col">Setup</th>
                    ${dates.map(d => `<th scope="col">${formatRunDate(d)}</th>`).join('')}
                </tr>
            </thead>
            <tbody>
                ${visibleSetups.map(setup => `
                    <tr>
                        <th scope="row">${setupLabel(setup)}</th>
                        ${dates.map(d => {
                            const rec = setup.history.find(h => h.t === d);
                            return `<td>${rec ? rec.scores[currentMetric].toFixed(1) + '%' : '—'}</td>`;
                        }).join('')}
                    </tr>
                `).join('')}
            </tbody>
        `;
    }
}

// Initialize layout
window.onload = function() {
    renderFilters();
    filterAndRender();
    initTrendChart();
    setupTooltip();
};
