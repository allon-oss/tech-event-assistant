"""A data source control and confirmation panel inside the existing four pages."""
import hashlib

import streamlit as st

from src.data_loader import DataValidationError
from src.upload_data import LABELS, parse_upload, template_csv
from src.upload_session import confirm_upload, switch_context


def render_data_source():
    """Return confirmed upload workspace, or None for the original Demo flow."""
    source = st.sidebar.radio('数据来源', ['使用演示数据', '上传自己的数据'],
                              key='data_source', width='stretch')
    st.sidebar.download_button('下载数据模板', template_csv(), file_name='活动数据模板.csv',
                               mime='text/csv', key='download_data_template', width='stretch')
    if source == '使用演示数据':
        switch_context(st.session_state, 'demo')
        return None

    st.sidebar.caption('仅当前会话可见，不写入项目文件。断开会话或重启后无法恢复，请下载保留。')
    with st.sidebar:
        file = st.file_uploader('上传 CSV / XLSX', type=['csv', 'xlsx'], key='event_upload', max_upload_size=5)
    with st.expander('上传要求与字段说明', expanded='_upload_workspace' not in st.session_state):
        st.caption('必填：姓名、身份、报名渠道、是否到场。支持英文或常见中文列名；'
                   '是否到场支持是/否、true/false、1/0、已签到/未签到。'
                   'XLSX 读取第一个工作表，最多 5 MB、10,000 条记录。')
        st.caption('模板只有表头；报名编号留空会自动生成，其余可选字段留空即可。身份与创业行业 / 关注方向可自行填写，例如品牌主理人、餐饮 / 食品、电商。未知列不参与分析。')
    if file is None:
        st.session_state.pop('_pending_upload', None)
    else:
        content = file.getvalue()
        digest = hashlib.sha256(file.name.encode('utf-8') + b'\x00' + content).hexdigest()
        if digest != st.session_state.get('_confirmed_upload_digest'):
            pending = st.session_state.get('_pending_upload')
            if not pending or pending['digest'] != digest:
                try:
                    pending = {'digest': digest, 'data': parse_upload(content, file.name)}
                except DataValidationError as error:
                    pending = {'digest': digest, 'error': str(error)}
                st.session_state['_pending_upload'] = pending
            if 'error' in pending:
                st.error(pending['error'])
            else:
                data = pending['data']
                st.subheader('上传数据预览 · 尚未应用')
                st.caption(f'校验通过，共 {len(data)} 条记录。以下显示前 20 条，已统一列名并补充缺失编号。')
                st.dataframe(data.head(20).rename(columns=LABELS), hide_index=True, width='stretch')
                if '_upload_workspace' in st.session_state:
                    st.warning('确认后将替换此前上传的数据、跟进修改和复盘草稿，请先下载需要保留的内容。')
                if st.button('确认使用这份数据', key='confirm_upload', type='primary'):
                    confirm_upload(st.session_state, data)
                    st.session_state['_confirmed_upload_digest'] = digest
                    st.session_state.pop('_pending_upload', None)
                    st.rerun()
    workspace = st.session_state.get('_upload_workspace')
    if workspace is None:
        st.info('请选择文件，完成校验和预览后点击「确认使用这份数据」，再开始分析。')
        st.stop()
    switch_context(st.session_state, 'upload')
    st.info(f'正在分析已确认的上传数据 · {len(workspace["data"])} 条记录 · 仅当前会话保存。')
    st.caption('未提供的信息保持空白，不推断意向或跟进状态；相关指标只统计明确填写的信息，0 不代表没有需求。'
               '方向图不统计未填写的方向。新文件在确认前不会替换当前分析数据。')
    return workspace
