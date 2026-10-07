"""Business definitions shared by KPIs, charts, and the follow-up list."""
import pandas as pd

from src.data_loader import CHANNELS, FIELDS, FOLLOWUP_STATUSES, EDITABLE_STATUSES, ROLES, VALUE_INTENTS


def valuable_mask(df: pd.DataFrame) -> pd.Series:
    return df['attended'].eq('是') & df['connection_intent'].isin(VALUE_INTENTS)


def calculate_kpis(df: pd.DataFrame) -> dict[str, int | float]:
    registered = len(df)
    attended = df['attended'].eq('是')
    valuable = valuable_mask(df)
    return {
        'registered': registered,
        'attended': int(attended.sum()),
        'attendance_rate': float(attended.sum() / registered) if registered else 0.0,
        'attended_founders': int((attended & df['role'].eq('创业者')).sum()),
        'valuable_connections': int(valuable.sum()),
        'pending_followups': int((valuable & df['followup_status'].eq('待跟进')).sum()),
    }


def _distribution(df: pd.DataFrame, column: str, categories: tuple) -> pd.DataFrame:
    categories = list(categories) + [v for v in df[column].unique() if v and v not in categories]
    counts = df[column].value_counts().reindex(categories, fill_value=0)
    return counts.rename_axis(column).reset_index(name='count')


def role_distribution(df: pd.DataFrame) -> pd.DataFrame:
    return _distribution(df, 'role', ROLES)


def field_distribution(df: pd.DataFrame) -> pd.DataFrame:
    return _distribution(df, 'field', FIELDS)


def channel_performance(df: pd.DataFrame) -> pd.DataFrame:
    channels = list(CHANNELS) + [v for v in df.registration_channel.unique() if v and v not in CHANNELS]
    registered = df.groupby('registration_channel').size().reindex(channels, fill_value=0)
    attended = df[df.attended.eq('是')].groupby('registration_channel').size().reindex(channels, fill_value=0)
    result = pd.DataFrame({'registered': registered, 'attended': attended})
    result['attendance_rate'] = attended.div(registered.where(registered.ne(0))).fillna(0.0)
    return result.rename_axis('registration_channel').reset_index()


def get_followups(
    df: pd.DataFrame, *, status: str | None = None,
    role: str | None = None, owner: str | None = None,
) -> pd.DataFrame:
    """None means no filter; an empty owner means no current assignment."""
    selected = valuable_mask(df)
    for column, value in [('followup_status', status), ('role', role), ('followup_owner', owner)]:
        if value is not None:
            selected &= df[column].eq(value)
    result = df.loc[selected].copy()
    priorities = {value: index for index, value in enumerate(EDITABLE_STATUSES)}
    result['_priority'] = result.followup_status.map(priorities)
    return result.sort_values(['_priority', 'attendee_id'], kind='stable').drop(columns='_priority')


def followup_progress(df: pd.DataFrame) -> dict[str, int]:
    counts = df.loc[valuable_mask(df), 'followup_status'].value_counts()
    return {status: int(counts.get(status, 0)) for status in FOLLOWUP_STATUSES}
