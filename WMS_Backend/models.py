from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base  # 引入我們在 database.py 建立的 Base 模板

# ==========================================
# 1. 人員模型 (對應 Users 表)
# ==========================================
class User(Base):
    __tablename__ = "Users"  # 必須與 DBeaver 裡的表名一模一樣

    emp_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department = Column(String)
    position = Column(String)  # '員工' 或 '主管'
    role = Column(String)      # '使用者' 或 '管理員'
    is_active = Column(Integer, default=1) # 1: 啟用, 0: 停用

    # 建立反向關聯：方便未來從「人」反查他借過的所有「訂單」
    records = relationship("Record", back_populates="user", foreign_keys="[Record.emp_id]")

# ==========================================
# 2. 物品模型 (對應 Items 表)
# ==========================================
class Item(Base):
    __tablename__ = "Items"

    item_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String)  # '耗材' 或 '資產'
    needs_manager_approval = Column(String)  # 'Y' 或 'N'
    total_qty = Column(Integer, default=0)
    damaged_qty = Column(Integer, default=0)
    is_active = Column(Integer, default=1) # 1: 啟用, 0: 停用

    # 建立反向關聯：方便未來從「物品」反查所有被借用的「紀錄」
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
    transaction_type = Column(String)  # '資產免審核', '資產須審核', '耗材'
    status = Column(String)            # 狀態機
    expected_borrow_time = Column(DateTime)
    expected_return_time = Column(DateTime)
    actual_return_time = Column(DateTime)
    manager_id = Column(String, ForeignKey("Users.emp_id"))
    reject_reason = Column(String)
    
    # 歷史快照欄位 (Snapshot)
    snap_user_name = Column(String)
    snap_user_dept = Column(String)
    snap_item_name = Column(String)
    snap_item_type = Column(String)

    # 建立關聯：讓程式知道如何透過 Foreign Key 找到對應的物件
    user = relationship("User", foreign_keys=[emp_id], back_populates="records")
    manager = relationship("User", foreign_keys=[manager_id])
    item = relationship("Item", back_populates="records")