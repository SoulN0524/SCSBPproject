# SBSC WHM 前端專案開發手冊

本文件旨在說明 **SBSC WHM 倉儲管理系統** 前端部分的專案架構、開發流程與技術規範。

## 🛠 技術棧 (Tech Stack)

- **建構工具**: [Vite](https://vitejs.dev/) - 提供極速的開發環境與編譯。
- **語言**: [TypeScript](https://www.typescriptlang.org/) - 提供強型別檢查與程式碼品質保證。
- **樣式**: 
  - [Tailwind CSS](https://tailwindcss.com/) - 實作快速響應式佈局。
  - [SCSS](https://sass-lang.com/) - 處理複雜的組件樣式與變數管理。
- **圖表**: [Chart.js](https://www.chartjs.org/) - 數據視覺化展示。

---

## 📂 專案架構 (Project Structure)

```text
frontend/
├── src/
│   ├── styles/
│   │   └── main.scss       # 全域樣式、品牌色變數、自定義元件
│   ├── types/
│   │   └── index.ts        # TypeScript Interface 定義 (Asset, Consumable 等)
│   └── main.ts             # 核心邏輯 (SPA 分頁切換、資料渲染、圖表初始化)
├── index.html              # HTML 骨架 (不包含邏輯與樣式)
├── tailwind.config.js      # Tailwind 設定與品牌色定義
├── tsconfig.json           # TypeScript 設定
└── package.json            # 專案依賴與腳本定義
```

---

## 🚀 快速開發指引

### 環境安裝
```bash
cd frontend
npm install
```

### 啟動開發伺服器
```bash
npm run dev
```

### 生產環境編譯
```bash
npm run build
```

---

## 💡 核心功能說明

### 1. SPA 分頁切換 (Single Page Application)
專案採用單頁式架構，透過 `main.ts` 中的 `switchPage(pageId)` 函數來切換顯示：
- `pageSearch`: 財產查詢 & 申請 (預設頁面)。
- `pageManage`: 財產管理 & 異動 (包含圖表分析)。

### 2. 圖表管理 (Chart.js)
所有圖表邏輯位於 `initManageCharts()`。為了防止分頁切換時產生 Canvas 渲染錯誤，每次重新渲染前都會調用 `chart.destroy()`。

### 3. 資料型別與強型別
新增資料結構時，請務必更新 `src/types/index.ts`。
例如，`Asset` 介面包含 `alert` 屬性，用於標示庫存為 0 或異常的項目。

### 4. 品牌視覺規範
樣式變數定義於 `main.scss` 中：
- `$brand-red`: `#800000`
- `$brand-gradient`: `linear-gradient(90deg, #FFA500, #FF6B6B)`

---

## 📡 API 串接建議
目前資料存放於 `main.ts` 的 `state` 物件中。未來串接 Python 後端時，建議在 `src/` 下建立 `api/` 資料夾，並使用 `fetch` 或 `axios` 進行請求封裝。

---

## 📝 備註
- 已移除舊有的 `css/` 與 `js/` 資料夾，請統一在 `src/` 目錄下進行開發。
