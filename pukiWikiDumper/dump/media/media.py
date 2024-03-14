import json
import os
import re
import threading
import time
from typing import Dict, List
import urllib.parse as urlparse

from bs4 import BeautifulSoup
import requests

from pukiWikiDumper.utils.util import smkdirs, uopen
from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.config import running_config



sub_thread_error = None


def get_attachs(url, ns: str = '',  dumpDir: str = '', session: requests.Session=None) -> List[Dict[str, str]]:
    """ Return a list of media filenames of a wiki """

    if dumpDir and os.path.exists(dumpDir + '/dumpMeta/attachs.jsonl'):
        with uopen(dumpDir + '/dumpMeta/attachs.jsonl', 'r') as f:
            attaches = [json.loads(line) for line in f]
            return attaches
    attaches: List[Dict[str, str]] = []

    attach_list_soup = BeautifulSoup(
        session.post(url, {
            'plugin': 'attach',
            'pcmd': 'list'
        }).text, running_config.html_parser)
    body = attach_list_soup.find('div', {'id': 'body'})
    hrefs = body.find_all('a', href=True)
    for a in hrefs:
        if "pcmd=open" in a['href']:
            full_url = urlparse.urljoin(url, a['href'])
            parsed = urlparse.urlparse(full_url)
            query = urlparse.parse_qs(parsed.query)

            file = query['file'][0]
            refer = query['refer'][0]
            age = int(query['age'][0]) if 'age' in query else None
            attaches.append({
                'refer': refer,
                'file': file,
                'age': age
            })
# <li><a href="./?plugin=attach&amp;pcmd=open&amp;file=sample1.png&amp;refer=BugTrack%2F100" title="2002/07/23 17:39:29 13.0KB">sample1.png</a> <span class="small">[<a href="./?plugin=attach&amp;pcmd=info&amp;file=sample1.png&amp;refer=BugTrack%2F100" title="添付ファイルの情報">詳細</a>]</span></li>
    print('Found %d files in namespace %s' % (len(attaches), ns or '(all)'))

    if dumpDir:
        smkdirs(dumpDir + '/dumpMeta')
        with uopen(dumpDir + '/dumpMeta/attachs.jsonl', 'w') as f:
            for attach in attaches:
                f.write(json.dumps(attach, ensure_ascii=False)+'\n')
    return attaches


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
            filename = attach['refer'].encode('utf-8').hex() + '_' + attach['file'].encode('utf-8').hex()
            filename = filename.upper()
            file = dumpDir + '/attach/' + filename
            local_size = -1
            if os.path.exists(file):
                local_size = os.path.getsize(file)
                print(threading.current_thread().name,
                              'File [[%s]] Exists' % attach)
                return
            # ?plugin=attach&pcmd=open&file=article.inc.php&refer=PukiWiki%2F1.4%2F%E8%87%AA%E4%BD%9C%E3%83%97%E3%83%A9%E3%82%B0%E3%82%A4%E3%83%B3
            with session.get(base_url, params={
                'plugin': "attach",
                'pcmd': "open",
                'file': attach['file'],
                'refer': attach['refer'],
                'age': attach['age'] if 'age' in attach else 0
                },
            stream=True, headers={'Referer': base_url}
            ) as r:
                r.raise_for_status()

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
