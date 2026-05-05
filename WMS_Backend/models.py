from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

# ==========================================
# 1. 人員模型 (對應 Users 表)
# ==========================================
class User(Base):
    __tablename__ = "Users"

    emp_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department = Column(String)
    position = Column(String)
    role = Column(String)
    is_active = Column(Integer, default=1)

    # 反向關聯
    records = relationship("Record", back_populates="user", foreign_keys="[Record.emp_id]")

# ==========================================
# 2. 物品模型 (對應 Items 表)
# ==========================================
class Item(Base):
    __tablename__ = "Items"

    item_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String)
    # 對齊 init_db.py 的 CHAR(1)
    needs_manager_approval = Column(String(1))  
    total_qty = Column(Integer, default=0)
    damaged_qty = Column(Integer, default=0)
    is_active = Column(Integer, default=1)

    # 反向關聯
    records = relationship("Record", back_populates="item")

# ==========================================
# 3. 紀錄模型 (對應 Records 表)
# ==========================================
class Record(Base):
    __tablename__ = "Records"

    record_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    emp_id = Column(String, ForeignKey("Users.emp_id"))
    item_id = Column(String, ForeignKey("Items.item_id"))
    qty = Column(Integer, nullable=False)
    transaction_type = Column(String)
    status = Column(String)
    
    # 時間欄位以 TEXT 儲存 (格式: 'YYYY-MM-DD HH:MM')
    expected_borrow_time = Column(String)
    expected_return_time = Column(String, nullable=True)
    actual_return_time = Column(String, nullable=True)
    manager_id = Column(String, ForeignKey("Users.emp_id"), nullable=True)
    reject_reason = Column(String, nullable=True)
    overdue_notice_sent = Column(Integer, default=0)
    
    # 關聯設定
    user = relationship("User", foreign_keys=[emp_id], back_populates="records")
    manager = relationship("User", foreign_keys=[manager_id])
    item = relationship("Item", back_populates="records")