import json
from pathlib import Path

import pytest

from pukiWikiDumper.dump.content.content import get_pages

PY_FILE_DIR = Path(__file__).parent

cmd_list_result = {
    'pukiwiki.localhost': 27,
    'pukiwiki.sourceforge.io_dev': 2653,
    'wikiwiki.jp_genshinwiki': 1764, # https://wikiwiki.jp/genshinwiki/?cmd=list
    'pukiwiki.sourceforge.io': 4229, # https://pukiwiki.sourceforge.io/?cmd=list
    'penguin.tantin.jp_mori': 5850, # http://penguin.tantin.jp/mori/?cmd=list
    'nekokabu.s7.xrea.com_wiki': (328, "64花札 天使の約束"), # http://nekokabu.s7.xrea.com/wiki/?cmd=list
}

@pytest.mark.parametrize("key, expected", cmd_list_result.items())
def test_get_titles(key, expected):
    expected, a_title = expected if isinstance(expected, tuple) else (expected, "")
    with open(PY_FILE_DIR / f"cmdlist.{key}.html", "rb") as f:
        content = f.read()
    pages = get_pages(url=f'https://{key.replace("_", "/")}/', debug_content=content)
    assert len(pages) == expected, f"Expected {expected} pages, got {len(pages)}"
    for page in pages:
        assert page['title'], f"Page title is empty: {page}"

    if a_title:
        assert any(a_title in page['title'] for page in pages), f"Expected title {a_title} not found"
    
    if not (PY_FILE_DIR / f"cmdlist.{key}.json").exists():
        with open(PY_FILE_DIR / f"cmdlist.{key}.json", "w") as f:
            json.dump(pages, f, indent=4, ensure_ascii=False)
    else:
        with open(PY_FILE_DIR / f"cmdlist.{key}.json", "r") as f:
            expected_pages = json.load(f)
        for page in pages:
            assert page in expected_pages, f"Page not found: {page}"

# test_get_titles("nekokabu.s7.xrea.com_wiki", 328)