
import http.cookiejar
import requests.utils
import json
import queue
import time

import requests
import urllib3

from pukiWikiDumper.__version__ import DUMPER_VERSION
from pukiWikiDumper.utils.util import uopen


def createSession(retries=5):
    session = requests.Session()
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        # Courtesy datashaman https://stackoverflow.com/a/35504626
        class CustomRetry(Retry):
            def increment(self, method=None, url=None, *args, **kwargs):
                if '_pool' in kwargs:
                    # type: urllib3.connectionpool.HTTPSConnectionPool
                    conn = kwargs['_pool']
                    if 'response' in kwargs:
                        try:
                            # drain conn in advance so that it won't be put back into conn.pool
                            kwargs['response'].drain_conn()
                        except:
                            pass
                    # Useless, retry happens inside urllib3
                    # for adapters in session.adapters.values():
                    #     adapters: HTTPAdapter
                    #     adapters.poolmanager.clear()

                    # Close existing connection so that a new connection will be used
                    if hasattr(conn, 'pool'):
                        pool = conn.pool  # type: queue.Queue
                        try:
                            # Don't directly use this, This closes connection pool by making conn.pool = None
                            conn.close()
                        except:
                            pass
                        conn.pool = pool
                return super(CustomRetry, self).increment(method=method, url=url, *args, **kwargs)

            def sleep(self, response=None):
                retry_after = self.get_retry_after(response)
                backoff = self.get_backoff_time()
                delay_sec = retry_after if retry_after is not None else backoff
                if response is None:
                    msg = 'req retry in %.2fs' % delay_sec
                else:
                    msg = 'req retry (%s, %s) in %.2fs' % (response.status, response.reason, delay_sec)
                print(msg)
                super(CustomRetry, self).sleep(response=response)

        __retries__ = CustomRetry(
            total=retries, backoff_factor=1.5,
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=['DELETE', 'PUT', 'GET',
                             'OPTIONS', 'TRACE', 'HEAD', 'POST']
        )
        session.mount("https://", HTTPAdapter(max_retries=__retries__))
        session.mount("http://", HTTPAdapter(max_retries=__retries__))
    except:
        pass

    session.headers.update({'User-Agent': 'pukiWikiDumper/' +
                           DUMPER_VERSION + ' (https://github.com/saveweb/pukiwiki-dumper)'})
    print('User-Agent:',session.headers.get('User-Agent'))

    return session


def load_cookies(session: requests.Session, cookies_file: str) -> bool:
    with uopen(cookies_file, 'r') as f: # cookies.txt or cookies.json
        if cookies_file.endswith('.json'):
            cookies_dict = json.load(f)
            cookies_dict = {c['Name raw']: c['Content raw'] for c in cookies_dict}
            cj = requests.utils.cookiejar_from_dict(cookies_dict)
        else:
            cj = http.cookiejar.MozillaCookieJar()
            cj.load(cookies_file, ignore_discard=True, ignore_expires=True)
        session.cookies.update(cj)
        print('Cookies loaded:', session.cookies.get_dict())
        return True
