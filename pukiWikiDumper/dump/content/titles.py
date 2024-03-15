from typing import Optional
import urllib.parse as urlparse

from bs4 import BeautifulSoup
import requests

from pukiWikiDumper.exceptions import CmdListDisabled
from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.config import running_config

def get_pages(url: str, debug_content: Optional[bytes] = None, session: requests.Session=None, useOldMethod=None):
    """Get titles given a doku.php URL and an (optional) namespace

    :param `useOldMethod`: `bool|None`. `None` will auto-detect if ajax api is enabled"""


    pages = []
    params = {'cmd': 'list'}
    if debug_content:
        soup = BeautifulSoup(debug_content, running_config.html_parser)
    else:
        r = session.get(url, params=params)
        from_encoding = None
        if r.encoding.lower() == 'euc-jp' or r.apparent_encoding.lower() == 'euc-jp':
            from_encoding = 'euc_jisx0213'
        soup = BeautifulSoup(r.content, running_config.html_parser, from_encoding=from_encoding, exclude_encodings=['iso-8859-1'])
    body = soup.find('div', {'id': 'body'})
    body = soup.find('div', {'class': 'body'}) if body is None else body # https://www.wikihouse.com/pukiwiki/index.php?cmd=list
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

        full_url = urlparse.urljoin(r.url, a['href'])
        parsed = urlparse.urlparse(full_url)


        encodings = [soup.original_encoding] + ['euc-jp', 'euc_jisx0213', 'utf-8', 'shift_jis']
        url_encoding = None
        for encoding in encodings:
            try:
                title = urlparse.unquote(parsed.query.replace("+", " "), errors='strict', encoding=encoding)
                url_encoding = encoding
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        assert url_encoding, f'Failed to parse query string: {parsed.query}'
        page = {
            'title': title,
            'url_encoding': url_encoding,
        }
        pages.append(page)

    return pages
