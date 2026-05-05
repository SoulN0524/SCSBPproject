import { Chart, registerables } from "chart.js";
import { AppState, InventoryItem } from "./types";
import "./styles/main.scss";

Chart.register(...registerables);

const API_BASE = "http://localhost:8000/api";

const state: any = {
  inventory: [],
  usageRecords: [],
  personalRecords: [],
  allUsers: [],
  currentUser: null as any,
  notices: [
    { name: "原子筆(黑)", rate: "6/日", days: "3天" },
    { name: "原子筆(紅)", rate: "2/日", days: "5天" },
    { name: "迴紋針", rate: "40/日", days: "6天" },
    { name: "訂書針", rate: "1/日", days: "4天" },
    { name: "便條紙", rate: "30/日", days: "5天" },
    { name: "電池", rate: "2/周", days: "3天" },
    { name: "印泥", rate: "1/月", days: "10天" },
  ],
};

let charts: { bar?: Chart; donut?: Chart } = {};

// --- API Calls ---

async function fetchInventory(): Promise<void> {
  try {
    console.log("Fetching inventory from:", `${API_BASE}/dashboards/inventory`);
    const response = await fetch(`${API_BASE}/dashboards/inventory`);
    if (!response.ok)
      throw new Error(
        `Failed to fetch inventory: ${response.status} ${response.statusText}`,
      );

    const data = await response.json();
    console.log("Inventory data received:", data);

    state.inventory = data;
    renderAll();

    if (state.inventory.length === 0) {
      console.warn("Inventory is empty. Please add items via 'Add Property'.");
      showToast("目前無庫存資料，請先新增財產");
    }

    if (
      document.getElementById("pageManage")?.classList.contains("hidden") ===
      false
    ) {
      initManageCharts();
    }
  } catch (error) {
    console.error("Error fetching inventory:", error);
    showToast("無法取得庫存資料，請檢查後端連線 (localhost:8000)");
  }
}

async function fetchUsageRecords(): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/dashboards/usage-records`);
    if (!response.ok) throw new Error("Failed to fetch usage records");
    state.usageRecords = await response.json();
    renderOrderQueryTable();
  } catch (error) {
    console.error("Error fetching usage records:", error);
  }
}

async function fetchPersonalRecords(empId: string): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/dashboards/my-records/${empId}`);
    if (!response.ok) throw new Error("Failed to fetch personal records");
    state.personalRecords = await response.json();
    renderPersonalDetailTable();
    updateStatusCards();
  } catch (error) {
    console.error("Error fetching personal records:", error);
  }
}

async function fetchUsers(): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/users/?is_active=1`);
    if (!response.ok) throw new Error("Failed to fetch users");
    state.allUsers = await response.json();

    const select = document.getElementById("currentUserSelect") as HTMLSelectElement;
    if (!select) return;

    select.innerHTML = state.allUsers.map((u: any) =>
      `<option value="${u.emp_id}" style="color:#333;background:white">${u.name} (${u.position})</option>`
    ).join("");

    // 預設選中第一位主管，若無則選第一位
    const defaultManager = state.allUsers.find((u: any) => u.position === "主管");
    if (defaultManager) select.value = defaultManager.emp_id;

    updateCurrentUser();

    select.addEventListener("change", updateCurrentUser);
  } catch (error) {
    console.error("Error fetching users:", error);
  }
}

function updateCurrentUser(): void {
  const select = document.getElementById("currentUserSelect") as HTMLSelectElement;
  if (!select) return;
  const empId = select.value;
  state.currentUser = state.allUsers.find((u: any) => u.emp_id === empId) || null;

  const avatar = document.getElementById("currentUserAvatar") as HTMLImageElement;
  const roleLabel = document.getElementById("currentUserRole");

  if (state.currentUser) {
    if (avatar) avatar.src = `https://api.dicebear.com/7.x/avataaars/svg?seed=${state.currentUser.name}`;
    if (roleLabel) roleLabel.textContent = `${state.currentUser.department} · ${state.currentUser.role}`;
    
    // Fetch personal records for the new user
    fetchPersonalRecords(state.currentUser.emp_id);
  }
}

function renderOrderQueryTable(): void {
  const tbody = document.getElementById("orderQueryTableBody");
  if (!tbody) return;

  const fEmpId = (
    document.getElementById("queryEmpId") as HTMLInputElement
  )?.value.toLowerCase();
  const fEmpName = (
    document.getElementById("queryEmpName") as HTMLInputElement
  )?.value.toLowerCase();
  const fPos = (document.getElementById("queryPosition") as HTMLSelectElement)
    ?.value;
  const fRole = (document.getElementById("queryRole") as HTMLSelectElement)
    ?.value;
  const fRange = (document.getElementById("queryDateRange") as HTMLInputElement)
    ?.value;

  const filtered = state.usageRecords.filter((r: any) => {
    if (fEmpId && !r["借用人編號"].toLowerCase().includes(fEmpId)) return false;
    if (fEmpName && !r["借用人姓名"].toLowerCase().includes(fEmpName))
      return false;
    if (fPos && r["借用人職位"] !== fPos) return false;
    if (fRole && r["借用人角色"] !== fRole) return false;

    // 日期間隔限制法 (Flatpickr range)
    if (fRange && fRange.includes("to")) {
      const [start, end] = fRange.split(" to ");
      const recordDate = r["預計租借時間"]?.split(" ")[0];
      if (recordDate < start || recordDate > end) return false;
    } else if (fRange) {
      // Single date picked
      const recordDate = r["預計租借時間"]?.split(" ")[0];
      if (recordDate !== fRange) return false;
    }

    return true;
  });

  tbody.innerHTML = filtered
    .map(
      (r: any) => `
    <tr class="border-b border-gray-50 hover:bg-gray-50">
      <td class="py-2 truncate">${r["借用人編號"]}</td>
      <td class="py-2 truncate">${r["借用人姓名"]}</td>
      <td class="py-2 font-medium truncate" title="${r["物品名稱"]}">${r["物品名稱"]}</td>
      <td class="py-2">${r["數量"]}</td>
      <td class="py-2"><span class="px-2 py-0.5 rounded-full ${r["原始狀態"] === "待簽核" ? "bg-yellow-100 text-yellow-700" : "bg-gray-100 text-gray-600"}">${r["原始狀態"]}</span></td>
      <td class="py-2">
        ${
          r["原始狀態"] === "待簽核"
            ? `
          <button onclick="handleApproveOrder('${r["訂單編號"]}')" class="bg-brand-red text-white px-2 py-1 rounded text-[10px] hover:bg-dark-red">簽核</button>
        `
            : "-"
        }
      </td>
    </tr>
  `,
    )
    .join("");
}

function renderPersonalDetailTable(): void {
  const tbody = document.getElementById("detailTableBody");
  if (!tbody) return;

  if (state.personalRecords.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-8 text-gray-400">目前無借用紀錄</td></tr>`;
    return;
  }

  tbody.innerHTML = state.personalRecords.map((r: any) => {
    let typeClass = r["交易類型"] === "耗材" ? "text-brand-red" : "";
    let approvalText = r["交易類型"].includes("須審核") ? "需簽核" : "免簽核";
    if (r["原始狀態"] === "待簽核") approvalText = "待簽核";
    
    return `
      <tr class="border-b border-gray-50 hover:bg-gray-50">
        <td class="py-3 ${typeClass}">${r["交易類型"].includes("資產") ? "資產" : "耗材"}</td>
        <td class="py-3">${approvalText}</td>
        <td class="py-3 font-medium">${r["物品名稱"]}</td>
        <td class="py-3">${r["數量"]}</td>
        <td class="py-3">${r["預計租借時間"]}</td>
        <td class="py-3">${r["預計歸還時間"] || "N/A"}</td>
        <td class="py-3">
          <span class="px-2 py-1 rounded-full text-[10px] ${getStatusColor(r["原始狀態"])}">
            ${r["原始狀態"]}
          </span>
        </td>
      </tr>
    `;
  }).join("");
}

function getStatusColor(status: string): string {
  switch (status) {
    case "待簽核": return "bg-yellow-100 text-yellow-700";
    case "已簽核": case "已預約": return "bg-blue-100 text-blue-700";
    case "借用中": return "bg-green-100 text-green-700";
    case "已逾期": return "bg-red-100 text-red-700";
    case "已結案": case "已歸還": return "bg-gray-100 text-gray-700";
    case "已駁回": return "bg-red-100 text-red-700";
    default: return "bg-gray-50 text-gray-500";
  }
}

function updateStatusCards(): void {
  const container = document.querySelector("#pageSearch aside");
  if (!container) return;

  const records = state.personalRecords;
  const signing = records.filter((r: any) => r["原始狀態"] === "待簽核");
  const approved = records.filter((r: any) => ["已簽核", "已預約"].includes(r["原始狀態"]));
  const borrowing = records.filter((r: any) => r["原始狀態"] === "借用中");
  const overdue = records.filter((r: any) => r["原始狀態"] === "已逾期");

  const renderCard = (title: string, count: number, items: any[]) => `
    <div class="status-card">
      <div class="flex justify-center items-center gap-2 status-title text-lg">
        <span class="text-2xl font-black">${count}</span> 案 ${title}
      </div>
      <div class="space-y-2 mt-2">
        ${items.slice(0, 3).map(i => `
          <div class="flex justify-between text-sm">
            <span class="text-gray-400">${i["預計租借時間"]?.split(" ")[0].slice(5)}</span>
            <span class="font-bold">${i["物品名稱"]}</span>
          </div>
        `).join("")}
        ${items.length > 3 ? `<div class="text-center text-[10px] text-gray-400">...以及其他 ${items.length - 3} 案</div>` : ""}
      </div>
    </div>
  `;

  // Update the aside content
  container.innerHTML = `
    <div class="flex items-center gap-2 mb-6">
      <span class="text-brand-red text-xl">🎯</span>
      <h2 class="text-xl font-bold text-brand-red">狀態列表 Status List</h2>
    </div>
    ${renderCard("簽核中", signing.length, signing)}
    ${renderCard("已簽核", approved.length, approved)}
    ${renderCard("借用中", borrowing.length, borrowing)}
    ${renderCard("已逾期", overdue.length, overdue)}
  `;
}

(window as any).handleApproveOrder = async (recordId: string) => {
  if (!recordId || recordId === "undefined") {
    showToast("錯誤：無效的訂單編號");
    return;
  }

  if (!state.currentUser) {
    showToast("請先在左側選擇當前操作人員");
    return;
  }

  if (state.currentUser.position !== "主管") {
    showToast(`簽核失敗：${state.currentUser.name} 的職位為「${state.currentUser.position}」，僅主管可執行簽核`);
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/records/${recordId}/approve`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manager_id: state.currentUser.emp_id }),
    });
    if (response.ok) {
      showToast(`訂單簽核成功！(簽核人: ${state.currentUser.name})`);
      fetchUsageRecords();
      fetchInventory();
    } else {
      const err = await response.json();
      showToast(`簽核失敗: ${err.detail}`);
    }
  } catch (e) {
    showToast("網路錯誤");
  }
};

async function submitPropertyAction(
  action: "add" | "update" | "scrap",
  data: any,
): Promise<void> {
  try {
    let response;
    if (action === "add") {
      response = await fetch(`${API_BASE}/items/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
    } else if (action === "update") {
      const { item_id, ...updateData } = data;
      response = await fetch(`${API_BASE}/items/${item_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updateData),
      });
    } else if (action === "scrap") {
      const url = new URL(`${API_BASE}/items/${data.item_id}/deactivate`);
      if (data.scrap_qty) {
        url.searchParams.append("scrap_qty", data.scrap_qty);
      }
      response = await fetch(url.toString(), {
        method: "PATCH",
      });
    }

    if (response && response.ok) {
      showToast(
        `${action === "add" ? "新增" : action === "update" ? "更新" : "報廢"}成功！`,
      );
      closeModal();
      fetchInventory();
    } else {
      const errorData = await response?.json();
      showToast(`操作失敗: ${errorData?.detail || "未知錯誤"}`);
    }
  } catch (error) {
    console.error(`Error during ${action}:`, error);
    showToast("系統錯誤，請稍後再試");
  }
}

// --- UI Rendering ---

function showToast(message: string): void {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className =
    "bg-white border-l-4 border-brand-red shadow-lg rounded px-4 py-3 transform transition-all duration-300 translate-x-full opacity-0 flex items-center gap-3";
  toast.innerHTML = `<span class="text-brand-red text-lg">ℹ️</span> <p class="text-sm font-medium text-gray-700">${message}</p>`;
  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove("translate-x-full", "opacity-0");
  });
  setTimeout(() => {
    toast.classList.add("translate-x-full", "opacity-0");
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function switchPage(pageId: string): void {
  const pageManage = document.getElementById("pageManage");
  const pageSearch = document.getElementById("pageSearch");
  const navSearch = document.getElementById("navSearch");
  const navManage = document.getElementById("navManage");

  pageManage?.classList.add("hidden");
  pageSearch?.classList.add("hidden");
  navSearch?.classList.remove("active-nav");
  navManage?.classList.remove("active-nav");

  const targetPage = document.getElementById(pageId);
  targetPage?.classList.remove("hidden");

  if (pageId === "pageManage") {
    navManage?.classList.add("active-nav");
    initManageCharts();
  } else if (pageId === "pageSearch") {
    navSearch?.classList.add("active-nav");
  }
  showToast(`切換至：${pageId === "pageManage" ? "財產管理" : "財產查詢"}`);
}

function renderInventoryItems(
  items: InventoryItem[],
  containerId: string,
): void {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  container.innerHTML = `
        <div class="flex justify-between text-[10px] font-bold text-brand-red mb-2 px-2 uppercase tracking-tighter">
            <span>名稱</span>
            <span class="text-gray-400 font-normal">存量狀況 (可用/總數)</span>
        </div>
    `;
  items.forEach((item) => {
    const total = item["物理總數"];
    const available = item["實際可用"];
    const percentage = total > 0 ? (available / total) * 100 : 0;
    const isCritical = available <= total * 0.1; // Alert if less than 10%

    const row = document.createElement("div");
    row.className = "flex items-center justify-between group py-1";
    row.innerHTML = `
            <span class="w-24 text-xs font-bold ${isCritical ? "text-red-500" : "text-gray-700"}">${item["物品名稱"]}</span>
            <div class="flex-1 mx-3 bg-gray-100 rounded-full h-3 overflow-hidden border border-gray-50">
                <div class="progress-gradient h-full transition-all duration-1000 ease-out" style="width: 0%"></div>
            </div>
            <span class="w-10 text-right text-xs font-bold ${isCritical ? "text-red-500" : "text-gray-800"}">${available}/${total}</span>
        `;
    container.appendChild(row);
    setTimeout(() => {
      const bar = row.querySelector(".progress-gradient") as HTMLElement;
      if (bar) bar.style.width = `${percentage}%`;
    }, 100);
  });
}

function renderNoticeTable(): void {
  const container = document.getElementById("noticeTableContainer");
  if (!container) return;
  container.innerHTML = `
        <table class="w-full text-xs text-center border-collapse">
            <thead>
                <tr class="text-brand-red font-bold border-b border-gray-100">
                    <th class="py-2">耗材名稱</th>
                    <th class="py-2">消耗速率</th>
                    <th class="py-2">安全邊際</th>
                </tr>
            </thead>
            <tbody class="text-gray-700 font-bold">
                ${state.notices
                  .map(
                    (n) => `
                    <tr class="border-b border-gray-50 hover:bg-gray-50">
                        <td class="py-3">${n.name}</td>
                        <td class="py-3">${n.rate}</td>
                        <td class="py-3 ${parseInt(n.days) <= 3 ? "text-red-500" : ""}">${n.days}</td>
                    </tr>
                `,
                  )
                  .join("")}
            </tbody>
        </table>
    `;
}

function renderAll(): void {
  const assets = state.inventory.filter((i) => i["物品類型"] === "資產");
  const consumables = state.inventory.filter((i) => i["物品類型"] === "耗材");

  renderInventoryItems(assets, "assetsContainerManage");
  renderInventoryItems(consumables, "consumablesContainerManage");
  renderInventoryItems(assets, "assetsContainerSearch");
  renderInventoryItems(consumables, "consumablesContainerSearch");
  renderNoticeTable();
}

function initManageCharts(): void {
  if (charts.bar) charts.bar.destroy();

  console.log("Rendering charts with inventory:", state.inventory);

  const assets = state.inventory.filter((i: any) => i["物品類型"] === "資產");
  const labels = assets.map((i: any) => i["物品名稱"]);
  const idle = assets.map((i: any) => i["實際可用"]);
  const reserved = assets.map((i: any) => i["凍結數量"]);
  const borrowed = assets.map((i: any) => i["借用中"]);
  const overdue = assets.map((i: any) => i["逾期數量"]);

  const barCtx = (
    document.getElementById("stackedBarChart") as HTMLCanvasElement
  )?.getContext("2d");
  if (barCtx) {
    charts.bar = new Chart(barCtx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "閒置中", data: idle, backgroundColor: "#86efac" },
          {
            label: "已預約/待簽核",
            data: reserved,
            backgroundColor: "#fde047",
          },
          {
            label: "借用中",
            data: borrowed,
            backgroundColor: "#fb923c",
          },
          {
            label: "已逾期",
            data: overdue,
            backgroundColor: "#ef4444", // Red color for overdue
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        scales: { x: { stacked: true }, y: { stacked: true } },
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 10, font: { size: 10 } },
          },
        },
      },
    });
  }
}

// --- Modal Logic ---

function openModal(title: string, contentHtml: string): void {
  const overlay = document.getElementById("modalOverlay");
  const modalTitle = document.getElementById("modalTitle");
  const modalBody = document.getElementById("modalBody");
  if (!overlay || !modalTitle || !modalBody) return;

  modalTitle.innerText = title;
  modalBody.innerHTML = contentHtml;
  overlay.classList.remove("hidden");
  overlay.classList.add("flex");
  setTimeout(() => {
    document.body.classList.add("modal-open");
  }, 10);
}

function closeModal(): void {
  const overlay = document.getElementById("modalOverlay");
  if (!overlay) return;
  document.body.classList.remove("modal-open");
  setTimeout(() => {
    overlay.classList.add("hidden");
    overlay.classList.remove("flex");
  }, 300);
}

async function handleAddProperty(): Promise<void> {
  let nextId = "Loading...";
  try {
    const res = await fetch(`${API_BASE}/items/next-id`);
    const json = await res.json();
    nextId = json.next_id;
  } catch (e) {
    console.error("Failed to fetch next ID", e);
    nextId = "Error";
  }

  const html = `
    <form id="formAddProperty">
      <div class="form-group">
        <label>物品編號 (自動生成)</label>
        <input type="text" name="item_id" value="${nextId}" readonly class="bg-gray-100 cursor-not-allowed">
      </div>
      <div class="form-group">
        <label>物品名稱</label>
        <input type="text" name="name" required placeholder="例如: 筆記型電腦" autocomplete="off">
      </div>
      <div class="form-group">
        <label>類型</label>
        <select name="type">
          <option value="資產">資產</option>
          <option value="耗材">耗材</option>
        </select>
      </div>
      <div class="form-group">
        <label>需要主管簽核</label>
        <select name="needs_manager_approval">
          <option value="Y">是 (Y)</option>
          <option value="N">否 (N)</option>
        </select>
      </div>
      <div class="form-group">
        <label>初始庫存總量</label>
        <input type="number" name="total_qty" required min="1" value="1">
      </div>
      <button type="submit" class="w-full bg-brand-red text-white py-3 rounded-xl font-bold shadow-lg hover:bg-[#600000] transition-all">確認新增</button>
    </form>
  `;
  openModal("新增財產 Item Registration", html);

  document
    .getElementById("formAddProperty")
    ?.addEventListener("submit", (e) => {
      e.preventDefault();
      const formData = new FormData(e.target as HTMLFormElement);
      const data = Object.fromEntries(formData.entries());
      submitPropertyAction("add", {
        ...data,
        total_qty: parseInt(data.total_qty as string),
      });
    });
}

function handleUpdateProperty(): void {
  const options = state.inventory
    .map((i) => `<option value="${i["物品編號"]}">${i["物品名稱"]}</option>`)
    .join("");
  const html = `
    <form id="formUpdateProperty">
      <div class="form-group">
        <label>選擇物品</label>
        <select name="item_id" id="updateItemSelect" required>
          <option value="">-- 請選擇 --</option>
          ${options}
        </select>
      </div>
      <div id="updateFields" class="hidden">
        <div class="form-group">
          <label>物品名稱</label>
          <input type="text" name="name" id="updateName">
        </div>
        <div class="form-group">
          <label>類型</label>
          <select name="type" id="updateType">
            <option value="資產">資產</option>
            <option value="耗材">耗材</option>
          </select>
        </div>
        <div class="form-group">
          <label>調整總量 (物理總數)</label>
          <input type="number" name="total_qty" id="updateQty" min="0">
        </div>
        <div class="form-group">
          <label>需要主管簽核</label>
          <select name="needs_manager_approval" id="updateApproval">
            <option value="Y">是 (Y)</option>
            <option value="N">否 (N)</option>
          </select>
        </div>
      </div>
      <button type="submit" class="w-full bg-brand-red text-white py-3 rounded-xl font-bold shadow-lg hover:bg-[#600000] transition-all">更新資料</button>
    </form>
  `;
  openModal("財產更新 Property Update", html);

  const select = document.getElementById(
    "updateItemSelect",
  ) as HTMLSelectElement;
  const fields = document.getElementById("updateFields");
  select?.addEventListener("change", () => {
    const item = state.inventory.find((i) => i["物品編號"] === select.value);
    if (item && fields) {
      fields.classList.remove("hidden");
      (document.getElementById("updateName") as HTMLInputElement).value =
        item["物品名稱"];
      (document.getElementById("updateType") as HTMLSelectElement).value =
        item["物品類型"];
      (document.getElementById("updateQty") as HTMLInputElement).value =
        item["物理總數"].toString();

      // Since item info from dashboard might not have needs_manager_approval directly (it's in Items table)
      // We might need to fetch the full item details or assume it's available in state if we fetched it.
      // Let's check if the inventory view has it. (Checked View_Item_Inventory in init_db.py, it DOES NOT have it)
      // So we need to fetch the item details.
      fetch(`${API_BASE}/items/${item["物品編號"]}`)
        .then((res) => res.json())
        .then((fullItem) => {
          (
            document.getElementById("updateApproval") as HTMLSelectElement
          ).value = fullItem.needs_manager_approval;
        });
    } else {
      fields?.classList.add("hidden");
    }
  });

  document
    .getElementById("formUpdateProperty")
    ?.addEventListener("submit", (e) => {
      e.preventDefault();
      const formData = new FormData(e.target as HTMLFormElement);
      const rawData = Object.fromEntries(formData.entries());
      const data: any = { item_id: rawData.item_id };
      if (rawData.name) data.name = rawData.name;
      if (rawData.type) data.type = rawData.type;
      if (rawData.total_qty)
        data.total_qty = parseInt(rawData.total_qty as string);
      if (rawData.needs_manager_approval)
        data.needs_manager_approval = rawData.needs_manager_approval;

      submitPropertyAction("update", data);
    });
}

function handleScrapProperty(): void {
  const options = state.inventory
    .map((i: any) => `<option value="${i["物品編號"]}">${i["物品名稱"]}</option>`)
    .join("");
  const html = `
    <form id="formScrapProperty">
      <div class="form-group">
        <label>選擇報廢物品</label>
        <select name="item_id" required>
          <option value="">-- 請選擇 --</option>
          ${options}
        </select>
      </div>
      <div class="form-group">
        <label>報廢數量 (留空則為全數報廢)</label>
        <input type="number" name="scrap_qty" min="1" placeholder="輸入報廢數量">
      </div>
      <p class="text-xs text-red-500 mb-4 font-medium">⚠️ 注意：報廢後該物品將依數量移除。若全數報廢，物品將不再顯示於可用清單。</p>
      <button type="submit" class="w-full bg-gray-800 text-white py-3 rounded-xl font-bold shadow-lg hover:bg-black transition-all">確認報廢</button>
    </form>
  `;
  openModal("財產報廢 Property Scrap", html);

  document
    .getElementById("formScrapProperty")
    ?.addEventListener("submit", (e) => {
      e.preventDefault();
      const formData = new FormData(e.target as HTMLFormElement);
      const data = Object.fromEntries(formData.entries());
      submitPropertyAction("scrap", data);
    });
}

(window as any).handleGlobalRequest = async (itemType: string) => {
  console.log("handleGlobalRequest triggered for:", itemType);
  
  try {
    if (!state.currentUser) {
      showToast("請先在側邊欄選擇當前人員");
      return;
    }

  let nextId = "...";
  try {
    const res = await fetch(`${API_BASE}/records/next-id`);
    const json = await res.json();
    nextId = json.next_id;
  } catch (e) {
    nextId = "Error";
  }

  const filteredItems = state.inventory.filter((i: any) => i["物品類型"] === itemType);
  if (filteredItems.length === 0) {
    console.warn("No items found for type:", itemType);
    showToast(`目前無庫存資料，無法進行${itemType === "資產" ? "借用" : "預約"}`);
    return;
  }
  const options = filteredItems.map((i: any) => `<option value="${i["物品編號"]}">${i["物品名稱"]} (庫存: ${i["實際可用"]})</option>`).join("");

  const html = `
    <form id="formRequestItem">
      <div class="form-group">
        <label>訂單編號 (預計)</label>
        <input type="text" value="${nextId}" readonly class="bg-gray-100 cursor-not-allowed">
      </div>
      <div class="form-group">
        <label>申請人</label>
        <input type="text" value="${state.currentUser.name} (${state.currentUser.emp_id})" readonly class="bg-gray-100 cursor-not-allowed">
      </div>
      <div class="form-group">
        <label>選擇物品</label>
        <select name="item_id" required>
          <option value="">-- 請選擇 --</option>
          ${options}
        </select>
      </div>
      <div class="form-group">
        <label>借用數量</label>
        <input type="number" name="qty" required min="1" value="1">
      </div>
      <div class="form-group">
        <label>預計借用時間</label>
        <input type="text" name="expected_borrow_time" id="reqBorrowTime" required placeholder="選擇日期時間" class="bg-white cursor-pointer" readonly>
      </div>
      ${itemType === "資產" ? `
        <div class="form-group">
          <label>預計歸還時間</label>
          <input type="text" name="expected_return_time" id="reqReturnTime" required placeholder="選擇日期時間" class="bg-white cursor-pointer" readonly>
        </div>
      ` : ""}
      <p class="text-[10px] text-gray-400 mb-4">* 耗材類僅需填寫預定領用時間</p>
      <button type="submit" class="w-full bg-brand-red text-white py-3 rounded-xl font-bold shadow-lg hover:bg-[#600000] transition-all">
        確認${itemType === "資產" ? "借用" : "預約"}
      </button>
    </form>
  `;

    try {
      openModal(`${itemType === "資產" ? "資產借用 Asset Borrow" : "耗材預約 Consumable Reservation"}`, html);
      console.log("Modal opened successfully");

      (window as any).flatpickr("#reqBorrowTime", {
        enableTime: true,
        dateFormat: "Y-m-d H:i",
        minDate: "today",
      });

      if (itemType === "資產") {
        (window as any).flatpickr("#reqReturnTime", {
          enableTime: true,
          dateFormat: "Y-m-d H:i",
          minDate: "today",
        });
      }
    } catch (err) {
      console.error("Error opening modal or initializing flatpickr:", err);
      showToast("系統錯誤，無法開啟表單");
      return;
    }

  document.getElementById("formRequestItem")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target as HTMLFormElement);
    const data: any = Object.fromEntries(formData.entries());
    
    const payload = {
      emp_id: state.currentUser.emp_id,
      item_id: data.item_id,
      qty: parseInt(data.qty),
      expected_borrow_time: data.expected_borrow_time,
      expected_return_time: data.expected_return_time || null,
    };

    try {
      const response = await fetch(`${API_BASE}/records/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        showToast("申請成功！");
        closeModal();
        fetchInventory();
        fetchUsageRecords();
        fetchPersonalRecords(state.currentUser.emp_id);
      } else {
        const err = await response.json();
        showToast(`申請失敗: ${err.detail}`);
      }
    } catch (error) {
      showToast("連線錯誤");
    }
  });
  } catch (error) {
    console.error("Critical error in handleGlobalRequest:", error);
    showToast("系統執行出錯");
  }
};

// --- Initialization ---

document.addEventListener("DOMContentLoaded", () => {
  fetchInventory();
  fetchUsageRecords();
  fetchUsers();

  document
    .getElementById("navSearch")
    ?.addEventListener("click", () => switchPage("pageSearch"));
  document
    .getElementById("navManage")
    ?.addEventListener("click", () => switchPage("pageManage"));

  document
    .getElementById("btnAddProperty")
    ?.addEventListener("click", handleAddProperty);
  document
    .getElementById("btnUpdateProperty")
    ?.addEventListener("click", handleUpdateProperty);
  document
    .getElementById("btnScrapProperty")
    ?.addEventListener("click", handleScrapProperty);
  const assetBtn = document.getElementById("btnRequestAsset");
  if (assetBtn) {
    console.log("Attaching listener to btnRequestAsset");
    assetBtn.addEventListener("click", () => (window as any).handleGlobalRequest("資產"));
  }

  const consumableBtn = document.getElementById("btnRequestConsumable");
  if (consumableBtn) {
    console.log("Attaching listener to btnRequestConsumable");
    consumableBtn.addEventListener("click", () => (window as any).handleGlobalRequest("耗材"));
  }
  document.getElementById("closeModal")?.addEventListener("click", closeModal);
  document.getElementById("modalOverlay")?.addEventListener("click", (e) => {
    if (e.target === document.getElementById("modalOverlay")) closeModal();
  });

  // Search Filters for Order Query
  ["queryEmpId", "queryEmpName", "queryPosition", "queryRole"].forEach((id) => {
    document
      .getElementById(id)
      ?.addEventListener("input", renderOrderQueryTable);
  });

  // Flatpickr Range
  (window as any).flatpickr("#queryDateRange", {
    mode: "range",
    dateFormat: "Y-m-d",
    onChange: () => {
      renderOrderQueryTable();
    },
  });

  switchPage("pageManage"); // Default to manage for testing
});
