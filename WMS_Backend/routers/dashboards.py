from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import database
import models

router = APIRouter(prefix="/api/dashboards", tags=["Dashboards (報表)"])

# ==========================================
# API 1: 取得動態庫存報表 (Inventory)
# ==========================================
@router.get(
    "/inventory",
    responses={200: {"description": "成功取得庫存狀態報表"}}
)
def get_inventory_status(
    skip: int = 0,
    limit: int = Query(100, description="設為 0 代表不限制筆數"),
    keyword: Optional[str] = Query(None, description="依物品編號或名稱模糊搜尋"),
    in_stock_only: bool = Query(False, description="是否只顯示『實際可用 > 0』的物品"),
    db: Session = Depends(database.get_db)
):
    """
    讀取 View_Item_Inventory 檢視表，支援關鍵字搜尋與可用庫存過濾
    """
    # 建立動態 SQL 基礎字串與參數字典
    base_sql = "SELECT * FROM View_Item_Inventory WHERE 1=1"
    params = {}

    # 動態疊加查詢條件
    if keyword:
        base_sql += ' AND ("物品編號" LIKE :kw OR "物品名稱" LIKE :kw)'
        params["kw"] = f"%{keyword}%"
    
    if in_stock_only:
        base_sql += ' AND "實際可用" > 0'

    # 處理分頁
    if limit > 0:
        base_sql += " LIMIT :limit OFFSET :skip"
        params["limit"] = limit
        params["skip"] = skip

    # 執行最終組合出的 SQL
    sql = text(base_sql)
    result = db.execute(sql, params).mappings().all()
    
    return result
# ==========================================
# API 2: 取得個人借用歷程 (My Records)
# ==========================================
@router.get(
    "/my-records/{emp_id}",
    responses={
        200: {"description": "成功取得個人借用歷程"},
        404: {"description": "找不到該名員工"}
    }
)
def get_my_records(
    emp_id: str,
    skip: int = 0,
    limit: int = Query(100, description="設為 0 代表不限制筆數"),
    performance: Optional[str] = Query(None, description="依歸還表現篩選 (如: 逾期未還, 準時歸還)"),
    status: Optional[str] = Query(None, description="依訂單狀態篩選"),
    db: Session = Depends(database.get_db)
):
    """
    查詢特定員工的所有借用紀錄，包含系統自動生成的表現評估
    """
    # 檢查員工是否存在
    user_exists = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not user_exists:
        raise HTTPException(status_code=404, detail="找不到該名員工")

    base_sql = 'SELECT * FROM View_Usage_Records WHERE "借用人編號" = :emp_id'
    params = {"emp_id": emp_id}

    if performance:
        base_sql += ' AND "歸還表現評估" = :perf'
        params["perf"] = performance
    
    if status:
        base_sql += ' AND "狀態" = :status'
        params["status"] = status

    # 預設按時間由新到舊排序
    base_sql += ' ORDER BY "預計租借時間" DESC'

    if limit > 0:
        base_sql += " LIMIT :limit OFFSET :skip"
        params["limit"] = limit
        params["skip"] = skip

    result = db.execute(text(base_sql), params).mappings().all()
    return result


# ==========================================
# API 3: 取得全域使用歷程總表 (Admin Records)
# ==========================================
@router.get(
    "/usage-records",
    responses={200: {"description": "成功取得全域使用歷程報表"}}
)
def get_all_usage_records(
    skip: int = 0,
    limit: int = Query(100, description="設為 0 代表不限制筆數"),
    dept: Optional[str] = Query(None, description="依部門篩選"),
    item_id: Optional[str] = Query(None, description="依物品編號篩選"),
    performance: Optional[str] = Query(None, description="依歸還表現篩選"),
    db: Session = Depends(database.get_db)
):
    """
    提供給管理員的總表，可從部門、物品或表現等多維度進行交叉分析
    """
    base_sql = "SELECT * FROM View_Usage_Records WHERE 1=1"
    params = {}

    if dept:
        base_sql += ' AND "借用人部門" = :dept'
        params["dept"] = dept
        
    if item_id:
        base_sql += ' AND "物品編號" = :item_id'
        params["item_id"] = item_id

    if performance:
        base_sql += ' AND "歸還表現評估" = :perf'
        params["perf"] = performance

    base_sql += ' ORDER BY "預計租借時間" DESC'

    if limit > 0:
        base_sql += " LIMIT :limit OFFSET :skip"
        params["limit"] = limit
        params["skip"] = skip

    result = db.execute(text(base_sql), params).mappings().all()
    return result