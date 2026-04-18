// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// --- 1. CONFIGURATION & MOCK DATA ---
const agentsConfig = {
    agent_gca: { id: 'agent_gca', name: 'Antigravity with GCA', color: '#4285F4', baseAcc: 0, baseLat: 0, baseTool: 0, baseMan: 0, cost: 'N/A' },
    agent_no_agent: { id: 'agent_no_agent', name: 'Antigravity with no agent', color: '#EA4335', baseAcc: 0, baseLat: 0, baseTool: 0, baseMan: 0, cost: 'N/A' }
};

const processEvalData = (evalDataArray) => {
    const agents = ['agent_gca', 'agent_no_agent'];
    
    const getAgentId = (setup) => {
        if (setup === "AGY with GCA") return "agent_gca";
        if (setup === "AGY with no agent") return "agent_no_agent";
        return null;
    };

    const agentTaskCounters = {}; // Map agentId_taskNum to current run counter

    const accumulation = {
        agent_gca: {},
        agent_no_agent: {}
    }; 
    let maxRunNumAllAgents = 0;

    // Accumulate data with task-specific run counters
    evalDataArray.forEach(row => {
        const agentId = getAgentId(row["Agent Setup"]);
        if (!agentId) return;
        
        const taskNum = row["Task"];
        const counterKey = `${agentId}_${taskNum}`;
        
        if (!agentTaskCounters[counterKey]) {
            agentTaskCounters[counterKey] = 0;
        }
        agentTaskCounters[counterKey]++;
        const adjustedRunNum = agentTaskCounters[counterKey];

        if (adjustedRunNum > maxRunNumAllAgents) {
            maxRunNumAllAgents = adjustedRunNum;
        }

        if (!accumulation[agentId][adjustedRunNum]) {
            accumulation[agentId][adjustedRunNum] = {
                accuracySum: 0,
                latencySum: 0,
                toolSum: 0,
                manifestSum: 0,
                inTokensSum: 0,
                outTokensSum: 0,
                count: 0
            };
        }
        const target = accumulation[agentId][adjustedRunNum];

        const acc = (parseFloat(row["Outcome Validity"]) / 5) * 100;
        target.accuracySum += acc;
        target.latencySum += parseFloat(row["Latency"]) || 0;
        target.inTokensSum += parseInt(row["Input Token"]) || 0;
        target.outTokensSum += parseInt(row["Output Token"]) || 0;

        const toolInv = row["Tool Invocation"];
        let toolScore = 0;
        if (toolInv !== "N/A" && !isNaN(parseFloat(toolInv))) {
            toolScore = (parseFloat(toolInv) / 5) * 100;
        }
        target.toolSum += toolScore;
        target.manifestSum += acc; 

        target.count++;
    });

    // Generate run labels dynamically
    const runLabels = [];
    for (let i = 1; i <= maxRunNumAllAgents; i++) {
        runLabels.push(`Run ${i}`);
    }

    // Initialize resultData with correct length
    const resultData = {};
    agents.forEach(a => {
        resultData[a] = runLabels.map(label => ({
            date: label,
            accuracy: null,
            latency: null,
            toolScore: null,
            manifestScore: null,
            inputTokens: null,
            outputTokens: null
        }));
    });

    // Populate resultData
    for (const agentId in accumulation) {
        for (const runNumStr in accumulation[agentId]) {
            const runNum = parseInt(runNumStr);
            const accData = accumulation[agentId][runNum];
            const runIdx = runNum - 1; 

            if (runIdx >= 0 && runIdx < maxRunNumAllAgents && resultData[agentId]) {
                const agentData = resultData[agentId][runIdx];
                agentData.accuracy = accData.accuracySum / accData.count;
                agentData.latency = accData.latencySum / accData.count;
                agentData.toolScore = accData.toolSum / accData.count;
                agentData.manifestScore = accData.manifestSum / accData.count;
                agentData.inputTokens = accData.inTokensSum / accData.count;
                agentData.outputTokens = accData.outTokensSum / accData.count;
            }
        }
    }

    return {
        labels: runLabels,
        timeSeriesData: resultData
    };
};

// Global variables to be populated after data loading
let labels = [];
let timeSeriesData = {};

const getAvgAccuracy = (agentId) => {
    const data = timeSeriesData[agentId];
    if (!data) return 0;
    const validData = data.filter(d => d.accuracy !== null);
    if (validData.length === 0) return 0;

    let totalWeight = 0;
    let weightedSum = 0;
    validData.forEach((d, index) => {
        const weight = index + 1;
        weightedSum += d.accuracy * weight;
        totalWeight += weight;
    });
    return weightedSum / totalWeight;
};

const getAvgLatency = (agentId) => {
    const data = timeSeriesData[agentId];
    if (!data) return 0;
    const validData = data.filter(d => d.latency !== null);
    if (validData.length === 0) return 0;

    let totalWeight = 0;
    let weightedSum = 0;
    validData.forEach((d, index) => {
        const weight = index + 1;
        weightedSum += d.latency * weight;
        totalWeight += weight;
    });
    return weightedSum / totalWeight;
};

const getAvgInputTokens = (agentId) => {
    const data = timeSeriesData[agentId];
    if (!data) return 0;
    const validData = data.filter(d => d.inputTokens !== null);
    if (validData.length === 0) return 0;
    const sum = validData.reduce((acc, d) => acc + d.inputTokens, 0);
    return sum / validData.length;
};

const getAvgOutputTokens = (agentId) => {
    const data = timeSeriesData[agentId];
    if (!data) return 0;
    const validData = data.filter(d => d.outputTokens !== null);
    if (validData.length === 0) return 0;
    const sum = validData.reduce((acc, d) => acc + d.outputTokens, 0);
    return sum / validData.length;
};

const featuresList = ['GKE', 'Storage', 'GCE', 'Vertex AI', 'AI Hypercomputer'];
const taskMatrixData = [];

// Global Table State
let currentViewMode = 'all';
let currentFeatureFilter = 'all';
let currentPage = 1;
const itemsPerPage = 10;


// --- 2. CHART.JS SETUP & INSTANCES ---

Chart.defaults.font.family = '"Roboto", sans-serif';
Chart.defaults.color = '#5F6368';
Chart.defaults.scale.grid.color = '#F1F3F4';
Chart.defaults.plugins.tooltip.backgroundColor = '#202124';
Chart.defaults.plugins.tooltip.titleFont.family = '"Roboto", sans-serif';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;

const commonLineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
        mode: 'index',
        intersect: false,
    },
    plugins: {
        legend: {
            display: true,
            position: 'bottom',
            labels: { usePointStyle: true, boxWidth: 8, font: { size: 11, family: '"Roboto", sans-serif' } }
        }
    },
    scales: {
        x: { grid: { display: false }, ticks: { maxTicksLimit: 7 } },
        y: { border: { display: false } }
    },
    elements: {
        line: { tension: 0.3, borderWidth: 2.5 },
        point: { radius: 4, hitRadius: 10, hoverRadius: 5, hoverBackgroundColor: '#fff', hoverBorderWidth: 2 }
    }
};

const charts = {};

const buildDatasets = (dataKey, isSingleAgentId = null) => {
    const datasets = [];
    const agentsToInclude = isSingleAgentId ? [isSingleAgentId] : ['agent_gca', 'agent_no_agent'];

    agentsToInclude.forEach(agentId => {
        const agent = agentsConfig[agentId];
        datasets.push({
            label: agent.name,
            data: timeSeriesData[agentId].map(d => d[dataKey]),
            borderColor: agent.color,
            backgroundColor: isSingleAgentId ? agent.color + '20' : 'transparent',
            pointBorderColor: agent.color,
            fill: !!isSingleAgentId
        });
    });

    return datasets;
};

const initCharts = () => {
    // 1. Leaderboard Bar Chart
    const leadCtx = document.getElementById('leaderboardChart').getContext('2d');
    charts.leaderboard = new Chart(leadCtx, {
        type: 'bar',
        data: {
            labels: Object.values(agentsConfig).map(a => a.name),
            datasets: [{
                label: 'Avg Accuracy',
                data: Object.keys(agentsConfig).map(id => getAvgAccuracy(id)),
                backgroundColor: Object.values(agentsConfig).map(a => a.color),
                borderRadius: 4,
                barThickness: 'flex',
                maxBarThickness: 36
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: (ctx) => ctx.parsed.x.toFixed(1) + '%' } }
            },
            scales: {
                x: { min: 60, max: 100, border: { display: false } },
                y: { grid: { display: false }, border: { display: false }, ticks: { font: { weight: '500' } } }
            }
        }
    });



    const buildGroupedBarDatasets = (dataKey) => {
        return Object.keys(agentsConfig).map(agentId => {
            const agent = agentsConfig[agentId];
            return {
                label: agent.name,
                data: timeSeriesData[agentId].map(d => d[dataKey]),
                backgroundColor: agent.color,
                borderRadius: 4,
                barThickness: 'flex',
                maxBarThickness: 16
            };
        });
    };

    const commonGroupedBarOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, font: { size: 11, family: '"Roboto", sans-serif' } } }
        },
        scales: {
            x: { grid: { display: false }, border: { display: false } },
            y: { border: { display: false } }
        }
    };

    // 2. Accuracy Bar Chart
    const trendCtx = document.getElementById('trendChart').getContext('2d');
    charts.trend = new Chart(trendCtx, {
        type: 'bar',
        data: { labels: labels, datasets: buildGroupedBarDatasets('accuracy') },
        options: {
            ...commonGroupedBarOptions,
            scales: { ...commonGroupedBarOptions.scales, y: { min: 50, max: 100, border: { display: false } } },
            plugins: { ...commonGroupedBarOptions.plugins, tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%` } } }
        }
    });

    // 3. Mini Chart: Latency
    const latCtx = document.getElementById('latencyChart').getContext('2d');
    charts.latency = new Chart(latCtx, {
        type: 'line',
        data: { labels: labels, datasets: buildDatasets('latency') },
        options: { ...commonLineOptions, plugins: { ...commonLineOptions.plugins, legend: { display: false } } }
    });

    // 5. Mini Chart: Manifest Score
    const manCtx = document.getElementById('manifestScoreChart').getContext('2d');
    charts.manifestScore = new Chart(manCtx, {
        type: 'line',
        data: { labels: labels, datasets: buildDatasets('manifestScore') },
        options: { ...commonLineOptions, plugins: { ...commonLineOptions.plugins, legend: { display: false } } }
    });

    // 6. Mini Chart: Input Tokens
    const inTokCtx = document.getElementById('inputTokensChart').getContext('2d');
    charts.inputTokens = new Chart(inTokCtx, {
        type: 'line',
        data: { labels: labels, datasets: buildDatasets('inputTokens') },
        options: { ...commonLineOptions, plugins: { ...commonLineOptions.plugins, legend: { display: false } } }
    });

    // 7. Mini Chart: Output Tokens
    const outTokCtx = document.getElementById('outputTokensChart').getContext('2d');
    charts.outputTokens = new Chart(outTokCtx, {
        type: 'line',
        data: { labels: labels, datasets: buildDatasets('outputTokens') },
        options: { ...commonLineOptions, plugins: { ...commonLineOptions.plugins, legend: { display: false } } }
    });



    // 9. Step Latency Chart



    // Render Configuration Table
    const configTbody = document.getElementById('configTableBody');
    configTbody.innerHTML = ''; // Clear existing
    Object.values(agentsConfig).sort((a, b) => getAvgAccuracy(b.id) - getAvgAccuracy(a.id)).forEach((config) => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-google-bg transition-colors duration-150";

        const avgLat = getAvgLatency(config.id);
        const avgAcc = getAvgAccuracy(config.id);
        const avgInTokens = getAvgInputTokens(config.id);
        const avgOutTokens = getAvgOutputTokens(config.id);

        tr.innerHTML = `
            <td class="py-4 pl-6 pr-3 whitespace-nowrap">
                <div class="font-medium text-google-textPrimary flex items-center gap-2">
                    <div class="w-2.5 h-2.5 rounded-full" style="background-color: ${config.color}"></div>
                    ${config.name}
                </div>
            </td>
            <td class="px-3 py-4 whitespace-nowrap text-right text-sm text-google-textSecondary">${avgLat.toFixed(1)}s</td>
            <td class="px-3 py-4 whitespace-nowrap text-right text-sm font-medium ${avgAcc > 90 ? 'text-google-green' : 'text-google-textPrimary'}">${avgAcc.toFixed(1)}%</td>
            <td class="px-3 py-4 whitespace-nowrap text-right text-sm text-google-textSecondary">${Math.round(avgInTokens)}</td>
            <td class="py-4 pl-3 pr-6 whitespace-nowrap text-right text-sm text-google-textSecondary">${Math.round(avgOutTokens)}</td>
        `;
        configTbody.appendChild(tr);
    });
};


// --- 3. VIEW UPDATING LOGIC ---

const updateTaskTableUI = () => {
    const filteredData = taskMatrixData;

    const totalItems = filteredData.length;
    const totalPages = Math.ceil(totalItems / itemsPerPage) || 1;

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, totalItems);
    const paginatedData = filteredData.slice(startIndex, endIndex);

    const paginationInfo = document.getElementById('paginationInfo');
    if (totalItems === 0) {
        paginationInfo.innerText = 'No tasks found';
    } else {
        paginationInfo.innerText = `Showing ${startIndex + 1} to ${endIndex} of ${totalItems} entries`;
    }

    document.getElementById('prevPage').disabled = currentPage === 1;
    document.getElementById('nextPage').disabled = currentPage === totalPages || totalPages === 0;

    const thead = document.getElementById('taskTableHeader');
    const tbody = document.getElementById('taskTableBody');

    let headerHTML = `
        <tr>
            <th scope="col" class="py-4 pl-6 pr-3 text-left text-xs font-medium text-google-textSecondary uppercase tracking-wider">Task Definition</th>
            <th scope="col" class="px-3 py-4 text-center text-xs font-medium text-google-textSecondary uppercase tracking-wider border-r border-google-border">Total Runs</th>
    `;

    if (currentViewMode === 'all') {
        headerHTML += `
            <th scope="col" class="px-3 py-4 text-center text-xs font-medium text-google-textSecondary uppercase tracking-wider">Antigravity with GCA</th>
            <th scope="col" class="px-3 py-4 text-center text-xs font-medium text-google-textSecondary uppercase tracking-wider">Antigravity with no agent</th>
        `;
    } else {
        headerHTML += `
            <th scope="col" class="px-3 py-4 text-center text-xs font-medium text-google-textSecondary uppercase tracking-wider">${agentsConfig[currentViewMode].name} Pass Rate</th>
        `;
    }
    headerHTML += `</tr>`;
    thead.innerHTML = headerHTML;

    let bodyHTML = '';

    if (paginatedData.length === 0) {
        bodyHTML = `<tr><td colspan="6" class="py-8 text-center text-sm text-google-textSecondary">No tasks match the selected filter.</td></tr>`;
    } else {
        paginatedData.forEach(task => {
            bodyHTML += `<tr class="hover:bg-google-bg transition-colors duration-150">`;
            bodyHTML += `
                <td class="py-3 pl-6 pr-3 whitespace-nowrap">
                    <div class="text-[10px] font-bold text-google-textSecondary uppercase tracking-wider mb-0.5">${task.id}</div>
                    <div class="font-medium text-google-textPrimary text-sm">${task.name}</div>
                </td>
                <td class="px-3 py-3 whitespace-nowrap text-center text-sm text-google-textSecondary border-r border-google-border">${task.runs}</td>
            `;

            const renderCell = (agentId) => {
                const rate = parseFloat(task[agentId].passRate);
                let colorClass = 'text-google-textPrimary';
                if (rate >= 90) colorClass = 'text-google-green font-medium';
                else if (rate < 80) colorClass = 'text-google-red font-medium';

                return `<td class="px-3 py-3 whitespace-nowrap text-center text-sm ${colorClass}">${task[agentId].passRate}%</td>`;
            };

            if (currentViewMode === 'all') {
                bodyHTML += renderCell('agent_gca');
                bodyHTML += renderCell('agent_no_agent');
            } else {
                bodyHTML += renderCell(currentViewMode);
            }

            bodyHTML += `</tr>`;
        });
    }
    tbody.innerHTML = bodyHTML;
};

const updateCharts = (viewMode) => {
    const isSingle = viewMode !== 'all' ? viewMode : null;

    const updateGroupedBarChart = (chartInstance, dataKey) => {
        const agentsToInclude = isSingle ? [isSingle] : ['agent_gca', 'agent_no_agent'];
        chartInstance.data.labels = labels; // Always use all run labels
        chartInstance.data.datasets = agentsToInclude.map(agentId => {
            const agent = agentsConfig[agentId];
            return {
                label: agent.name,
                data: timeSeriesData[agentId].map(d => d[dataKey]),
                backgroundColor: agent.color,
                borderRadius: 4,
                barThickness: 'flex',
                maxBarThickness: 16
            };
        });
        chartInstance.update();
    };

    updateGroupedBarChart(charts.trend, 'accuracy');
    charts.latency.data.datasets = buildDatasets('latency', isSingle);
    charts.latency.update();
    charts.manifestScore.data.datasets = buildDatasets('manifestScore', isSingle);
    charts.manifestScore.update();
    charts.inputTokens.data.datasets = buildDatasets('inputTokens', isSingle);
    charts.inputTokens.update();
    charts.outputTokens.data.datasets = buildDatasets('outputTokens', isSingle);
    charts.outputTokens.update();



    if (isSingle) {
        const agent = agentsConfig[isSingle];
        charts.leaderboard.data.labels = [agent.name];
        charts.leaderboard.data.datasets[0].data = [getAvgAccuracy(isSingle)];
        charts.leaderboard.data.datasets[0].backgroundColor = [agent.color];
    } else {
        charts.leaderboard.data.labels = Object.values(agentsConfig).map(a => a.name);
        charts.leaderboard.data.datasets[0].data = Object.keys(agentsConfig).map(id => getAvgAccuracy(id));
        charts.leaderboard.data.datasets[0].backgroundColor = Object.values(agentsConfig).map(a => a.color);
    }
    charts.leaderboard.update();
};

// --- 4. INITIALIZATION & EVENT LISTENERS ---

const setupEventListeners = () => {
    const pills = document.querySelectorAll('.view-pill');
    pills.forEach(pill => {
        pill.addEventListener('click', (e) => {
            pills.forEach(p => p.classList.remove('active'));
            e.currentTarget.classList.add('active');

            currentViewMode = e.currentTarget.getAttribute('data-agent');

            updateCharts(currentViewMode);
            updateTaskTableUI();
        });
    });



    document.getElementById('prevPage').addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            updateTaskTableUI();
        }
    });

    document.getElementById('nextPage').addEventListener('click', () => {
        currentPage++;
        updateTaskTableUI();
    });
};

async function loadData() {
    let allData = [];
    let i = 1;
    while (true) {
        const file = `eval_results/eval-results-${i}.jsonl`;
        try {
            const response = await fetch(file);
            if (!response.ok) {
                break;
            }
            const text = await response.text();
            const lines = text.split('\n');
            for (const line of lines) {
                if (line.trim()) {
                    const row = JSON.parse(line);
                    row.__fileIndex__ = i;
                    allData.push(row);
                }
            }
            i++;
        } catch (e) {
            break;
        }
    }
    return allData;
}

async function initializeDashboard() {
    try {
        let allData = await loadData();

        if (allData.length === 0) {
            console.warn("No data loaded from manifest files.");
        }

        const processed = processEvalData(allData);
        labels = processed.labels;
        timeSeriesData = processed.timeSeriesData;

        // Process data for task matrix
        const tasks = {};
        allData.forEach(row => {
            const taskNum = row["Task"];
            const taskNames = [
                "",
                "Summarize existing app architecture",
                "Generate a manifest for deploying fine-tuned local mode to GKE cluster",
                "Deploy a local vLLM inference stack to GKE cluster",
                "Generate a manifest to migrate app from using Gemini API to local model",
                "Apply local model configuration to GKE cluster"
            ];
            if (!tasks[taskNum]) {
                tasks[taskNum] = {
                    id: `Task ${taskNum}`,
                    name: taskNames[taskNum] || `Run for task ${taskNum}`,
                    feature: "N/A",
                    runs: 0,
                    agent_gca: { sum: 0, count: 0 },
                    agent_no_agent: { sum: 0, count: 0 }
                };
            }
            const setup = row["Agent Setup"];
            const agentId = setup === "AGY with GCA" ? "agent_gca" : (setup === "AGY with no agent" ? "agent_no_agent" : null);
            if (agentId && tasks[taskNum][agentId]) {
                const acc = (parseFloat(row["Outcome Validity"]) / 5) * 100;
                tasks[taskNum][agentId].sum += acc;
                tasks[taskNum][agentId].count++;
            }
            tasks[taskNum].runs++;
        });

        // Clear existing mock data array and fill with task summaries
        taskMatrixData.length = 0;
        for (const taskKey in tasks) {
            const t = tasks[taskKey];
            taskMatrixData.push({
                id: t.id,
                name: t.name,
                feature: t.feature,
                runs: t.runs,
                agent_gca: { passRate: t.agent_gca.count > 0 ? (t.agent_gca.sum / t.agent_gca.count).toFixed(1) : "0.0" },
                agent_no_agent: { passRate: t.agent_no_agent.count > 0 ? (t.agent_no_agent.sum / t.agent_no_agent.count).toFixed(1) : "0.0" }
            });
        }

    } catch (e) {
        console.error("Failed to load data from manifest.", e);
        const processed = processEvalData([]);
        labels = processed.labels;
        timeSeriesData = processed.timeSeriesData;
    }

    initCharts();
    updateTaskTableUI();
    setupEventListeners();
}

window.onload = () => {
    initializeDashboard();
};
