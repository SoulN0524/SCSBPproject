from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. 定義資料庫的位置與名稱
# sqlite:/// 代表使用 SQLite，./WMS.db 代表在當前資料夾下的 WMS.db 檔案
SQLALCHEMY_DATABASE_URL = "sqlite:///./WMS.db"

# 2. 建立資料庫引擎 (Engine)
# connect_args={"check_same_thread": False} 是 SQLite 在 FastAPI 中特有的設定
# 因為 FastAPI 會使用多執行緒，而 SQLite 預設不允許多個執行緒共用同一個連線
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 3. 建立 SessionLocal 類別
# 這就像是資料庫的「連線工廠」。autocommit=False 確保我們修改資料後必須手動確認(commit)，避免寫入到一半出錯
# autoflush=False 則是關閉自動刷新，保留更高的控制權
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. 建立 Base 類別
# 未來我們所有的資料表模型 (Models) 都必須繼承這個 Base 類別
Base = declarative_base()

# 5. 定義取得資料庫連線的依賴函數 (Dependency)
def get_db():
    db = SessionLocal()
    try:
        # yield 會把連線交給需要使用的 API，等 API 執行完畢後再繼續往下執行
        yield db
    finally:
        # 確保無論 API 執行成功或發生錯誤，連線都會被安全地關閉，避免資源耗盡
        db.close()