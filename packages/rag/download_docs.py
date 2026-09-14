from pathlib import Path
from urllib.parse import urljoin, urlparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup

from packages.rag.config import get_library, raw_dir


USER_AGENT = (
    "GeoAgent-RAG-Documentation-Collector/0.1 "
    "(research project; official documentation only)"
)


def fetch(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()

    return response.text


def extract_links(
    html: str,
    current_url: str,
    base_url: str,
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    base_domain = urlparse(base_url).netloc

    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(
            current_url,
            anchor["href"],
        )

        parsed = urlparse(absolute)

        # Only HTTP(S).
        if parsed.scheme not in {"http", "https"}:
            continue

        # Official documentation domain only.
        if parsed.netloc != base_domain:
            continue

        # Stay inside this documentation base URL.
        if not absolute.startswith(base_url):
            continue

        # Remove fragments and query parameters.
        clean_url = absolute.split("#")[0].split("?")[0]

        # Keep documentation pages only.
        if clean_url.endswith((".html", "/")):
            links.add(clean_url)

    return sorted(links)


def url_to_output_path(
    url: str,
    base_url: str,
    output_dir: Path,
) -> Path:
    """
    Convert a documentation URL into a collision-free local path.
    """

    parsed_url = urlparse(url)
    parsed_base = urlparse(base_url)

    base_path = parsed_base.path

    relative = parsed_url.path.removeprefix(base_path)

    if not relative or relative.endswith("/"):
        relative = relative + "index.html"

    elif not relative.endswith(".html"):
        relative = relative + ".html"

    return output_dir / relative


def save_raw(
    url: str,
    html: str,
    base_url: str,
    output_dir: Path,
) -> Path:
    output = url_to_output_path(
        url,
        base_url,
        output_dir,
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        html,
        encoding="utf-8",
    )

    return output


def crawl(
    base_url: str,
    output_dir: Path,
):
    visited = set()
    queue = [base_url]

    while queue:
        url = queue.pop(0)

        if url in visited:
            continue

        visited.add(url)

        print(f"Fetching: {url}")

        try:
            html = fetch(url)

        except requests.RequestException as e:
            print(f"ERROR: {e}")
            continue

        output = save_raw(
            url,
            html,
            base_url,
            output_dir,
        )

        print(f"Saved: {output}")

        links = extract_links(
            html,
            url,
            base_url,
        )

        for link in links:
            if link not in visited:
                queue.append(link)

        print(
            f"Discovered: {len(links)} links | "
            f"Queue: {len(queue)} | "
            f"Visited: {len(visited)}"
        )

    print()
    print("Crawl complete.")
    print("Pages collected:", len(visited))


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python packages/rag/download_docs.py <library>"
        )
        raise SystemExit(1)

    library_name = sys.argv[1]

    library = get_library(library_name)

    output_dir = raw_dir(library.name)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Library: {library.name}")
    print(f"Version: {library.version}")
    print(f"Base URL: {library.base_url}")
    print(f"Output: {output_dir}")
    print()

    crawl(
        library.base_url,
        output_dir,
    )


if __name__ == "__main__":
    main()