document.addEventListener('DOMContentLoaded', () => {
    // Set default dates
    const today = new Date();
    const fiveYearsAgo = new Date();
    fiveYearsAgo.setFullYear(today.getFullYear() - 5);
    
    document.getElementById('end_date').valueAsDate = today;
    document.getElementById('start_date').valueAsDate = fiveYearsAgo;
    document.getElementById('ticker').value = '2330.TW, SPY';
    document.getElementById('amount').value = 10000;

    let growthChart = null;

    const tickerInput = document.getElementById('ticker');
    const infoContainer = document.getElementById('company-info-container');
    
    // Fetch Company Info on Blur
    tickerInput.addEventListener('blur', async () => {
        const val = tickerInput.value.trim();
        if(!val) return;

        // Show skeleton loading cards
        const tickers = val.split(',').map(t => t.trim()).filter(Boolean);
        infoContainer.innerHTML = tickers.map(() => `
            <div class="company-card">
                <div class="skeleton short" style="margin-bottom:0.6rem;height:0.7rem;width:40%"></div>
                <div class="skeleton wide" style="margin-bottom:0.5rem;height:1rem;width:75%"></div>
                <div class="skeleton short" style="margin-bottom:1rem;height:0.75rem;width:45%;border-radius:1rem"></div>
                <div class="skeleton full"></div>
                <div class="skeleton full"></div>
                <div class="skeleton wide"></div>
            </div>
        `).join('');

        try {
            const res = await fetch(`/api/info?tickers=${encodeURIComponent(val)}`);
            if(!res.ok) throw new Error("Failed to fetch info");
            const data = await res.json();

            infoContainer.innerHTML = '';

            for (const [ticker, info] of Object.entries(data.data)) {
                const card = document.createElement('div');
                card.className = 'company-card';
                card.innerHTML = `
                    <div class="company-ticker">${ticker}</div>
                    <div class="company-name">${info.name}</div>
                    <div class="company-sector">${info.sector}</div>
                    ${info.short_intro ? `<p style="font-size:0.8rem;color:#a5b4fc;margin-bottom:0.75rem;">${info.short_intro}</p>` : ''}
                    <div class="company-summary">${info.summary}</div>
                `;
                infoContainer.appendChild(card);
            }

        } catch(e) {
            infoContainer.innerHTML = '<div class="info-placeholder"><p style="color:var(--danger)">無法取得資料，請稍後再試。</p></div>';
        }
    });
    
    // Trigger blur once on load to populate defaults
    tickerInput.dispatchEvent(new Event('blur'));


    const form = document.getElementById('dca-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const btn = document.getElementById('submit-btn');
        const errorMsg = document.getElementById('error-message');
        
        btn.classList.add('btn-loading');
        btn.innerHTML = '<span>計算中...</span>';
        errorMsg.textContent = '';
        
        const payload = {
            tickers: tickerInput.value.trim(),
            amount: parseFloat(document.getElementById('amount').value),
            start_date: document.getElementById('start_date').value,
            end_date: document.getElementById('end_date').value
        };

        try {
            const response = await fetch('/api/calculate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || '發生未知錯誤');
            }

            renderDashboard(data);

        } catch (error) {
            errorMsg.textContent = error.message;
        } finally {
            btn.classList.remove('btn-loading');
            btn.innerHTML = '<span>開始計算</span>';
        }
    });

    function renderDashboard(data) {
        // Formate numbers
        const nFormat = new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 0 });
        const pFormat = new Intl.NumberFormat('zh-TW', { style: 'percent', maximumFractionDigits: 2 });

        document.getElementById('kpi-invested').textContent = '$' + nFormat.format(data.total_invested);
        document.getElementById('kpi-final').textContent = '$' + nFormat.format(data.final_value);
        
        const cagrEl = document.getElementById('kpi-cagr');
        cagrEl.textContent = pFormat.format(data.cagr);
        cagrEl.parentElement.className = 'kpi-card ' + (data.cagr >= 0 ? 'success' : 'danger');

        const ddEl = document.getElementById('kpi-drawdown');
        ddEl.textContent = pFormat.format(data.max_drawdown);

        renderChart(data);
    }

    const COLORS = [
        { border: '#6366f1', bg: 'rgba(99, 102, 241, 0.1)' }, // Indigo
        { border: '#ec4899', bg: 'rgba(236, 72, 153, 0.1)' }, // Pink
        { border: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' }, // Emerald
        { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)' }, // Amber
        { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.1)' }  // Purple
    ];

    function renderChart(data) {
        const ctx = document.getElementById('growth-chart').getContext('2d');
        
        if (growthChart) {
            growthChart.destroy();
        }

        Chart.defaults.color = '#94a3b8';
        Chart.defaults.font.family = "'Inter', sans-serif";
        
        const datasets = [];
        let colorIndex = 0;
        
        // Add actual portfolio lines for each ticker
        for (const [ticker, stats] of Object.entries(data.tickers)) {
            const color = COLORS[colorIndex % COLORS.length];
            datasets.push({
                label: `${ticker} (CAGR: ${(stats.cagr * 100).toFixed(1)}%)`,
                data: stats.portfolio,
                borderColor: color.border,
                backgroundColor: color.bg,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: true,
                tension: 0.4
            });
            colorIndex++;
        }

        // Add overall invested line
        datasets.push({
            label: '整體累計投入本金',
            data: data.chart_invested,
            borderColor: '#94a3b8',
            borderWidth: 1.5,
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false,
            tension: 0.1
        });

        growthChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.chart_labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            boxWidth: 8
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#e2e8f0',
                        bodyColor: '#e2e8f0',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    // Strip out the CAGR part from tooltip label for cleaner look
                                    label = label.split(' (')[0] + ': ';
                                }
                                if (context.parsed.y !== null) {
                                    label += new Intl.NumberFormat('zh-TW', { style: 'currency', currency: 'TWD', maximumFractionDigits: 0 }).format(context.parsed.y);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { maxTicksLimit: 8 }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            callback: function(value) {
                                if(value >= 1000000) return (value / 1000000) + 'M';
                                if(value >= 1000) return (value / 1000) + 'K';
                                return value;
                            }
                        }
                    }
                }
            }
        });
    }
});
