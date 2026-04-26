from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# ==========================================
# 1. User (人員) 的安檢門
# ==========================================
# 基礎模型 (共用的欄位)
class UserBase(BaseModel):
    name: str
    department: str
    position: str = Field(..., description="必須是 '員工' 或 '主管'")
    role: str = Field(..., description="必須是 '使用者' 或 '管理員'")

# 建立資料時使用的模型 (前端送到後端)
class UserCreate(UserBase):
    emp_id: str

# 回傳資料時使用的模型 (後端吐給前端)
class UserResponse(UserCreate):
    # 這是 Pydantic V2 的專屬設定，允許它讀取 SQLAlchemy 的資料庫物件
    model_config = {"from_attributes": True}


# ==========================================
# 2. Item (物品) 的安檢門
# ==========================================
class ItemBase(BaseModel):
    name: str
    type: str = Field(..., description="必須是 '耗材' 或 '資產'")
    needs_manager_approval: str = Field(..., description="'Y' 或 'N'")
    total_qty: int

class ItemCreate(ItemBase):
    item_id: str

class ItemResponse(ItemCreate):
    model_config = {"from_attributes": True}


# ==========================================
# 3. Record (紀錄/訂單) 的安檢門
# ==========================================
# 使用者送出訂單時，只需要提供這 4 個欄位，其他(如狀態、交易類型)由後端程式判斷
class RecordCreate(BaseModel):
    emp_id: str
    item_id: str
    qty: int = Field(..., gt=0, description="借用數量必須大於 0")
    expected_borrow_time: datetime
    expected_return_time: Optional[datetime] = None  # 耗材可能沒有預計歸還時間

# 主管點擊「退回修改」或「已駁回」時，前端傳來的格式
class RecordReject(BaseModel):
    manager_id: str
    reject_reason: str

# 主管點擊「放行」時，前端傳來的格式
class RecordApprove(BaseModel):
    manager_id: str

# 後端吐給前端的完整訂單資料格式
class RecordResponse(BaseModel):
    record_id: int
    emp_id: str
    item_id: str
    qty: int
    transaction_type: str
    status: str
    expected_borrow_time: datetime
    expected_return_time: Optional[datetime]
    actual_return_time: Optional[datetime]
    manager_id: Optional[str]
    reject_reason: Optional[str]

    model_config = {"from_attributes": True}

# ==========================================
# 4. 使用者自行取消
# ==========================================
class RecordCancel(BaseModel):
    emp_id: str

# ==========================================
# 5. 管理員驗收歸還
# ==========================================
class RecordReturn(BaseModel):
    admin_id: str
    damaged_qty: int = Field(0, ge=0, description="毀損數量預設為 0，且不可小於 0")