"""Kiểm thử API danh sách / xoá tài liệu (service được thay bằng bản giả)."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user_id
from app.db import get_db
from app.main import app
from app.models import Document, DocumentStatus
from app.routers import documents as documents_router
from app.services import ingestion_service

USER_ID = uuid4()


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_documents(client, monkeypatch):
    doc = Document(id=uuid4(), owner_id=USER_ID, title="GT_Co_so_du_lieu", source_url=None, license="Mock",
                   storage_path="x.pdf", status=DocumentStatus.indexed, page_count=30,
                   created_at=datetime.now(timezone.utc))
    captured = {}

    def fake(db, owner_id):
        captured["owner_id"] = owner_id
        return [(doc, 31)]

    monkeypatch.setattr(documents_router, "list_documents", fake)
    body = client.get("/api/documents").json()
    assert captured == {"owner_id": USER_ID}  # chỉ tài liệu của user đã xác thực
    assert body[0]["status"] == "indexed" and body[0]["page_count"] == 30 and body[0]["chunk_count"] == 31
    assert "storage_path" not in body[0]


def test_delete_document(client, monkeypatch):
    calls = []
    monkeypatch.setattr(documents_router, "delete_document", lambda db, owner, doc_id: calls.append((owner, doc_id)) or True)
    doc_id = uuid4()
    r = client.delete(f"/api/documents/{doc_id}")
    assert r.status_code == 204 and calls == [(USER_ID, doc_id)]


def test_delete_unknown_document_404(client, monkeypatch):
    monkeypatch.setattr(documents_router, "delete_document", lambda *a: False)
    assert client.delete(f"/api/documents/{uuid4()}").status_code == 404


class FakeDB:
    def __init__(self, document):
        self.document, self.deleted, self.commits = document, [], 0

    def scalar(self, stmt):
        return self.document

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1


def test_delete_document_service_removes_row_then_storage(monkeypatch):
    doc = Document(id=uuid4(), owner_id=USER_ID, storage_path="u/d.pdf")
    removed = []
    monkeypatch.setattr(ingestion_service, "delete_pdf", lambda path: removed.append(path))
    db = FakeDB(doc)
    assert ingestion_service.delete_document(db, USER_ID, doc.id) is True
    assert db.deleted == [doc] and db.commits == 1 and removed == ["u/d.pdf"]


def test_delete_document_service_not_found(monkeypatch):
    monkeypatch.setattr(ingestion_service, "delete_pdf", lambda path: pytest.fail("không được xoá file"))
    assert ingestion_service.delete_document(FakeDB(None), USER_ID, uuid4()) is False
