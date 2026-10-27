"""Kích hoạt extension pgvector trên Supabase và tạo các bảng còn thiếu.

Bảng hiện có: documents, document_chunks (Task 1); quiz_sets, quiz_questions, quiz_question_sources,
quiz_attempts, quiz_responses, user_topic_mastery (Task 4).

Chạy từ thư mục backend/:
    python init_db.py

Chạy lại nhiều lần an toàn: bảng đã có được bỏ qua. Lưu ý: create_all KHÔNG sửa cấu trúc bảng đã
tồn tại — muốn đổi cột của bảng cũ phải viết migration riêng.
"""
from sqlalchemy import inspect, text

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

    existing = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)

    for table in Base.metadata.tables:
        print(f"  {'đã có   ' if table in existing else 'MỚI TẠO '} {table}")


if __name__ == "__main__":
    main()
