"""Session-owned upload workspace and separate review editor contexts."""
from copy import deepcopy
from uuid import uuid4

from src.followup_store import FollowupStore, display_followups
from src.metrics import get_followups
from src.upload_data import validate_upload_data


def _clear_editor_state(session):
    for key in list(session):
        if key.startswith('review_') or key.startswith('followup_editor_') or key in (
            'restore_revision', 'feedback', 'active_editor_key',
            'status_filter', 'role_filter', 'owner_filter',
        ):
            del session[key]
    session['editor_generation'] = session.get('editor_generation', 0) + 1


def switch_context(session, context):
    previous = session.get('_data_context')
    if previous == context:
        return
    contexts = session.setdefault('_data_ui_contexts', {})
    if previous:
        contexts[previous] = {k: deepcopy(session[k]) for k in session if k.startswith('review_')}
    _clear_editor_state(session)
    for key, value in contexts.get(context, {}).items():
        session[key] = deepcopy(value)
    session['_data_context'] = context


def confirm_upload(session, frame):
    """Called only after user confirmation; replace only this session's upload."""
    clean = validate_upload_data(frame)
    session['_upload_workspace'] = {
        'data': clean.copy(deep=True), 'baseline': clean.copy(deep=True),
        'version': 0, 'id': uuid4().hex,
    }
    session.get('_data_ui_contexts', {}).pop('upload', None)
    if session.get('_data_context') == 'upload':
        _clear_editor_state(session)


class UploadFollowupStore(FollowupStore):
    """In-memory backend reusing guarded edit merging, never the disk backend."""
    def __init__(self, workspace):
        self.workspace = workspace

    def _validate(self, data):
        return validate_upload_data(data)

    def _baseline(self):
        return self.workspace['baseline'].copy(deep=True)

    def revision(self):
        return f"upload:{self.workspace['id']}:{self.workspace['version']}"

    def load(self):
        return self.workspace['data'].copy(deep=True), self.revision()

    def _save_data(self, merged, revision):
        self._check_revision(revision)
        self.workspace['data'] = merged.copy(deep=True)
        self.workspace['version'] += 1

    def current_path(self):
        return '用户上传数据（当前会话）'

    def restore(self, revision):
        self._check_revision(revision)
        self._save_data(self._baseline(), revision)

    def export_csv(self):
        exported = display_followups(get_followups(self.load()[0]), demo_aliases=False).drop(columns='报名编号')
        # Protect the downloaded spreadsheet without changing the source facts.
        exported = exported.map(lambda value: "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value)
        return exported.to_csv(index=False).encode('utf-8-sig')
