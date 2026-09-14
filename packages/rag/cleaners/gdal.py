from packages.rag.cleaners._sphinx_common import clean_sphinx_html


# GDAL's docs appear to use a Read the Docs-style Sphinx theme, but this
# wasn't verified against real HTML (gdal.org isn't reachable from this
# environment). The selector list below is intentionally broad, covering
# classic RTD, Furo, and PyData conventions. After running
# `clean_docs.py gdal`, check its printed "EMPTY" count - if it's high,
# inspect one raw page in rag/raw/gdal/ and add the right selector here.
CONTENT_SELECTORS = [
    "div[role='main']",
    "article[role='main']",
    "div.document",
    "div.bd-article",
    "main",
]


def clean_html(html: str) -> str:
    """Clean a GDAL documentation page."""

    return clean_sphinx_html(html, CONTENT_SELECTORS)
