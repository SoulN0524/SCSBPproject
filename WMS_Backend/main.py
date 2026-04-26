from fastapi import FastAPI
from routers import users, items, records, dashboards

# 建立 FastAPI 實體，並設定在 Swagger 文件上顯示的標題
app = FastAPI(
    title="WMS 倉儲管理系統 API",
    description="提供人員、物品、借用紀錄與庫存報表的後端服務",
    version="1.0.0"
)

# 註冊所有的 API 路由分機
app.include_router(users.router)
app.include_router(items.router)
app.include_router(records.router)
app.include_router(dashboards.router)

@app.get("/")
def root():
    return {"message": "歡迎來到 WMS API，請前往 /docs 查看 API 文件"}