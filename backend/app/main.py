"""Điểm vào FastAPI. Chạy từ thư mục backend/:

    uvicorn app.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origins, settings
from app.routers import chat, documents, quizzes, study_plans

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="StudyMate AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(quizzes.router)
app.include_router(study_plans.router)

if settings.dev_user_id is not None:
    log.warning("DEV_USER_ID đang bật: request không có token sẽ chạy dưới user %s. Không dùng trên môi trường thật.", settings.dev_user_id)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
