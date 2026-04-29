import sqlite3

def initialize_database():
    # 連接到當前資料夾的 WMS.db
    conn = sqlite3.connect('WMS.db')
    
    # 強制啟用 SQLite 的 Foreign Key (外鍵) 檢查
    # 確保 User/Item 被硬刪除時，若有 Records 關聯會正確阻擋
    conn.execute("PRAGMA foreign_keys = ON;")
    
    cursor = conn.cursor()

    # 執行 SQL 腳本以建立所有的表與 View
    sql_script = """
    -- 1. 建立人員表
    CREATE TABLE IF NOT EXISTS Users (
        emp_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        department TEXT,
        position TEXT CHECK(position IN ('員工', '主管')), 
        role TEXT CHECK(role IN ('使用者', '管理員')),
        is_active INTEGER DEFAULT 1
    );

    -- 2. 建立物品表 (新增 damaged_qty)
    CREATE TABLE IF NOT EXISTS Items (
        item_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT CHECK(type IN ('耗材', '資產')), 
        needs_manager_approval CHAR(1) CHECK(needs_manager_approval IN ('Y', 'N')), 
        total_qty INTEGER DEFAULT 0,
        damaged_qty INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    );

    -- 3. 建立紀錄表 
    CREATE TABLE IF NOT EXISTS Records (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_id TEXT,
        item_id TEXT,
        qty INTEGER NOT NULL,
        transaction_type TEXT CHECK(transaction_type IN ('資產免審核', '資產須審核', '耗材')),
        status TEXT CHECK(status IN ('待審核', '已預約', '借用中', '已歸還', '已歸還(部分毀損)', '已結案', '退回修改', '已駁回', '已取消', '已失效')),
        expected_borrow_time DATETIME,
        expected_return_time DATETIME,
        actual_return_time DATETIME,
        manager_id TEXT,
        reject_reason TEXT,
        overdue_notice_sent INTEGER DEFAULT 0,
        snap_user_name TEXT,
        snap_user_dept TEXT,
        snap_item_name TEXT,
        snap_item_type TEXT,
        FOREIGN KEY (emp_id) REFERENCES Users(emp_id),
        FOREIGN KEY (item_id) REFERENCES Items(item_id),
        FOREIGN KEY (manager_id) REFERENCES Users(emp_id)
    );

    -- 4. 建立庫存檢視表 (扣除毀損數量)
    DROP VIEW IF EXISTS View_Item_Inventory;
    CREATE VIEW View_Item_Inventory AS
    SELECT 
        i.item_id AS "物品編號",
        i.name AS "物品名稱",
        i.total_qty AS "物理總數",
        i.damaged_qty AS "累積毀損數量",
        
        IFNULL(SUM(CASE WHEN r.status = '借用中' THEN r.qty ELSE 0 END), 0) AS "借用數量",
        
        IFNULL(SUM(CASE 
            WHEN r.status IN ('待審核', '已預約') THEN r.qty 
            WHEN r.status = '退回修改' AND datetime('now', 'localtime') <= r.expected_borrow_time THEN r.qty
            ELSE 0 
        END), 0) AS "凍結數量",
        
        -- 實際可用 = 物理總數 - 累積毀損 - 借用中 - 凍結中
        (i.total_qty - i.damaged_qty) - IFNULL(SUM(CASE 
            WHEN r.status IN ('待審核', '已預約', '借用中') THEN r.qty 
            WHEN r.status = '退回修改' AND datetime('now', 'localtime') <= r.expected_borrow_time THEN r.qty
            ELSE 0 
        END), 0) AS "實際可用"
    FROM Items i
    LEFT JOIN Records r ON i.item_id = r.item_id
    WHERE i.is_active = 1
    GROUP BY i.item_id;

    -- 5. 建立使用歷程檢視表
    DROP VIEW IF EXISTS View_Usage_Records;
    CREATE VIEW View_Usage_Records AS
    SELECT 
        -- 借用人資訊
        r.emp_id AS "借用人編號", 
        r.snap_user_name AS "借用人姓名", 
        r.snap_user_dept AS "借用人部門",        
        
        -- 物品資訊 (從 Records 表的快照欄位讀取，確保歷史資料不受後續修改影響)
        r.item_id AS "物品編號",
        r.snap_item_name AS "物品名稱",  
        r.qty AS "數量",
        r.transaction_type AS "交易類型",
        r.status AS "狀態",
        r.expected_borrow_time AS "預計租借時間",
        r.expected_return_time AS "預計歸還時間",
        r.actual_return_time AS "實際歸還時間",
        
        -- 審核人資訊 (從 Users 表 JOIN 過來)
        r.manager_id AS "審核人員編號",
        m.name AS "審核人員姓名",
        m.department AS "審核人員部門",
        
        CASE 
            -- 1. 優先判斷「已歸還(部分毀損)」的時間表現
            WHEN r.actual_return_time IS NOT NULL AND r.status = '已歸還(部分毀損)' 
                 AND ABS(strftime('%s', r.actual_return_time) - strftime('%s', r.expected_return_time)) <= 1800 
                 THEN '準時歸還 (部分毀損)'
            WHEN r.actual_return_time IS NOT NULL AND r.status = '已歸還(部分毀損)' 
                 AND r.actual_return_time < r.expected_return_time THEN '提前歸還 (部分毀損)'
            WHEN r.actual_return_time IS NOT NULL AND r.status = '已歸還(部分毀損)' 
                 AND r.actual_return_time > r.expected_return_time THEN '逾期歸還 (部分毀損)'
            
            -- 2. 判斷「已歸還」(正常完好) 的時間表現
            WHEN r.actual_return_time IS NOT NULL 
                 AND ABS(strftime('%s', r.actual_return_time) - strftime('%s', r.expected_return_time)) <= 1800 
                 THEN '準時歸還'
            WHEN r.actual_return_time IS NOT NULL AND r.actual_return_time < r.expected_return_time THEN '提前歸還'
            WHEN r.actual_return_time IS NOT NULL AND r.actual_return_time > r.expected_return_time THEN '逾期歸還'

            -- 3. 借用中的逾期告警與正常狀態
            WHEN r.status = '借用中' AND datetime('now', 'localtime') > r.expected_return_time THEN '逾期未還'
            WHEN r.status = '借用中' THEN '借用中'

            -- 4. 依照要求的客製化文字
            WHEN r.status = '已預約' THEN '已預約，尚未取用'

            -- 5. 讓每個狀態獨立顯示，不留白也不合併成已終止
            WHEN r.status = '待審核' THEN '待審核'
            WHEN r.status = '退回修改' THEN '退回修改'
            WHEN r.status = '已駁回' THEN '已駁回'
            WHEN r.status = '已取消' THEN '已取消'
            WHEN r.status = '已失效' THEN '已失效'
            
            ELSE r.status
        END AS "歸還表現評估"
    FROM Records r
    LEFT JOIN Users m ON r.manager_id = m.emp_id;
    """
    
    try:
        cursor.executescript(sql_script)
        conn.commit()
        print("資料庫初始化完成")
    except Exception as e:
        print(f"初始化出錯: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    initialize_database()