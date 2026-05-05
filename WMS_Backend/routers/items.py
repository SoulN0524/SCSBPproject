from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import database, models, schemas
from sqlalchemy import text

router = APIRouter(prefix="/api/items", tags=["Items"])

# ==========================================
# API 0: 取得下一筆可用的物品編號 (Next ID)
# ==========================================
@router.get("/next-id")
def get_next_id(db: Session = Depends(database.get_db)):
    """
    找出目前最大的物品編號(如果是純數字)，並回傳 +1 的結果。
    如果資料庫為空，預設回傳 "1"。
    """
    items = db.query(models.Item.item_id).all()
    if not items:
        return {"next_id": "1"}
    
    try:
        # 嘗試將所有 ID 轉為整數，找最大值
        ids = [int(i.item_id) for i in items if i.item_id.isdigit()]
        if not ids:
            # 如果都不是純數字，則回傳目前筆數+1或維持字串處理(此處採簡單方案)
            return {"next_id": str(len(items) + 1)}
        return {"next_id": str(max(ids) + 1)}
    except:
        return {"next_id": str(len(items) + 1)}

# ==========================================
# API 1: 新增物品 (Create)
# ==========================================
@router.post(
    "/", 
    response_model=schemas.ItemResponse,
    responses={
        400: {"description": "此物品編號已存在"},
        422: {"description": "前端傳遞的資料格式錯誤 (如數量為負數)"}
    }
)
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db)):
    db_item = db.query(models.Item).filter(models.Item.item_id == item.item_id).first()
    if db_item:
        raise HTTPException(status_code=400, detail="此物品編號已存在")
    
    new_item = models.Item(**item.model_dump())
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

# ==========================================
# API 2: 查詢單一物品 (Read One)
# ==========================================
@router.get(
    "/{item_id}", 
    response_model=schemas.ItemResponse,
    responses={
        404: {"description": "找不到該物品"}
    }
)
def get_item(item_id: str, db: Session = Depends(database.get_db)):
    item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="找不到該物品")
    return item

# ==========================================
# API 3: 取得所有物品清單 (Read All)
# ==========================================
@router.get(
    "/", 
    response_model=List[schemas.ItemResponse],
    responses={
        200: {"description": "成功取得物品清單"}
    }
)
def get_items(
    skip: int = 0, 
    limit: int = 100, 
    item_type: Optional[str] = Query(None, description="依物品類型篩選 (耗材/資產)"),
    is_active: Optional[int] = Query(None, description="1為啟用，0為停用/報廢"),
    db: Session = Depends(database.get_db)
):
    query = db.query(models.Item)
    
    if item_type:
        query = query.filter(models.Item.type == item_type)
    if is_active is not None:
        query = query.filter(models.Item.is_active == is_active)
        
    items = query.offset(skip).limit(limit).all()
    return items

# ==========================================
# API 4: 更新物品資料 (Update)
# ==========================================
@router.patch(
    "/{item_id}", 
    response_model=schemas.ItemResponse,
    responses={
        404: {"description": "找不到該物品"},
        422: {"description": "傳入的欄位格式或選項不符規定"}
    }
)
def update_item(
    item_id: str, 
    item_update: schemas.ItemUpdate, 
    db: Session = Depends(database.get_db)
):
    db_item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="找不到該物品")

    update_data = item_update.model_dump(exclude_unset=True)

    if 'total_qty' in update_data:
        sql = text('''
            SELECT "累積毀損數量" + "借用中" + "逾期數量" + "凍結數量" AS occupied
            FROM View_Item_Inventory WHERE "物品編號" = :item_id
        ''')
        row = db.execute(sql, {"item_id": item_id}).mappings().first()
        occupied = row["occupied"] if row else 0
        
        if update_data['total_qty'] < occupied:
            raise HTTPException(
                status_code=400, 
                detail=f"總量不可低於已佔用數量({occupied} = 毀損+借用中+凍結)"
            )
    
    for key, value in update_data.items():
        setattr(db_item, key, value)

    db.commit()
    db.refresh(db_item)
    return db_item

# ==========================================
# API 5: 停用/報廢物品 (Soft Delete / Scrap)
# ==========================================
@router.patch(
    "/{item_id}/deactivate",
    responses={
        404: {"description": "找不到該物品"}
    }
)
def deactivate_item(
    item_id: str, 
    scrap_qty: Optional[int] = Query(None, description="報廢數量，若不帶則視為全數報廢"),
    db: Session = Depends(database.get_db)
):
    db_item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="找不到該物品")
    
    # 原始數量定義為目前的 (物理總數 + 累積毀損)
    original_total = db_item.total_qty + db_item.damaged_qty
    
    if scrap_qty is None or scrap_qty >= db_item.total_qty:
        # 全數報廢邏輯：
        # is_active 變為 0 
        # damaged_qty 等於該物品原始數量
        # (不變更 total_qty，保留原始紀錄)
        db_item.is_active = 0
        db_item.damaged_qty = original_total
    else:
        # 部分報廢邏輯：
        # 直接記錄 damaged_qty (增加)
        db_item.damaged_qty += scrap_qty
        # 不更動 total_qty，因為 View 會自動扣除 damaged_qty
    
    db.commit()
    return {"message": f"物品 {item_id} 報廢處理完成", "item_id": item_id, "is_active": db_item.is_active}

# ==========================================
# API 6: 徹底刪除物品 (Hard Delete)
# ==========================================
@router.delete(
    "/{item_id}",
    responses={
        404: {"description": "找不到該物品"},
        409: {"description": "若該物品已有借用紀錄，可能因 Foreign Key 限制無法刪除"}
    }
)
def hard_delete_item(item_id: str, db: Session = Depends(database.get_db)):
    db_item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="找不到該物品")
    
    db.delete(db_item)
    db.commit()
    return {"message": f"物品 {item_id} 資料已徹底抹除"}