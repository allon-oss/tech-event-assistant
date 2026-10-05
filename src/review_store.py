"""Local UTF-8 Markdown persistence with conflict checks and atomic replacement."""
import hashlib
import os
from pathlib import Path
import tempfile

DEFAULT_DRAFT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'event_review_draft.md'


class ReviewStoreError(ValueError):
    """Safe, readable error for the review page."""


class ReviewStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_DRAFT_PATH

    def load(self) -> tuple[str, str | None]:
        try:
            content = self.path.read_bytes()
            return content.decode('utf-8'), hashlib.sha256(content).hexdigest()
        except FileNotFoundError:
            return '', None
        except (OSError, UnicodeError) as exc:
            raise ReviewStoreError('复盘草稿读取失败，请检查文件权限及 UTF-8 编码。已有文件不会被自动覆盖。') from exc

    def _check_revision(self, expected):
        if self.load()[1] != expected:
            raise ReviewStoreError('已保存草稿已更新，请先导出当前编辑，再刷新页面读取最新版本后保存。')

    def save(self, text: str, revision: str | None) -> str:
        self._check_revision(revision)
        content = text.encode('utf-8')
        temporary = None
        failure = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=self.path.parent,
                                             suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._check_revision(revision)
            os.replace(temporary, self.path)
        except (OSError, ReviewStoreError) as exc:
            failure = exc if isinstance(exc, ReviewStoreError) else ReviewStoreError(
                '复盘草稿保存失败，请检查写入权限或关闭占用文件的软件。原草稿保持不变，可先导出当前编辑。')
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    failure = ReviewStoreError(f'{failure or "草稿已写入。"} 临时文件未能清理，请关闭占用文件的软件后重试。')
        if failure is not None:
            raise failure
        return hashlib.sha256(content).hexdigest()
