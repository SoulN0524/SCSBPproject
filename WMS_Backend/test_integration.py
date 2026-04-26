import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from main import app  

client = TestClient(app)

# ==========================================
# 測試資料暫存區 (Shared State)
# ==========================================
state = {
    # 人員 ID
    "u_emp_user": "E001",   # 員工 + 使用者
    "u_emp_admin": "E002",  # 員工 + 管理員
    "u_mgr_user": "M001",   # 主管 + 使用者
    "u_mgr_admin": "M002",  # 主管 + 管理員
    "u_dummy": "X999",      # 待刪除測試人員
    
    # 物品 ID
    "i_asset_audit": "A001", # 資產 (須審核) - 總數 10
    "i_asset_free": "A002",  # 資產 (免審核) - 總數 10
    "i_consumable": "C001",  # 耗材 - 總數 100
    "i_dummy": "X888",       # 待刪除測試物品
    
    # 訂單 ID 暫存
    "records": {}
}

# 時間變數輔助
now = datetime.now()
tomorrow = (now + timedelta(days=1)).isoformat()
yesterday = (now - timedelta(days=1)).isoformat() # 模擬逾期
next_week = (now + timedelta(days=7)).isoformat()

# 讓程式暫停，方便查看資料庫
def pause_for_inspection(step_name: str):
    print(f"\n[{step_name}] 程式已暫停。請開啟 DBeaver 查看變化。")
    input("查看完畢後，請在終端機按下 Enter 鍵繼續下一步...")
    print("繼續執行測試...\n")


# ==========================================
# 模塊一：基礎建設與軟刪除 (CRUD & Soft Delete)
# ==========================================
def test_01_create_users():
    users_data = [
        {"emp_id": state["u_emp_user"], "name": "員工甲", "department": "行銷部", "position": "員工", "role": "使用者"},
        {"emp_id": state["u_emp_admin"], "name": "員工乙", "department": "總務處", "position": "員工", "role": "管理員"},
        {"emp_id": state["u_mgr_user"], "name": "主管丙", "department": "行銷部", "position": "主管", "role": "使用者"},
        {"emp_id": state["u_mgr_admin"], "name": "主管丁", "department": "總務處", "position": "主管", "role": "管理員"},
        {"emp_id": state["u_dummy"], "name": "離職員工", "department": "開發部", "position": "員工", "role": "使用者"}
    ]
    for u in users_data:
        res = client.post("/api/users/", json=u)
        assert res.status_code == 200

def test_02_create_items():
    items_data = [
        {"item_id": state["i_asset_audit"], "name": "高階筆電", "type": "資產", "needs_manager_approval": "Y", "total_qty": 10},
        {"item_id": state["i_asset_free"], "name": "投影筆", "type": "資產", "needs_manager_approval": "N", "total_qty": 10},
        {"item_id": state["i_consumable"], "name": "A4影印紙", "type": "耗材", "needs_manager_approval": "N", "total_qty": 100},
        {"item_id": state["i_dummy"], "name": "報廢螢幕", "type": "資產", "needs_manager_approval": "N", "total_qty": 5}
    ]
    for i in items_data:
        res = client.post("/api/items/", json=i)
        assert res.status_code == 200
    pause_for_inspection("模塊一 (前半)：確認 5 位人員與 4 項物品已成功建立")

def test_03_soft_delete():
    # 刪除人員與物品
    res_u = client.delete(f"/api/users/{state['u_dummy']}")
    res_i = client.delete(f"/api/items/{state['i_dummy']}")
    assert res_u.status_code == 200
    assert res_i.status_code == 200
    pause_for_inspection("模塊一 (後半)：確認 u_dummy 與 i_dummy 的 is_active 變為 0，且從 View_Item_Inventory 消失")


# ==========================================
# 模塊二：防呆機制與越權攔截 (Error Handling)
# ==========================================
def test_04_boundary_stock():
    # 【失敗組】借用大於庫存 (11 > 10)
    res_fail = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_asset_free"],
        "qty": 11, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_fail.status_code == 400

    # 【成功組】借用等於可用庫存 (剛好借 10 個)
    res_success = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_asset_free"],
        "qty": 10, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_success.status_code == 200
    state["records"]["boundary_stock"] = res_success.json()["record_id"]
    
    # 事後清理：把這 10 個取消掉，把庫存還給後面的測試使用
    client.put(f"/api/records/{state['records']['boundary_stock']}/cancel", json={"emp_id": state["u_emp_user"]})

def test_05_boundary_soft_deleted():
    # 【失敗組】使用已停用的人員借用
    res_fail_user = client.post("/api/records/", json={
        "emp_id": state["u_dummy"], "item_id": state["i_asset_free"],
        "qty": 1, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_fail_user.status_code == 400

    # 【失敗組】借用已報廢的物品
    res_fail_item = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_dummy"],
        "qty": 1, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_fail_item.status_code == 400

def test_06_boundary_self_approve():
    # 主管丙 (M001) 發起須審核資產借用
    res = client.post("/api/records/", json={
        "emp_id": state["u_mgr_user"], "item_id": state["i_asset_audit"],
        "qty": 1, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    record_id = res.json()["record_id"]
    
    # 【失敗組】主管丙嘗試自己核准自己的單
    res_fail = client.put(f"/api/records/{record_id}/approve", json={"manager_id": state["u_mgr_user"]})
    assert res_fail.status_code == 403

    # 【成功組】主管丁 (M002) 代為核准
    res_success = client.put(f"/api/records/{record_id}/approve", json={"manager_id": state["u_mgr_admin"]})
    assert res_success.status_code == 200
    
    # 順便讓管理員領取，為下一個測試鋪路
    client.put(f"/api/records/{record_id}/pickup")
    state["records"]["borrowed_item"] = record_id

def test_07_boundary_cancel():
    record_id = state["records"]["borrowed_item"] # 目前狀態：借用中
    
    # 【失敗組】嘗試取消已在「借用中」的訂單
    res_fail = client.put(f"/api/records/{record_id}/cancel", json={"emp_id": state["u_mgr_user"]})
    assert res_fail.status_code == 400

    pause_for_inspection("模塊二：防呆與邊界測試完成 (防超貸、停用攔截、自我簽核阻擋、無效取消攔截皆正常)")


# ==========================================
# 模塊三：各類物品的生命週期 (Lifecycles)
# ==========================================
def test_08_lifecycle_consumable():
    # 耗材
    res = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_consumable"],
        "qty": 5, "expected_borrow_time": tomorrow, "expected_return_time": None
    })
    assert res.status_code == 200
    assert res.json()["status"] == "已結案"

def test_09_lifecycle_user_cancel():
    # 使用者自主取消
    res = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_asset_audit"],
        "qty": 2, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    record_id = res.json()["record_id"]
    
    res_cancel = client.put(f"/api/records/{record_id}/cancel", json={"emp_id": state["u_emp_user"]})
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "已取消"

def test_10_lifecycle_reject_and_timeout():
    # 雙軌退件與逾期失效 (利用昨日的時間發起訂單，模擬已經過期)
    res = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_asset_audit"],
        "qty": 1, "expected_borrow_time": yesterday, "expected_return_time": next_week
    })
    record_id = res.json()["record_id"]
    
    # 主管退回修改 (Soft Reject)
    res_reject = client.put(f"/api/records/{record_id}/reject?action_type=soft", json={
        "manager_id": state["u_mgr_admin"], "reject_reason": "數量有誤"
    })
    assert res_reject.status_code == 200
    
    # 使用者嘗試重新送審，預期因為已經超過預計取用時間，狀態強制轉為「已失效」
    res_resubmit = client.put(f"/api/records/{record_id}/resubmit")
    assert res_resubmit.status_code == 400
    assert "已失效" in res_resubmit.json()["detail"]

    pause_for_inspection("模塊三：生命週期測試完成 (耗材直結、自主取消、退件逾期失效皆觸發成功)")


# ==========================================
# 模塊四：歸還與部分毀損連動 (Return & Damage)
# ==========================================
def test_11_return_normal():
    # 使用模塊二建立的借用中訂單 (M001 借了 A001 數量 1)
    record_id = state["records"]["borrowed_item"]
    
    # 員工乙 (管理員) 執行正常歸還
    res = client.put(f"/api/records/{record_id}/return", json={
        "admin_id": state["u_emp_admin"], "damaged_qty": 0
    })
    assert res.status_code == 200
    assert res.json()["status"] == "已歸還"

def test_12_return_damaged():
    # 建立一筆免審核資產借用，數量 5
    res = client.post("/api/records/", json={
        "emp_id": state["u_emp_user"], "item_id": state["i_asset_free"],
        "qty": 5, "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    record_id = res.json()["record_id"]
    
    # 管理員領取
    client.put(f"/api/records/{record_id}/pickup")
    
    # 員工乙 (管理員) 執行部分毀損歸還，損壞 2 個
    res_return = client.put(f"/api/records/{record_id}/return", json={
        "admin_id": state["u_emp_admin"], "damaged_qty": 2
    })
    assert res_return.status_code == 200
    assert res_return.json()["status"] == "已歸還(部分毀損)"

    pause_for_inspection("模塊四：歸還測試完成。請確認 View_Item_Inventory 中「投影筆(A002)」的累積毀損數量為 2，實際可用變為 8")