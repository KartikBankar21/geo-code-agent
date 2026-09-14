from packages.rag.cleaners._sphinx_common import clean_sphinx_html


# PyProj docs use the Furo Sphinx theme (see pyproj's pyproject.toml,
# which lists `furo` under its `docs` dependency group).
CONTENT_SELECTORS = [
    "article[role='main']",
    "div.content",
    "main",
]


def clean_html(html: str) -> str:
    """Clean a PyProj documentation page (Furo Sphinx theme)."""

    return clean_sphinx_html(html, CONTENT_SELECTORS)
