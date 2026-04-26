# 未來可以串接 SMTP (Email) 或 LINE Notify API
def send_rejection_notice(emp_id: str, item_id: str, reason: str):
    # 這裡暫時用 print 模擬發送動作
    print("="*40)
    print(f"【系統通知】發送給員工：{emp_id}")
    print(f"您的物品 ({item_id}) 借用申請已被主管駁回。")
    print(f"駁回原因：{reason}")
    print("="*40)

def send_approval_notice(emp_id: str, item_id: str):
    print("="*40)
    print(f"【系統通知】發送給員工：{emp_id}")
    print(f"您的物品 ({item_id}) 借用申請已核准，請準時領取。")
    print("="*40)