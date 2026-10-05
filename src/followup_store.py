"""Local CSV persistence: only follow-up fields may differ from the demo."""
import hashlib
import os
from pathlib import Path
import tempfile

import pandas as pd

from src.data_loader import DEFAULT_DATA_PATH, REQUIRED_COLUMNS, DataValidationError, load_data, validate_data
from src.metrics import get_followups, valuable_mask

DEFAULT_WORKING_PATH = DEFAULT_DATA_PATH.with_name('demo_tech_event_working.csv')
EDITABLE_COLUMNS = ('followup_status', 'followup_owner', 'next_action', 'notes')
OWNER_DISPLAY_NAMES = {'景川': '林舟'}
TABLE_LABELS = {
    'attendee_id':'报名编号', 'name':'姓名', 'role':'身份', 'organization':'公司 / 项目',
    'field':'方向', 'connection_intent':'对接意向', 'followup_status':'当前跟进状态',
    'followup_owner':'跟进负责人', 'next_action':'下一步动作', 'notes':'备注',
}


def display_followups(df: pd.DataFrame) -> pd.DataFrame:
    display = df[list(TABLE_LABELS)].rename(columns=TABLE_LABELS).copy()
    display['跟进负责人'] = display['跟进负责人'].replace(OWNER_DISPLAY_NAMES)
    return display


class FollowupStore:
    def __init__(self, demo_path=None, working_path=None):
        self.demo_path = Path(demo_path) if demo_path is not None else DEFAULT_DATA_PATH
        self.working_path = Path(working_path) if working_path is not None else DEFAULT_WORKING_PATH
        if self.demo_path.resolve() == self.working_path.resolve():
            raise DataValidationError('工作文件不能与原始 Demo 文件使用相同路径。')

    def current_path(self) -> Path:
        return self.working_path if self.working_path.exists() else self.demo_path

    def revision(self) -> str:
        source = self.current_path()
        try:
            return f'{source.name}:' + hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as exc:
            raise DataValidationError('无法读取当前文件版本，请检查文件与权限。') from exc

    def _check_revision(self, expected):
        if expected != self.revision():
            raise DataValidationError('数据已更新，请刷新页面后重新编辑或确认恢复，避免覆盖新修改。')

    def _check_baseline(self, df, baseline):
        if len(df) != len(baseline) or set(df.attendee_id) != set(baseline.attendee_id):
            raise DataValidationError('报名记录总数或编号与原始 Demo 不一致，不能保存。')
        indexed = df.set_index('attendee_id').loc[baseline.attendee_id]
        original = baseline.set_index('attendee_id')
        immutable = [c for c in REQUIRED_COLUMNS if c not in EDITABLE_COLUMNS and c != 'attendee_id']
        if not indexed[immutable].equals(original[immutable]):
            raise DataValidationError('只读核心字段发生变化，不能保存。')
        outside = ~valuable_mask(baseline).to_numpy()
        if not indexed.loc[outside, list(EDITABLE_COLUMNS)].equals(original.loc[outside, list(EDITABLE_COLUMNS)]):
            raise DataValidationError('未到场或无明确对接价值对象不得编辑。')

    def load(self) -> tuple[pd.DataFrame, str]:
        revision = self.revision()
        data = load_data(self.current_path())
        self._check_baseline(data, load_data(self.demo_path))
        self._check_revision(revision)
        return data, revision

    def save_edits(self, snapshot: pd.DataFrame, edited: pd.DataFrame, revision: str) -> None:
        self._check_revision(revision)
        current, _ = self.load()
        if not snapshot.equals(current):
            raise DataValidationError('报名记录或页面数据已发生变化，请刷新后重试。')
        if edited.columns.duplicated().any() or 'attendee_id' not in edited or not set(EDITABLE_COLUMNS).issubset(edited):
            raise DataValidationError('编辑内容缺少编号或跟进字段，不能保存。')
        edited = edited.copy().fillna('').astype(str)
        if edited.attendee_id.eq('').any() or edited.attendee_id.duplicated().any():
            raise DataValidationError('报名编号不能为空或重复，不能保存。')
        allowed_ids = set(get_followups(current).attendee_id)
        if not set(edited.attendee_id).issubset(allowed_ids):
            raise DataValidationError('未到场、未知编号或无明确对接价值对象不得编辑。')
        indexed = current.set_index('attendee_id')
        edits = edited.set_index('attendee_id')
        for column in edits.columns:
            if column not in EDITABLE_COLUMNS:
                if column not in indexed or not edits[column].equals(indexed.loc[edits.index, column]):
                    raise DataValidationError('只读核心字段发生变化，不能保存。')
        indexed.loc[edits.index, list(EDITABLE_COLUMNS)] = edits[list(EDITABLE_COLUMNS)]
        # Keep baseline ordering and every registration; never write just the filtered list.
        merged = indexed.reset_index()[list(REQUIRED_COLUMNS)]
        merged = validate_data(merged)
        self._check_baseline(merged, load_data(self.demo_path))
        temporary = None
        failure = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                                             dir=self.working_path.parent, suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                merged.to_csv(handle, index=False)
                handle.flush()
                os.fsync(handle.fileno())
            self._check_revision(revision)
            os.replace(temporary, self.working_path)
        except (OSError, DataValidationError) as exc:
            failure = (exc if isinstance(exc, DataValidationError) else DataValidationError(
                '跟进信息保存失败，请检查写入权限或关闭占用 CSV 的软件。原文件保持不变。'))
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    failure = DataValidationError(
                        f'{failure or "跟进信息保存未完成。"} 临时写入文件未能清理，请关闭占用文件的软件后重试。')
        if failure is not None:
            raise failure

    def restore(self, revision: str) -> None:
        self._check_revision(revision)
        load_data(self.demo_path)
        try:
            self.working_path.unlink(missing_ok=True)
        except OSError as exc:
            raise DataValidationError('恢复失败，请检查权限或关闭占用工作文件的软件。') from exc

    def export_csv(self) -> bytes:
        # Read saved data at export time, independent of UI filters and unsaved edits.
        data, _ = self.load()
        return display_followups(get_followups(data)).drop(columns='报名编号').to_csv(index=False).encode('utf-8-sig')
