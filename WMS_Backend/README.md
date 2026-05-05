---

# WMS 倉儲管理系統 - 開發與架構手冊

## 1. 專案簡介
本專案為一個基於 **FastAPI** 與 **SQLite** 的倉儲管理系統 (WMS)。主要用於管理企業內部的資產借用與耗材領用。
本系統不僅具備基礎的借用管理,更導入了**企業級稽核與防呆機制**,包含:自動化庫存鎖定(防超貸)、主管雙軌審核、退件逾期失效、領取逾期失效、實體部分毀損連動扣庫存、以及確保稽核軌跡的「軟刪除」與「歷史快照」架構,並搭配背景排程器自動巡檢逾期未還訂單並寄發通知。

### 🌟 v1.2 最新更新與核心里程碑
* **資料庫防禦升級**:導入「軟刪除 (Soft Delete)」取代物理刪除,並在訂單建立時寫入「歷史快照 (Snapshot)」,確保歷史稽核軌跡不因人員調職或物品改名而失真。
* **流程防呆極限化**:實作「先檢查庫存 + 寫入後二次驗證」的併發防超貸雙保險、退件逾期自動轉「已失效」、**已預約但領取時超時也自動轉「已失效」**,並嚴格限制「借用中」的物品禁止由使用者自行取消,必須走實體驗收。
* **歸還與毀損連動**:新增「管理員實體驗收」API,支援提報「部分毀損」,並會自動連動扣除物品庫存表的物理總數。
* **權限統一守門**:抽出 `_verify_manager` / `_verify_admin` 兩個 helper,**所有需要主管或管理員身分的動作都集中守門**,避免越權與重複判斷。並一致禁止「自我簽核」與「自我發放」。
* **背景排程巡檢**:導入 `scheduler.py`,系統啟動後即在背景非同步執行,定期檢查所有「借用中且超過預計歸還時間」的訂單並寄發逾期通知,以 `overdue_notice_sent` 欄位避免重複轟炸。
* **高階邏輯報表**:完善 `View_Usage_Records` 檢視表,透過 `LEFT JOIN` 動態關聯審核主管資訊,並精準處理 `CASE WHEN` 的運算順序,自動評估使用者的歸還表現(準時、提前、逾期,並區分是否部分毀損)。
* **自動化測試工程**:建構完整的 E2E 整合測試腳本 (`test_integration.py`),分為 7 大模塊共 19 個測試,涵蓋正/反向邊界測試,並內建暫停斷點以利資料庫即時觀測。

---

## 2. 技術棧 (Tech Stack)
* **語言:** Python 3.10+
* **框架:** FastAPI
* **資料庫 ORM:** SQLAlchemy (搭配 SQLite)
* **資料驗證:** Pydantic (v2)
* **執行環境:** Uvicorn
* **背景排程:** asyncio (FastAPI lifespan)
* **測試框架:** pytest + httpx (TestClient)

---

## 3. 專案目錄與模組互動架構
本專案採用模組化 (Modular) 與分層架構,確保程式碼具備高維護性與單一職責。以下是各個 `.py` 檔案的詳細用途與互動關係:

```text
WMS_Backend/
├── main.py              # 啟動進入點 (含 lifespan 排程器掛載)
├── database.py          # 資料庫連線工廠
├── models.py            # 資料庫實體定義 (SQLAlchemy)
├── schemas.py           # 資料驗證模型 (Pydantic)
├── init_db.py           # 資料庫建表與檢視表 (View) 初始化腳本
├── reset_data.py        # 測試用輔助腳本 (一鍵清空資料 + 重置 AUTOINCREMENT)
├── scheduler.py         # 背景排程器 (定期巡檢逾期未還訂單)
├── WMS.db               # SQLite 資料庫實體檔案 (動態生成)
├── test_integration.py  # E2E 整合測試腳本 (含檢視斷點)
├── routers/             # API 路由層 (Controllers)
│   ├── __init__.py
│   ├── users.py         # 人員管理 (含軟刪除)
│   ├── items.py         # 物品管理 (含軟刪除、總量降級防呆)
│   ├── records.py       # 核心借用與生命週期狀態機
│   └── dashboards.py    # 唯讀報表 (直連 View)
└── services/            # 外部服務整合層
    ├── __init__.py
    └── notifications.py # 模擬通知服務 (核准/駁回/退回/逾期)
```

### 檔案職責與互動說明
* **`main.py` (總機)**:系統的啟動入口。負責建立 FastAPI 實例,將 `routers/` 下的所有 API 路由掛載進來,並透過 `lifespan` 在系統啟動時把 `scheduler.check_overdue_records()` 丟到背景非同步執行,系統關閉時自動取消任務。
* **`database.py` (連線工廠)**:設定 SQLAlchemy 引擎與 `SessionLocal`,提供 `get_db()` 依賴注入函式。
* **`models.py` (底層藍圖)**:定義 `User`, `Item`, `Record` 三個 ORM 類別,直接對應資料表結構與 Foreign Key 關聯;Record 內含完整的歷史快照欄位 (`snap_user_name`, `snap_user_dept`, `snap_item_name`, `snap_item_type`) 與逾期通知旗標 (`overdue_notice_sent`)。
* **`schemas.py` (安檢門)**:定義所有 API 的 Request / Response 格式。針對借用流程提供 `RecordCreate` / `RecordApprove` / `RecordReject` / `RecordPickup` / `RecordReturn` / `RecordCancel` 等專用 schema,精準驗證每個動作的必填欄位。
* **`routers/records.py` (核心大腦)**:系統中最複雜的模組,共 9 支 API,包含:
    1. 透過 `schemas` 驗證前端資料。
    2. 在頂端定義 `_verify_manager` 與 `_verify_admin` 兩個 helper,所有需要主管/管理員身分的動作都呼叫它們做集中守門。
    3. 查詢 `View_Item_Inventory` 進行**事前**防超貸檢查,寫入後再用 `db.flush()` 做**事後**二次驗證,雙保險擋下併發超貸。
    4. 將「歷史快照」寫入訂單,並依物品類型自動派發狀態機(耗材直接結案 / 資產免審核直接已預約 / 資產須審核進入待審核)。
    5. 在 pickup 與 resubmit 時都會檢查 `datetime.now() > expected_borrow_time`,逾期則自動將狀態改為「已失效」並回傳 400。
* **`routers/items.py`**:除了基本 CRUD,在 PATCH 修改 `total_qty` 時會比對 `View_Item_Inventory` 的「累積毀損 + 借用 + 凍結」總和,**禁止把總量改到比已佔用數還低**,避免帳面變負數。
* **`routers/dashboards.py`**:三支唯讀報表 API,直接讀取 View,搭配關鍵字、表現、部門等多維度過濾。
* **`scheduler.py` (排程器)**:背景無限迴圈,每 60 秒巡檢一次「狀態為『借用中』、`expected_return_time` 已過、且 `overdue_notice_sent = 0`」的訂單,觸發 `send_overdue_notice` 並把旗標設為 1,避免同一筆訂單重複寄信。實務部署時可將間隔改為 86400(一天一次)。
* **`services/notifications.py`**:模擬寄信服務,提供 `send_approval_notice` / `send_rejection_notice` / `send_soft_reject_notice` / `send_overdue_notice` 四種通知,以 Logger + print 方式呈現,方便 Demo 觀察。
* **`init_db.py` (基礎建設)**:純 SQL 初始化腳本。負責建立含有 `is_active`(軟刪除)、`damaged_qty`(毀損數)、`overdue_notice_sent`(逾期旗標)、`snap_*`(歷史快照)等欄位的資料表,以及兩張報表專用的邏輯 View。
* **`reset_data.py` (清道夫)**:依 FK 安全順序(Records → Items → Users)清空資料,並重置 `sqlite_sequence` 讓 `record_id` 從 1 重新開始。

---

## 4. 核心業務邏輯 (Business Logic)

### A. 借用與防超貸機制
* **依物品屬性自動派發流程**:耗材一律免還、直接結案並即時扣 `total_qty`;資產則依 `needs_manager_approval` 自動進入「待審核」或「已預約」。
* **強制歸還時間**:借用「資產」時系統強制要求填寫「預計歸還時間」,耗材則允許免填(API 端會自動把該欄位設為 None)。
* **雙保險防超貸**:
    1. **事前檢查** — 訂單建立前,比對 `View_Item_Inventory` 的「實際可用」數量,庫存不足直接擋下(400 Error)。
    2. **事後二次驗證** — 寫入訂單後 `db.flush()`,讓新訂單也納入 View 計算,若「實際可用」變成負數代表發生併發超貸,系統會 rollback 並回傳 409,要求重試。

### B. 狀態機與生命週期
* **雙軌退件機制**(同一支 API 用 `?action_type=soft` 或 `?action_type=hard` 區分):
    * **退回修改 (Soft Reject)**:狀態轉「退回修改」,**保留凍結庫存**。若超過「預計取用時間」仍未重新送審,resubmit 時會被強制標記為「已失效」並釋放庫存。
    * **直接駁回 (Hard Reject)**:狀態轉「已駁回」,立即釋放庫存並寄發駁回通知。
* **領取逾期自動失效**:即使主管已核准、狀態為「已預約」,管理員若在 `expected_borrow_time` 之後才嘗試 pickup,系統會自動把狀態改為「已失效」並回傳 400,杜絕「冷凍訂單」永遠卡住庫存。
* **取消申請**:使用者只能在實體發放前(待審核、已預約、退回修改)自行取消;一旦進入「借用中」,則必須透過管理員走實體歸還流程,不允許繞過。
* **管理員統一點交**:無論資產是否需要審核,實體的「發放 (Pickup)」與「歸還 (Return)」一律限制 `role = '管理員'` 的人員執行。並且**禁止管理員自我發放/自我簽核**(借用人 ≠ 操作者)。
* **權限守門統一化**:`_verify_manager` 檢查 `position == '主管'` 且仍在職,`_verify_admin` 檢查 `role == '管理員'` 且仍在職。所有需要這兩種身分的 API 都呼叫它們,避免重複判斷與遺漏。

### C. 稽核軌跡:軟刪除與歷史快照
* **軟刪除 (Soft Delete)**:人員離職或物品報廢時,API 僅會將 `is_active` 設為 `0`。防止破壞歷史紀錄的關聯,同時禁止停用的人/物發起新訂單。`View_Item_Inventory` 也會自動過濾掉 `is_active = 0` 的物品。
* **歷史快照 (Snapshot)**:借用當下,系統會將「借用人姓名/部門」與「物品名稱/類型」「影印」一份存入 `Records` 表(`snap_*` 欄位)。未來的歷程報表完全依賴快照,確保跨部門成本分攤的稽核準確性,即使原始的 User / Item 後來被改名或改部門也不影響歷史。
* **部分毀損連動**:歸還時若提報 `damaged_qty > 0`,系統會將訂單標記為「已歸還(部分毀損)」,並自動把毀損數量累加至 `Items.damaged_qty`,從總庫存中**永久扣除**。
* **總量降級防呆**:管理員若想透過 PATCH 調降 `total_qty`,系統會驗證新值不可低於「累積毀損 + 借用中 + 凍結中」,避免帳面失衡。

### D. 背景排程器與逾期通知
* **檢查條件**:`status = '借用中'` AND `expected_return_time` 不為 NULL AND `expected_return_time < now()` AND `overdue_notice_sent = 0`。
* **執行頻率**:當前設為 60 秒一次(便於 Demo 觀察),實務上建議調整為 `asyncio.sleep(86400)`(一天一次)。
* **重複轟炸防護**:寄發通知後立即把 `overdue_notice_sent` 設為 `1`,確保同一筆逾期訂單只會通知一次。
* **生命週期掛載**:透過 FastAPI 的 `lifespan` context 註冊,系統啟動時自動開跑、關閉時自動取消,不需手動管理。

---

## 5. 資料庫邏輯檢視表 (Views)
本系統高度依賴檢視表來即時運算報表,確保資料的一致性:

1. **`View_Item_Inventory` (庫存動態表)**
   * 自動過濾已被軟刪除 (`is_active = 0`) 的物品。
   * **實際可用 = 物理總數 − 累積毀損數量 − 借用數量 − 凍結數量**。
   * 「凍結數量」會把「待審核」「已預約」與「退回修改且尚在取用期限內」三種狀態都計入,確保庫存帳精準反映「正在被佔用」的實況;退回修改一旦過期就不再計入。

2. **`View_Usage_Records` (使用歷程與表現表)**
   * 直接讀取 Records 表內的 `snap_*` 歷史快照,確保借用人與物品名稱即使後來改名也仍呈現「當時的真相」。
   * **多表關聯 (LEFT JOIN)**:透過連結 `Users` 表,動態抓取該筆訂單「審核人員」的最新姓名與部門。
   * 內建分層的 `CASE WHEN` 邏輯,精準評估歸還表現:
     - 區分「正常歸還」與「部分毀損歸還」兩條時間表現分支
     - 用 `±1800 秒` 容忍區間判斷準時 / 提前 / 逾期歸還
     - 借用中且過期顯示「逾期未還」、其他狀態各自獨立顯示中文標籤
   * 所有顯示欄位皆已全面中文化。

---

## 6. 快速啟動與測試指南 (Quick Start)

### 步驟 1:環境準備
確保已安裝 Python 3.10+,並安裝所需套件:
```bash
pip install fastapi uvicorn sqlalchemy pydantic pytest httpx
```

### 步驟 2:初始化資料庫
第一次啟動,或當 `models.py` 結構有重大變更時,請先刪除舊的 `WMS.db`,然後執行:
```bash
python init_db.py
```
*(系統將自動建立所有資料表、防呆約束與邏輯 View)*

### 步驟 3:啟動伺服器
```bash
uvicorn main:app --reload
```
開啟瀏覽器前往 `http://127.0.0.1:8000/docs` 即可使用 Swagger UI 進行視覺化 API 測試。
*(背景的逾期巡檢排程器會自動隨伺服器啟動,終端機可看到 `啟動排程巡檢` 的 log)*

### 步驟 4:執行斷點整合測試 (Integration Testing)
本專案提供完整的 E2E 測試腳本,涵蓋 **7 大模塊共 19 個測試**:

| 模塊 | 內容 |
|------|------|
| 1. 基礎建設與軟刪除 | 建立 5 位人員 + 4 件物品、軟刪除驗證 |
| 2. 防呆與越權攔截 | 庫存上限、停用人/物、自我簽核擋下、借用中無法取消 |
| 3. 物品生命週期 | 耗材直接結案、使用者自主取消、退回修改 → 重送過期失效 |
| 4. 歸還與部分毀損 | 正常歸還、部分毀損連動扣 `damaged_qty` |
| 5. 權限矩陣 | approve 須主管、pickup/return 須管理員、禁止自我發放 |
| 6. 時間驅動 | 已預約但 pickup 過期失效、退回修改 resubmit 仍有效 |
| 7. 併發超貸 | 雙執行緒同時搶有限庫存,驗證最多只有一個成功 |

執行(務必加 `-s` 才能看到 print 與暫停):
```bash
pytest test_integration.py -s
```
*(腳本會在每個模塊結束時暫停,並提示在 DBeaver 等資料庫工具下哪一段 SQL、預期看到什麼,按 Enter 才繼續)*

### 步驟 5:測試資料重置
若在測試過程中需要把系統還原為「空資料」狀態,請確保終端機沒有執行伺服器,然後:
```bash
python reset_data.py
```

---

## 7. API 端點總覽

### Users(`/api/users`)
| 方法 | 路徑 | 用途 |
|------|------|------|
| POST | `/` | 新增使用者 |
| GET | `/` | 取得使用者清單(支援部門/角色/啟用狀態過濾) |
| GET | `/{emp_id}` | 查詢單一使用者 |
| PATCH | `/{emp_id}` | 更新使用者欄位 |
| PATCH | `/{emp_id}/deactivate` | 軟刪除(離職) |
| DELETE | `/{emp_id}` | 硬刪除(若有 FK 關聯會被擋) |

### Items(`/api/items`)
與 Users 結構幾乎一致,額外在 PATCH `total_qty` 時會驗證不可低於「已佔用」。

### Records(`/api/records`)
| 方法 | 路徑 | 用途 |
|------|------|------|
| POST | `/` | 使用者發起借用申請(含雙保險防超貸) |
| GET | `/` | 取得訂單清單(支援人/物/狀態/類型/時間區間/排序) |
| GET | `/{record_id}` | 查詢單一訂單 |
| PUT | `/{record_id}/approve` | 主管核准(驗證主管身分 + 禁止自我簽核) |
| PUT | `/{record_id}/reject?action_type=soft\|hard` | 主管退件(同一端點,以 query 參數區分軟退/硬駁) |
| PUT | `/{record_id}/resubmit` | 退回修改後重送(會檢查取用時間是否仍有效) |
| PUT | `/{record_id}/pickup` | 管理員實體發放(驗證管理員 + 禁止自我發放 + 過期失效) |
| PUT | `/{record_id}/return` | 管理員實體驗收(支援部分毀損連動扣庫存) |
| PUT | `/{record_id}/cancel` | 使用者自行取消(僅限發放前狀態) |

### Dashboards(`/api/dashboards`)
| 方法 | 路徑 | 用途 |
|------|------|------|
| GET | `/inventory` | 動態庫存報表(支援關鍵字、僅顯示有庫存) |
| GET | `/my-records/{emp_id}` | 個人借用歷程(支援表現/狀態過濾) |
| GET | `/usage-records` | 全域使用歷程總表(支援部門/物品/表現過濾) |
