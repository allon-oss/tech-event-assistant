"""Presentation helpers for the existing four-page Streamlit workspace."""
from html import escape
from pathlib import Path

import streamlit as st


def apply_theme():
    # Static, local CSS only. Uploaded values never become HTML or CSS.
    st.html(Path(__file__).with_name('theme.css'))


def render_brand():
    st.sidebar.html('''<div class="workspace-brand">
        <span class="brand-mark" aria-hidden="true">↗</span>
        <div><strong>活动工作台</strong><span>创业活动 · 观察与跟进</span></div>
    </div>''')


def render_workspace_header(page):
    st.html(f'''<div class="workspace-topline">
        <span>创业活动观察与跟进助手</span><span>{escape(page)}</span>
    </div>''')


def render_overview(kpis):
    st.html('''<section class="overview-hero" aria-label="活动总览介绍">
        <div class="hero-copy"><span class="eyebrow">每一场交流，都有下一步</span>
        <h1>看见创业者，<br>延续有价值的连接。</h1>
        <p>从活动观察到会后跟进，把一次见面变成持续的交流。</p></div>
        <div class="connection-art" aria-hidden="true">
            <span class="orbit orbit-one"></span><span class="orbit orbit-two"></span>
            <span class="person person-one"></span><span class="person person-two"></span>
            <span class="person person-three"></span><span class="art-spark">✳</span>
            <span class="art-caption">相遇 · 交流 · 再连接</span>
        </div>
    </section>''')
    st.subheader('活动总览')
    st.caption('基于当前完整报名与签到记录，了解这一场活动。')
    attendance, relationships = st.columns(2, gap='medium')
    with attendance, st.container(border=True, key='attendance_summary'):
        st.markdown('#### 报名与到场')
        registered, attended = st.columns(2)
        registered.metric('报名人数', str(kpis['registered']), help='全部有效报名记录。')
        attended.metric('到场人数', str(kpis['attended']), help='是否到场为「是」的人数。')
        st.metric('到场率', f"{kpis['attendance_rate']:.0%}", help='到场人数 ÷ 报名人数。')
        st.progress(float(kpis['attendance_rate']))
    with relationships, st.container(border=True, key='relationship_summary'):
        st.markdown('#### 关系与跟进')
        founders, valuable = st.columns(2)
        founders.metric('到场创业者人数', str(kpis['attended_founders']),
                        help='身份为创业者且实际到场的人数。')
        valuable.metric('明确对接价值人数', str(kpis['valuable_connections']),
                        help='已到场，且希望寻找投资、创业者、合作伙伴或招聘人才。含已完成对接。')
        with st.container(key='pending_summary'):
            st.metric('待跟进人数', str(kpis['pending_followups']),
                      help='有明确对接价值且状态为「待跟进」的人数。')
            st.caption('从明确下一步动作开始，让连接继续。')
    st.markdown('### 接下来，推进一步')
    cards = [
        ('01', '活动观察', '了解谁来了，来自哪里', '查看身份、行业与报名渠道，找到值得继续观察的信号。', 'go_observation'),
        ('02', '关系跟进', '让一次交流有后续', '筛选对接对象，记录负责人、跟进状态与下一步动作。', 'go_followup'),
        ('03', '活动复盘', '为下一场积累经验', '结合数据与人工观察，整理成一份可编辑的复盘草稿。', 'go_review'),
    ]
    for column, (number, page, title, description, key) in zip(st.columns(3, gap='medium'), cards):
        with column, st.container(border=True, key='card_' + key):
            st.html(f'<div class="step-label"><span>{number}</span>{page}</div>')
            st.markdown(f'#### {title}')
            st.caption(description)
            st.button(f'进入{page} →', key=key, width='stretch', on_click=_navigate, args=(page,))


def _navigate(page):
    # A callback runs before the next script pass, so the sidebar radio remains
    # the single page selector and existing session-owned editors survive.
    st.session_state['page'] = page
