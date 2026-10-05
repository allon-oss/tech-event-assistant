"""Streamlit review UI; calculations and persistence live in separate modules."""
import streamlit as st

from src.review_generator import (
    OBSERVATION_FIELDS, channel_observations, format_rate, generate_review, summarize_review,
)
from src.review_store import ReviewStore, ReviewStoreError


def _remember_observation(field):
    st.session_state['review_observations'][field] = st.session_state['review_' + field]


def _remember_draft():
    st.session_state['review_draft'] = st.session_state['review_editor']


def _replace_editor(data, revision):
    draft = generate_review(data, st.session_state['review_observations'])
    st.session_state['review_draft'] = draft
    st.session_state['review_editor'] = draft
    st.session_state['review_generated_revision'] = revision
    st.session_state['review_confirm_regenerate'] = False


@st.dialog('导出 Markdown')
def _export_dialog(draft):
    st.caption('已准备当前编辑后的正文，包含未保存的修改。点击下载；需要继续修改时返回编辑后再次导出。')
    st.download_button('下载 Markdown', data=draft.encode('utf-8'),
                       file_name='创业者交流_活动复盘.md', mime='text/markdown',
                       key='export_review', on_click='ignore')
    if st.button('返回编辑', key='return_from_review_export'):
        st.rerun()


def render_review_page(data, revision, source):
    st.subheader('活动复盘')
    st.caption('创业者交流 · 数据与人工观察生成本地草稿，正式使用前由你确认。')
    summary = summarize_review(data)
    st.markdown('### 1. 数据摘要')
    st.caption(f'当前读取：{source.name} · 每次页面运行读取最新已保存数据。关系跟进页的未保存编辑不参与统计。')
    results = [('报名人数', str(summary['kpis']['registered'])),
               ('到场人数', str(summary['kpis']['attended'])),
               ('到场率', format_rate(summary['kpis']['attendance_rate'])),
               ('到场创业者人数', str(summary['kpis']['attended_founders']))]
    for column, (label, value) in zip(st.columns(4), results):
        column.metric(label, value)
    with st.expander('人群结构、方向与渠道明细', expanded=True):
        st.caption('身份占比和前三方向按全部报名者统计；到场创业者按实际到场统计。')
        roles = summary['roles'].rename(columns={'role':'身份', 'count':'报名人数', 'share':'报名占比'}).copy()
        roles['报名占比'] = roles['报名占比'].map(format_rate)
        st.dataframe(roles, hide_index=True, width='stretch')
        fields = summary['top_fields']
        if fields.empty:
            st.write('暂无关注方向数据。')
        else:
            st.write('人数最多的方向：' + '、'.join(f'{r.field} {r.count} 人' for r in fields.itertuples()))
        channels = summary['channels'].rename(columns={
            'registration_channel':'渠道', 'registered':'报名人数', 'attended':'到场人数', 'attendance_rate':'到场率',
        }).copy()
        channels['到场率'] = channels.apply(
            lambda row: format_rate(row['到场率']) if row['报名人数'] else '暂无（无报名）', axis=1,
        )
        st.dataframe(channels, hide_index=True, width='stretch')
        for sentence in channel_observations(summary):
            st.write(sentence)
    st.metric('明确对接价值人数', summary['kpis']['valuable_connections'])
    for column, (label, count) in zip(st.columns(4), summary['progress'].items()):
        column.metric(label, count)
    if summary['paused']:
        st.caption(f'另有暂不跟进 {summary["paused"]} 人，仍计入明确对接价值总数。')

    review_store = ReviewStore()
    if 'review_draft' not in st.session_state:
        try:
            draft, saved_revision = review_store.load()
        except ReviewStoreError as error:
            st.error(str(error))
            return
        st.session_state['review_draft'] = draft
        st.session_state['review_saved_text'] = draft
        st.session_state['review_saved_revision'] = saved_revision
    if 'review_observations' not in st.session_state:
        st.session_state['review_observations'] = {field:'' for field in OBSERVATION_FIELDS}

    st.divider()
    st.markdown('### 2. 人工补充')
    st.caption('以下均为可选人工观察。输入不会写回 CSV；本次会话保留输入，刷新后需重新填写。保存的草稿会保留已整合的文字。')
    for field, (label, placeholder) in OBSERVATION_FIELDS.items():
        key = 'review_' + field
        if key not in st.session_state:
            st.session_state[key] = st.session_state['review_observations'][field]
        st.text_area(label, key=key, height=100, placeholder=placeholder,
                     on_change=_remember_observation, args=(field,))
    if st.button('生成复盘草稿', key='generate_review', type='primary'):
        if st.session_state['review_draft'].strip():
            st.session_state['review_confirm_regenerate'] = True
        else:
            _replace_editor(data, revision)
    if st.session_state.get('review_confirm_regenerate'):
        st.warning('重新生成将替换当前未保存的草稿内容，也会替换编辑区中的已加载版本。此前保存的文件在再次点击保存前保持不变。')
        confirm, cancel = st.columns(2)
        if confirm.button('确认重新生成', key='confirm_regenerate_review'):
            _replace_editor(data, revision)
            st.rerun()
        if cancel.button('取消重新生成', key='cancel_regenerate_review'):
            st.session_state['review_confirm_regenerate'] = False
            st.rerun()

    st.divider()
    st.markdown('### 3. 复盘草稿')
    st.info('以下内容由结构化数据与人工输入生成，请在正式使用前人工确认。')
    st.caption('编辑区可直接修改。复制：点击正文，按 Ctrl+A 全选，再按 Ctrl+C 复制。失焦后修改进入当前会话；刷新前请保存或导出。')
    generated_revision = st.session_state.get('review_generated_revision')
    if generated_revision and generated_revision != revision:
        st.warning('活动数据已更新，当前草稿尚未同步。请保留所需人工编辑，再点击生成并确认替换。')
    elif st.session_state['review_saved_revision'] and not generated_revision:
        st.caption('已读取此前保存的草稿；该稿可能基于较早数据。点击生成并确认替换可使用最新数据重新整理。')
    if 'review_editor' not in st.session_state:
        st.session_state['review_editor'] = st.session_state['review_draft']
    draft = st.text_area('可编辑复盘草稿', key='review_editor', height=600, on_change=_remember_draft)
    st.session_state['review_draft'] = draft
    save, export = st.columns(2)
    if save.button('保存复盘草稿', key='save_review', disabled=not draft.strip()):
        try:
            st.session_state['review_saved_revision'] = review_store.save(
                draft, st.session_state['review_saved_revision'],
            )
            st.session_state['review_saved_text'] = draft
            st.success('复盘草稿已保存，刷新或重启应用后可继续读取。')
        except ReviewStoreError as error:
            st.error(str(error))
    if export.button('导出 Markdown', key='prepare_review_export', disabled=not draft.strip()):
        _export_dialog(draft)
    if draft != st.session_state['review_saved_text']:
        st.caption('当前草稿有未保存的修改。')
    st.caption('保存位置：data/event_review_draft.md。导出包含当前编辑后的正文，无须先保存。')
