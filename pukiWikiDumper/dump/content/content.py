import builtins
import os
import time
import threading

from bs4 import BeautifulSoup
from requests import Session

from pukiWikiDumper.exceptions import ActionEditDisabled, ActionEditTextareaNotFound

from .revisions import get_revisions, get_source_diff, get_source_edit, save_page_changes
from .titles import get_titles
from pukiWikiDumper.utils.util import load_titles, smkdirs, uopen
from pukiWikiDumper.utils.util import print_with_lock as print
from pukiWikiDumper.utils.config import running_config



sub_thread_error = None


def dump_content(puki_url: str = '', dumpDir: str = '', session: Session = None,
                threads: int = 1, ignore_errors: bool = False, ignore_action_disabled_edit: bool = False,
                current_only: bool = False):
    if not dumpDir:
        raise ValueError('dumpDir must be set')

    titles = load_titles(titlesFilePath=dumpDir + '/dumpMeta/titles.txt')
    if titles is None:
        titles = get_titles(url=puki_url, session=session)
        with uopen(dumpDir + '/dumpMeta/titles.txt', 'w') as f:
            f.write('\n'.join(titles))
            f.write('\n--END--\n')

    if not len(titles):
        print('Empty wiki')
        return False

    def try_dump_page(*args, **kwargs):
        try:
            dump_page(*args, **kwargs)
        except Exception as e:
            if isinstance(e, ActionEditDisabled) and ignore_action_disabled_edit:
                print('[',args[2],'] action disabled: edit. ignored')
            elif isinstance(e, ActionEditTextareaNotFound) and ignore_action_disabled_edit:
                print('[',args[2],'] action edit: textarea not found. ignored')
            elif not ignore_errors:
                global sub_thread_error
                sub_thread_error = e
                raise e
            else:
                print('[',args[2]+1,']Error in sub thread: (', e, ') ignored')
    ts = titles.copy()
    while ts:
        title = ts.pop(0)
        while threading.active_count() > threads:
            time.sleep(0.05)
        if sub_thread_error:
            raise sub_thread_error
        getSource = [get_source_diff, get_source_edit]
        t = threading.Thread(target=try_dump_page, args=(dumpDir,
                                                     getSource,
                                                     title,
                                                     puki_url,
                                                     session,
                                                     current_only,
                                                     ))
        print('Content: (%d/%d): [[%s]] ...' % (len(titles) - len(ts), len(titles), title))
        t.daemon = True
        t.start()

    while threading.active_count() > 1:
        time.sleep(2)
        print('Waiting for %d threads to finish' %
              (threading.active_count() - 1), end='\r')


def dump_page(dumpDir: str,
              getSource,
              title: str,
              puki_url: str,
              session: Session,
              current_only: bool,):
    msg_header = f'[{title}]: '
    use_hex = True
    filepath = dumpDir + '/wiki/' + (title.encode('utf-8').hex().upper() if use_hex else title) + '.txt'
    if os.path.exists(filepath):
        print(msg_header, '    [[%s]] exists. skip' % (title))
        return

    srouce = None
    err = None
    for action in getSource:
        try:
            srouce = action(puki_url, title, session=session)
        except Exception as e:
            print(msg_header, '    Error in sub thread: (', e, ') ignored')
            err = e
            continue
    if srouce is None:
        raise err

    if use_hex: # title to UTF-8 HEX
        child_path = ''
    else:
        child_path = title.lstrip('/')
        child_path = '/'.join(child_path.split('/')[:-1])

    smkdirs(dumpDir, '/wiki/' + child_path)

    with uopen(filepath, 'w') as f:
        f.write(srouce)

    if current_only:
        print(msg_header, '    [[%s]] saved.' % (title))
        return

    revs = get_revisions(puki_url, title, session=session, msg_header=msg_header)


    save_page_changes(dumpDir=dumpDir, child_path=child_path, title=title, 
                       revs=revs, msg_header=msg_header)


    for rev in revs[1:]:
        if 'id' in rev and rev['id']:
            try:
                txt = getSource(puki_url, title, rev['id'], session=session)
                smkdirs(dumpDir, '/attic/' + child_path)
                with uopen(dumpDir + '/attic/' + title.replace(':', '/') + '.' + rev['id'] + '.txt', 'w') as f:
                    f.write(txt)
                print(msg_header, '    Revision %s of [[%s]] saved.' % (
                    rev['id'], title))
            except DispositionHeaderMissingError:
                print(msg_header, '    Revision %s of [[%s]] is empty. (probably deleted)' % (
                    rev['id'], title))
        else:
            print(msg_header, '    Revision %s of [[%s]] failed: %s' % (rev['id'], title, 'Rev id not found (please check ?do=revisions of this page)'))


            # time.sleep(1.5)

