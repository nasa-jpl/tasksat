/**
 * Timeline Charts - Render TaskSAT timeline evolution data using Chart.js
 */

/**
 * Render all timelines in the evolution data
 * @param {Object} evolutionData - Timeline evolution data from verifier
 * @param {string} containerId - ID of container element
 */
function renderAllTimelines(evolutionData, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const zones = evolutionData.zones;
    const timelines = evolutionData.timelines;

    // Create a chart for each timeline
    Object.keys(timelines).forEach(timelineId => {
        const timelineData = timelines[timelineId];
        renderTimeline(container, timelineId, timelineData, zones);
    });
}

/**
 * Render a single timeline chart
 * @param {HTMLElement} container - Container element
 * @param {string} timelineId - Timeline identifier
 * @param {Object} timelineData - Timeline data {type, values}
 * @param {Array} zones - Zone time boundaries
 */
function renderTimeline(container, timelineId, timelineData, zones) {
    // Create card for this timeline
    const card = document.createElement('div');
    card.className = 'card mb-3';

    const header = document.createElement('div');
    header.className = 'card-header d-flex justify-content-between align-items-center';

    const titleSpan = document.createElement('span');
    titleSpan.innerHTML = `<strong>${timelineId}</strong> <span class="badge bg-secondary">${timelineData.type}</span>`;

    const resetBtn = document.createElement('button');
    resetBtn.className = 'btn btn-sm btn-outline-secondary';
    resetBtn.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i> Reset Zoom';
    resetBtn.title = 'Reset zoom and pan';
    resetBtn.style.display = 'none'; // Hidden by default

    header.appendChild(titleSpan);
    header.appendChild(resetBtn);

    const body = document.createElement('div');
    body.className = 'card-body';

    const canvas = document.createElement('canvas');
    canvas.id = `chart-${timelineId}`;
    canvas.style.height = '200px';

    body.appendChild(canvas);
    card.appendChild(header);
    card.appendChild(body);
    container.appendChild(card);

    // Create chart based on timeline type
    const ctx = canvas.getContext('2d');
    const chartData = convertTimelineToChartData(timelineData, zones);

    const config = {
        type: getChartType(timelineData.type),
        data: chartData,
        options: getChartOptions(timelineId, timelineData.type)
    };

    const chart = new Chart(ctx, config);

    // Show reset button when zoomed/panned
    chart.options.plugins.zoom.zoom.onZoom = () => {
        resetBtn.style.display = 'inline-block';
    };
    chart.options.plugins.zoom.pan.onPan = () => {
        resetBtn.style.display = 'inline-block';
    };

    // Reset zoom handler
    resetBtn.onclick = () => {
        chart.resetZoom();
        resetBtn.style.display = 'none';
    };
}

/**
 * Get Chart.js chart type based on timeline type
 */
function getChartType(timelineType) {
    switch (timelineType) {
        case 'state':
        case 'atomic':
            return 'line'; // Will use stepped line
        case 'rate':
        case 'cumulative':
            return 'line';
        case 'claimable':
            return 'line'; // Will use fill
        default:
            return 'line';
    }
}

/**
 * Convert timeline data to Chart.js dataset format
 */
function convertTimelineToChartData(timelineData, zones) {
    const type = timelineData.type;
    const values = timelineData.values;

    let chartData = {
        labels: [],
        datasets: []
    };

    if (type === 'state' || type === 'atomic') {
        // Step chart for state/atomic timelines
        chartData = convertStepData(values, zones, type);
    } else if (type === 'rate') {
        // Line chart showing value over time
        chartData = convertRateData(values, zones);
    } else if (type === 'cumulative') {
        // Line chart for cumulative values
        chartData = convertCumulativeData(values, zones);
    } else if (type === 'claimable') {
        // Area chart for claimable resources
        chartData = convertClaimableData(values, zones);
    }

    return chartData;
}

/**
 * Convert state/atomic timeline to step chart data
 */
function convertStepData(values, zones, type) {
    const points = [];
    const labels = [];

    // Map state names to numeric values for state timelines
    let stateMap = {};
    let nextStateValue = 0;

    for (let i = 0; i < values.length; i++) {
        const startTime = zones[i];
        const endTime = zones[i + 1] || zones[i];
        const value = values[i];

        let numericValue;
        if (type === 'state') {
            // Map state names to numbers
            if (!(value in stateMap)) {
                stateMap[value] = nextStateValue++;
            }
            numericValue = stateMap[value];
        } else {
            // Atomic: boolean to 0/1
            numericValue = value ? 1 : 0;
        }

        // Add point at start of zone
        labels.push(startTime);
        points.push(numericValue);

        // Add point at end of zone (same value - creates step)
        if (endTime !== startTime) {
            labels.push(endTime);
            points.push(numericValue);
        }
    }

    return {
        labels: labels,
        datasets: [{
            label: 'Value',
            data: points,
            stepped: 'before',
            borderColor: 'rgb(75, 192, 192)',
            backgroundColor: 'rgba(75, 192, 192, 0.1)',
            fill: false,
            tension: 0
        }]
    };
}

/**
 * Convert rate timeline to line chart data
 */
function convertRateData(values, zones) {
    const points = [];
    const labels = [];

    for (let i = 0; i < values.length; i++) {
        const time = zones[i];
        const valueData = values[i];
        const value = valueData.value;

        labels.push(time);
        points.push(value);
    }

    // Add final point
    if (zones.length > values.length) {
        const lastValue = values[values.length - 1];
        const lastTime = zones[zones.length - 1];
        const rate = lastValue.rate;
        const duration = lastTime - zones[zones.length - 2];
        const finalValue = lastValue.value + (rate * duration);

        labels.push(lastTime);
        points.push(finalValue);
    }

    return {
        labels: labels,
        datasets: [{
            label: 'Value',
            data: points,
            borderColor: 'rgb(54, 162, 235)',
            backgroundColor: 'rgba(54, 162, 235, 0.1)',
            fill: false,
            tension: 0.1
        }]
    };
}

/**
 * Convert cumulative timeline to line chart data
 */
function convertCumulativeData(values, zones) {
    const points = [];
    const labels = [];

    for (let i = 0; i < values.length; i++) {
        labels.push(zones[i]);
        points.push(values[i]);
    }

    // Add final point
    if (zones.length > values.length) {
        labels.push(zones[zones.length - 1]);
        points.push(values[values.length - 1]);
    }

    return {
        labels: labels,
        datasets: [{
            label: 'Cumulative Value',
            data: points,
            borderColor: 'rgb(153, 102, 255)',
            backgroundColor: 'rgba(153, 102, 255, 0.1)',
            fill: false,
            tension: 0.1
        }]
    };
}

/**
 * Convert claimable timeline to area chart data
 */
function convertClaimableData(values, zones) {
    const points = [];
    const labels = [];

    for (let i = 0; i < values.length; i++) {
        const startTime = zones[i];
        const endTime = zones[i + 1] || zones[i];
        const value = values[i];

        // Add step points
        labels.push(startTime);
        points.push(value);

        if (endTime !== startTime) {
            labels.push(endTime);
            points.push(value);
        }
    }

    return {
        labels: labels,
        datasets: [{
            label: 'Available',
            data: points,
            stepped: 'before',
            borderColor: 'rgb(255, 159, 64)',
            backgroundColor: 'rgba(255, 159, 64, 0.3)',
            fill: true,
            tension: 0
        }]
    };
}

/**
 * Get Chart.js options for a timeline
 */
function getChartOptions(timelineId, timelineType) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: false
            },
            title: {
                display: false
            },
            zoom: {
                zoom: {
                    wheel: {
                        enabled: true,
                    },
                    pinch: {
                        enabled: true
                    },
                    mode: 'x',
                },
                pan: {
                    enabled: true,
                    mode: 'x',
                }
            }
        },
        scales: {
            x: {
                type: 'linear',
                title: {
                    display: true,
                    text: 'Time'
                }
            },
            y: {
                title: {
                    display: true,
                    text: 'Value'
                },
                beginAtZero: timelineType === 'atomic' || timelineType === 'claimable'
            }
        },
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        }
    };
}
