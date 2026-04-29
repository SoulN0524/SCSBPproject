import database
import models
from sqlalchemy import text

def clear_all_data():
    """清空所有資料表內的資料，保留資料表架構與 View，並重置自增主鍵"""
    # 直接使用 SessionLocal，這在獨立執行的腳本中比 next(get_db()) 更安全
    db = database.SessionLocal()
    
    try:
        print("開始清空資料...")
        
        # 1. 刪除資料 (先刪子表再刪父表)
        deleted_records = db.query(models.Record).delete()
        print(f"已刪除 Records 表資料：{deleted_records} 筆")
        
        deleted_items = db.query(models.Item).delete()
        print(f"已刪除 Items 表資料：{deleted_items} 筆")
        
        deleted_users = db.query(models.User).delete()
        print(f"已刪除 Users 表資料：{deleted_users} 筆")
        
        # 2. 針對 SQLite，重置 AUTOINCREMENT 的計數器
        # 這樣下一次建立 Record 時，record_id 才會重新從 1 開始，方便 Demo 與測試
        db.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('Records', 'Items', 'Users')"))
        print("已重置資料庫的自動遞增 (AUTOINCREMENT) 計數器")
        
        db.commit()
        print("資料庫清空與重置完成！")
        
    except Exception as e:
        db.rollback()
        print(f"清空資料時發生錯誤：{e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("【開發與 Demo 專用工具】")
    confirm = input("警告：這將會刪除 WMS 資料庫中所有的資料，並將 ID 歸零。確定要執行嗎？ (y/n): ")
    if confirm.lower() == 'y':
        clear_all_data()
    else:
        print("已取消操作。")