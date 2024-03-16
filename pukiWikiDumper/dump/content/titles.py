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
        r = None
    else:
        r = session.get(url, params=params)
        from_encoding = None
        if str(r.encoding).lower() == 'euc-jp' or str(r.apparent_encoding).lower() == 'euc-jp':
            from_encoding = 'euc_jisx0213'
        soup = BeautifulSoup(r.content, running_config.html_parser, from_encoding=from_encoding, exclude_encodings=['iso-8859-1'])
    body = soup.find('div', {'id': 'body'})
    body = soup.find('div', {'class': 'body'}) if body is None else body # https://www.wikihouse.com/pukiwiki/index.php?cmd=list
    body = soup.find('div', {'class': 'content'}) if body is None else body # http://penguin.tantin.jp/mori/?cmd=list
    body = soup.body if body is None else body # https://texwiki.texjp.org/?cmd=list
    if body is None:
        raise CmdListDisabled('Action index is disabled')
    if body.find('div', {'id': 'content'}) is not None:
        body = body.find('div', {'id': 'content'})
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

        full_url = urlparse.urljoin(r.url if r else url, a['href'])
        parsed = urlparse.urlparse(full_url)
        if not parsed.query: # workround for https://wikiwiki.jp/ wikis
            wikipath = urlparse.urlparse(r.url if r else url).path
            page_fullpath = urlparse.urlparse(full_url).path
            pagepath = page_fullpath.replace(wikipath, '')

            if "?" not in full_url and pagepath.endswith('.html'): # workround for http://penguin.tantin.jp/mori/?cmd=list
                pagepath = pagepath[:-5]

        encodings = [soup.original_encoding] + ['euc-jp', 'euc_jisx0213', 'utf-8', 'shift_jis']
        url_encoding = None
        title_to_parse = parsed.query if parsed.query else pagepath
        for encoding in encodings:
            try:
                parsed_title = urlparse.unquote(title_to_parse.replace("+", " "), errors='strict', encoding=encoding)
                url_encoding = encoding
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        assert url_encoding, f'Failed to parse query string: {title_to_parse}'
        page = {
            'title': parsed_title if parsed_title else title,
            'url_encoding': url_encoding,
        }
        pages.append(page)

    return pages
