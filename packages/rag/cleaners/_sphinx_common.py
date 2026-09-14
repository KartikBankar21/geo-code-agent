import re

from bs4 import BeautifulSoup


def normalize_text(text: str) -> str:
    """Normalize documentation text while preserving technical identifiers."""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    text = re.sub(r"([(:])\s+", r"\1", text)

    return text.strip()


def extract_text(element) -> str:
    """Extract human-readable text while preserving inline identifiers."""

    text = element.get_text("", strip=False)

    return normalize_text(text)


def format_signature(text: str) -> str:
    """Normalize whitespace in a Sphinx API signature."""

    text = " ".join(text.split())

    text = text.replace(" ,", ",")
    text = text.replace("( ", "(")
    text = text.replace(" )", ")")
    text = text.replace(" = ", "=")

    text = re.sub(r",\s*", ", ", text)

    return text.strip()


def clean_code(code: str) -> str:
    """Clean Sphinx code while preserving Python formatting."""

    code = code.replace("\xa0", " ")

    lines = []

    for line in code.splitlines():
        stripped = line.lstrip()

        if stripped.startswith(">>> "):
            prefix_len = len(line) - len(stripped)
            line = line[:prefix_len] + stripped[4:]

        elif stripped.startswith("... "):
            prefix_len = len(line) - len(stripped)
            line = line[:prefix_len] + stripped[4:]

        lines.append(line.rstrip())

    return "\n".join(lines).strip()


def process_definition_content(element, lines):
    """Process the contents of a definition."""

    for child in element.children:
        if getattr(child, "name", None):
            process_element(child, lines)


def process_definition_list(dl, lines):
    """Process Sphinx definition lists (API signatures, parameter lists)."""

    for child in dl.children:
        if not getattr(child, "name", None):
            continue

        if child.name == "dt":
            classes = child.get("class", [])

            # API signature - this class pair ("sig sig-object") comes
            # from Sphinx's own Python domain (sphinx.domains.python),
            # not from the theme, so it's the same across PyData/Furo/
            # classic-RTD sites.
            if "sig" in classes and "sig-object" in classes:
                text = child.get_text("", strip=True)

                text = text.replace("[source]", "")
                text = text.replace("#", "").strip()

                text = format_signature(text)

                if text:
                    lines.append(f"**{text}**")
                    lines.append("")

                continue

            # Field heading (Parameters/Returns/Raises/...).
            if "field-odd" in classes or "field-even" in classes:
                text = child.get_text(" ", strip=True)

                if text:
                    text = text.replace(":", "").strip()

                    lines.append(f"**{text}:**")
                    lines.append("")

                continue

            # Parameter definition.
            name = child.find("strong", recursive=False)

            classifier = child.find(
                "span",
                class_="classifier",
                recursive=False,
            )

            if name:
                parameter_name = normalize_text(
                    name.get_text(" ", strip=True)
                )

                if classifier:
                    parameter_type = normalize_text(
                        classifier.get_text(" ", strip=True)
                    )

                    lines.append(
                        f"**{parameter_name}** — {parameter_type}"
                    )
                else:
                    lines.append(
                        f"**{parameter_name}**"
                    )

                lines.append("")

            else:
                text = child.get_text(" ", strip=True)

                if text:
                    lines.append(f"**{text}**")
                    lines.append("")

        elif child.name == "dd":
            process_definition_content(child, lines)


def process_element(element, lines):
    """Process one documentation element."""

    if element.name is None:
        return

    # Headings.
    if element.name in {
        "h1", "h2", "h3",
        "h4", "h5", "h6",
    }:
        text = extract_text(element)

        text = text.replace("#", "").strip()

        if text:
            level = int(element.name[1])

            lines.append(
                f"{'#' * level} {text}"
            )

            lines.append("")

        return

    # Paragraphs.
    if element.name == "p":
        classes = element.get("class", [])

        if "rubric" in classes:
            text = extract_text(element)

            if text:
                lines.append(f"## {text}")
                lines.append("")

            return

        text = extract_text(element)

        if text:
            lines.append(text)
            lines.append("")

        return

    # Definition lists.
    if element.name == "dl":
        process_definition_list(element, lines)
        return

    # Code blocks.
    if element.name == "div":
        classes = element.get("class", [])

        if "highlight" in classes:
            pre = element.find("pre")

            if pre:
                code = clean_code(
                    pre.get_text(
                        "",
                        strip=False,
                    )
                )

                if code:
                    lines.append("```python")
                    lines.append(code)
                    lines.append("```")
                    lines.append("")

            return

    # Containers.
    if element.name in {
        "section",
        "article",
        "main",
        "div",
    }:
        for child in element.children:
            if getattr(child, "name", None):
                process_element(child, lines)


def clean_sphinx_html(html: str, content_selectors: list[str]) -> str:
    """
    Convert one Sphinx-generated documentation page into Markdown.

    `content_selectors` is a list of CSS selectors tried in order to
    find the page's main content container - this is the only part of
    a Sphinx page that actually varies by theme (PyData uses
    `div.bd-article`, Furo uses `article[role='main']`, classic
    Read the Docs uses `div[role='main']`, etc). The first selector
    that matches is used; if none match, the function falls back to
    `<body>` and finally gives up (returning an empty string), which
    the caller (`clean_docs.py`) reports as an "EMPTY" page rather than
    failing silently.
    """

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-documentation elements.
    for element in soup(
        [
            "script",
            "style",
            "nav",
            "footer",
            "header",
        ]
    ):
        element.decompose()

    content = None

    for selector in content_selectors:
        content = soup.select_one(selector)

        if content is not None:
            break

    if content is None:
        content = soup.body

    if content is None:
        return ""

    lines = []

    for child in content.children:
        if getattr(child, "name", None):
            process_element(child, lines)

    return "\n".join(lines).strip() + "\n"
