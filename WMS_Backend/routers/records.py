from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import database, models, schemas
from services.notifications import send_rejection_notice, send_approval_notice
from sqlalchemy import text
from datetime import datetime

router = APIRouter(prefix="/api/records", tags=["Records"])

# ==========================================
# 動作 1：使用者送出借用訂單
# ==========================================
@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(database.get_db)):
    # 1. 查詢人員與物品，同時檢查是否為「啟用」狀態
    user = db.query(models.User).filter(models.User.emp_id == record.emp_id, models.User.is_active == 1).first()
    item = db.query(models.Item).filter(models.Item.item_id == record.item_id, models.Item.is_active == 1).first()

    if not user:
        raise HTTPException(status_code=400, detail="人員不存在或已停用")
    if not item:
        raise HTTPException(status_code=400, detail="物品不存在或已停用")
    
    # 如果是資產類物品，必須填寫預計歸還時間
    if item.type == '資產' and record.expected_return_time is None:
        raise HTTPException(
            status_code=400, 
            detail="資產類物品（無論是否需審核）均必須填寫『預計歸還時間』"
        )
    
    # 防超貸：檢查實際可用庫存
    sql = text('SELECT "實際可用" FROM View_Item_Inventory WHERE "物品編號" = :item_id')
    inventory = db.execute(sql, {"item_id": record.item_id}).mappings().first()

    if inventory is None:
        raise HTTPException(status_code=404, detail="找不到該物品的庫存資訊")
        
    if record.qty > inventory["實際可用"]:
        raise HTTPException(
            status_code=400, 
            detail=f'庫存不足！目前實際可用數量僅剩 {inventory["實際可用"]} 個'
        )

    # 2. 【核心邏輯】依據物品屬性，自動決定「交易類型」與「初始狀態」
    if item.type == '耗材':
        tx_type = '耗材'
        initial_status = '已結案' # 耗材拿了就走
    elif item.needs_manager_approval == 'Y':
        tx_type = '資產須審核'
        initial_status = '待審核'
    else:
        tx_type = '資產免審核'
        initial_status = '已預約' # 免審核直接進入預約狀態凍結庫存

    # 3. 建立訂單，並將快照資訊寫入
    new_record = models.Record(
        **record.model_dump(),
        transaction_type=tx_type,
        status=initial_status,
        # 寫入歷史快照
        snap_user_name=user.name,
        snap_user_dept=user.department,
        snap_item_name=item.name,
        snap_item_type=item.type
    )
    
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

# ==========================================
# 動作 2：主管放行 (Approve)
# ==========================================
@router.put("/{record_id}/approve")
def approve_record(record_id: int, payload: schemas.RecordApprove, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")
    
    # 【防呆】禁止自我簽核
    if record.emp_id == payload.manager_id:
        raise HTTPException(status_code=403, detail="禁止自我簽核")

    # 更新狀態
    record.status = '已預約'
    record.manager_id = payload.manager_id
    db.commit()

    # 觸發通知
    send_approval_notice(record.emp_id, record.item_id)
    return {"message": "訂單已核准"}

# ==========================================
# 動作 3：主管退件 (Reject - 雙軌制)
# ==========================================
@router.put("/{record_id}/reject")
def reject_record(record_id: int, action_type: str, payload: schemas.RecordReject, db: Session = Depends(database.get_db)):
    # action_type 讓前端傳入 'soft' (退回修改) 或 'hard' (直接駁回)
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    
    if action_type == 'soft':
        record.status = '退回修改' # 繼續凍結庫存
    elif action_type == 'hard':
        record.status = '已駁回'   # 釋放庫存
        send_rejection_notice(record.emp_id, record.item_id, payload.reject_reason)
    else:
        raise HTTPException(status_code=400, detail="未知的退件類型")

    record.manager_id = payload.manager_id
    record.reject_reason = payload.reject_reason
    db.commit()
    return {"message": f"訂單已{record.status}"}

# ==========================================
# 動作 4：使用者領取，管理員確認發放 (Pickup)
# ==========================================
@router.put("/{record_id}/pickup")
def pickup_record(record_id: int, db: Session = Depends(database.get_db)):
    # 實務上這裡可以透過 Depends 或 payload 加入管理員權限驗證 (admin_id)
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")
        
    if record.status != '已預約':
        raise HTTPException(status_code=400, detail="只有『已預約』狀態的訂單可以進行領取")

    # 更新狀態為借用中
    record.status = '借用中'
    db.commit()
    
    return {"message": "物品已領取", "status": record.status}

# ==========================================
# 動作 5：使用者重新送審 (Resubmit - 針對退回修改)
# ==========================================
@router.put("/{record_id}/resubmit")
def resubmit_record(record_id: int, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")

    if record.status != '退回修改':
        raise HTTPException(status_code=400, detail="只有『退回修改』狀態的訂單可以重新送審")

    # 檢查是否已經超過預計取用時間
    if datetime.now() > record.expected_borrow_time:
        # 逾期了，強制將狀態轉為已失效，終止流程
        record.status = '已失效'
        db.commit()
        raise HTTPException(
            status_code=400, 
            detail="已超過預計取用時間，此訂單已失效，請重新發起借用申請"
        )

    # 重新進入審核流程
    record.status = '待審核'
    record.reject_reason = None # 清除前一次的退件原因
    db.commit()

    return {"message": "訂單已重新送審", "status": record.status}

# routers/records.py (加在最下方)

# ==========================================
# 動作 6：使用者自行取消申請 (Cancel)
# ==========================================
@router.put("/{record_id}/cancel")
def cancel_record(record_id: int, payload: schemas.RecordCancel, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")

    # 只能取消自己的訂單
    if record.emp_id != payload.emp_id:
        raise HTTPException(status_code=403, detail="您只能取消自己的借用申請")

    # 只能在取用前取消
    if record.status not in ['待審核', '已預約', '退回修改']:
        raise HTTPException(status_code=400, detail=f"目前狀態為『{record.status}』，無法取消")

    record.status = '已取消'
    db.commit()
    return {"message": "借用申請已成功取消", "status": record.status}


# ==========================================
# 動作 7：管理員驗收歸還 (Return)
# ==========================================
@router.put("/{record_id}/return")
def return_record(record_id: int, payload: schemas.RecordReturn, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")

    # 只有借用中的物品可以歸還
    if record.status != '借用中':
        raise HTTPException(status_code=400, detail="只有『借用中』的訂單可以進行歸還驗收")

    # 確認執行者是否為管理員
    admin = db.query(models.User).filter(models.User.emp_id == payload.admin_id).first()
    if not admin or admin.role != '管理員':
        raise HTTPException(status_code=403, detail="只有『管理員』權限的人員可以執行歸還驗收")

    # 毀損數量不可以大於借出數量
    if payload.damaged_qty > record.qty:
        raise HTTPException(status_code=400, detail="提報的毀損數量不可大於借出數量")

    # 1. 決定最終狀態
    if payload.damaged_qty > 0:
        record.status = '已歸還(部分毀損)'
        # 2. 連動扣除實體庫存：找出該物品，將累積毀損數量加上去
        item = db.query(models.Item).filter(models.Item.item_id == record.item_id).first()
        if item:
            item.damaged_qty += payload.damaged_qty
    else:
        record.status = '已歸還'

    # 3. 壓上實際歸還時間
    record.actual_return_time = datetime.now()
    db.commit()

    return {
        "message": "歸還驗收完成", 
        "status": record.status, 
        "damaged_qty_reported": payload.damaged_qty
    }