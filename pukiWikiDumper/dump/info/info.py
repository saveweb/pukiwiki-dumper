import json
import os
import re
import base64
from typing import Optional, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag
import requests

from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.util import uopen
from pukiWikiDumper.utils.config import running_config


INFO_FILEPATH = 'dumpMeta/info.json'
HOMEPAGE_FILEPATH = 'dumpMeta/index.html'
CHECKPAGE_FILEPATH = 'dumpMeta/check.html'
LOGO_FILEPATH = 'dumpMeta/logo.ico'

# info.json keys
INFO_WIKI_NAME = "wiki_name"
INFO_RAW_TITLE = "raw_title"
INFO_PUKI_URL = "puki_url"
INFO_LANG = "language"
INFO_ICON_URL = "icon_url"

def get_info(dumpDir: str) -> dict:
    if os.path.exists(os.path.join(dumpDir, INFO_FILEPATH)):
        with uopen(os.path.join(dumpDir, INFO_FILEPATH), 'r') as f:
            _info = json.load(f)
            return _info

    return {}


def update_info_json(dumpDir: str, info: dict):
    '''Only updates given keys in info.'''
    _info = get_info(dumpDir)
    info = {**_info, **info}

    with uopen(os.path.join(dumpDir, INFO_FILEPATH), 'w') as f:
        json.dump(info, f, indent=4, ensure_ascii=False)


def get_html_lang(html: Union[bytes, str]) -> Optional[str]:
    '''Returns the language of the html document.'''

    soup = BeautifulSoup(html, running_config.html_parser)
    # <html lang="en" dir="ltr" class="no-js">
    html_tag = soup.html
    
    lang = None
    if html_tag:
        lang = html_tag.get('lang')
    
    if isinstance(lang, list):
        lang = lang[0]

    return lang


def get_wiki_name(html: Union[bytes, str]):
    '''Returns the name of the wiki.

    Tuple: (wiki_name: Optional[str], raw_title: Optional[str])'''

    soup = BeautifulSoup(html, running_config.html_parser)
    try:
        raw_title = soup.title.text
    except:
        print(    '[red]Error: Could not find HTML title[/red]', end='')
        if isinstance(html, str) and 'Warning' in html:
            print(' [red]and the HTML contains PHP warning.[/red]')
            print('       Re-run with --trim-php-warnings or change the --parser may help.')
        else:
            print('.')
        raise
    # # [FrontPage - {wikiname}
    wiki_name = re.search(r' - (.+?)$', raw_title)
    if wiki_name is not None:
        wiki_name = wiki_name.group(1)
    else:
        print('Warning: Could not find wiki name in HTML title.')
    
    if not isinstance(wiki_name, (str, type(None))):
        wiki_name = None

    if isinstance(wiki_name, str):
        wiki_name = wiki_name.replace('\n', ' ').replace('\r', '').strip()

    return wiki_name, raw_title


def get_raw_icon_href(html: Union[bytes ,str]):
    '''Returns the icon url.'''

    soup = BeautifulSoup(html, running_config.html_parser)
    # <img id="logo" src="image/pukiwiki.png" width="80" height="80" alt="[PukiWiki]" title="[PukiWiki]" />
    icon_tag = soup.find('img', {'id': 'logo'})
    icon_url = None
    if icon_tag:
        icon_url = icon_tag.get('src')
        icon_url = icon_url.strip()
    else:
        print('Warning: Could not find icon in HTML.')

    return icon_url


def save_icon(dumpDir: str, url_or_dataUrl: str, session: requests.Session):
    if url_or_dataUrl is None:
        return False
    if url_or_dataUrl.startswith('data:image'):
        assert 'base64,' in url_or_dataUrl, 'Icon is not base64 encoded.'
        print('Saving icon from data url. (base64 encoded)')
        data_base64 = url_or_dataUrl.split('base64,')[1]
        data = base64.urlsafe_b64decode(data_base64)
        with open(os.path.join(dumpDir, LOGO_FILEPATH), 'wb') as f:
            f.write(data)
        return True

    r = session.get(url_or_dataUrl)
    subfix = ""
    if 'image' in r.headers.get('content-type', ''):
        subfix = r.headers['content-type'].split('/')[1]
    if 'image' not in r.headers.get('content-type', ''):
        print('Warning: Icon is not an image.')
        return False
    with open(os.path.join(dumpDir, LOGO_FILEPATH.replace(".ico", f'.{subfix}')), 'wb') as f:
        f.write(r.content)
        return True



def update_info(dumpDir: str, puki_url: str, session: requests.Session):
    '''Saves the info of the wiki.'''
    homepage_html = session.get(puki_url).text
    with uopen(os.path.join(dumpDir, HOMEPAGE_FILEPATH), 'w') as f:
        f.write(homepage_html)
        print('Saved homepage to', HOMEPAGE_FILEPATH)

    wiki_name, raw_title = get_wiki_name(homepage_html)
    lang = get_html_lang(homepage_html)
    icon_href = get_raw_icon_href(homepage_html)
    icon_url = None
    if icon_href is not None and icon_href.startswith('data:image'):
        # base64 encoded data url
        icon_url = icon_href
    elif icon_href is not None:
        # normal url
        icon_url = urljoin(puki_url, icon_href)

    save_icon(dumpDir=dumpDir, url_or_dataUrl=icon_url, session=session)

    info = {
        INFO_WIKI_NAME: wiki_name,
        INFO_RAW_TITLE: raw_title,
        INFO_PUKI_URL: puki_url,
        INFO_LANG: lang,
        INFO_ICON_URL: icon_url,
    }
    print('Info:', info)
    update_info_json(dumpDir, info)
