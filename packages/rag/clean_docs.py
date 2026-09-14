from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.rag.config import get_library, raw_dir, cleaned_dir
from packages.rag.cleaners import geopandas, shapely, rasterio, pyproj, gdal


CLEANERS = {
    "geopandas": geopandas.clean_html,
    "shapely": shapely.clean_html,
    "rasterio": rasterio.clean_html,
    "pyproj": pyproj.clean_html,
    "gdal": gdal.clean_html,
}


def get_cleaner(library: str):
    """Return the library-specific HTML cleaner."""

    try:
        return CLEANERS[library]
    except KeyError:
        available = ", ".join(sorted(CLEANERS))
        raise ValueError(
            f"No cleaner implemented for library '{library}'. "
            f"Available: {available}"
        )


def clean_file(
    source: Path,
    raw_root: Path,
    clean_root: Path,
    cleaner,
) -> Path:
    """Clean one HTML file and write the corresponding Markdown file."""

    html = source.read_text(
        encoding="utf-8"
    )

    markdown = cleaner(html)

    relative = source.relative_to(raw_root)

    output = clean_root / relative.with_suffix(".md")

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        markdown,
        encoding="utf-8",
    )

    return output


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python packages/rag/clean_docs.py <library>"
        )
        raise SystemExit(1)

    library_name = sys.argv[1]

    library = get_library(library_name)

    raw_root = raw_dir(library.name)
    clean_root = cleaned_dir(library.name)

    cleaner = get_cleaner(library.name)

    sources = sorted(
        raw_root.rglob("*.html")
    )

    print(f"Library: {library.name}")
    print(f"Raw pages: {len(sources)}")

    cleaned = 0
    empty = 0

    for source in sources:
        output = clean_file(
            source,
            raw_root,
            clean_root,
            cleaner,
        )

        content = output.read_text(
            encoding="utf-8"
        ).strip()

        if content:
            cleaned += 1
            print(f"Cleaned: {source}")
        else:
            empty += 1
            print(f"EMPTY:   {source}")

    print()
    print("==============================")
    print("Cleaning complete")
    print("==============================")
    print(f"Raw pages:     {len(sources)}")
    print(f"Cleaned pages: {cleaned}")
    print(f"Empty pages:   {empty}")


if __name__ == "__main__":
    main()