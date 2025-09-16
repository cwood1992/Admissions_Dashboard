// Data structure
const funnelData = {
    reps: {
        'Randy': { leads: 7406, enrollments: 764, starts: 87 },
        'Cori': { leads: 7190, enrollments: 696, starts: 76 },
        'Sue': { leads: 4300, enrollments: 334, starts: 22 },
        'Thomas': { leads: 2724, enrollments: 272, starts: 51 }
    },
    totals: { leads: 21620, enrollments: 2066, starts: 236 }
};

const data = {
    combined: {
        cohorts: ['551', '552', '553', '554', '555', '556', '557', '558', '559'],
        reps: {
            'Cori': [7.0, 12.0, 7.1, 13.5, 8.3, 6.2, 13.0, 10.6, 17.5],
            'Randy': [11.1, 12.0, 5.1, 9.6, 12.2, 8.9, 13.5, 13.4, 12.4],
            'Sue': [null, null, 0.0, 3.1, 8.9, 3.3, 2.8, 9.0, 8.2],
            'Thomas': [16.4, 15.2, 6.5, 15.4, 12.9, 12.0, 22.9, 28.9, 16.2]
        },
        totals: {'Cori': 11.0, 'Randy': 11.0, 'Sue': 5.8, 'Thomas': 16.2}
    },
    'ndt-day': {
        cohorts: ['NDT551', 'NDT552', 'NDT553', 'NDT554', 'NDT555', 'NDT556', 'NDT557', 'NDT558', 'NDT559'],
        reps: {
            'Cori': [4.5, 8.2, 7.5, 5.1, 12.1, 4.5, 22.4, 8.1, 20.9],
            'Randy': [11.3, 9.4, 5.2, 1.9, 15.9, 6.7, 14.9, 5.1, 13.9],
            'Sue': [null, null, 0.0, 4.5, 4.2, 8.3, 3.8, 9.1, 12.0],
            'Thomas': [0.0, 7.1, 5.3, 0.0, 23.1, 13.3, 20.0, 15.4, 14.3]
        },
        totals: {'Cori': 11.0, 'Randy': 9.3, 'Sue': 6.8, 'Thomas': 9.7}
    },
    'ndt-night': {
        cohorts: ['NDT552NC', 'NDT554NC', 'NDT556NC', 'NDT558NC'],
        reps: {
            'Cori': [0.0, 22.2, 0.0, 28.6],
            'Randy': [0.0, 27.8, 11.1, 20.0],
            'Sue': [null, 0.0, 0.0, 0.0],
            'Thomas': [0.0, 25.0, 0.0, 50.0]
        },
        totals: {'Cori': 15.0, 'Randy': 17.9, 'Sue': 0.0, 'Thomas': 21.4}
    },
    'udt': {
        cohorts: ['UDT551', 'UDT552', 'UDT553', 'UDT554', 'UDT555', 'UDT556', 'UDT557', 'UDT558', 'UDT559'],
        reps: {
            'Cori': [8.6, 23.1, 6.7, 18.8, 2.6, 8.8, 5.1, 8.6, 13.5],
            'Randy': [10.9, 17.5, 5.0, 10.9, 9.3, 10.0, 12.2, 17.6, 11.3],
            'Sue': [null, null, 0.0, 2.7, 12.5, 0.0, 2.2, 10.7, 5.6],
            'Thomas': [27.3, 35.7, 8.3, 21.7, 5.6, 12.5, 25.0, 33.3, 16.7]
        },
        totals: {'Cori': 9.8, 'Randy': 11.9, 'Sue': 5.8, 'Thomas': 21.8}
    }
};

// Volume data structure with actual data
const volumeData = {
    'combined': {
        cohorts: ['551', '552', '553', '554', '555', '556', '557', '558', '559'],
        reps: {
            'Cori': {
                enrollments: [114, 83, 85, 96, 96, 65, 108, 132, 80],
                starts: [8, 10, 6, 13, 8, 4, 14, 14, 14]
            },
            'Randy': {
                enrollments: [135, 100, 98, 136, 98, 79, 96, 112, 89],
                starts: [15, 12, 5, 13, 12, 7, 13, 15, 11]
            },
            'Sue': {
                enrollments: [0, 0, 9, 65, 56, 61, 72, 89, 61],
                starts: [0, 0, 0, 2, 5, 2, 2, 8, 5]
            },
            'Thomas': {
                enrollments: [55, 46, 31, 39, 31, 25, 35, 38, 37],
                starts: [9, 7, 2, 6, 4, 3, 8, 11, 6]
            }
        }
    },
    'ndt-day': {
        cohorts: ['NDT551', 'NDT552', 'NDT553', 'NDT554', 'NDT555', 'NDT556', 'NDT557', 'NDT558', 'NDT559'],
        reps: {
            'Cori': {
                enrollments: [44, 49, 40, 39, 58, 22, 49, 37, 43],
                starts: [2, 4, 3, 2, 7, 1, 11, 3, 9]
            },
            'Randy': {
                enrollments: [71, 53, 58, 54, 44, 30, 47, 39, 36],
                starts: [8, 5, 3, 1, 7, 2, 7, 2, 5]
            },
            'Sue': {
                enrollments: [0, 0, 4, 22, 24, 24, 26, 22, 25],
                starts: [0, 0, 0, 1, 1, 2, 1, 2, 3]
            },
            'Thomas': {
                enrollments: [22, 28, 19, 12, 13, 15, 15, 13, 7],
                starts: [0, 2, 1, 0, 3, 2, 3, 2, 1]
            }
        }
    },
    'ndt-night': {
        cohorts: ['NDT552NC', 'NDT554NC', 'NDT556NC', 'NDT558NC'],
        reps: {
            'Cori': {
                enrollments: [8, 9, 9, 14],
                starts: [0, 2, 0, 4]
            },
            'Randy': {
                enrollments: [7, 18, 9, 5],
                starts: [0, 5, 1, 1]
            },
            'Sue': {
                enrollments: [0, 6, 9, 11],
                starts: [0, 0, 0, 0]
            },
            'Thomas': {
                enrollments: [4, 4, 2, 4],
                starts: [0, 1, 0, 2]
            }
        }
    },
    'udt': {
        cohorts: ['UDT551', 'UDT552', 'UDT553', 'UDT554', 'UDT555', 'UDT556', 'UDT557', 'UDT558', 'UDT559'],
        reps: {
            'Cori': {
                enrollments: [70, 26, 45, 48, 38, 34, 59, 81, 37],
                starts: [6, 6, 3, 9, 1, 3, 3, 7, 5]
            },
            'Randy': {
                enrollments: [64, 40, 40, 64, 54, 40, 49, 68, 53],
                starts: [7, 7, 2, 7, 5, 4, 6, 12, 6]
            },
            'Sue': {
                enrollments: [0, 0, 5, 37, 32, 28, 46, 56, 36],
                starts: [0, 0, 0, 1, 4, 0, 1, 6, 2]
            },
            'Thomas': {
                enrollments: [33, 14, 12, 23, 18, 8, 20, 21, 30],
                starts: [9, 5, 1, 5, 1, 1, 5, 7, 5]
            }
        }
    }
};

const repColors = {
    'Cori': '#FF6384',
    'Randy': '#36A2EB', 
    'Sue': '#FFCE56',
    'Thomas': '#4BC0C0'
};

let currentChart = null;
let comparisonChart = null;
let repFunnelCharts = {};
let shareCharts = {};
let currentChartType = 'line';

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    updateDashboard();
    updateRepFunnelCharts();
    updateShareCharts();
});

function setupEventListeners() {
    document.getElementById('programFilter').addEventListener('change', function() {
        updateDashboard();
        toggleFunnelVisibility();
    });
    document.getElementById('repFilter').addEventListener('change', updateDashboard);
    
    document.getElementById('lineChart').addEventListener('click', function() {
        setChartType('line');
    });
    
    document.getElementById('barChart').addEventListener('click', function() {
        setChartType('bar');
    });
}

function toggleFunnelVisibility() {
    const programType = document.getElementById('programFilter').value;
    const funnelSection = document.getElementById('funnelSection');
    
    if (programType === 'combined') {
        funnelSection.style.display = 'block';
    } else {
        funnelSection.style.display = 'none';
    }
}

function setChartType(type) {
    currentChartType = type;
    document.querySelectorAll('.controls button').forEach(btn => btn.classList.remove('active'));
    document.getElementById(type + 'Chart').classList.add('active');
    updateDashboard();
}

function updateDashboard() {
    const programType = document.getElementById('programFilter').value;
    const repFilter = document.getElementById('repFilter').value;
    
    updateSummaryCards(programType, repFilter);
    updateTrendsChart(programType, repFilter);
    updateComparisonChart(programType, repFilter);
    updateDataTable(programType, repFilter);
}

function updateSummaryCards(programType, repFilter) {
    const dataset = data[programType];
    const filteredData = filterData(dataset, repFilter);
    
    // Calculate statistics
    const averages = {};
    const variances = {};
    
    Object.keys(filteredData.reps).forEach(rep => {
        const values = filteredData.reps[rep].filter(v => v !== null);
        if (values.length > 0) {
            averages[rep] = values.reduce((a, b) => a + b, 0) / values.length;
            const mean = averages[rep];
            variances[rep] = values.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / values.length;
        }
    });

    // Top performer
    const topPerformer = Object.keys(averages).reduce((a, b) => averages[a] > averages[b] ? a : b);
    document.getElementById('topPerformer').textContent = topPerformer;

    // Most consistent (lowest variance)
    const mostConsistent = Object.keys(variances).reduce((a, b) => variances[a] < variances[b] ? a : b);
    document.getElementById('mostConsistent').textContent = mostConsistent;

    // Best cohort
    const cohortAverages = dataset.cohorts.map((cohort, index) => {
        const values = Object.values(dataset.reps).map(repData => repData[index]).filter(v => v !== null);
        return {
            cohort: cohort,
            average: values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : 0
        };
    });
    const bestCohort = cohortAverages.reduce((a, b) => a.average > b.average ? a : b);
    document.getElementById('bestCohort').textContent = bestCohort.cohort;

    // Program average
    const allValues = Object.values(averages);
    const programAvg = allValues.length > 0 ? 
        (allValues.reduce((a, b) => a + b, 0) / allValues.length).toFixed(1) + '%' : 'N/A';
    document.getElementById('programAverage').textContent = programAvg;
}

function filterData(dataset, repFilter) {
    if (repFilter === 'all') {
        return dataset;
    }
    
    return {
        cohorts: dataset.cohorts,
        reps: { [repFilter]: dataset.reps[repFilter] },
        totals: { [repFilter]: dataset.totals[repFilter] }
    };
}

function updateTrendsChart(programType, repFilter) {
    const ctx = document.getElementById('trendsChart').getContext('2d');
    const dataset = data[programType];
    const filteredData = filterData(dataset, repFilter);
    
    if (currentChart) {
        currentChart.destroy();
    }

    const datasets = Object.keys(filteredData.reps).map(rep => ({
        label: rep,
        data: filteredData.reps[rep],
        borderColor: repColors[rep],
        backgroundColor: repColors[rep],
        fill: currentChartType === 'line' ? false : true,
        tension: 0.4
    }));

    currentChart = new Chart(ctx, {
        type: currentChartType,
        data: {
            labels: filteredData.cohorts,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Start Rate (%)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Cohort'
                    }
                }
            }
        }
    });

    document.getElementById('chartTitle').textContent = 
        `Performance Trends - ${programType.toUpperCase().replace('-', ' ')}`;
}

function updateComparisonChart(programType, repFilter) {
    const ctx = document.getElementById('comparisonChart').getContext('2d');
    const dataset = data[programType];
    const filteredData = filterData(dataset, repFilter);

    if (comparisonChart) {
        comparisonChart.destroy();
    }

    const reps = Object.keys(filteredData.totals);
    const totals = reps.map(rep => filteredData.totals[rep]);
    const colors = reps.map(rep => repColors[rep]);

    comparisonChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: reps,
            datasets: [{
                label: 'Start Rate (%)',
                data: totals,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 2
            }]
        },
        options: {
            indexAxis: 'y', // This makes it horizontal
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Hide legend since colors already identify reps
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Start Rate (%)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Lead Rep'
                    }
                }
            },
            elements: {
                bar: {
                    borderRadius: 4 // Rounded corners for modern look
                }
            }
        }
    });
}

function updateDataTable(programType, repFilter) {
    const dataset = data[programType];
    const filteredData = filterData(dataset, repFilter);
    
    let tableHTML = '<table><thead><tr><th>Lead Rep</th>';
    filteredData.cohorts.forEach(cohort => {
        tableHTML += `<th>${cohort}</th>`;
    });
    tableHTML += '<th>TOTAL</th></tr></thead><tbody>';

    Object.keys(filteredData.reps).forEach(rep => {
        const repClass = `rep-${rep.toLowerCase()}`;
        tableHTML += `<tr class="${repClass}"><td><strong>${rep}</strong></td>`;
        filteredData.reps[rep].forEach(value => {
            tableHTML += `<td>${value === null ? 'N/A' : value.toFixed(1) + '%'}</td>`;
        });
        tableHTML += `<td><strong>${filteredData.totals[rep].toFixed(1)}%</strong></td></tr>`;
    });

    tableHTML += '</tbody></table>';
    document.getElementById('tableContainer').innerHTML = tableHTML;
    document.getElementById('tableTitle').textContent = 
        `Detailed Performance Data - ${programType.toUpperCase().replace('-', ' ')}`;
}

function updateRepFunnelCharts() {
    const reps = ['Cori', 'Randy', 'Sue', 'Thomas'];
    
    reps.forEach(rep => {
        const ctx = document.getElementById(`${rep.toLowerCase()}FunnelChart`).getContext('2d');
        const repData = funnelData.reps[rep];
        
        // Destroy existing chart
        if (repFunnelCharts[rep]) {
            repFunnelCharts[rep].destroy();
        }

        // Calculate conversion rates for display
        const leadToEnroll = ((repData.enrollments / repData.leads) * 100).toFixed(1);
        const enrollToStart = ((repData.starts / repData.enrollments) * 100).toFixed(1);

        repFunnelCharts[rep] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [`Leads\n${repData.leads.toLocaleString()}`, `Enrollments\n${repData.enrollments.toLocaleString()}\n(${leadToEnroll}%)`, `Starts\n${repData.starts.toLocaleString()}\n(${enrollToStart}%)`],
                datasets: [{
                    data: [repData.leads, repData.enrollments, repData.starts],
                    backgroundColor: [
                        repColors[rep] + '40',
                        repColors[rep] + '80', 
                        repColors[rep]
                    ],
                    borderColor: repColors[rep],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        display: false
                    },
                    x: {
                        ticks: {
                            font: {
                                size: 10
                            }
                        }
                    }
                },
                elements: {
                    bar: {
                        borderRadius: 4
                    }
                }
            }
        });
    });
}

function updateShareCharts() {
    const shareTypes = [
        { id: 'leadsShareChart', dataKey: 'leads' },
        { id: 'enrollmentsShareChart', dataKey: 'enrollments' },
        { id: 'startsShareChart', dataKey: 'starts' }
    ];

    shareTypes.forEach(shareType => {
        const ctx = document.getElementById(shareType.id).getContext('2d');
        
        // Destroy existing chart
        if (shareCharts[shareType.id]) {
            shareCharts[shareType.id].destroy();
        }

        const reps = Object.keys(funnelData.reps);
        const data = reps.map(rep => funnelData.reps[rep][shareType.dataKey]);
        const total = data.reduce((a, b) => a + b, 0);
        const percentages = data.map(value => ((value / total) * 100).toFixed(1));

        shareCharts[shareType.id] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: reps.map((rep, index) => `${rep}\n${data[index].toLocaleString()}\n(${percentages[index]}%)`),
                datasets: [{
                    data: data,
                    backgroundColor: reps.map(rep => repColors[rep]),
                    borderColor: reps.map(rep => repColors[rep]),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            font: {
                                size: 10
                            },
                            padding: 10
                        }
                    }
                }
            }
        });
    });
}

// Update the setupEventListeners function
function setupEventListeners() {
    document.getElementById('programFilter').addEventListener('change', function() {
        updateDashboard();
        toggleFunnelVisibility();
        toggleVolumeVisibility(); // Add this line
        updateVolumeChart(); // Add this line
    });
    document.getElementById('repFilter').addEventListener('change', updateDashboard);
    
    document.getElementById('lineChart').addEventListener('click', function() {
        setChartType('line');
    });
    
    document.getElementById('barChart').addEventListener('click', function() {
        setChartType('bar');
    });
}

// Add this new function for volume visibility
function toggleVolumeVisibility() {
    const programType = document.getElementById('programFilter').value;
    const volumeSection = document.getElementById('volumeSection');
    
    // Show volume chart for all program types
    volumeSection.style.display = 'block';
}

// Updated volume chart function (uses main program filter)
function updateVolumeChart() {
    const ctx = document.getElementById('volumeChart').getContext('2d');
    const programType = document.getElementById('programFilter').value;
    
    // Don't show volume chart for individual rep filters
    const repFilter = document.getElementById('repFilter').value;
    if (repFilter !== 'all') {
        document.getElementById('volumeSection').style.display = 'none';
        return;
    } else {
        document.getElementById('volumeSection').style.display = 'block';
    }
    
    const dataset = volumeData[programType];
    
    if (!dataset) {
        // Hide if no data for this program type
        document.getElementById('volumeSection').style.display = 'none';
        return;
    }
    
    if (volumeChart) {
        volumeChart.destroy();
    }

    const reps = Object.keys(dataset.reps);
    const cohorts = dataset.cohorts;
    
    // Create datasets for starts (bottom) and enrollments (top)
    const startsDatasets = reps.map(rep => ({
        label: `${rep} - Starts`,
        data: dataset.reps[rep].starts,
        backgroundColor: repColors[rep],
        borderColor: repColors[rep],
        borderWidth: 1,
        stack: 'volume'
    }));
    
    const enrollmentsDatasets = reps.map(rep => ({
        label: `${rep} - Enrollments`,
        data: dataset.reps[rep].enrollments,
        backgroundColor: repColors[rep] + '50',
        borderColor: repColors[rep],
        borderWidth: 1,
        stack: 'volume'
    }));

    const programTitles = {
        'combined': 'Combined Programs (NDT + UDT)',
        'ndt-day': 'NDT Day Classes',
        'ndt-night': 'NDT Night Classes',
        'udt': 'UDT Classes'
    };

    volumeChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: cohorts,
            datasets: [...startsDatasets, ...enrollmentsDatasets]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `${programTitles[programType]} - Volume by Cohort`,
                    font: {
                        size: 16,
                        weight: 'bold'
                    }
                },
                legend: {
                    position: 'top',
                    labels: {
                        generateLabels: function(chart) {
                            return reps.map(rep => ({
                                text: rep,
                                fillStyle: repColors[rep],
                                strokeStyle: repColors[rep],
                                lineWidth: 2
                            }));
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return `Cohort ${context[0].label}`;
                        },
                        label: function(context) {
                            const rep = context.dataset.label.split(' - ')[0];
                            const type = context.dataset.label.includes('Starts') ? 'Starts' : 'Enrollments';
                            return `${rep} ${type}: ${context.parsed.y}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Cohort'
                    }
                },
                y: {
                    beginAtZero: true,
                    stacked: true,
                    title: {
                        display: true,
                        text: 'Count'
                    }
                }
            },
            elements: {
                bar: {
                    borderRadius: 2
                }
            }
        }
    });
}

// Update the DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    updateDashboard();
    updateRepFunnelCharts();
    updateShareCharts();
    updateVolumeChart(); // Make sure this is called
});