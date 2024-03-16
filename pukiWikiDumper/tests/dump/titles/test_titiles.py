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
    'penguin.tantin.jp': 1,
}

@pytest.mark.parametrize("key, expected", cmd_list_result.items())
def test_get_titles(key, expected):
    with open(PY_FILE_DIR / f"cmdlist.{key}.html", "rb") as f:
        content = f.read()
    pages = get_pages(url=f'https://{key.replace("_", "/")}', debug_content=content)
    assert len(pages) == expected, f"Expected {expected} pages, got {len(pages)}"
    for page in pages:
        assert page['title'], f"Page title is empty: {page}"
    
    if not (PY_FILE_DIR / f"cmdlist.{key}.json").exists():
        with open(PY_FILE_DIR / f"cmdlist.{key}.json", "w") as f:
            json.dump(pages, f, indent=4, ensure_ascii=False)
    else:
        with open(PY_FILE_DIR / f"cmdlist.{key}.json", "r") as f:
            expected_pages = json.load(f)
        for page in pages:
            assert page in expected_pages, f"Page not found: {page}"

# for key, expected in cmd_list_result.items():
#     test_get_titles(key, expected)