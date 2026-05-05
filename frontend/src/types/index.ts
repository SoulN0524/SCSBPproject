export interface InventoryItem {
  "物品編號": string;
  "物品名稱": string;
  "物品類型": "耗材" | "資產";
  "物理總數": number;
  "累積毀損數量": number;
  "借用中": number;
  "逾期數量": number;
  "凍結數量": number;
  "實際可用": number;
}

export interface Notice {
  name: string;
  rate: string;
  days: string;
}

export interface ChartData {
  labels: string[];
  idle: number[];
  reserved: number[];
  borrowed: number[];
  overdue: number[];
}

export interface AppState {
  inventory: InventoryItem[];
  notices: Notice[];
}
