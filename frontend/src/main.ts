import { Chart, registerables } from 'chart.js';
import { AppState, Asset } from './types';
import './styles/main.scss';

Chart.register(...registerables);

const state: AppState = {
    assets: [
        { name: '筆電', current: 15, total: 20 },
        { name: '智能會議電視', current: 1, total: 2 },
        { name: '機械手臂', current: 0, total: 1, alert: true },
        { name: '靜音屏風', current: 3, total: 8 },
        { name: '推車', current: 2, total: 3 }
    ],
    consumables: [
        { name: '原子筆(黑)', current: 29, total: 60 },
        { name: '原子筆(紅)', current: 10, total: 60 },
        { name: '迴紋針', current: 53, total: 80 },
        { name: '訂書針', current: 4, total: 10 },
        { name: '便條紙', current: 28, total: 40 },
        { name: '電池', current: 25, total: 60 },
        { name: '印泥', current: 7, total: 8 }
    ],
    notices: [
        { name: '原子筆(黑)', rate: '6/日', days: '3天' },
        { name: '原子筆(紅)', rate: '2/日', days: '5天' },
        { name: '迴紋針', rate: '40/日', days: '6天' },
        { name: '訂書針', rate: '1/日', days: '4天' },
        { name: '便條紙', rate: '30/日', days: '5天' },
        { name: '電池', rate: '2/周', days: '3天' },
        { name: '印泥', rate: '1/月', days: '10天' }
    ],
    chartData: {
        labels: ['筆電', '智能會議電視', '機械手臂', '靜音屏風', '推車'],
        idle: [12, 1, 0, 3, 2],
        reserved: [3, 0, 1, 2, 0],
        borrowed: [4, 1, 0, 2, 1],
        overdue: [1, 0, 0, 1, 0]
    }
};

let charts: { bar?: Chart; donut?: Chart } = {};

function showToast(message: string): void {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'bg-white border-l-4 border-brand-red shadow-lg rounded px-4 py-3 transform transition-all duration-300 translate-x-full opacity-0 flex items-center gap-3';
    toast.innerHTML = `<span class="text-brand-red text-lg">ℹ️</span> <p class="text-sm font-medium text-gray-700">${message}</p>`;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.classList.remove('translate-x-full', 'opacity-0'); });
    setTimeout(() => {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function switchPage(pageId: string): void {
    const pageManage = document.getElementById('pageManage');
    const pageSearch = document.getElementById('pageSearch');
    const navSearch = document.getElementById('navSearch');
    const navManage = document.getElementById('navManage');

    pageManage?.classList.add('hidden');
    pageSearch?.classList.add('hidden');
    navSearch?.classList.remove('active-nav');
    navManage?.classList.remove('active-nav');

    const targetPage = document.getElementById(pageId);
    targetPage?.classList.remove('hidden');

    if (pageId === 'pageManage') {
        navManage?.classList.add('active-nav');
        initManageCharts();
    } else if (pageId === 'pageSearch') {
        navSearch?.classList.add('active-nav');
    }
    showToast(`切換至：${pageId === 'pageManage' ? '財產管理' : '財產查詢'}`);
}

function renderProgressItems(data: (Asset | { name: string; current: number; total: number })[], containerId: string): void {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = `
        <div class="flex justify-between text-[10px] font-bold text-brand-red mb-2 px-2 uppercase tracking-tighter">
            <span>資產名稱</span>
            <span class="text-gray-400 font-normal">存量狀況 (未預約數量/庫存總量)</span>
        </div>
    `;
    data.forEach(item => {
        const percentage = (item.current / item.total) * 100;
        const isCritical = item.current === 0 || (item as Asset).alert;
        const row = document.createElement('div');
        row.className = 'flex items-center justify-between group';
        row.innerHTML = `
            <span class="w-24 text-xs font-bold ${isCritical ? 'text-red-500' : 'text-gray-700'}">${item.name}</span>
            <div class="flex-1 mx-3 bg-gray-100 rounded-full h-3 overflow-hidden border border-gray-50">
                <div class="progress-gradient h-full transition-all duration-1000 ease-out" style="width: 0%"></div>
            </div>
            <span class="w-10 text-right text-xs font-bold ${isCritical ? 'text-red-500' : 'text-gray-800'}">${item.current}/${item.total}</span>
        `;
        container.appendChild(row);
        setTimeout(() => {
            const bar = row.querySelector('.progress-gradient') as HTMLElement;
            if (bar) bar.style.width = `${percentage}%`;
        }, 100);
    });
}

function renderNoticeTable(): void {
    const container = document.getElementById('noticeTableContainer');
    if (!container) return;
    container.innerHTML = `
        <table class="w-full text-[10px] text-center border-collapse">
            <thead>
                <tr class="text-brand-red font-bold border-b border-gray-100">
                    <th class="py-2">耗材名稱</th>
                    <th class="py-2">消耗速率</th>
                    <th class="py-2">安全邊際</th>
                </tr>
            </thead>
            <tbody class="text-gray-700 font-bold">
                ${state.notices.map(n => `
                    <tr class="border-b border-gray-50 hover:bg-gray-50">
                        <td class="py-3">${n.name}</td>
                        <td class="py-3">${n.rate}</td>
                        <td class="py-3 ${parseInt(n.days) <= 3 ? 'text-red-500' : ''}">${n.days}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function initManageCharts(): void {
    if (charts.bar) charts.bar.destroy();
    if (charts.donut) charts.donut.destroy();

    const barCtx = (document.getElementById('stackedBarChart') as HTMLCanvasElement)?.getContext('2d');
    if (barCtx) {
        charts.bar = new Chart(barCtx, {
            type: 'bar',
            data: {
                labels: state.chartData.labels,
                datasets: [
                    { label: '閒置中', data: state.chartData.idle, backgroundColor: '#86efac' },
                    { label: '已預約', data: state.chartData.reserved, backgroundColor: '#fde047' },
                    { label: '借用中', data: state.chartData.borrowed, backgroundColor: '#fb923c' },
                    { label: '已逾期', data: state.chartData.overdue, backgroundColor: '#ef4444' }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: { x: { stacked: true }, y: { stacked: true } },
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } }
            }
        });
    }

    const donutCtx = (document.getElementById('donutChart') as HTMLCanvasElement)?.getContext('2d');
    if (donutCtx) {
        charts.donut = new Chart(donutCtx, {
            type: 'doughnut',
            data: { datasets: [{ data: [14.2, 85.8], backgroundColor: ['#800000', '#e5e7eb'] }] },
            options: { cutout: '70%', plugins: { tooltip: { enabled: false } } },
            plugins: [{
                id: 'textCenter',
                beforeDraw: function(chart: any) {
                    const { width, height, ctx } = chart;
                    ctx.restore();
                    ctx.font = "bold 1.2em 'Noto Sans TC'";
                    ctx.textBaseline = "middle";
                    ctx.fillStyle = "#800000";
                    const text = "14.2%";
                    const textX = Math.round((width - ctx.measureText(text).width) / 2);
                    const textY = height / 2;
                    ctx.fillText(text, textX, textY);
                    ctx.save();
                }
            }]
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    renderProgressItems(state.assets, 'assetsContainerManage');
    renderProgressItems(state.consumables, 'consumablesContainerManage');
    renderProgressItems(state.assets, 'assetsContainerSearch');
    renderProgressItems(state.consumables, 'consumablesContainerSearch');
    renderNoticeTable();
    
    document.getElementById('navSearch')?.addEventListener('click', () => switchPage('pageSearch'));
    document.getElementById('navManage')?.addEventListener('click', () => switchPage('pageManage'));
    
    switchPage('pageSearch');
});
