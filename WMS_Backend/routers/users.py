from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

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
@router.post(
    "/",
    response_model=schemas.UserResponse,
    responses={
        400: {"description": "此員工編號已存在"},
        422: {"description": "前端傳遞的資料格式錯誤"}
    }
)
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
@router.get(
    "/", 
    response_model=List[schemas.UserResponse],
    responses={
        200: {"description": "成功取得使用者清單"}
    }
)
def get_users(
    skip: int = 0, 
    limit: int = Query(100, description="限制回傳筆數，設為 0 代表不限制取得全部"), 
    department: Optional[str] = Query(None, description="依部門精確篩選"),
    is_active: Optional[int] = Query(None, description="1為在職，0為停用"),
    role: Optional[str] = Query(None, description="依權限角色篩選 (使用者/管理員)"),
    db: Session = Depends(database.get_db)
):
    # 先建立基礎查詢物件 (還不要觸發 .all())
    query = db.query(models.User)
    
    # 若前端有傳入特定參數，則動態疊加過濾條件
    if department:
        query = query.filter(models.User.department == department)
    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)
    if role:
        query = query.filter(models.User.role == role)
        
    # 最後加上分頁限制並撈取資料庫
    users = query.offset(skip).limit(limit).all()
    return users


# ==========================================
# API 3: 透過員編查詢單一使用者 (Read One)
# ==========================================
@router.get(
    "/{emp_id}",
    response_model=schemas.UserResponse,
    responses={
        404: {"description": "找不到該名員工"}
    }
)
def get_user(emp_id: str, db: Session = Depends(database.get_db)):
    
    # 尋找特定員編
    user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    
    # 防呆檢查：如果找不到這個人
    if user is None:
        raise HTTPException(status_code=404, detail="找不到該名員工")
        
    return user

# ==========================================
# API 3-2: 更新單一使用者資料 (Update)
# ==========================================
@router.patch(
    "/{emp_id}", 
    response_model=schemas.UserResponse,
    responses={
        404: {"description": "找不到該名員工"},
        422: {"description": "傳入的欄位格式或選項不符規定"}
    }
)
def update_user(
    emp_id: str, 
    user_update: schemas.UserUpdate, 
    db: Session = Depends(database.get_db)
):
    db_user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到該名員工")

    # exclude_unset=True 確保只更新前端確實有傳遞的欄位
    update_data = user_update.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.commit()
    db.refresh(db_user)
    return db_user

# ==========================================
# API 4: 停用使用者 (Soft Delete)
# ==========================================
@router.patch(
    "/{emp_id}/deactivate",
    responses={
        404: {"description": "找不到該名員工"}
    }
)
def deactivate_user(emp_id: str, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到該名員工")
    
    db_user.is_active = 0
    db.commit()
    return {"message": f"員工 {emp_id} 已成功停用，歷史紀錄已保留"}

# ==========================================
# API 5: 徹底刪除使用者 (Hard Delete - 僅供管理或重置使用)
# ==========================================
@router.delete(
    "/{emp_id}",
    responses={
        404: {"description": "找不到該名員工"},
        409: {"description": "若該名員工已有借用紀錄，可能因 Foreign Key 限制無法刪除"}
    }
)
def hard_delete_user(emp_id: str, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.emp_id == emp_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="找不到該名員工")
    
    db.delete(db_user)
    db.commit()
    return {"message": f"員工 {emp_id} 資料已徹底抹除"}