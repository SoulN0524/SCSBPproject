from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text, desc, asc
from typing import List, Optional, Literal
from datetime import datetime
import database, models, schemas
from services.notifications import send_rejection_notice, send_approval_notice, send_soft_reject_notice

router = APIRouter(prefix="/api/records", tags=["Records"])

def _verify_manager(db: Session, manager_id: str):
    """確認簽核者真的是『主管』且仍在職"""
    manager = db.query(models.User).filter(
        models.User.emp_id == manager_id,
        models.User.is_active == 1
    ).first()
    if not manager:
        raise HTTPException(status_code=404, detail="審核人不存在或已停用")
    if manager.position != '主管':
        raise HTTPException(status_code=403, detail="僅『主管』可執行此動作")
    return manager

def _verify_admin(db: Session, admin_id: str):
    """確認操作者真的是『管理員』且仍在職"""
    admin = db.query(models.User).filter(
        models.User.emp_id == admin_id,
        models.User.is_active == 1
    ).first()
    if not admin:
        raise HTTPException(status_code=404, detail="操作者不存在或已停用")
    if admin.role != '管理員':
        raise HTTPException(status_code=403, detail="僅『管理員』可執行此動作")
    return admin

# ==========================================
# API 1: 使用者發起借用申請 (Create)
# ==========================================
@router.post("/", response_model=schemas.RecordResponse)
def create_record(record: schemas.RecordCreate, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.emp_id == record.emp_id, models.User.is_active == 1).first()
    item = db.query(models.Item).filter(models.Item.item_id == record.item_id, models.Item.is_active == 1).first()

    if not user: raise HTTPException(status_code=400, detail="人員不存在或已停用")
    if not item: raise HTTPException(status_code=400, detail="物品不存在或已停用")
    
    if item.type == '資產' and record.expected_return_time is None:
        raise HTTPException(status_code=400, detail="資產類物品必須填寫『預計歸還時間』")
    
    # 檢查動態庫存 (防超貸)
    sql = text('SELECT "實際可用" FROM View_Item_Inventory WHERE "物品編號" = :item_id')
    inventory = db.execute(sql, {"item_id": record.item_id}).mappings().first()

    if inventory is None:
        raise HTTPException(status_code=404, detail="找不到該物品的庫存資訊")
    if record.qty > inventory["實際可用"]:
        raise HTTPException(status_code=400, detail=f'庫存不足！實際可用數量僅剩 {inventory["實際可用"]} 個')

    
    record_data = record.model_dump()
    # 判定交易類型與初始狀態 (DBRule.txt 規則 1)
    if item.type == '耗材':
        # 耗材：狀態為「已預約」，不需要歸還時間
        # total_qty 在取用時才扣除 (DBRule.txt 規則 5)
        tx_type, initial_status = '耗材', '已預約'
        record_data['expected_return_time'] = None
    elif item.needs_manager_approval == 'Y':
        tx_type, initial_status = '資產須審核', '待簽核'
    else:
        tx_type, initial_status = '資產免審核', '已預約'

    new_record = models.Record(
        **record_data,
        transaction_type=tx_type,
        status=initial_status
    )
    
    db.add(new_record)
    db.flush()

    # 二次驗證(這次的 View 已包含當前這筆,若有併發超貸會被抓出來)
    recheck = db.execute(sql, {"item_id": record.item_id}).mappings().first()
    if recheck["實際可用"] < 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="庫存併發衝突,請稍後重試")


    db.commit()
    db.refresh(new_record)
    return new_record

# ==========================================
# API 2: 取得所有借用紀錄 (Read All)
# ==========================================
@router.get(
    "/", 
    response_model=List[schemas.RecordResponse],
    responses={200: {"description": "成功取得訂單紀錄清單"}}
)
def get_records(
    skip: int = 0, 
    limit: int = 100,
    emp_id: Optional[str] = Query(None, description="依員工編號篩選"),
    item_id: Optional[str] = Query(None, description="依物品編號篩選"),
    status: Optional[str] = Query(None, description="依狀態篩選"),
    tx_type: Optional[str] = Query(None, alias="transaction_type", description="依交易類型篩選"),
    start_date: Optional[datetime] = Query(None, description="查詢區間：開始時間"),
    end_date: Optional[datetime] = Query(None, description="查詢區間：結束時間"),
    sort_by: str = Query("record_id", description="排序欄位"),
    order: Literal["asc", "desc"] = Query("desc", description="排序方向：asc (AZ) 或 desc (ZA)"),
    db: Session = Depends(database.get_db)
):
    query = db.query(models.Record)
    
    # 動態過濾
    if emp_id: query = query.filter(models.Record.emp_id == emp_id)
    if item_id: query = query.filter(models.Record.item_id == item_id)
    if status: query = query.filter(models.Record.status == status)
    if tx_type: query = query.filter(models.Record.transaction_type == tx_type)
    if start_date: query = query.filter(models.Record.expected_borrow_time >= start_date)
    if end_date: query = query.filter(models.Record.expected_borrow_time <= end_date)

    # 動態排序
    sort_attr = getattr(models.Record, sort_by, models.Record.record_id)
    query = query.order_by(desc(sort_attr)) if order == "desc" else query.order_by(asc(sort_attr))

    return query.offset(skip).limit(limit).all()

# ==========================================
# API 3: 查詢單一訂單明細 (Read One)
# ==========================================
@router.get(
    "/{record_id}", 
    response_model=schemas.RecordResponse, 
    responses={404: {"description": "找不到該筆訂單"}}
)
def get_record(record_id: int, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="找不到該筆訂單")
    return record

# ==========================================
# API 4: 主管放行申請 (Approve)
# ==========================================
@router.put(
    "/{record_id}/approve",
    responses={
        400: {"description": "只有『待簽核』的訂單可以核准"},
        403: {"description": "禁止自我簽核"},
        404: {"description": "找不到該筆訂單"}
    }
)
def approve_record(record_id: int, payload: schemas.RecordApprove, db: Session = Depends(database.get_db)):
    import traceback
    try:
        record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
        if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")
        
        _verify_manager(db, payload.manager_id)

        if record.status != '待簽核':
            raise HTTPException(status_code=400, detail=f"目前狀態為『{record.status}』，無法核准")
        if record.emp_id == payload.manager_id:
            raise HTTPException(status_code=403, detail="禁止自我簽核")

        record.status = '已簽核'
        record.manager_id = payload.manager_id
        db.commit()

        send_approval_notice(record.emp_id, record.item_id)
        return {"message": "訂單已簽核"}
    except HTTPException:
        raise
    except Exception as e:
        print("!!! APPROVE ERROR !!!")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# API 5: 實體發放點交 (Pickup)
# ==========================================
@router.put(
    "/{record_id}/pickup",
    responses={
        400: {"description": "狀態不符或已過取用時間"},
        403: {"description": "權限不足（非管理員）或自我發放"},
        404: {"description": "找不到該筆訂單"}
    }
)
def pickup_record(
    record_id: int,
    payload: schemas.RecordPickup,
    db: Session = Depends(database.get_db)
):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")

    # 1. 權限檢查（用 helper 一行搞定，跟 approve/reject/return 統一）
    _verify_admin(db, payload.admin_id)

    # 2. 狀態檢查 (已預約 或 已簽核 都可以領取)
    if record.status not in ['已預約', '已簽核']:
        raise HTTPException(status_code=400, detail=f"目前狀態為『{record.status}』，無法領取")

    # 3. 禁止自我發放（管理員不能自己領自己預約的東西，避免繞過控管）
    if record.emp_id == payload.admin_id:
        raise HTTPException(status_code=403, detail="禁止自我發放")

    # 4. 過期失效（字串比較，格式: 'YYYY-MM-DD HH:MM')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if now_str > record.expected_borrow_time:
        record.status = '已失效'
        db.commit()
        raise HTTPException(status_code=400, detail="已超過預期取用時間，訂單自動失效")

    # 5. 根據物品類型決定後續狀態 (DBRule.txt 規則 2 & 5)
    item = db.query(models.Item).filter(models.Item.item_id == record.item_id).first()
    if item and item.type == '耗材':
        # 耗材：取用後直接「已結案」，同時扣除 total_qty
        record.status = '已結案'
        item.total_qty = max(0, item.total_qty - record.qty)
    else:
        # 資產：進入「借用中」狀態
        record.status = '借用中'

    db.commit()
    return {"message": "物品已領取", "status": record.status}

# ==========================================
# API 6: 管理員驗收歸還 (Return)
# ==========================================
@router.put(
    "/{record_id}/return",
    responses={
        400: {"description": "狀態不符或毀損數量異常"},
        403: {"description": "權限不足（非管理員）"},
        404: {"description": "找不到該筆訂單"}
    }
)
def return_record(record_id: int, payload: schemas.RecordReturn, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")

    _verify_admin(db, payload.admin_id)          

    if record.status != '借用中':
        raise HTTPException(status_code=400, detail="只有『借用中』的訂單可歸還")
    if record.emp_id == payload.admin_id:        
        raise HTTPException(status_code=403, detail="禁止自我簽核")
    if payload.damaged_qty > record.qty:
        raise HTTPException(status_code=400, detail="毀損數量不可大於借出數量")

    # 處理毀損與庫存連動
    if payload.damaged_qty > 0:
        record.status = '已結案'
        item = db.query(models.Item).filter(models.Item.item_id == record.item_id).first()
        if item: item.damaged_qty += payload.damaged_qty
    else:
        record.status = '已結案'

    record.actual_return_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    db.commit()
    return {"message": "歸還驗收完成", "status": record.status, "reported_damaged": payload.damaged_qty}


# ==========================================
# API 7: 主管退件處理 (Reject)
# ==========================================
@router.put(
    "/{record_id}/reject",
    responses={
        400: {"description": "狀態不符或未知的退件類型"},
        404: {"description": "找不到該筆訂單"}
    }
)
def reject_record(
    record_id: int, 
    action_type: Literal["soft", "hard"], 
    payload: schemas.RecordReject, 
    db: Session = Depends(database.get_db)
):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")
    
    _verify_manager(db, payload.manager_id)

    if record.status != '待簽核':
        raise HTTPException(status_code=400, detail=f"目前狀態為『{record.status}』，無法退件")
    if record.emp_id == payload.manager_id:
        raise HTTPException(status_code=403, detail="禁止自我簽核")
    if action_type == 'soft':
        record.status = '退回修改'
        send_soft_reject_notice(record.emp_id, record.item_id, payload.reject_reason)
    elif action_type == 'hard':
        record.status = '已駁回'
        send_rejection_notice(record.emp_id, record.item_id, payload.reject_reason)
    else:
        raise HTTPException(status_code=400, detail="未知的退件類型")

    record.manager_id = payload.manager_id
    record.reject_reason = payload.reject_reason
    db.commit()
    return {"message": f"訂單已{record.status}"}


# ==========================================
# API 8: 重新送審 (Resubmit)
# ==========================================
@router.put(
    "/{record_id}/resubmit",
    responses={
        400: {"description": "狀態不符或已過期"},
        404: {"description": "找不到該筆訂單"}
    }
)
def resubmit_record(record_id: int, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")

    if record.status != '退回修改':
        raise HTTPException(status_code=400, detail="只有『退回修改』的訂單可重新送審")

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if now_str > record.expected_borrow_time:
        record.status = '已失效'
        db.commit()
        raise HTTPException(status_code=400, detail="已超過預期取用時間，訂單自動失效")

    record.status = '待簽核'
    record.reject_reason = None
    db.commit()
    return {"message": "訂單已重新送審", "status": record.status}


# ==========================================
# API 9: 使用者自行取消申請 (Cancel)
# ==========================================
@router.put(
    "/{record_id}/cancel",
    responses={
        400: {"description": "訂單已進入發放流程，無法取消"},
        403: {"description": "非本人操作"},
        404: {"description": "找不到該筆訂單"}
    }
)
def cancel_record(record_id: int, payload: schemas.RecordCancel, db: Session = Depends(database.get_db)):
    record = db.query(models.Record).filter(models.Record.record_id == record_id).first()
    if not record: raise HTTPException(status_code=404, detail="找不到該筆訂單")

    if record.emp_id != payload.emp_id:
        raise HTTPException(status_code=403, detail="只能取消自己的申請")

    valid_cancel_status = ['待簽核', '已預約', '退回修改', '已簽核']
    if record.status not in valid_cancel_status:
        raise HTTPException(status_code=400, detail=f"目前狀態為『{record.status}』，無法取消")

    record.status = '已取消'
    db.commit()
    return {"message": "借用申請已成功取消", "status": record.status}