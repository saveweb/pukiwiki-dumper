import json
import os
import threading
import time
from typing import Dict, List, Optional
import urllib.parse as urlparse

from bs4 import BeautifulSoup
import requests
from tqdm import tqdm

from pukiWikiDumper.dump.content.titles import get_pages
from pukiWikiDumper.utils.util import load_pages, smkdirs, uopen
from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.config import running_config



sub_thread_error = None


def get_attachs(base_url: str, ns: str = '', ns_encoding: str = 'utf-8', dumpDir: str = '', session: requests.Session=None) -> List[Dict[str, str]]:
    """ Return a list of media filenames of a wiki """

    if dumpDir and os.path.exists(dumpDir + '/dumpMeta/attachs.jsonl'):
        with uopen(dumpDir + '/dumpMeta/attachs.jsonl', 'r') as f:
            attaches = [json.loads(line) for line in f]
            return attaches

    attaches: List[Dict] = []

    params={'plugin': 'attach', 'pcmd': 'list'}
    if ns:
        params['refer'] = ns

    params_encoded = urlparse.urlencode(params, encoding=ns_encoding, errors='strict')
    url = base_url + '?' + params_encoded

    r = session.get(url, headers={'Referer': url})

    from_encoding = None
    if str(r.encoding).lower() == 'euc-jp' or str(r.apparent_encoding).lower() == 'euc-jp':
        from_encoding = 'euc_jisx0213'

    attach_list_soup = BeautifulSoup(r.content, running_config.html_parser,from_encoding=from_encoding, exclude_encodings=['iso-8859-1', 'windows-1252'])

    body = attach_list_soup.find('div', {'id': 'body'})
    body = attach_list_soup.find('div', {'class': 'body'}) if body is None else body
    body = attach_list_soup.body if body is None else body # https://texwiki.texjp.org/?plugin=attach&pcmd=list

    if body is None and 'Fatal error: Allowed memory size of' in r.text:
        # http://deco.gamedb.info/wiki/?plugin=attach&pcmd=list
        print('Fatal error: Allowed memory size of... (OOM), ns:', ns)
        if ns:
            # avoid infinite loop
            return []
        pages = load_pages(pagesFilePath=dumpDir + '/dumpMeta/pages.jsonl')
        if pages is None:
            pages = get_pages(url=base_url, session=session)
        for page in tqdm(pages):
            for attach in get_attachs(base_url=base_url, ns=page['title'], ns_encoding=page['url_encoding'], session=session):
                if attach not in attaches:
                    attaches.append(attach)
        print('Found %d files in all namespaces' % len(attaches))
        if dumpDir:
            save_attachs(dumpDir, attaches)
        return attaches
    
    assert body, f'Failed to find body in {r.url}'
    hrefs = body.find_all('a', href=True) # type: ignore
    for a in hrefs:
        if "pcmd=info" in a['href']:
            full_url: str = urlparse.urljoin(base_url, a['href'])
            parsed = urlparse.urlparse(full_url)

            encodings = [attach_list_soup.original_encoding] + ['euc-jp', 'euc_jisx0213', 'utf-8', 'shift_jis']
            query = None
            url_encoding: str = None
            for encoding in encodings:
                try:
                    query = urlparse.parse_qs(parsed.query, errors='strict', encoding=encoding)
                    url_encoding = encoding
                    break
                except UnicodeDecodeError:
                    pass
            assert query, f'Failed to parse query string: {parsed.query}'

            file = query['file'][0]
            refer = query['refer'][0]
            age = int(query['age'][0]) if 'age' in query else None
            attaches.append({
                'refer': refer,
                'file': file,
                'age': age,
                'url_encoding': url_encoding,
            })
        # https://wikiwiki.jp/genshinwiki/?cmd=attach&pcmd=list
        elif "pcmd=list" in a['href']:
            full_url: str = urlparse.urljoin(base_url, a['href'])
            parsed = urlparse.urlparse(full_url)

            encodings = [attach_list_soup.original_encoding] + ['euc-jp', 'euc_jisx0213', 'utf-8', 'shift_jis']
            query = None
            url_encoding: Optional[str] = None
            for encoding in encodings:
                try:
                    query = urlparse.parse_qs(parsed.query, errors='strict', encoding=encoding)
                    url_encoding = encoding
                    break
                except UnicodeDecodeError:
                    pass
            assert query, f'Failed to parse query string: {parsed.query}'

            ns = query['refer'][0]
            assert ns, f'Failed to parse refer: {parsed.query}'
            print(f'Looking for attachs in namespace {ns}')
            ns_saved = 0
            for attach in get_attachs(base_url, ns=ns, ns_encoding=url_encoding or 'utf-8', session=session):
                if attach not in attaches:
                    attaches.append(attach)
                    ns_saved += 1
                else:
                    # print(f'Found duplicate attach: {attach}')
                    pass
            print(f'Found {ns_saved} new attachs in namespace {ns}')
        else:
            continue
# <li><a href="./?plugin=attach&amp;pcmd=open&amp;file=sample1.png&amp;refer=BugTrack%2F100" title="2002/07/23 17:39:29 13.0KB">sample1.png</a> <span class="small">[<a href="./?plugin=attach&amp;pcmd=info&amp;file=sample1.png&amp;refer=BugTrack%2F100" title="添付ファイルの情報">詳細</a>]</span></li>
    print('Found %d files in namespace %s' % (len(attaches), ns or '(all)'))
    if dumpDir:
        save_attachs(dumpDir, attaches)

    return attaches


def save_attachs(dumpDir: str, attaches: List[Dict]):
    smkdirs(dumpDir + '/dumpMeta')
    with uopen(dumpDir + '/dumpMeta/attachs.jsonl', 'w') as f:
        for attach in attaches:
            f.write(json.dumps(attach, ensure_ascii=False)+'\n')


def dump_attachs(base_url: str = '', dumpDir: str = '', session=None, threads: int = 1, ignore_errors: bool = False):
    if not dumpDir:
        raise ValueError('dumpDir must be set')

    smkdirs(dumpDir + '/attach')

    attaches = get_attachs(base_url, dumpDir=dumpDir, session=session)
    def try_download(*args, **kwargs):
        try:
            download(*args, **kwargs)
        except Exception as e:
            if not ignore_errors:
                global sub_thread_error
                sub_thread_error = e
                raise e
            print(threading.current_thread().name, 'Error in sub thread: (', e, ') ignored')
    index_of_title = -1
    for attach in attaches:
        index_of_title += 1
        while threading.active_count() > threads:
            time.sleep(0.1)
        if sub_thread_error:
            raise sub_thread_error
        print('Media: (%d/%d): [[%s]] ...' % (index_of_title+1, len(attaches), attach))

        def download(attach: Dict[str, str], session: requests.Session):
            filename = attach['refer'].encode('utf-8').hex() + '_' + attach['file'].encode('utf-8').hex() + (f".{attach['age']}" if attach['age'] else "")
            filename = filename.upper()
            if len(filename) > 255: # filename too long
                subdir_A = filename[:255]
                subfilename_B = filename[255:]
                smkdirs(dumpDir, '/attach/' + subdir_A)
                file = dumpDir + '/attach/' + subdir_A + '/' + subfilename_B
            else:
                file = dumpDir + '/attach/' + filename
            local_size = -1
            if os.path.exists(file):
                local_size = os.path.getsize(file)
                print(threading.current_thread().name,
                              'File [[%s]] Exists' % attach)
                return
            # ?plugin=attach&pcmd=open&file=article.inc.php&refer=PukiWiki%2F1.4%2F%E8%87%AA%E4%BD%9C%E3%83%97%E3%83%A9%E3%82%B0%E3%82%A4%E3%83%B3
            params={
                'plugin': "attach",
                'pcmd': "open",
                'file': attach['file'],
                'refer': attach['refer'],
            }
            if attach['age']:
                params['age'] = attach['age']
            urlencoded = urlparse.urlencode(params, encoding=attach['url_encoding'], errors='strict')
            url = base_url + '?' + urlencoded

            # workround for wikiwiki.jp
            # https://wikiwiki.jp/genshinwiki/?plugin=attach&pcmd=open&file=浮流の対玉_5.png&refer=バッグ%2F聖遺物 ->
            # https://cdn.wikiwiki.jp/to/w/genshinwiki/バッグ/聖遺物/::attach/浮流の対玉_5.png
            if 'wikiwiki.jp' in base_url:
                url = ("https://cdn.wikiwiki.jp/to/w/" + 
                       base_url.replace("https://wikiwiki.jp/", "").rstrip('/') + '/' +
                       f"{attach['refer']}/::attach/{attach['file']}" +
                       (f"?age={attach['age']}" if attach['age'] else "")
                       )
                print(f"wikipedia.jp detected, using {url} instead of {base_url}?{urlencoded}")

            with session.get(url,
            stream=True, headers={'Referer': base_url}
            ) as r:
                if local_size == -1:  # file does not exist
                    to_download = True
                else:
                    remote_size = int(r.headers.get('Content-Length', -2))
                    if local_size == remote_size:  # file exists and is complete
                        print(threading.current_thread().name,
                              'File [[%s]] exists (%d bytes)' % (attach, local_size))
                        to_download = False
                    elif remote_size == -2:
                        print(threading.current_thread().name,
                          'File [[%s]] cannot get remote size ("Content-Length" missing), ' % attach +
                          'will re-download anyway')
                        to_download = True
                    else:
                        to_download = True  # file exists but is incomplete

                if to_download:
                    if 'wikiwiki.jp' in base_url:
                        r.raise_for_status()
                    else:
                        assert "content-disposition" in r.headers, r.url
                    with open(file, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                        print(threading.current_thread().name,
                              'File [[%s]] Done' % attach)
                # modify mtime based on Last-Modified header
                last_modified = r.headers.get('Last-Modified', None)
                if last_modified:
                    mtime = time.mktime(time.strptime(
                        last_modified, '%a, %d %b %Y %H:%M:%S %Z'))
                    atime = os.stat(file).st_atime
                    # atime is not modified
                    os.utime(file, times=(atime, mtime))
                    # print(atime, mtime)

            # time.sleep(1.5)

        t = threading.Thread(target=try_download, daemon=True,
                             args=(attach, session))
        t.start()

    while threading.active_count() > 1:
        time.sleep(2)
        print('Waiting for %d threads to finish' %
              (threading.active_count() - 1), end='\r')
