from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import database

router = APIRouter(prefix="/api/dashboards", tags=["Dashboards (報表)"])

@router.get("/inventory")
def get_inventory_status(db: Session = Depends(database.get_db)):
    # 直接執行我們寫好的 SQLite View
    # .mappings().all() 會把資料庫的結果自動轉換成漂亮的 JSON 字典格式
    sql = text("SELECT * FROM View_Item_Inventory")
    result = db.execute(sql).mappings().all()
    return result

@router.get("/my-records/{emp_id}")
def get_my_records(emp_id: str, db: Session = Depends(database.get_db)):
    # 查詢該員工的所有借用歷程與動態表現評估
    sql = text("SELECT * FROM View_Usage_Records WHERE emp_id = :emp_id")
    result = db.execute(sql, {"emp_id": emp_id}).mappings().all()
    return result