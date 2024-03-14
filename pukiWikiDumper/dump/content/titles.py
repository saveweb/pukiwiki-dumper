from typing import Optional
from bs4 import BeautifulSoup
import requests
from pukiWikiDumper.exceptions import CmdListDisabled
from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.config import running_config

def get_titles(url: str, debug_content: Optional[bytes] = None, session: requests.Session=None, useOldMethod=None):
    """Get titles given a doku.php URL and an (optional) namespace

    :param `useOldMethod`: `bool|None`. `None` will auto-detect if ajax api is enabled"""


    titles = []
    params = {'cmd': 'list'}
    if debug_content:
        soup = BeautifulSoup(debug_content, running_config.html_parser)
    else:
        r = session.get(url, params=params)
        soup = BeautifulSoup(r.text, running_config.html_parser)
    body = soup.find('div', {'id': 'body'})
    if body is None:
        raise CmdListDisabled('Action index is disabled')
    ul = body.find('ul')
    if ul is None:
        raise CmdListDisabled('Action index is disabled')
    
    for li in ul.find_all('li'):
        a = li.find('a')
        if a is None:
            continue
        href = a.get('href')
        if href and href.startswith('#'):
            continue
        title = a.text
        titles.append(title)

    return titles
