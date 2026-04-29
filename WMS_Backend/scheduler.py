import asyncio
import logging
from datetime import datetime
from database import SessionLocal
import models
from services.notifications import send_overdue_notice

logger = logging.getLogger(__name__)

async def check_overdue_records():
    """
    這是一個背景任務，會持續在背景執行。
    實務上通常設定每天早上 8 點執行一次，這裡為了測試方便，設定為每 60 秒檢查一次。
    """
    while True:
        logger.info("啟動排程巡檢：檢查是否有逾期未還的物品...")
        
        # 每次檢查都需要一個獨立的資料庫連線
        db = SessionLocal()
        try:
            now = datetime.now()
            
            # 撈出所有「借用中」且「有設定預計歸還時間」，且「時間已過期」的訂單
            overdue_records = db.query(models.Record).filter(
                models.Record.status == '借用中',
                models.Record.expected_return_time != None,
                models.Record.expected_return_time < now,
                models.Record.overdue_notice_sent == 0
            ).all()

            if overdue_records:
                logger.info(f"發現 {len(overdue_records)} 筆逾期紀錄，準備發送通知...")
                for record in overdue_records:
                    # 觸發通知
                    send_overdue_notice(record.emp_id, record.item_id, record.expected_return_time)
                    record.overdue_notice_sent = 1 # 標記已發送過逾期通知，避免重複發送
                    # 備註：實務上我們可能會在資料庫加一個 `overdue_notice_sent` (布林值) 的欄位
                    # 避免同一個逾期的物品，每 60 秒就被狂寄信轟炸。
                    # 如果有加那個欄位，這裡就可以寫： record.overdue_notice_sent = True
                
                db.commit()
            else:
                logger.info("目前無逾期未還的物品。")

        except Exception as e:
            logger.error(f"排程器執行時發生錯誤: {e}")
        finally:
            db.close() # 確保連線關閉

        # 暫停 60 秒後再檢查下一次 (實務上可以改成 asyncio.sleep(86400) 即一天檢查一次)
        await asyncio.sleep(60)