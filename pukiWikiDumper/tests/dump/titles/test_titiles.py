from pathlib import Path

import pytest

from pukiWikiDumper.dump.content.content import get_pages

PY_FILE_DIR = Path(__file__).parent

cmd_list_result = {
    '1': 27,
    '2': 4203,
    '3': 2653,
    '4': 1, # https://wikiwiki.jp/genshinwiki/?cmd=list
    '5': 4229, # https://pukiwiki.sourceforge.io/?cmd=list
}

@pytest.mark.parametrize("key, expected", cmd_list_result.items())
def test_get_titles(key, expected):
    with open(PY_FILE_DIR / f"cmd_list.{key}.html", "rb") as f:
        content = f.read()
    pages = get_pages(url="http://local/", debug_content=content)
    assert len(pages) == expected, f"Expected {expected} pages, got {len(pages)}"