import urllib.parse as urlparse

import requests
from bs4 import BeautifulSoup

from pukiWikiDumper.exceptions import ActionEditDisabled, ActionEditTextareaNotFound
from pukiWikiDumper.utils.config import running_config


# args must be same as getSourceEdit(), even if not used
def get_source_diff(url, page, rev='', session: requests.Session = None,):
    """Export the raw source of a page (at a given revision)"""

    params={'cmd': 'diff', 'page': page['title']}
    query = urlparse.urlencode(params, encoding=page['url_encoding'], errors='strict')
    r = session.get(url + '?' + query)
    from_encoding = None
    if str(r.encoding).lower() == 'euc-jp' or str(r.apparent_encoding).lower() == 'euc-jp':
        from_encoding = 'euc_jisx0213'
    soup = BeautifulSoup(r.content, running_config.html_parser, from_encoding=from_encoding, exclude_encodings=['ISO-8859-1'])
    source = None

    pre = soup.find('pre')
    if pre is None:
        raise ActionEditTextareaNotFound(page['title'])
    for span in pre.find_all('span'):
        # remove diff-remove and keep diff-add spans
        if 'diff_removed' in span.get('class', []):
            span.decompose()
    source = pre.text.strip()

    return source

# args must be same as getSourceEdit(), even if not used
def get_source_source(url, page, rev='', session: requests.Session = None,):
    """Export the raw source of a page (at a given revision)"""

    params={'cmd': 'source', 'page': page['title']}
    query = urlparse.urlencode(params, encoding=page['url_encoding'], errors='strict')
    r = session.get(url + '?' + query)
    from_encoding = None
    if str(r.encoding).lower() == 'euc-jp' or str(r.apparent_encoding).lower() == 'euc-jp':
        from_encoding = 'euc_jisx0213'
    soup = BeautifulSoup(r.content, running_config.html_parser, from_encoding=from_encoding, exclude_encodings=['ISO-8859-1'])
    source = None

    # #source
    pre = soup.find('pre', {'id': 'source'})
    if pre is None:
        raise ActionEditTextareaNotFound(page['title'])

    source = pre.text.strip()

    return source

# args must be same as getSourceExport(), even if not used
def get_source_edit(url, page, rev='', session: requests.Session = None,):
    """Export the raw source of a page by scraping the edit box content. Yuck."""

    params={'cmd': 'edit', 'page': page['title']}
    query = urlparse.urlencode(params, encoding=page['url_encoding'], errors='strict')
    r = session.get(url + '?' + query)
    from_encoding = None
    if str(r.encoding).lower() == 'euc-jp' or str(r.apparent_encoding).lower() == 'euc-jp':
        from_encoding = 'euc_jisx0213'
    soup = BeautifulSoup(r.content, running_config.html_parser, from_encoding=from_encoding, exclude_encodings=['ISO-8859-1'])
    source = None
    try:
        source = ''.join(soup.find('textarea', {'name': 'msg'}).text).strip()
    except AttributeError as e:
        if 'Action disabled: source' in r.text:
            raise ActionEditDisabled(page['title'])
    
    if not source:
        raise ActionEditTextareaNotFound(page['title'])

    return source
