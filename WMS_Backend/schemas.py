from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# ==========================================
# 1. User (人員) 的安檢門
# ==========================================
# 基礎模型 (共用的欄位)
class UserBase(BaseModel):
    name: str = Field(..., max_length=50)
    department: str = Field(..., max_length=50)
    position: Literal["員工", "主管"]
    role: Literal["使用者", "管理員"]

# 建立資料時使用的模型 (前端送到後端)
class UserCreate(UserBase):
    emp_id: str = Field(..., max_length=20)

# 供 PATCH API 專用，所有欄位皆為 Optional
class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=50)
    position: Optional[Literal["員工", "主管"]] = None
    role: Optional[Literal["使用者", "管理員"]] = None

# 回傳資料時使用的模型 (後端吐給前端)
class UserResponse(UserCreate):
    is_active: int
    model_config = {"from_attributes": True}


# ==========================================
# 2. Item (物品) 的安檢門
# ==========================================
class ItemBase(BaseModel):
    name: str = Field(..., max_length=100)
    type: Literal["耗材", "資產"]
    needs_manager_approval: Literal["Y", "N"]
    total_qty: int = Field(..., ge=0, description="總數量不可為負數")

class ItemCreate(ItemBase):
    item_id: str = Field(..., max_length=50)

class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    type: Optional[Literal["耗材", "資產"]] = None
    needs_manager_approval: Optional[Literal["Y", "N"]] = None
    total_qty: Optional[int] = Field(None, ge=0)

class ItemResponse(ItemCreate):
    is_active: int
    damaged_qty: int

    model_config = {"from_attributes": True}


# ==========================================
# 3. Record (紀錄/訂單) 的安檢門
# ==========================================
# 使用者送出訂單時，只需要提供這 4 個欄位，其他(如狀態、交易類型)由後端程式判斷
class RecordCreate(BaseModel):
    emp_id: str
    item_id: str
    qty: int = Field(..., gt=0, description="借用數量必須大於 0")
    expected_borrow_time: str
    expected_return_time: Optional[str] = None  # 耗材可能沒有預計歸還時間

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

    expected_borrow_time: Optional[str] = None
    expected_return_time: Optional[str] = None
    actual_return_time: Optional[str] = None
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

# ==========================================
# 6. 管理員發放點交
# ==========================================
class RecordPickup(BaseModel):
    admin_id: str