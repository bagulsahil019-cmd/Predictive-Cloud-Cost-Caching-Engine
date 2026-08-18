// UI Constants & Elements
const keysList = [
    { name: "user_profile", weight: 0.60 },
    { name: "image_metadata", weight: 0.20 },
    { name: "search_products", weight: 0.12 },
    { name: "recommendations_feed", weight: 0.06 },
    { name: "analytics_report", weight: 0.02 }
];

// Sliders and controls
const predictiveToggle = document.getElementById("predictive-toggle");
const trafficRateSlider = document.getElementById("traffic-rate-slider");
const trafficRateVal = document.getElementById("traffic-rate-val");

const dbComputeSlider = document.getElementById("db-compute-slider");
const dbComputeVal = document.getElementById("db-compute-val");

const dbEgressSlider = document.getElementById("db-egress-slider");
const dbEgressVal = document.getElementById("db-egress-val");

const cacheStorageSlider = document.getElementById("cache-storage-slider");
const cacheStorageVal = document.getElementById("cache-storage-val");

const cacheWriteSlider = document.getElementById("cache-write-slider");
const cacheWriteVal = document.getElementById("cache-write-val");

const resetBtn = document.getElementById("reset-btn");

// Metric fields
const hitRatioVal = document.getElementById("hit-ratio-val");
const avgLatencyVal = document.getElementById("avg-latency-val");
const savingsVal = document.getElementById("savings-val");
const latencySavedVal = document.getElementById("latency-saved-val");
const logCountVal = document.getElementById("log-count");
const logsContainer = document.getElementById("logs-container");

// Simulation interval state
let simulationIntervalId = null;
let metricsIntervalId = null;
let costChart = null;

// Initialize Chart.js
function initChart() {
    const ctx = document.getElementById('costChart').getContext('2d');
    costChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Direct DB Fetch Only',
                    borderColor: '#ff5a5f',
                    backgroundColor: 'rgba(255, 90, 95, 0.05)',
                    borderWidth: 2,
                    pointRadius: 0,
                    data: [],
                    fill: true
                },
                {
                    label: 'Standard Cache Routing',
                    borderColor: '#f77f00',
                    backgroundColor: 'rgba(247, 127, 0, 0.05)',
                    borderWidth: 2,
                    pointRadius: 0,
                    data: [],
                    fill: true
                },
                {
                    label: 'Predictive Cache Routing',
                    borderColor: '#00f5d4',
                    backgroundColor: 'rgba(0, 245, 212, 0.05)',
                    borderWidth: 3,
                    pointRadius: 0,
                    data: [],
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // We use custom header legend
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#9ca3af',
                        display: false // Hide long timestamps
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#9ca3af',
                        callback: function(value) {
                            return '$' + value.toFixed(2);
                        }
                    }
                }
            }
        }
    });
}

// Fetch settings from API on load
async function fetchSettings() {
    try {
        const response = await fetch('/settings');
        const settings = await response.json();
        
        predictiveToggle.checked = settings.predictive_active;
        
        dbComputeSlider.value = settings.p_compute;
        dbComputeVal.textContent = `$${parseFloat(settings.p_compute).toFixed(4)}`;
        
        dbEgressSlider.value = settings.p_egress_per_kb;
        dbEgressVal.textContent = `$${parseFloat(settings.p_egress_per_kb).toFixed(5)}`;
        
        cacheStorageSlider.value = settings.p_storage_per_kb;
        cacheStorageVal.textContent = `$${parseFloat(settings.p_storage_per_kb).toFixed(5)}`;
        
        cacheWriteSlider.value = settings.p_write_op;
        cacheWriteVal.textContent = `$${parseFloat(settings.p_write_op).toFixed(4)}`;
        
    } catch (error) {
        console.error("Error fetching settings:", error);
    }
}

// Send current UI settings state to backend
async function saveSettings() {
    const data = {
        p_compute: parseFloat(dbComputeSlider.value),
        p_egress_per_kb: parseFloat(dbEgressSlider.value),
        p_storage_per_kb: parseFloat(cacheStorageSlider.value),
        p_write_op: parseFloat(cacheWriteSlider.value),
        predictive_active: predictiveToggle.checked
    };
    
    // Update labels instantly
    dbComputeVal.textContent = `$${data.p_compute.toFixed(4)}`;
    dbEgressVal.textContent = `$${data.p_egress_per_kb.toFixed(5)}`;
    cacheStorageVal.textContent = `$${data.p_storage_per_kb.toFixed(5)}`;
    cacheWriteVal.textContent = `$${data.p_write_op.toFixed(4)}`;
    
    try {
        await fetch('/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    } catch (error) {
        console.error("Error updating settings:", error);
    }
}

// Pick a random key based on custom frequency weights
function pickWeightedKey() {
    const r = Math.random();
    let cumulative = 0;
    for (const key of keysList) {
        cumulative += key.weight;
        if (r <= cumulative) {
            return key.name;
        }
    }
    return keysList[0].name;
}

// Simulates query requests to the backend
async function sendSimulatedRequest() {
    const key = pickWeightedKey();
    try {
        await fetch(`/query?key=${encodeURIComponent(key)}`);
    } catch (e) {
        console.error("Failed simulation request query", e);
    }
}

// Start traffic generation
function restartSimulation() {
    if (simulationIntervalId) {
        clearInterval(simulationIntervalId);
    }
    
    const rate = parseFloat(trafficRateSlider.value);
    trafficRateVal.textContent = `${rate.toFixed(1)} reqs/sec`;
    
    const intervalMs = 1000 / rate;
    simulationIntervalId = setInterval(sendSimulatedRequest, intervalMs);
}

// Format Unix Timestamp
function formatTime(unixTime) {
    const d = new Date(unixTime * 1000);
    return d.toTimeString().split(' ')[0] + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

// Update metrics and charts
async function updateMetrics() {
    try {
        const response = await fetch('/metrics');
        const metrics = await response.json();
        
        // Update dashboard indicators
        hitRatioVal.textContent = `${(metrics.cache_hit_ratio * 100).toFixed(1)}%`;
        avgLatencyVal.textContent = `${metrics.avg_latency_ms} ms`;
        
        // Show comparison: savings vs standard cache or vs DB direct
        const predictiveActive = predictiveToggle.checked;
        if (predictiveActive) {
            const savingsPct = metrics.savings_vs_standard_pct;
            savingsVal.textContent = `${savingsPct > 0 ? '+' : ''}${savingsPct}%`;
            if (savingsPct >= 0) {
                savingsVal.className = "metric-value text-glow";
            } else {
                savingsVal.className = "metric-value text-red"; // Negative savings
            }
        } else {
            savingsVal.textContent = "Inactive";
            savingsVal.className = "metric-value text-red";
        }
        
        latencySavedVal.textContent = `${metrics.latency_saved_seconds}s`;
        logCountVal.textContent = `${metrics.total_requests} requests`;
        
        // Update logs stream
        if (metrics.logs.length === 0) {
            logsContainer.innerHTML = `
                <div class="empty-logs">
                    <i class="fa-solid fa-chart-simple"></i>
                    <p>Simulation active. Logs will stream here dynamically as request traffic starts...</p>
                </div>`;
        } else {
            logsContainer.innerHTML = metrics.logs.map(log => {
                let actionClass = 'direct-fetch';
                let badgeClass = 'direct';
                
                if (log.routing_action === 'CACHE_HIT') {
                    actionClass = 'cache-hit';
                    badgeClass = 'hit';
                } else if (log.routing_action === 'CACHE_ROUTED') {
                    actionClass = 'cache-route';
                    badgeClass = 'route';
                }
                
                return `
                    <div class="log-row ${actionClass}">
                        <span class="log-time">${formatTime(log.timestamp)}</span>
                        <span class="log-badge ${badgeClass}">${log.routing_action}</span>
                        <span class="log-key">${log.key}</span>
                        <span class="log-metrics">(${log.size_kb}KB, latency: ${log.latency_ms}ms, cost: $${log.cost_incurred.toFixed(5)})</span>
                        <span class="log-reason">${log.reason}</span>
                    </div>
                `;
            }).join('');
        }
        
        // Update Chart
        if (metrics.chart_history && metrics.chart_history.length > 0) {
            const history = metrics.chart_history;
            costChart.data.labels = history.map((_, idx) => idx);
            costChart.data.datasets[0].data = history.map(h => h.direct);
            costChart.data.datasets[1].data = history.map(h => h.standard);
            costChart.data.datasets[2].data = history.map(h => h.predictive);
            costChart.update();
        }
        
    } catch (e) {
        console.error("Failed fetching metrics", e);
    }
}

// Reset button event
resetBtn.addEventListener("click", async () => {
    if (confirm("Are you sure you want to reset the simulation stats and cache?")) {
        try {
            await fetch('/reset', { method: 'POST' });
            // Clear chart
            costChart.data.labels = [];
            costChart.data.datasets.forEach(dataset => dataset.data = []);
            costChart.update();
            // Clear local logs
            logsContainer.innerHTML = '';
            // Refresh
            updateMetrics();
        } catch (e) {
            console.error("Reset failed", e);
        }
    }
});

// Event Listeners for inputs
predictiveToggle.addEventListener("change", saveSettings);
dbComputeSlider.addEventListener("input", saveSettings);
dbEgressSlider.addEventListener("input", saveSettings);
cacheStorageSlider.addEventListener("input", saveSettings);
cacheWriteSlider.addEventListener("input", saveSettings);

trafficRateSlider.addEventListener("input", restartSimulation);

// Init on Load
window.addEventListener("load", async () => {
    initChart();
    await fetchSettings();
    restartSimulation();
    
    // Poll metrics every 1.5 seconds for UI fluidity
    metricsIntervalId = setInterval(updateMetrics, 1500);
});
