from pathlib import Path

from pukiWikiDumper.dump.content.content import get_titles

PY_FILE_DIR = Path(__file__).parent

cmd_list_result = {
    '1': 27,
    '2': 4203,
    '3': 2653,
}

def test_get_titles():
    for i in cmd_list_result.keys():
        with open(PY_FILE_DIR / f"cmd_list.{i}.html", "rb") as f:
            content = f.read()
        titles = get_titles(url="debug", debug_content=content)
        # print(titles)
        assert len(titles) == cmd_list_result[i]
