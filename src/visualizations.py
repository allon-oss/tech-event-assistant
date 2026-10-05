"""Three focused Plotly charts; all business aggregation lives in metrics.py."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BLUE = '#376983'
AMBER = '#B66B24'


def _style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template='plotly_white', height=height,
        margin=dict(l=10, r=15, t=25, b=20),
        font=dict(family='Microsoft YaHei, Arial, sans-serif', size=13, color='#233344'),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor='#EDF0F3', zeroline=False)
    return fig


def _count_chart(summary: pd.DataFrame, category: str) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=summary['count'].tolist(), y=summary[category].tolist(), orientation='h',
        marker_color=BLUE, text=summary['count'].tolist(), textposition='outside',
        cliponaxis=False, hovertemplate='%{y}<br>报名人数：%{x} 人<extra></extra>',
    ))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(autorange='reversed')
    fig.update_xaxes(title='报名人数（人）', rangemode='tozero', dtick=10)
    return _style(fig, 350)


def role_chart(summary: pd.DataFrame) -> go.Figure:
    return _count_chart(summary, 'role')


def field_chart(summary: pd.DataFrame) -> go.Figure:
    return _count_chart(summary, 'field')


def channel_chart(summary: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    channels = summary['registration_channel'].tolist()
    fig.add_trace(go.Bar(
        x=channels, y=summary['registered'].tolist(), name='报名人数（左轴）',
        marker_color=BLUE, text=summary['registered'].tolist(), textposition='outside',
        customdata=summary['attended'].tolist(),
        hovertemplate='%{x}<br>报名：%{y} 人<br>到场：%{customdata} 人<extra></extra>',
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=channels, y=summary['attendance_rate'].tolist(), name='到场率（右轴）',
        mode='lines+markers+text', marker=dict(size=9), line=dict(color=AMBER, width=2),
        text=[f'{rate:.1%}' for rate in summary['attendance_rate']], textposition='top center',
        hovertemplate='%{x}<br>到场率：%{y:.1%}<extra></extra>',
    ), secondary_y=True)
    fig.update_yaxes(title_text='报名人数（人）', rangemode='tozero', secondary_y=False)
    fig.update_yaxes(title_text='到场率', tickformat='.0%', range=[0, 1], dtick=.2,
                     showgrid=False, secondary_y=True)
    fig.update_layout(legend=dict(orientation='h', y=1.2, x=0), bargap=.48)
    return _style(fig, 380)
