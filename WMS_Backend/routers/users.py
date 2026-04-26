from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

# 引入我們剛剛寫好的三個基礎建設
import database
import models
import schemas

# 1. 建立路由分機
# prefix 定義了這個檔案裡所有 API 的共同網址前綴
# tags 則是未來在自動產生的 API 文件 (Swagger UI) 上的分類標籤
router = APIRouter(
    prefix="/api/users",
    tags=["Users"]
)

# ==========================================
# API 1: 新增使用者 (Create)
# ==========================================
# response_model 確保後端吐出去的資料符合安檢門的規定 (隱藏敏感資訊，轉換格式)
@router.post("/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    
    # 步驟 1：防呆檢查，確認這個員工編號是否已經存在
    # 用 Python 物件導向的方式下達 SQL 查詢
    db_user = db.query(models.User).filter(models.User.emp_id == user.emp_id).first()
    if db_user:
        # 如果找到了，就丟出 HTTP 400 錯誤，拒絕寫入
        raise HTTPException(status_code=400, detail="此員工編號已存在")

    # 步驟 2：將前端傳來的 Pydantic Schema 轉換為 SQLAlchemy 的資料庫模型
    # **user.model_dump() 是一種快速解包的寫法，等於把 name, department... 一次塞進去
    new_user = models.User(**user.model_dump())

    # 步驟 3：寫入資料庫的標準三部曲
    db.add(new_user)      # 推入暫存區
    db.commit()           # 確定寫入硬碟
    db.refresh(new_user)  # 重新從資料庫讀取最新狀態 (確保拿到完整的物件)

    # 步驟 4：回傳結果給前端 (FastAPI 會自動透過 response_model 把它轉換成 JSON)
    return new_user


# ==========================================
# API 2: 取得所有使用者清單 (Read All)
# ==========================================
@router.get("/", response_model=List[schemas.UserResponse])
def get_users(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    
    # 利用 offset(skip) 跟 limit() 實作簡單的分頁功能，避免一次撈出幾萬筆資料把伺服器塞爆
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


# ==========================================
# API 3: 透過員編查詢單一使用者 (Read One)
# ==========================================
@router.get("/{emp_id}", response_model=schemas.UserResponse)
def get_user(emp_id: str, db: Session = Depends(database.get_db)):
    
    # 尋找特定員編
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    
    # 防呆檢查：如果找不到這個人
    if user is None:
        raise HTTPException(status_code=404, detail="找不到該名員工")
        
    return user

# ==========================================
# API 4: 刪除使用者 (Delete) - 實際上是軟刪除，保留歷史紀錄
# ==========================================
@router.delete("/{emp_id}")
def delete_user(emp_id: str, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到該名員工")
    
    # 執行軟刪除
    db_user.is_active = 0
    db.commit()
    return {"message": f"員工 {emp_id} 已成功停用，歷史紀錄已保留"}