"""Tiện ích dùng chung cho test: session DB giả ghi lại thao tác thay vì gửi tới PostgreSQL."""
import pytest


class RecordingSession:
    def __init__(self):
        self.added: list = []
        self.executed: list = []
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    def execute(self, stmt):
        self.executed.append(stmt)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, obj):
        pass

    def of_type(self, cls) -> list:
        return [o for o in self.added if isinstance(o, cls)]


@pytest.fixture
def recording_db() -> RecordingSession:
    return RecordingSession()
