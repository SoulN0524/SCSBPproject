import database
import models
from sqlalchemy.orm import Session

def clear_all_data():
    """清空所有資料表內的資料，但保留資料表架構與 View"""
    # 取得資料庫連線
    db: Session = next(database.get_db())
    
    try:
        # 由於有 Foreign Key 的限制，刪除順序很重要
        # 必須先刪除子表 (Records)，再刪除父表 (Users, Items)
        print("開始清空資料...")
        
        deleted_records = db.query(models.Record).delete()
        print(f"已刪除 Records 表資料：{deleted_records} 筆")
        
        deleted_items = db.query(models.Item).delete()
        print(f"已刪除 Items 表資料：{deleted_items} 筆")
        
        deleted_users = db.query(models.User).delete()
        print(f"已刪除 Users 表資料：{deleted_users} 筆")
        
        db.commit()
        print("資料庫清空完成！")
        
    except Exception as e:
        db.rollback()
        print(f"清空資料時發生錯誤：{e}")
    finally:
        db.close()

if __name__ == "__main__":
    confirm = input("警告：這將會刪除資料庫中所有的資料。確定要執行嗎？ (y/n): ")
    if confirm.lower() == 'y':
        clear_all_data()
    else:
        print("已取消操作。")