"""Streamlit event workflow with local persistence or isolated public sessions."""
import hashlib
import streamlit as st

from src.data_loader import (
    DataValidationError, EDITABLE_STATUSES, OWNERS, ROLES,
)
from src.metrics import (
    calculate_kpis, channel_performance, field_distribution,
    get_followups, role_distribution, followup_progress,
)
from src.visualizations import channel_chart, field_chart, role_chart

from src.followup_store import FollowupStore, OWNER_DISPLAY_NAMES, TABLE_LABELS, display_followups
from src.review_page import render_review_page
from src.app_mode import get_app_mode
from src.session_store import SessionFollowupStore, SessionReviewStore
from src.upload_page import render_data_source
from src.upload_session import UploadFollowupStore


def restore_controls(store):
    if st.button('恢复演示数据', key='request_restore'):
        try:
            st.session_state['restore_revision'] = store.revision()
        except DataValidationError as error:
            st.error(str(error))
    if 'restore_revision' in st.session_state:
        st.warning('确认恢复后，已保存的跟进修改和当前未保存的编辑将被清除，重新使用原始演示数据。')
        confirm, cancel = st.columns(2)
        if confirm.button('确认恢复', key='confirm_restore', type='primary'):
            try:
                store.restore(st.session_state['restore_revision'])
                del st.session_state['restore_revision']
                st.session_state['editor_generation'] = st.session_state.get('editor_generation', 0) + 1
                st.session_state['feedback'] = '已恢复演示数据'
                st.rerun()
            except DataValidationError as error:
                st.error(str(error))
        if cancel.button('取消', key='cancel_restore'):
            del st.session_state['restore_revision']
            st.rerun()

st.set_page_config(page_title='科技创业活动观察与跟进助手', page_icon='📋', layout='wide')

try:
    mode = get_app_mode()
except DataValidationError as error:
    st.error(str(error))
    st.stop()
is_demo = mode == 'demo'

st.sidebar.title('活动工作台')
st.sidebar.caption('创业者交流 · V1.0 作品集 Demo')
page = st.sidebar.radio('页面', ['活动总览', '活动观察', '关系跟进', '活动复盘'], key='page')
st.sidebar.divider()

st.title('科技创业活动观察与跟进助手')
st.markdown('从报名与签到数据中快速观察活动表现，并沉淀后续关系跟进。')
upload_workspace = render_data_source()
is_upload = upload_workspace is not None
st.sidebar.caption('用户上传数据 · 当前会话' if is_upload else
                   'Synthetic Demo Data\n\n' + ('Demo Mode · 当前会话' if is_demo else 'Local Mode · 本地保存'))
if not is_upload:
    st.info('作品集 Demo · Synthetic Demo Data：人物、公司和项目均为虚构，没有真实客户数据。')
if is_demo and not is_upload:
    st.caption('演示修改仅保存在你的当前会话，其他访问者不可见。刷新、断开会话或服务重启后会重置，请及时下载需要保留的内容。')

try:
    store = (UploadFollowupStore(upload_workspace) if is_upload else
             SessionFollowupStore(st.session_state) if is_demo else FollowupStore())
    data, revision = store.load()
except DataValidationError as error:
    st.error(str(error))
    st.caption('演示数据暂时不可用，请稍后刷新。' if is_demo
               else '请修正本地 CSV 后刷新页面。字段说明见 data/DATA_DICTIONARY.md。')
    if not is_demo and not is_upload:
        restore_controls(store)
    st.stop()

if 'feedback' in st.session_state:
    st.success(st.session_state.pop('feedback'))

if page == '活动总览':
    st.subheader('活动总览')
    st.caption('创业者交流 · 以下指标均基于完整报名与签到记录')
    kpis = calculate_kpis(data)
    cards = [
        ('报名人数', str(kpis['registered']), '全部有效报名记录。'),
        ('到场人数', str(kpis['attended']), '是否到场为「是」的人数。'),
        ('到场率', f"{kpis['attendance_rate']:.0%}", '到场人数 ÷ 报名人数。'),
        ('到场创业者人数', str(kpis['attended_founders']), '身份为创业者且实际到场的人数。'),
        ('明确对接价值人数', str(kpis['valuable_connections']), '已到场，且希望寻找投资、创业者、合作伙伴或招聘人才。含已完成对接。'),
        ('待跟进人数', str(kpis['pending_followups']), '有明确对接价值且状态为「待跟进」的人数。'),
    ]
    for offset in (0, 3):
        for column, (label, value, help_text) in zip(st.columns(3), cards[offset:offset+3]):
            column.metric(label, value, help=help_text, border=True)
    st.divider()
    st.markdown('**继续观察与行动**')
    st.write('在「活动观察」查看参与者结构与渠道表现；在「关系跟进」筛选对象、编辑并保存下一步动作。')
    with st.expander('统计口径'):
        st.write('明确对接价值 = 已到场，且对接意向属于寻找投资、寻找创业者、寻找合作伙伴、招聘 / 人才。')
        st.write('行业交流和暂无明确需求不计入明确对接价值；已完成对接表示介绍动作完成，不代表融资、合作或招聘成交。')

elif page == '活动观察':
    st.subheader('活动观察')
    st.caption('身份和方向按全部报名者统计；渠道到场率 = 该渠道到场人数 ÷ 该渠道报名人数。')
    left, right = st.columns(2, gap='large')
    with left:
        st.markdown('#### 参与者身份构成')
        st.plotly_chart(role_chart(role_distribution(data)), width='stretch', key='roles', config={'displayModeBar': False})
    with right:
        st.markdown('#### 创业 / 关注方向分布')
        st.plotly_chart(field_chart(field_distribution(data)), width='stretch', key='fields', config={'displayModeBar': False})
    st.markdown('#### 报名渠道表现')
    st.caption('蓝色柱形读左轴人数，棕色折线读右轴到场率；渠道应同时比较规模与到场表现。')
    st.plotly_chart(channel_chart(channel_performance(data)), width='stretch', key='channels', config={'displayModeBar': False})

elif page == '关系跟进':
    st.subheader('关系跟进')
    st.caption('仅展示已到场且有明确对接意向的对象。待跟进优先，暂不跟进排在最后。')
    for column, (label, count) in zip(st.columns(4), followup_progress(data).items()):
        column.metric(label, count, border=True)
    first, second, third = st.columns(3)
    status = first.selectbox('跟进状态', ['全部', *EDITABLE_STATUSES], key='status_filter')
    roles = list(dict.fromkeys([*ROLES, *data.role.tolist()])) if is_upload else ROLES
    owners = sorted(set(data.followup_owner) - {''}) if is_upload else OWNERS
    role = second.selectbox('身份', ['全部', *roles], key='role_filter')
    owner = third.selectbox(
        '负责人', ['全部', *owners, '无当前负责人'], key='owner_filter',
        format_func=lambda value: value if is_upload else OWNER_DISPLAY_NAMES.get(value, value),
    )
    followups = get_followups(
        data, status=None if status == '全部' else status,
        role=None if role == '全部' else role,
        owner=None if owner == '全部' else '' if owner == '无当前负责人' else owner,
    )
    st.caption(f'当前显示 {len(followups)} 位 / 共 {calculate_kpis(data)["valuable_connections"]} 位明确对接价值对象')
    st.caption('编辑状态、负责人、下一步动作和备注后，请点击保存修改。切换筛选、页面或刷新会丢弃未保存编辑。')
    if followups.empty:
        st.info('没有符合当前筛选条件的对象，请调整跟进状态、身份或负责人。')
    else:
        display = display_followups(followups, demo_aliases=not is_upload).reset_index(drop=True)
        signature = repr((revision, status, role, owner, st.session_state.get('editor_generation', 0)))
        editor_key = 'followup_editor_' + hashlib.sha256(signature.encode()).hexdigest()[:20]
        st.session_state['active_editor_key'] = editor_key
        with st.form('followup_form'):
            edited = st.data_editor(
                display, key=editor_key, hide_index=True, width='stretch', height=440,
                num_rows='fixed', disabled=['报名编号','姓名','身份','公司 / 项目','方向','对接意向'],
                column_config={
                    '报名编号':st.column_config.TextColumn(width='small', pinned=True),
                    '姓名':st.column_config.TextColumn(width='small', pinned=True),
                    '当前跟进状态':st.column_config.SelectboxColumn(options=([''] if is_upload else []) + list(EDITABLE_STATUSES), required=not is_upload, width='medium'),
                    '跟进负责人': (st.column_config.TextColumn(width='small') if is_upload else
                                  st.column_config.SelectboxColumn(options=['', *[OWNER_DISPLAY_NAMES.get(o,o) for o in OWNERS]], width='small')),
                    '下一步动作':st.column_config.TextColumn(width='medium', required=not is_upload),
                    '备注':st.column_config.TextColumn(width='large'),
                },
            )
            save = st.form_submit_button('保存修改', key='save_changes', type='primary')
        if save:
            candidate = edited.rename(columns={label:key for key,label in TABLE_LABELS.items()}).copy()
            if not is_upload:
                candidate['followup_owner'] = candidate['followup_owner'].replace({v:k for k,v in OWNER_DISPLAY_NAMES.items()})
            try:
                store.save_edits(data, candidate, revision)
                st.session_state['editor_generation'] = st.session_state.get('editor_generation', 0) + 1
                st.session_state['feedback'] = '跟进信息已保存'
                st.rerun()
            except DataValidationError as error:
                st.error(str(error))
    st.caption('需要跟进时须填写负责人及具体动作；已完成对接或暂不跟进时，请清空负责人，并将动作填为「暂无」。')
    st.divider()
    st.caption('导出全部明确对接价值对象的最新已保存数据，不受当前筛选影响。未保存编辑不进入导出。')
    try:
        st.download_button('导出最新跟进表', data=store.export_csv(), file_name='创业者交流_最新跟进表.csv',
                           mime='text/csv', key='export_followups')
    except DataValidationError as error:
        st.error(str(error))
    if not is_upload:
        restore_controls(store)

elif page == '活动复盘':
    render_review_page(
        data, revision, store.current_path() if is_upload else
        '当前会话数据（原始 Synthetic Demo CSV）' if is_demo else store.current_path(),
        review_store=(SessionReviewStore(upload_workspace) if is_upload else
                      SessionReviewStore(st.session_state) if is_demo else None), is_demo=is_demo or is_upload,
    )
