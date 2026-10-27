"""Đánh giá RAG Tutor trên bộ mock data: 50 câu rag_eval + 10 câu negative_eval.

Câu hỏi được gửi qua POST /api/chat, tức là đi qua Supervisor trước: script đếm cả số câu hỏi
kiến thức bị phân loại nhầm sang Quiz Agent / Study Planner.
Mỗi câu tạo một phiên chat + một bản ghi agent_runs: sau khi đánh giá, chạy
`python scripts/seed_demo_profile.py --reset` để đưa dữ liệu demo về trạng thái chuẩn.

Chạy từ thư mục backend/ (sau khi đã nạp corpus, vd. bằng scripts/test_rag.py):
    python scripts/evaluate_rag.py            # tiếp tục từ lần chạy trước nếu có
    python scripts/evaluate_rag.py --reset    # chạy lại từ đầu

Tiến độ được lưu sau MỖI câu vào scripts/output/eval_progress.json, nên nếu bị dừng giữa chừng
(hết quota, mất mạng...) chạy lại sẽ tiếp tục, không gọi lại LLM cho câu đã xong.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Document  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MOCK_DATA = ROOT / "StudyMate_AI_Bo_mock_data_CSDL" / "data"
OUTPUT = Path(__file__).resolve().parent / "output" / "eval_progress.json"
PAGE_TOLERANCE = 1  # chunk chỉ lưu trang bắt đầu, nội dung có thể vắt sang trang sau


def load_progress(reset: bool) -> dict:
    if reset or not OUTPUT.exists():
        return {"rag": {}, "neg": {}}
    return json.loads(OUTPUT.read_text(encoding="utf-8"))


def save_progress(progress: dict) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def document_ids_by_file(owner_id) -> dict[str, str]:
    """Ánh xạ tên file PDF (trong bộ eval) -> document_id đã upload (title = tên file bỏ đuôi)."""
    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.owner_id == owner_id).all()
        return {f"{d.title}.pdf": str(d.id) for d in docs}
    finally:
        db.close()


def ask(client: TestClient, question: str) -> dict | None:
    response = client.post("/api/chat", json={"question": question, "top_k": 5})
    if response.status_code != 200:
        print(f"    LỖI HTTP {response.status_code}: {response.text[:200]}")
        return None
    body = response.json()
    if body["type"] == "rag_answer":
        return {**body["rag_answer"], "routed_to": "rag_tutor"}
    if body["type"] == "error":
        print(f"    LỖI agent: {body['message']}")
        return None
    # Bị Supervisor chuyển nhầm sang agent khác: coi như không trả lời được.
    return {"answer": body["message"], "has_enough_evidence": False, "citations": [], "sources": [],
            "routed_to": body["intent"]}


def run_answerable(client: TestClient, items: list, file_to_doc: dict, progress: dict) -> None:
    for item in items:
        if item["id"] in progress["rag"]:
            continue
        missing = [r["file_name"] for r in item["references"] if r["file_name"] not in file_to_doc]
        if missing:
            sys.exit(f"Chưa upload tài liệu {missing}. Chạy scripts/test_rag.py trước.")
        body = ask(client, item["question"])
        if body is None:
            continue
        gold = {(file_to_doc[r["file_name"]], r["pdf_page"]) for r in item["references"]}
        retrieved = {(s["document_id"], s["page_number"]) for s in body["sources"]}
        recall_hit = any(
            d == gd and p is not None and abs(p - gp) <= PAGE_TOLERANCE for d, p in retrieved for gd, gp in gold
        )
        progress["rag"][item["id"]] = {
            "category": item["category"],
            "question": item["question"],
            "has_enough_evidence": body["has_enough_evidence"],
            "recall_hit": recall_hit,
            "n_citations": len(body["citations"]),
            "routed_to": body["routed_to"],
            "answer": body["answer"][:400],
        }
        save_progress(progress)
        print(f"  {item['id']} [{item['category']}] evidence={body['has_enough_evidence']} "
              f"recall={recall_hit} citations={len(body['citations'])}")


def run_negative(client: TestClient, items: list, progress: dict) -> None:
    for item in items:
        if item["id"] in progress["neg"]:
            continue
        body = ask(client, item["question"])
        if body is None:
            continue
        progress["neg"][item["id"]] = {
            "question": item["question"],
            "has_enough_evidence": body["has_enough_evidence"],
            "n_citations": len(body["citations"]),
            "routed_to": body["routed_to"],
            "answer": body["answer"][:200],
        }
        save_progress(progress)
        verdict = "OK" if body["has_enough_evidence"] is False else "!! TRẢ LỜI CÂU CẦN TỪ CHỐI !!"
        print(f"  {item['id']} evidence={body['has_enough_evidence']} {verdict}")


def report(progress: dict, n_rag: int, n_neg: int) -> None:
    rag, neg = progress["rag"], progress["neg"]
    if len(rag) < n_rag or len(neg) < n_neg:
        print(f"\nChưa xong: {len(rag)}/{n_rag} rag, {len(neg)}/{n_neg} negative. Chạy lại để tiếp tục.")
        return

    answered = [v for v in rag.values() if v["has_enough_evidence"]]
    recall = sum(v["recall_hit"] for v in rag.values())
    cited = sum(1 for v in answered if v["n_citations"] > 0)
    refused = sum(1 for v in neg.values() if v["has_enough_evidence"] is False)

    print(f"\n=== KẾT QUẢ ({n_rag} rag_eval + {n_neg} negative_eval) ===")
    print(f"LLM: provider={settings.llm_provider}, ngưỡng tương đồng={settings.retrieval_min_similarity}")
    print(f"Recall@5:                         {recall}/{n_rag} = {recall / n_rag:.1%}   (mục tiêu ≥ 80%)")
    print(f"Tỷ lệ trả lời câu trả lời được:   {len(answered)}/{n_rag} = {len(answered) / n_rag:.1%}")
    print(f"Có trích dẫn hợp lệ khi trả lời:  {cited}/{len(answered) or 1} = {cited / (len(answered) or 1):.1%}   (mục tiêu ≥ 90%)")
    print(f"Từ chối đúng câu không có căn cứ: {refused}/{n_neg} = {refused / n_neg:.1%}")
    misrouted = {k: v["routed_to"] for k, v in {**rag, **neg}.items() if v.get("routed_to", "rag_tutor") != "rag_tutor"}
    print(f"Supervisor chuyển nhầm khỏi RAG:  {len(misrouted)}/{n_rag + n_neg} {misrouted or ''}")

    by_category: dict[str, list[int]] = {}
    for v in rag.values():
        stats = by_category.setdefault(v["category"], [0, 0])
        stats[0] += 1
        stats[1] += v["recall_hit"]
    print("\nRecall@5 theo loại câu hỏi:")
    for category, (total, hits) in by_category.items():
        print(f"  {category}: {hits}/{total}")

    misses = [k for k, v in rag.items() if not v["recall_hit"]]
    false_refusals = [k for k, v in rag.items() if not v["has_enough_evidence"]]
    print(f"\nTruy xuất trượt: {misses}")
    print(f"Từ chối oan (câu trả lời được): {false_refusals}")
    print(f"\nChi tiết: {OUTPUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="Bỏ kết quả cũ, chạy lại từ đầu")
    args = parser.parse_args()

    if settings.dev_user_id is None:
        sys.exit("DEV_USER_ID chưa đặt trong .env (script chạy dưới user này).")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    rag_items = json.loads((MOCK_DATA / "rag_eval.json").read_text(encoding="utf-8"))
    neg_items = json.loads((MOCK_DATA / "negative_eval.json").read_text(encoding="utf-8"))
    progress = load_progress(args.reset)
    file_to_doc = document_ids_by_file(settings.dev_user_id)
    client = TestClient(app)

    print(f"Đã có: {len(progress['rag'])}/{len(rag_items)} rag, {len(progress['neg'])}/{len(neg_items)} negative")
    run_answerable(client, rag_items, file_to_doc, progress)
    run_negative(client, neg_items, progress)
    report(progress, len(rag_items), len(neg_items))


if __name__ == "__main__":
    main()
