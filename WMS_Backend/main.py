import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import users, items, records, dashboards
from scheduler import check_overdue_records

# 1. 定義系統的生命週期 (啟動與關閉時要執行的事)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [系統啟動時] 將檢查逾期未還的排程器丟到背景非同步執行
    task = asyncio.create_task(check_overdue_records())
    yield
    # [系統關閉時] 將排程器強制停止，釋放資源
    task.cancel()

# 2. 建立 FastAPI 實體，並設定在 Swagger 文件上顯示的資訊
app = FastAPI(
    title="WMS 倉儲管理系統 API",
    description="提供人員、物品、借用紀錄與庫存報表的後端服務",
    version="1.0.0",
    lifespan=lifespan  # <--- 關鍵：將排程器掛載進來
)

# 2.5 設定 CORS (允許跨來源資源共用)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在正式環境建議限制為前端的網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 註冊所有的 API 路由分機
app.include_router(users.router)
app.include_router(items.router)
app.include_router(records.router)
app.include_router(dashboards.router)

# 4. 根目錄測試端點
@app.get("/")
def root():
    return {"message": "歡迎來到 WMS API，請前往 /docs 查看 API 文件"}