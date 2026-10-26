"""Kích hoạt extension pgvector trên Supabase và tạo bảng.

Chạy từ thư mục backend/:
    python init_db.py
"""
from sqlalchemy import text

from app import models  # noqa: F401  (đăng ký models vào Base.metadata)
from app.db import Base, engine


def main() -> None:
    with engine.begin() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        print(f"Đã kết nối: {version}")

        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        vector_version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
        print(f"pgvector đã bật (phiên bản {vector_version})")

    # create_all chỉ tạo bảng chưa tồn tại, không sửa bảng đã có.
    Base.metadata.create_all(bind=engine)
    print("Đã tạo bảng:", ", ".join(Base.metadata.tables))


if __name__ == "__main__":
    main()
