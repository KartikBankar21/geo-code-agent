from packages.rag.cleaners._sphinx_common import clean_sphinx_html


# Shapely docs use the Furo Sphinx theme, whose main content lives in
# <article role="main" id="furo-main-content">.
CONTENT_SELECTORS = [
    "article[role='main']",
    "div.content",
    "main",
]


def clean_html(html: str) -> str:
    """Clean a Shapely documentation page (Furo Sphinx theme)."""

    return clean_sphinx_html(html, CONTENT_SELECTORS)
