"""Read the local CSV and reject invalid data before displaying any metrics."""
import csv
from pathlib import Path

import pandas as pd

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / 'data' / 'demo_tech_event.csv'
REQUIRED_COLUMNS = (
    'attendee_id', 'name', 'role', 'organization', 'startup_stage', 'field',
    'registration_channel', 'attended', 'connection_intent', 'followup_status',
    'followup_owner', 'next_action', 'notes',
)
ROLES = ('创业者', '投资人', '产业嘉宾', '科技从业者', '其他')
FIELDS = ('AI Agent', 'AI 应用', '企业服务 / SaaS', 'Robotics', '开发者工具', '消费科技', '其他')
CHANNELS = ('社群', '朋友推荐', '公众号', '小红书', '合作机构')
FOLLOWUP_STATUSES = ('待跟进', '已初步建联', '跟进中', '已完成对接')
EDITABLE_STATUSES = (*FOLLOWUP_STATUSES, '暂不跟进')
ACTIVE_STATUSES = FOLLOWUP_STATUSES[:3]
OWNERS = ('景川', '小林', 'Mia')
VALUE_INTENTS = ('寻找投资', '寻找创业者', '寻找合作伙伴', '招聘 / 人才')
ENUMS = {
    'role': ROLES,
    'startup_stage': ('想法阶段', 'MVP', '已上线', '已有收入', '融资中', '不适用'),
    'field': FIELDS,
    'registration_channel': CHANNELS,
    'attended': ('是', '否'),
    'connection_intent': (*VALUE_INTENTS, '行业交流', '暂无明确需求', '未到场'),
    'followup_status': (*FOLLOWUP_STATUSES, '暂不跟进', '未到场'),
    'followup_owner': (*OWNERS, ''),
}


class DataValidationError(ValueError):
    """A readable message that can safely be shown in the app."""


def _reject(mask: pd.Series, message: str) -> None:
    if mask.any():
        lines = [str(pos + 2) for pos, invalid in enumerate(mask) if invalid]
        locations = '、'.join(lines[:5]) + (' 等' if len(lines) > 5 else '')
        raise DataValidationError(f'{message}（数据行 {locations}，表头为第 1 行）。请检查 CSV。')


def validate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy; optional blanks remain empty strings."""
    if df.columns.duplicated().any():
        raise DataValidationError('CSV 存在重复字段名，请确保每列名称唯一。')
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise DataValidationError('CSV 缺少必要字段：' + '、'.join(missing))
    if df.empty:
        raise DataValidationError('CSV 没有报名记录，请检查文件内容。')
    clean = df.loc[:, list(REQUIRED_COLUMNS)].fillna('').astype(str)
    for column in clean.columns:
        clean[column] = clean[column].str.strip()
    for column, label in [('attendee_id', '报名编号'), ('name', '姓名'), ('next_action', '下一步动作')]:
        _reject(clean[column].eq(''), f'{label}不能为空')
    _reject(clean.attendee_id.duplicated(keep=False), '报名编号重复')
    for column, choices in ENUMS.items():
        _reject(~clean[column].isin(choices), f'{column} 含空值或不支持的选项')

    no_show = clean.attended.eq('否')
    inconsistent_no_show = (
        clean.connection_intent.ne('未到场') | clean.followup_status.ne('未到场')
        | clean.next_action.ne('未到场') | clean.followup_owner.ne('')
    )
    _reject(no_show & inconsistent_no_show, '未到场者的意向、状态、动作必须均为「未到场」，负责人须为空')
    _reject(~no_show & (clean[['connection_intent', 'followup_status', 'next_action']].eq('未到场').any(axis=1)),
            '到场者不能标记为「未到场」')
    active = clean.followup_status.isin(ACTIVE_STATUSES)
    valuable = clean.connection_intent.isin(VALUE_INTENTS)
    _reject(active & clean.followup_owner.eq(''), '需要跟进的记录必须有负责人')
    _reject(active & clean.next_action.isin(('', '暂无', '未到场')), '需要跟进的记录必须有具体下一步动作')
    _reject(~active & clean.followup_owner.ne(''), '无当前跟进任务的记录不应分配负责人')
    _reject(clean.followup_status.isin(FOLLOWUP_STATUSES) & ~valuable, '对接进度必须对应明确对接意向')
    _reject(~no_show & valuable & ~clean.followup_status.isin(EDITABLE_STATUSES), '明确对接意向必须有对应跟进状态')
    _reject(clean.followup_status.isin(('暂不跟进', '已完成对接')) & clean.next_action.ne('暂无'),
            '暂不跟进或已完成对接时，下一步动作应为「暂无」')
    _reject(clean.role.eq('创业者') & clean.startup_stage.eq('不适用'), '创业者须填写项目阶段')
    return clean


def load_data(path: str | Path | None = None) -> pd.DataFrame:
    """Load UTF-8/BOM CSV independent of the shell's current directory."""
    source = Path(path) if path is not None else DEFAULT_DATA_PATH
    try:
        # Check shape first: Pandas can silently interpret malformed extra fields as an index.
        with source.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, None)
            if not header:
                raise DataValidationError('CSV 文件为空，请添加字段名与报名记录。')
            if len(set(header)) != len(header):
                raise DataValidationError('CSV 存在重复字段名，请确保每列名称唯一。')
            for line, row in enumerate(reader, start=2):
                if len(row) != len(header):
                    raise DataValidationError(f'CSV 第 {line} 行列数与表头不一致，请检查分隔符或缺失单元格。')
            handle.seek(0)
            df = pd.read_csv(handle, dtype=str, keep_default_na=False)
    except FileNotFoundError as exc:
        raise DataValidationError('找不到活动数据。请确认 data/demo_tech_event.csv 文件存在。') from exc
    except UnicodeError as exc:
        raise DataValidationError('无法识别 CSV 编码，请保存为 UTF-8（可带 BOM）后重试。') from exc
    except (csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataValidationError('CSV 格式无法读取，请检查逗号分隔符与引号是否完整。') from exc
    except OSError as exc:
        raise DataValidationError('无法打开活动数据，请检查文件路径与读取权限。') from exc
    return validate_data(df)
