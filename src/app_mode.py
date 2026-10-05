"""Deployment mode selection; reject typos rather than silently sharing files."""
import os

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.data_loader import DataValidationError


def get_app_mode() -> str:
    configured = os.environ.get('APP_MODE')
    if configured is None:
        try:
            configured = st.secrets.get('APP_MODE', 'local')
        except StreamlitSecretNotFoundError:
            configured = 'local'
    mode = str(configured).strip().lower()
    if mode not in ('local', 'demo'):
        raise DataValidationError('APP_MODE 配置无效，请设置为 local 或 demo。公网演示须使用 demo。')
    return mode
