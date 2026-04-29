from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import database, models, schemas
from sqlalchemy import text

router = APIRouter(prefix="/api/items", tags=["Items"])

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
            SELECT "累積毀損數量" + "借用數量" + "凍結數量" AS occupied
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
# API 5: 停用/報廢物品 (Soft Delete)
# ==========================================
@router.patch(
    "/{item_id}/deactivate",
    responses={
        404: {"description": "找不到該物品"}
    }
)
def deactivate_item(item_id: str, db: Session = Depends(database.get_db)):
    db_item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="找不到該物品")
    
    db_item.is_active = 0
    db.commit()
    return {"message": f"物品 {item_id} 已標記為停用/報廢，歷史紀錄已保留"}

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