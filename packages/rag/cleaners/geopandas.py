from packages.rag.cleaners._sphinx_common import clean_sphinx_html


# GeoPandas docs use the PyData Sphinx theme.
CONTENT_SELECTORS = [
    "div.bd-article",
    "main",
]


def clean_html(html: str) -> str:
    """Clean a GeoPandas documentation page (PyData Sphinx theme)."""

    return clean_sphinx_html(html, CONTENT_SELECTORS)
