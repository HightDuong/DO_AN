"""Xuất OpenAPI schema của backend ra frontend/openapi.json để sinh kiểu TypeScript cho Frontend.

Chạy từ thư mục backend/ mỗi khi đổi schema API:
    python scripts/export_openapi.py
    cd ../frontend && npm run gen:api
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    OUTPUT.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Đã ghi {OUTPUT} ({len(app.openapi()['paths'])} đường dẫn)")


if __name__ == "__main__":
    main()
