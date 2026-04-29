import logging
from datetime import datetime

# 設定日誌格式 (模擬企業系統的 Log 紀錄)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def send_approval_notice(emp_id: str, item_id: str):
    """發送：核准通知"""
    subject = "【WMS 系統通知】借用申請已核准"
    body = f"員工 {emp_id} 您好，您申請借用的物品 ({item_id}) 已由主管核准。\n請於預計時間前往管理室完成點交領取手續。"
    
    # 模擬寄送 Email / Line 的動作
    logger.info(f"正在發送通知至員工 {emp_id}...")
    print(f"\n{'='*50}\n[信件主旨] {subject}\n[信件內文]\n{body}\n{'='*50}\n")


def send_rejection_notice(emp_id: str, item_id: str, reason: str):
    """發送：直接駁回通知"""
    subject = "【WMS 系統通知】借用申請遭駁回"
    body = f"員工 {emp_id} 您好，您申請借用的物品 ({item_id}) 已被主管駁回。\n駁回原因：{reason}\n若有疑問請直接聯繫您的審核主管。"
    
    logger.info(f"正在發送通知至員工 {emp_id}...")
    print(f"\n{'='*50}\n[信件主旨] {subject}\n[信件內文]\n{body}\n{'='*50}\n")


def send_soft_reject_notice(emp_id: str, item_id: str, reason: str):
    """發送：退回修改通知"""
    subject = "【WMS 系統通知】借用申請需修改"
    body = f"員工 {emp_id} 您好，您申請借用的物品 ({item_id}) 已被主管退回要求修改。\n主管指示：{reason}\n請至系統中修改申請內容後，重新點擊『送審』。"
    
    logger.info(f"正在發送通知至員工 {emp_id}...")
    print(f"\n{'='*50}\n[信件主旨] {subject}\n[信件內文]\n{body}\n{'='*50}\n")

def send_overdue_notice(emp_id: str, item_id: str, expected_time):
    """發送：逾期未還通知"""
    subject = "【WMS 系統通知】⚠️ 物品逾期未還警告"
    # 將時間格式化為易讀的字串
    time_str = expected_time.strftime("%Y-%m-%d %H:%M")
    
    body = f"員工 {emp_id} 您好，您借用的物品 ({item_id}) 已超過預計歸還時間 ({time_str})。\n請盡速將物品歸還至管理室。若物品已遺失或毀損，請主動通報管理員。"
    
    logger.info(f"正在發送 [逾期警告] 至員工 {emp_id}...")
    print(f"\n{'='*50}\n[信件主旨] {subject}\n[信件內文]\n{body}\n{'='*50}\n")