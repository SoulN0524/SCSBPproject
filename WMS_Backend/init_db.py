import os
import sqlite3

def initialize_database():
    # 取得目前腳本所在的目錄，並組合出 WMS.db 的絕對路徑
    current_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(current_dir, 'WMS.db')
    
    # 連接到正確資料夾下的 WMS.db
    conn = sqlite3.connect(db_path)
    
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

    -- 3. 建立紀錄表 (更新狀態清單)
    CREATE TABLE IF NOT EXISTS Records (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_id TEXT,
        item_id TEXT,
        qty INTEGER NOT NULL,
        transaction_type TEXT CHECK(transaction_type IN ('資產免審核', '資產須審核', '耗材')),
        -- 依據 DBRule.txt 更新狀態清單
        status TEXT CHECK(status IN ('待簽核', '已簽核', '已預約', '借用中', '已逾期', '已結案', '已駁回', '已取消', '退回修改', '已失效', '已歸還')),
        expected_borrow_time DATETIME,
        expected_return_time DATETIME,
        actual_return_time DATETIME,
        manager_id TEXT,
        reject_reason TEXT,
        overdue_notice_sent INTEGER DEFAULT 0,
        FOREIGN KEY (emp_id) REFERENCES Users(emp_id),
        FOREIGN KEY (item_id) REFERENCES Items(item_id),
        FOREIGN KEY (manager_id) REFERENCES Users(emp_id)
    );

    -- 4. 建立庫存檢視表 (優化分類：預約數 vs 借用數)
    DROP VIEW IF EXISTS View_Item_Inventory;
    CREATE VIEW View_Item_Inventory AS
    SELECT 
        i.item_id AS "物品編號",
        i.name AS "物品名稱",
        i.type AS "物品類型",
        i.total_qty AS "物理總數",
        i.damaged_qty AS "累積毀損數量",
        
        -- 借用中
        IFNULL(SUM(CASE WHEN r.status = '借用中' THEN r.qty ELSE 0 END), 0) AS "借用中",
        
        -- 已逾期
        IFNULL(SUM(CASE WHEN r.status = '已逾期' THEN r.qty ELSE 0 END), 0) AS "逾期數量",
        
        -- 待簽核 + 已簽核 + 已預約 = 被預定但尚未取用的數量
        IFNULL(SUM(CASE WHEN r.status IN ('待簽核', '已簽核', '已預約') THEN r.qty ELSE 0 END), 0) AS "凍結數量",
        
        -- 實際可用 = 物理總數 - 累積毀損 - (借用 + 逾期 + 凍結)
        (i.total_qty - i.damaged_qty) - IFNULL(SUM(CASE 
            WHEN r.status IN ('待簽核', '已簽核', '已預約', '借用中', '已逾期') THEN r.qty 
            ELSE 0 
        END), 0) AS "實際可用"
    FROM Items i
    LEFT JOIN Records r ON i.item_id = r.item_id
    WHERE i.is_active = 1
    GROUP BY i.item_id;

    -- 5. 建立使用歷程檢視表 (包含借用人資訊與物品名稱)
    DROP VIEW IF EXISTS View_Usage_Records;
    CREATE VIEW View_Usage_Records AS
    SELECT 
        r.record_id AS "訂單編號",
        r.emp_id AS "借用人編號",         
        u.name AS "借用人姓名",
        u.position AS "借用人職位",
        u.role AS "借用人角色",
        r.item_id AS "物品編號",
        i.name AS "物品名稱",
        r.qty AS "數量",
        r.transaction_type AS "交易類型",
        r.status AS "原始狀態",
        r.expected_borrow_time AS "預計租借時間",
        r.expected_return_time AS "預計歸還時間",
        r.actual_return_time AS "實際歸還時間",
        
        r.manager_id AS "審核人員編號",
        m.name AS "審核人員姓名",
        
        CASE 
            -- 1. 已歸還 (閒置中) 的表現
            WHEN r.status = '閒置中' AND r.actual_return_time <= r.expected_return_time THEN '準時歸還'
            WHEN r.status = '閒置中' AND r.actual_return_time > r.expected_return_time THEN '逾期歸還'
            
            -- 2. 借用中的即時逾期判斷 (動態顯示)
            WHEN r.status = '借用中' AND datetime('now', 'localtime') > r.expected_return_time THEN '已逾期 (尚未歸還)'
            WHEN r.status = '已逾期' THEN '已逾期 (系統標記)'
            
            -- 3. 其他流程狀態
            WHEN r.status = '待簽核' THEN '等待管理者核准'
            WHEN r.status = '已簽核' THEN '已核准，待取用'
            WHEN r.status = '已預約' THEN '預約成功，待取用'
            WHEN r.status = '借用中' THEN '使用中'
            
            ELSE r.status
        END AS "當前狀態評估"
    FROM Records r
    LEFT JOIN Users u ON r.emp_id = u.emp_id
    LEFT JOIN Users m ON r.manager_id = m.emp_id
    LEFT JOIN Items i ON r.item_id = i.item_id;
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