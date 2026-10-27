"""Tự động hóa: dọn dữ liệu cũ -> nạp corpus mock -> kiểm thử RAG Tutor.

Chạy từ thư mục backend/:
    python scripts/test_rag.py

Yêu cầu: DATABASE_URL, GEMINI_API_KEY, SUPABASE_* trong .env đã đúng, và
DEV_USER_ID đã đặt (script chạy dưới user này, không qua xác thực thật).
"""
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Document  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "sample_docs"

# Theo StudyMate_AI_Bo_mock_data_CSDL/data/manifest.json -> ingest_pdf.
# Chỉ 3 file này được nạp; các PDF khác có thể còn sót lại trong sample_docs/ từ lần test
# trước (vd. bản scan cũ) và KHÔNG thuộc bộ mock data, không nạp vào đây.
CORPUS_FILES = [
    "GT_Co_so_du_lieu.pdf",
    "BT_SQL_Bai_tap_va_loi_giai.pdf",
    "CD_Giao_dich_va_ACID.pdf",
]

IN_SCOPE_QUESTION = "GROUP BY và HAVING khác nhau như thế nào?"
TRAP_QUESTION = "MongoDB sharding hoạt động như thế nào?"


def _fail(msg: str) -> None:
    print(f"\n[THAT BAI] {msg}")
    sys.exit(1)


def check_prerequisites() -> UUID:
    if settings.dev_user_id is None:
        _fail("DEV_USER_ID chưa đặt trong .env. Thêm dòng DEV_USER_ID=<uuid bất kỳ> rồi chạy lại.")
    missing = [f for f in CORPUS_FILES if not (CORPUS_DIR / f).exists()]
    if missing:
        _fail(f"Thiếu file trong sample_docs/: {missing}")
    return settings.dev_user_id


def reset_dev_documents(owner_id: UUID) -> None:
    """Xoá document + chunk cũ của dev user để môi trường test lặp lại được (idempotent).

    Không xoá file trên Supabase Storage (không cần thiết cho test này, tránh rủi ro thao tác
    ngoài ý muốn lên Storage).
    """
    print("== Bước 0: dọn dữ liệu test cũ của DEV_USER_ID ==")
    db = SessionLocal()
    try:
        old = db.query(Document).filter(Document.owner_id == owner_id).all()
        for doc in old:
            print(f"  xoá document cũ: {doc.id}  title={doc.title!r}  status={doc.status.value}")
            db.delete(doc)  # cascade xoá document_chunks qua FK ON DELETE CASCADE
        db.commit()
        print(f"  đã xoá {len(old)} document cũ." if old else "  không có dữ liệu cũ.")
    finally:
        db.close()


def upload_corpus(client: TestClient) -> None:
    print("\n== Bước 1: nạp 3 file PDF trong corpus/ (GT, BT, CD) ==")
    for name in CORPUS_FILES:
        path = CORPUS_DIR / name
        with path.open("rb") as f:
            response = client.post(
                "/api/documents/upload",
                files={"file": (name, f, "application/pdf")},
                data={"title": path.stem, "source_url": "", "license": "Mock data - StudyMate AI"},
            )
        if response.status_code != 201:
            _fail(f"Upload {name} thất bại ({response.status_code}): {response.text[:500]}")
        body = response.json()
        if body["status"] != "indexed":
            _fail(f"Upload {name} không ở trạng thái indexed: {body}")
        print(f"  OK {name}: {body['chunk_count']} chunk, document_id={body['id']}")


def ask(client: TestClient, question: str) -> dict:
    response = client.post("/api/chat", json={"question": question})
    if response.status_code != 200:
        _fail(f"POST /api/chat thất bại ({response.status_code}): {response.text[:500]}")
    body = response.json()
    # /api/chat đi qua Supervisor: câu hỏi kiến thức phải được chuyển tới RAG Tutor.
    if body["type"] != "rag_answer":
        _fail(f"Supervisor không chuyển câu hỏi tới RAG Tutor: type={body['type']}, intent={body['intent']}")
    return body["rag_answer"]


def check_in_scope_question(client: TestClient) -> None:
    print(f"\n== Bước 2: câu hỏi trong phạm vi: {IN_SCOPE_QUESTION!r} ==")
    result = ask(client, IN_SCOPE_QUESTION)
    print(f"  has_enough_evidence = {result['has_enough_evidence']}")
    print(f"  answer: {result['answer'][:300]}")
    if result["has_enough_evidence"] is not True:
        _fail(f"Mong đợi has_enough_evidence=True nhưng nhận được: {result}")
    if not result["citations"]:
        _fail("has_enough_evidence=True nhưng citations rỗng (vi phạm quy tắc chống bịa nguồn).")
    print(f"  {len(result['citations'])} trích dẫn:")
    for c in result["citations"]:
        print(f"    - trang {c['page_number']} | {c['section']} | {c['quote'][:90]!r}")


def check_trap_question(client: TestClient) -> None:
    print(f"\n== Bước 3: câu hỏi bẫy (ngoài phạm vi): {TRAP_QUESTION!r} ==")
    result = ask(client, TRAP_QUESTION)
    print(f"  has_enough_evidence = {result['has_enough_evidence']}")
    print(f"  answer: {result['answer'][:300]}")
    if result["has_enough_evidence"] is not False:
        _fail(f"Mong đợi has_enough_evidence=False nhưng nhận được: {result}")
    if result["citations"]:
        _fail(f"has_enough_evidence=False nhưng vẫn có citations (nguy cơ bịa nguồn): {result['citations']}")


def main() -> None:
    owner_id = check_prerequisites()
    client = TestClient(app)

    reset_dev_documents(owner_id)
    upload_corpus(client)
    check_in_scope_question(client)
    check_trap_question(client)

    print("\n=== TAT CA BUOC PASS ===")


if __name__ == "__main__":
    main()
