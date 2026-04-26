from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import database, models, schemas

router = APIRouter(prefix="/api/items", tags=["Items"])

@router.post("/", response_model=schemas.ItemResponse)
def create_item(item: schemas.ItemCreate, db: Session = Depends(database.get_db)):
    db_item = db.query(models.Item).filter(models.Item.item_id == item.item_id).first()
    if db_item:
        raise HTTPException(status_code=400, detail="此物品編號已存在")
    
    new_item = models.Item(**item.model_dump())
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@router.get("/", response_model=List[schemas.ItemResponse])
def get_items(db: Session = Depends(database.get_db)):
    return db.query(models.Item).all()

@router.delete("/{item_id}")
def delete_item(item_id: str, db: Session = Depends(database.get_db)):
    db_item = db.query(models.Item).filter(models.Item.item_id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="找不到該物品")
    
    # 執行軟刪除
    db_item.is_active = 0
    db.commit()
    return {"message": f"物品 {item_id} 已標記為停用/報廢，歷史紀錄已保留"}