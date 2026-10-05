"""Demo-only storage owned by the visitor's session; never writes any files."""
import hashlib
from pathlib import Path

from src.data_loader import DEFAULT_DATA_PATH, load_data
from src.followup_store import FollowupStore
from src.review_store import ReviewStoreError


class SessionFollowupStore(FollowupStore):
    """Reuse local edit validation and export with an isolated in-memory backend."""

    def __init__(self, session, demo_path=None):
        self.session = session
        self.demo_path = Path(demo_path) if demo_path is not None else DEFAULT_DATA_PATH
        if '_demo_followup_data' not in session:
            session['_demo_followup_data'] = load_data(self.demo_path)
            session['_demo_followup_version'] = 0

    def current_path(self) -> Path:
        # Only used to identify the immutable source, never a working file.
        return self.demo_path

    def revision(self) -> str:
        return f"session:{self.session['_demo_followup_version']}"

    def load(self):
        return self.session['_demo_followup_data'].copy(deep=True), self.revision()

    def _save_data(self, merged, revision):
        self._check_revision(revision)
        self.session['_demo_followup_data'] = merged.copy(deep=True)
        self.session['_demo_followup_version'] += 1

    def restore(self, revision):
        self._check_revision(revision)
        self._save_data(load_data(self.demo_path), revision)


class SessionReviewStore:
    """Keep saved Markdown in this session, ignoring any local draft on disk."""

    def __init__(self, session):
        self.session = session

    def load(self):
        return self.session.get('_demo_review_text', ''), self.session.get('_demo_review_revision')

    def save(self, text, revision):
        if self.load()[1] != revision:
            raise ReviewStoreError('已保存草稿已更新，请先导出当前编辑，再重新读取后保存。')
        current = hashlib.sha256(text.encode('utf-8')).hexdigest()
        self.session['_demo_review_text'] = text
        self.session['_demo_review_revision'] = current
        return current
