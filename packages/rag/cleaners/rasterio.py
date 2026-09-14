from packages.rag.cleaners._sphinx_common import clean_sphinx_html


# Rasterio docs use the classic Read the Docs Sphinx theme
# (sphinx_rtd_theme), whose main content lives in
# <div role="main" class="...body...">.
CONTENT_SELECTORS = [
    "div[role='main']",
    "div.document",
    "main",
]


def clean_html(html: str) -> str:
    """Clean a Rasterio documentation page (classic Read the Docs theme)."""

    return clean_sphinx_html(html, CONTENT_SELECTORS)
