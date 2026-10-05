"""Reserved LLM adapter; no SDK, credentials, configuration or network access."""


def generate_review(summary: dict, observations: dict) -> str:
    """Future providers consume calculated facts + human text and return Markdown.

    This placeholder always fails explicitly, so an unavailable provider cannot
    be mistaken for a generated draft. It performs no external calls.
    """
    raise NotImplementedError('LLM 复盘生成尚未配置、尚未启用；请使用 template 模板生成。')
