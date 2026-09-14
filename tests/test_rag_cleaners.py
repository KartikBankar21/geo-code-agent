from packages.rag.cleaners._sphinx_common import clean_sphinx_html
from packages.rag.cleaners import geopandas, shapely, rasterio, pyproj, gdal


PYDATA_PAGE = """
<html><body>
<nav>sidebar nav - should be stripped</nav>
<div class="bd-article">
<h1>GeoDataFrame.buffer</h1>
<p>Return a GeoSeries of geometries representing the buffer.</p>
<dl class="py method">
  <dt class="sig sig-object py" id="geopandas.GeoDataFrame.buffer">
    <span class="sig-name">buffer</span>
    <span class="sig-paren">(</span>distance<span class="sig-paren">)</span>
    <a class="headerlink" href="#x">#</a>
  </dt>
  <dd>
    <dl class="field-list">
      <dt class="field-odd">Parameters</dt>
      <dd class="field-odd">
        <p><strong>distance</strong> <span class="classifier">float</span></p>
      </dd>
    </dl>
    <div class="highlight"><pre>&gt;&gt;&gt; gdf.buffer(500)
0    POLYGON (...)
</pre></div>
  </dd>
</dl>
</div>
<footer>footer - should be stripped</footer>
</body></html>
"""

FURO_PAGE = """
<html><body>
<header class="mobile-header">should be stripped</header>
<article role="main" id="furo-main-content">
<h1>shapely.buffer</h1>
<p>Computes the buffer of a geometry.</p>
<dl class="py function">
  <dt class="sig sig-object py" id="shapely.buffer">
    <span class="sig-name">buffer</span>
    <span class="sig-paren">(</span>geometry, distance<span class="sig-paren">)</span>
  </dt>
  <dd><p>Returns a buffered geometry.</p></dd>
</dl>
</article>
</body></html>
"""

RTD_CLASSIC_PAGE = """
<html><body>
<div class="document">
  <div class="documentwrapper">
    <div class="body" role="main">
      <h1>rasterio.open</h1>
      <p>Open a raster dataset for reading or writing.</p>
      <dl class="py function">
        <dt class="sig sig-object py" id="rasterio.open">
          <span class="sig-name">open</span>
          <span class="sig-paren">(</span>fp, mode<span class="sig-paren">)</span>
        </dt>
        <dd><p>Returns a dataset object.</p></dd>
      </dl>
    </div>
  </div>
</div>
</body></html>
"""


def test_pydata_theme_extracts_heading_and_paragraph():
    markdown = clean_sphinx_html(PYDATA_PAGE, ["div.bd-article", "main"])

    assert "# GeoDataFrame.buffer" in markdown
    assert "buffer of a geometry" not in markdown  # sanity: not cross-contaminated
    assert "Return a GeoSeries" in markdown


def test_pydata_theme_extracts_signature_and_code_block():
    markdown = clean_sphinx_html(PYDATA_PAGE, ["div.bd-article", "main"])

    assert "buffer(distance)" in markdown
    assert "```python" in markdown
    assert "gdf.buffer(500)" in markdown
    # >>> prompt markers should be stripped from the code block.
    assert ">>> " not in markdown


def test_pydata_theme_strips_nav_and_footer():
    markdown = clean_sphinx_html(PYDATA_PAGE, ["div.bd-article", "main"])

    assert "sidebar nav" not in markdown
    assert "footer -" not in markdown


def test_furo_theme_content_selector_finds_article_role_main():
    markdown = clean_sphinx_html(FURO_PAGE, shapely.CONTENT_SELECTORS)

    assert "# shapely.buffer" in markdown
    assert "buffer(geometry, distance)" in markdown
    assert "mobile-header" not in markdown
    assert "should be stripped" not in markdown


def test_classic_rtd_theme_content_selector_finds_role_main():
    markdown = clean_sphinx_html(RTD_CLASSIC_PAGE, rasterio.CONTENT_SELECTORS)

    assert "# rasterio.open" in markdown
    assert "open(fp, mode)" in markdown


def test_missing_content_falls_back_to_empty_string():
    markdown = clean_sphinx_html("<html><body></body></html>", ["div.nonexistent"])

    # No real content extracted - clean_docs.py treats this as an
    # "EMPTY" page by checking `.strip()`, same as it always has.
    assert markdown.strip() == ""


def test_all_five_library_cleaners_are_callable():
    # Each per-library module just needs to expose clean_html() and not
    # blow up on a page that doesn't match its primary selector - the
    # shared engine's fallback chain should still produce *something*
    # (even if imperfect) rather than raising.
    for module in (geopandas, shapely, rasterio, pyproj, gdal):
        result = module.clean_html("<html><body><main><p>hi</p></main></body></html>")
        assert "hi" in result
