from search_local.profiles import _dedupe_sources
from search_local.models import Source


def test_dedupe_sources_re_ranks():
    sources = [Source(engine="x", query="q", rank=7, url="https://a.test"), Source(engine="x", query="q", rank=8, url="https://a.test")]
    out = _dedupe_sources(sources)
    assert len(out) == 1
    assert out[0].rank == 1
