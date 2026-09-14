from pathlib import Path
import re
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.rag.config import cleaned_dir, chunks_dir


MAX_CHARS = 6000


def normalize_text(text: str) -> str:
    """Normalize whitespace without destroying Markdown structure."""

    text = text.replace("\xa0", " ")

    # Remove excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove trailing whitespace.
    text = "\n".join(
        line.rstrip()
        for line in text.splitlines()
    )

    return text.strip()


def split_large_section(
    text: str,
    max_chars: int = MAX_CHARS,
):
    """
    Split a large section into smaller pieces while trying to preserve
    paragraph/code-block boundaries.
    """

    if len(text) <= max_chars:
        return [text]

    blocks = re.split(
        r"\n\s*\n",
        text,
    )

    chunks = []
    current = []
    current_length = 0

    for block in blocks:
        block = block.strip()

        if not block:
            continue

        block_length = len(block)

        if (
            current
            and current_length + block_length + 2 > max_chars
        ):
            chunks.append(
                "\n\n".join(current)
            )

            current = []
            current_length = 0

        current.append(block)
        current_length += block_length + 2

    if current:
        chunks.append(
            "\n\n".join(current)
        )

    return chunks


def extract_title(
    text: str,
    fallback: str,
) -> str:
    """Extract the first Markdown heading as the document title."""

    match = re.search(
        r"^#\s+(.+)$",
        text,
        re.MULTILINE,
    )

    if match:
        return match.group(1).strip()

    return fallback


def chunk_markdown(
    text: str,
    source: Path,
):
    """
    Convert one cleaned Markdown document into semantic chunks.
    """

    text = normalize_text(text)

    if not text:
        return []

    title = extract_title(
        text,
        source.stem,
    )

    sections = re.split(
        r"(?=^#{1,2}\s+)",
        text,
        flags=re.MULTILINE,
    )

    sections = [
        section.strip()
        for section in sections
        if section.strip()
    ]

    chunks = []

    for index, section in enumerate(sections):
        parts = split_large_section(section)

        for part_index, part in enumerate(parts):

            chunk = {
                "id": (
                    f"{source.stem}-"
                    f"{index}-"
                    f"{part_index}"
                ),
                "source": str(source),
                "title": title,
                "text": part,
            }

            chunks.append(chunk)

    return chunks


def process_file(
    source: Path,
    clean_dir: Path,
    chunk_dir: Path,
):
    """Chunk one Markdown document and write JSON output."""

    text = source.read_text(
        encoding="utf-8"
    )

    chunks = chunk_markdown(
        text,
        source,
    )

    relative = source.relative_to(
        clean_dir
    )

    output = (
        chunk_dir
        / relative.with_suffix(".json")
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            chunks,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return output, chunks


def main():

    if len(sys.argv) != 2:
        print(
            "Usage: "
            "python packages/rag/chunk_docs.py "
            "<library>"
        )
        sys.exit(1)

    library = sys.argv[1]

    clean_dir = cleaned_dir(library)
    chunk_dir = chunks_dir(library)

    if not clean_dir.exists():
        raise RuntimeError(
            f"Cleaned documentation directory "
            f"does not exist: {clean_dir}"
        )

    sources = sorted(
        clean_dir.rglob("*.md")
    )

    print(
        f"Library: {library}"
    )
    print(
        f"Clean Markdown files: {len(sources)}"
    )

    total_chunks = 0

    for source in sources:

        output, chunks = process_file(
            source,
            clean_dir,
            chunk_dir,
        )

        total_chunks += len(chunks)

        print(
            f"Chunked: {source} "
            f"-> {len(chunks)} chunks"
        )

    print()
    print(
        "Total chunks:",
        total_chunks,
    )


if __name__ == "__main__":
    main()