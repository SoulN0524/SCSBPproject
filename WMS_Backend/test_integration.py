import os
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# ============================================
# DEMO 模式：每次執行前重置 WMS.db
# ============================================
if os.path.exists("WMS.db"):
    os.remove("WMS.db")
    print("\n[DEMO] 已清除舊 WMS.db")

from init_db import initialize_database
initialize_database()

from main import app  # ⚠ 必須在 init_db 之後 import

client = TestClient(app)

# ============================================
# 共用狀態 & 時間變數
# ============================================
state = {
    # 人員
    "u_emp_user":  "E001",  # 員工 + 使用者
    "u_emp_admin": "E002",  # 員工 + 管理員  ← 主要的 pickup/return 執行者
    "u_mgr_user":  "M001",  # 主管 + 使用者  ← 用來測「主管但不是管理員」
    "u_mgr_admin": "M002",  # 主管 + 管理員  ← 主要的 approve/reject 執行者
    "u_dummy":     "X999",  # 待停用
    # 物品
    "i_asset_audit": "A001",  # 資產 + 須審核
    "i_asset_free":  "A002",  # 資產 + 免審核
    "i_consumable":  "C001",  # 耗材
    "i_dummy":       "X888",  # 待停用
    "i_concurrent":  "A003",  # 併發測試專用
    # 訂單
    "records": {}
}

now = datetime.now()
tomorrow  = (now + timedelta(days=1)).isoformat()
yesterday = (now - timedelta(days=1)).isoformat()
next_week = (now + timedelta(days=7)).isoformat()


# ============================================
# 終端輸出工具
# ============================================
def step(label):
    """每個 test 開頭印一行,告訴你在跑什麼"""
    print(f"\n→ {label}")

def pause(name, *, sql=None, expect=None):
    """模塊結束時的暫停點,列出該下什麼 SQL、預期看到什麼"""
    print(f"\n[PAUSE] {name}")
    if sql:
        print(f"   DBeaver SQL → {sql}")
    if expect:
        print(f"   預期看到    → {expect}")
    input("   按 Enter 繼續 ")


# ============================================
# 模塊 1:基礎建設與軟刪除
# ============================================
def test_01_create_users():
    step("[1-1] 新增 5 位人員 (4 角色組合 + 1 待停用)")
    users = [
        {"emp_id": "E001", "name": "員工甲", "department": "行銷部", "position": "員工", "role": "使用者"},
        {"emp_id": "E002", "name": "員工乙", "department": "總務處", "position": "員工", "role": "管理員"},
        {"emp_id": "M001", "name": "主管丙", "department": "行銷部", "position": "主管", "role": "使用者"},
        {"emp_id": "M002", "name": "主管丁", "department": "總務處", "position": "主管", "role": "管理員"},
        {"emp_id": "X999", "name": "離職員工", "department": "開發部", "position": "員工", "role": "使用者"},
    ]
    for u in users:
        res = client.post("/api/users/", json=u)
        assert res.status_code == 200, res.json()


def test_02_create_items():
    step("[1-2] 新增 4 項物品 (2 資產 + 1 耗材 + 1 待停用)")
    items = [
        {"item_id": "A001", "name": "高階筆電",   "type": "資產", "needs_manager_approval": "Y", "total_qty": 10},
        {"item_id": "A002", "name": "投影筆",     "type": "資產", "needs_manager_approval": "N", "total_qty": 10},
        {"item_id": "C001", "name": "A4影印紙",   "type": "耗材", "needs_manager_approval": "N", "total_qty": 100},
        {"item_id": "X888", "name": "報廢螢幕",   "type": "資產", "needs_manager_approval": "N", "total_qty": 5},
    ]
    for i in items:
        res = client.post("/api/items/", json=i)
        assert res.status_code == 200, res.json()

    pause("基礎資料建立完成",
          sql="SELECT * FROM Users; SELECT * FROM Items;",
          expect="5 位人員 + 4 項物品,is_active 全為 1")


def test_03_soft_delete():
    step("[1-3] 軟刪除 X999 (人) 與 X888 (物)")
    assert client.patch(f"/api/users/{state['u_dummy']}/deactivate").status_code == 200
    assert client.patch(f"/api/items/{state['i_dummy']}/deactivate").status_code == 200

    pause("軟刪除完成",
          sql='SELECT emp_id, is_active FROM Users WHERE emp_id="X999"; '
              'SELECT * FROM View_Item_Inventory WHERE "物品編號"="X888";',
          expect="X999 的 is_active=0;X888 不再出現在 View (View 已過濾停用品)")


# ============================================
# 模塊 2:防呆與越權攔截
# ============================================
def test_04_boundary_stock():
    step("[2-1] 庫存上限:借 11 失敗、借 10 成功")
    res_fail = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A002", "qty": 11,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_fail.status_code == 400

    res_ok = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A002", "qty": 10,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_ok.status_code == 200

    # 取消,把庫存還給後面
    client.put(f"/api/records/{res_ok.json()['record_id']}/cancel", json={"emp_id": "E001"})


def test_05_boundary_soft_deleted():
    step("[2-2] 已停用的人/物無法借用")
    res_u = client.post("/api/records/", json={
        "emp_id": "X999", "item_id": "A002", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_u.status_code == 400

    res_i = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "X888", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    assert res_i.status_code == 400


def test_06_boundary_self_approve():
    step("[2-3] 自我簽核擋下 → 跨人簽核 → 由管理員發放")
    res = client.post("/api/records/", json={
        "emp_id": "M001", "item_id": "A001", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    # M001 想自己核准自己 → 403
    assert client.put(f"/api/records/{rid}/approve", json={"manager_id": "M001"}).status_code == 403
    # M002 跨人核准 → 200
    assert client.put(f"/api/records/{rid}/approve", json={"manager_id": "M002"}).status_code == 200
    # E002 (管理員) 發放
    assert client.put(f"/api/records/{rid}/pickup", json={"admin_id": "E002"}).status_code == 200

    state["records"]["borrowed_item"] = rid


def test_07_boundary_cancel():
    step("[2-4] 借用中無法取消")
    rid = state["records"]["borrowed_item"]
    res = client.put(f"/api/records/{rid}/cancel", json={"emp_id": "M001"})
    assert res.status_code == 400

    pause("防呆與越權測試完成",
          sql="SELECT record_id, emp_id, item_id, qty, status FROM Records ORDER BY record_id;",
          expect="1 筆『借用中』(M001 的 A001) + 1 筆『已取消』(剛才借 10 個那筆)")


# ============================================
# 模塊 3:物品生命週期
# ============================================
def test_08_lifecycle_consumable():
    step("[3-1] 耗材直接結案 + 即時扣 total_qty")
    res = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "C001", "qty": 5,
        "expected_borrow_time": tomorrow, "expected_return_time": None
    })
    assert res.status_code == 200
    assert res.json()["status"] == "已結案"


def test_09_lifecycle_user_cancel():
    step("[3-2] 使用者自主取消")
    res = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A001", "qty": 2,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]
    res_c = client.put(f"/api/records/{rid}/cancel", json={"emp_id": "E001"})
    assert res_c.status_code == 200
    assert res_c.json()["status"] == "已取消"


def test_10_lifecycle_reject_then_expire():
    step("[3-3] 退回修改 → resubmit 時已過期 → 自動失效")
    # expected_borrow_time 設成昨天,模擬重送時已逾期
    res = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A001", "qty": 1,
        "expected_borrow_time": yesterday, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    # 主管軟退件
    res_rej = client.put(f"/api/records/{rid}/reject?action_type=soft",
                         json={"manager_id": "M002", "reject_reason": "數量有誤"})
    assert res_rej.status_code == 200

    # 重送 → 因為已過 expected_borrow_time,被強制標為「已失效」
    res_re = client.put(f"/api/records/{rid}/resubmit")
    assert res_re.status_code == 400
    assert "已失效" in res_re.json()["detail"]

    pause("生命週期測試完成",
          sql='SELECT item_id, total_qty FROM Items WHERE item_id="C001"; '
              "SELECT record_id, status FROM Records WHERE status IN ('已結案','已取消','已失效');",
          expect="C001 的 total_qty 從 100 → 95;三種終態各 1 筆")


# ============================================
# 模塊 4:歸還與部分毀損
# ============================================
def test_11_return_normal():
    step("[4-1] 正常歸還 (M001 借的 A001 由 E002 驗收)")
    rid = state["records"]["borrowed_item"]
    res = client.put(f"/api/records/{rid}/return",
                     json={"admin_id": "E002", "damaged_qty": 0})
    assert res.status_code == 200
    assert res.json()["status"] == "已歸還"


def test_12_return_damaged():
    step("[4-2] 部分毀損歸還 (E001 借 5 個 A002,毀損 2)")
    res = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A002", "qty": 5,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    client.put(f"/api/records/{rid}/pickup", json={"admin_id": "E002"})

    res_ret = client.put(f"/api/records/{rid}/return",
                         json={"admin_id": "E002", "damaged_qty": 2})
    assert res_ret.status_code == 200
    assert res_ret.json()["status"] == "已歸還(部分毀損)"

    pause("歸還與毀損測試完成",
          sql='SELECT * FROM View_Item_Inventory WHERE "物品編號"="A002";',
          expect="A002:累積毀損=2、借用數量=0、實際可用=8")


# ============================================
# 模塊 5:權限矩陣
# (test_13~15 共用同一筆 record,依序驗證 approve/pickup/return 的角色守門)
# ============================================
def test_13_perm_approve_requires_manager():
    step("[5-1] 員工 (E001) 試圖 approve → 403 (僅主管可)")
    res = client.post("/api/records/", json={
        "emp_id": "M001", "item_id": "A001", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]
    state["records"]["perm_chain"] = rid

    res_fail = client.put(f"/api/records/{rid}/approve", json={"manager_id": "E001"})
    assert res_fail.status_code == 403


def test_14_perm_pickup_requires_admin():
    step("[5-2] M002 核准 → M001 (主管但非管理員) 試圖 pickup → 403")
    rid = state["records"]["perm_chain"]

    assert client.put(f"/api/records/{rid}/approve", json={"manager_id": "M002"}).status_code == 200

    # M001 是「主管+使用者」,role 不是管理員 → pickup 必擋
    res_fail = client.put(f"/api/records/{rid}/pickup", json={"admin_id": "M001"})
    assert res_fail.status_code == 403


def test_15_perm_return_requires_admin():
    step("[5-3] E002 領取 → M001 試圖 return → 403 → E002 才能驗收")
    rid = state["records"]["perm_chain"]

    client.put(f"/api/records/{rid}/pickup", json={"admin_id": "E002"})

    res_fail = client.put(f"/api/records/{rid}/return",
                          json={"admin_id": "M001", "damaged_qty": 0})
    assert res_fail.status_code == 403

    res_ok = client.put(f"/api/records/{rid}/return",
                        json={"admin_id": "E002", "damaged_qty": 0})
    assert res_ok.status_code == 200


def test_16_perm_no_self_pickup():
    step("[5-4] 禁止自我發放 (E002 自己借 → 自己想領 → 403)")
    res = client.post("/api/records/", json={
        "emp_id": "E002", "item_id": "A002", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    # E002 是借用人,自己想領自己 → 403
    res_self = client.put(f"/api/records/{rid}/pickup", json={"admin_id": "E002"})
    assert res_self.status_code == 403

    # M002 (另一位管理員) 代為發放 → 200
    res_ok = client.put(f"/api/records/{rid}/pickup", json={"admin_id": "M002"})
    assert res_ok.status_code == 200

    pause("權限矩陣測試完成",
          sql="SELECT record_id, emp_id, manager_id, status FROM Records "
              "ORDER BY record_id DESC LIMIT 5;",
          expect="perm_chain 那筆 status='已歸還';E002 自借的那筆 status='借用中'")


# ============================================
# 模塊 6:時間驅動
# ============================================
def test_17_time_pickup_expired():
    step("[6-1] 已預約但 pickup 時過期 → status 自動轉為『已失效』")
    res = client.post("/api/records/", json={
        "emp_id": "M001", "item_id": "A001", "qty": 1,
        "expected_borrow_time": yesterday, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    client.put(f"/api/records/{rid}/approve", json={"manager_id": "M002"})

    res_pickup = client.put(f"/api/records/{rid}/pickup", json={"admin_id": "E002"})
    assert res_pickup.status_code == 400
    assert "已失效" in res_pickup.json()["detail"]

    # 二次確認:DB 內 status 真的被寫入「已失效」
    res_check = client.get(f"/api/records/{rid}")
    assert res_check.json()["status"] == "已失效"


def test_18_time_resubmit_success():
    step("[6-2] 退回修改 → resubmit (時間仍有效) → 回到『待審核』")
    res = client.post("/api/records/", json={
        "emp_id": "E001", "item_id": "A001", "qty": 1,
        "expected_borrow_time": tomorrow, "expected_return_time": next_week
    })
    rid = res.json()["record_id"]

    client.put(f"/api/records/{rid}/reject?action_type=soft",
               json={"manager_id": "M002", "reject_reason": "請補充用途"})

    res_re = client.put(f"/api/records/{rid}/resubmit")
    assert res_re.status_code == 200
    assert res_re.json()["status"] == "待審核"

    # 收尾:核准後立刻取消 (避免污染後面的庫存)
    client.put(f"/api/records/{rid}/approve", json={"manager_id": "M002"})
    client.put(f"/api/records/{rid}/cancel", json={"emp_id": "E001"})

    pause("時間驅動測試完成",
          sql="SELECT record_id, status, expected_borrow_time FROM Records "
              "ORDER BY record_id DESC LIMIT 3;",
          expect="一筆『已取消』(剛才 resubmit 成功後收尾)、一筆『已失效』(test_17 過期)")


# ============================================
# 模塊 7:併發超貸
# ⚠ 註:SQLite + 共用 connection 會被自然序列化,這裡實際驗的是
#       「第一道庫存檢查 + 二次驗證」是否正確擋下超貸,而非真正的 race。
# ============================================
def test_19_concurrent_overbooking():
    step("[7-1] 建立 A003 數量 5 → 2 個 thread 同時各借 3")

    client.post("/api/items/", json={
        "item_id": "A003", "name": "併發測試物品",
        "type": "資產", "needs_manager_approval": "N", "total_qty": 5
    })

    def submit():
        return client.post("/api/records/", json={
            "emp_id": "E001", "item_id": "A003", "qty": 3,
            "expected_borrow_time": tomorrow, "expected_return_time": next_week
        })

    with ThreadPoolExecutor(max_workers=2) as ex:
        results = [f.result() for f in [ex.submit(submit) for _ in range(2)]]

    successes = [r for r in results if r.status_code == 200]
    failures  = [r for r in results if r.status_code != 200]

    print(f"   結果 → {len(successes)} 成功 / {len(failures)} 失敗")

    # 兩個都成功 = 系統超貸 = bug
    assert len(successes) <= 1, "兩個 request 都成功,代表庫存防超貸失靈!"

    total_borrowed = sum(r.json()["qty"] for r in successes)
    assert total_borrowed <= 5

    pause("併發超貸測試完成",
          sql='SELECT * FROM View_Item_Inventory WHERE "物品編號"="A003";',
          expect=f'A003:借用數量={total_borrowed}、實際可用={5-total_borrowed} (絕不會 < 0)')
