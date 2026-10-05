"""Deterministic review facts and prose; no UI, files, or external APIs."""
import pandas as pd

from src import llm_provider
from src.metrics import (
    calculate_kpis, channel_performance, field_distribution,
    followup_progress, role_distribution, valuable_mask,
)

OBSERVATION_FIELDS = {
    'highlights': ('活动亮点', '记录现场氛围、嘉宾反馈、超出预期的部分等。'),
    'problems': ('活动问题', '记录签到、流程、内容安排、参与者体验等问题。'),
    'channel_judgment': ('对渠道表现的人工判断', '例如：社群报名量大，但临时取消较多。仅记录你实际观察到的情况。'),
    'key_relationships': ('值得重点跟进的人或关系', '补充跟进表未体现的关系信息；仅填写正式复盘需要的内容。'),
    'improvements': ('下一场活动可以改进什么', '记录下一场可执行的改进建议。'),
}


def format_rate(value: float) -> str:
    return f'{value * 100:.1f}'.rstrip('0').rstrip('.') + '%'


def summarize_review(data: pd.DataFrame) -> dict:
    """All population/field shares use registrations; onsite counts are separate."""
    kpis = calculate_kpis(data)
    roles = role_distribution(data)
    roles['share'] = roles['count'] / len(data) if len(data) else 0.0
    attended_roles = role_distribution(data[data.attended.eq('是')])
    channels = channel_performance(data)
    eligible = channels[channels.registered.gt(0)]

    def leaders(column, highest=True):
        if eligible.empty:
            return []
        extreme = eligible[column].max() if highest else eligible[column].min()
        return eligible.loc[eligible[column].eq(extreme), 'registration_channel'].tolist()

    fields = field_distribution(data)
    top_fields = fields[fields['count'].gt(0)].sort_values('count', ascending=False, kind='stable').head(3)
    paused = int((valuable_mask(data) & data.followup_status.eq('暂不跟进')).sum())
    return {
        'kpis': kpis, 'roles': roles, 'attended_roles': attended_roles,
        'channels': channels, 'top_fields': top_fields,
        'most_registered': leaders('registered'),
        'highest_attendance': leaders('attendance_rate'),
        'lowest_attendance': leaders('attendance_rate', highest=False),
        'progress': followup_progress(data), 'paused': paused,
    }


def channel_observations(summary: dict) -> list[str]:
    """Compare quantities only, excluding channels with no registrations."""
    sentences = []
    for key, label, column in [
        ('most_registered', '报名人数最多的渠道', 'registered'),
        ('highest_attendance', '到场率最高的渠道', 'attendance_rate'),
        ('lowest_attendance', '到场率最低的渠道', 'attendance_rate'),
    ]:
        names = summary[key]
        if not names:
            continue
        value = summary['channels'].set_index('registration_channel').loc[names[0], column]
        display = f'{int(value)} 人' if column == 'registered' else format_rate(value)
        tie = '（并列）' if len(names) > 1 else ''
        sentences.append(f'{label}为{"、".join(names)}{tie}，为 {display}。')
    return sentences


def generate_review(
    data: pd.DataFrame, observations: dict | None = None, *, backend: str = 'template',
) -> str:
    """Generate Markdown from current facts; LLM use is explicitly disabled.

    Backend selection is independent of Local/Demo persistence. Providers receive
    the shared calculated summary and normalized human observations, not raw rows.
    """
    if backend not in ('template', 'llm'):
        raise ValueError('不支持的复盘生成方式；请选择 template 或 llm。')
    summary = summarize_review(data)
    human = {key: str((observations or {}).get(key) or '').strip() for key in OBSERVATION_FIELDS}
    if backend == 'llm':
        return llm_provider.generate_review(summary, human)
    return _generate_template_review(summary, human)


def _generate_template_review(summary: dict, human: dict) -> str:
    """Render calculated facts and explicitly attributed human observations."""
    kpis = summary['kpis']
    onsite = summary['attended_roles']
    onsite = onsite[onsite['count'].gt(0)].sort_values('count', ascending=False, kind='stable')
    if onsite.empty:
        onsite_text = '暂无到场人员。'
    else:
        composition = '、'.join(f'{row.role} {row.count} 人' for row in onsite.itertuples())
        largest = onsite[onsite['count'].eq(onsite['count'].max())]['role'].tolist()
        tie = '（并列）' if len(largest) > 1 else ''
        onsite_text = f'到场人员中，{composition}；{"、".join(largest)}是人数最多的参与群体{tie}。'

    lines = [
        '# 创业者交流 · 活动复盘草稿', '',
        '> 以下内容由结构化数据与人工输入生成，请在正式使用前人工确认。', '',
        '## 1. 活动概况', '', '**数据事实**', '',
        f'本次创业者交流共收到 {kpis["registered"]} 人报名，实际到场 {kpis["attended"]} 人，'
        f'整体到场率为 {format_rate(kpis["attendance_rate"])}。', onsite_text, '',
        '## 2. 参与者与渠道观察', '', '**数据事实 · 全部报名者**', '',
    ]
    role_text = '、'.join(f'{r.role} {r.count} 人（{format_rate(r.share)}）'
                          for r in summary['roles'].itertuples() if r.count)
    lines.append(f'报名者身份构成：{role_text}。' if role_text else '暂无报名者身份数据。')
    fields = summary['top_fields']
    if not fields.empty:
        field_text = '、'.join(f'{r.field} {r.count} 人' for r in fields.itertuples())
        lines.extend([f'人数最多的 {len(fields)} 个关注方向：{field_text}。',
                      '方向按人数降序取前三名；并列时按活动观察页的方向顺序展示。'])
    lines.extend(['', '**数据事实 · 渠道表现**', ''])
    for row in summary['channels'].itertuples():
        rate = format_rate(row.attendance_rate) if row.registered else '暂无（无报名）'
        lines.append(f'- {row.registration_channel}：报名 {row.registered} 人，到场 {row.attended} 人，到场率 {rate}。')
    lines.extend(['', *channel_observations(summary)])
    if human['channel_judgment']:
        lines.extend(['', '**人工判断 · 渠道**', '', human['channel_judgment']])
    lines.extend(['', '## 3. 关键关系与跟进情况', '', '**数据事实**', '',
                  f'已到场且有明确对接价值的对象共 {kpis["valuable_connections"]} 人。'])
    progress = '、'.join(f'{status} {count} 人' for status, count in summary['progress'].items())
    if summary['paused']:
        progress += f'、暂不跟进 {summary["paused"]} 人'
    lines.extend([f'当前进度：{progress}。',
                  '明确对接价值按已到场且有投资、创业者、合作伙伴或人才对接意向统计；已完成对接表示介绍动作完成。'])
    if human['key_relationships']:
        lines.extend(['', '**人工补充 · 重点关系**', '', human['key_relationships']])
    lines.extend(['', '## 4. 活动亮点与问题', ''])
    for key, title in [('highlights', '亮点'), ('problems', '问题')]:
        if human[key]:
            lines.extend([f'**人工观察 · {title}**', '', human[key], ''])
    if not human['highlights'] and not human['problems']:
        lines.append('活动亮点与问题暂无人工补充。')
    lines.extend(['', '## 5. 后续行动', '', '**基于当前跟进状态的行动清单**', ''])
    if kpis['pending_followups']:
        lines.append(f'- 优先完成剩余 {kpis["pending_followups"]} 位明确对接价值对象的待跟进事项。')
    if summary['progress']['已初步建联'] or summary['progress']['跟进中']:
        lines.append(f'- 继续推进已初步建联 {summary["progress"]["已初步建联"]} 人与跟进中 '
                     f'{summary["progress"]["跟进中"]} 人的既有对接任务。')
    if not any(summary['progress'][s] for s in ['待跟进', '已初步建联', '跟进中']):
        lines.append('- 当前没有待跟进、已初步建联或跟进中的任务；按后续新增需求更新跟进表。')
    if human['key_relationships']:
        lines.append('- 按第 3 节人工补充的重点关系逐项确认下一步。')
    if human['improvements']:
        lines.extend(['', '**人工建议**', '', human['improvements']])
    return '\n'.join(lines).rstrip() + '\n'
