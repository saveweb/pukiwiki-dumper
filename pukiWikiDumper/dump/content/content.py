import json
import os
import time
import threading
from typing import Dict

from requests import Session

from pukiWikiDumper.exceptions import ActionEditDisabled, ActionEditTextareaNotFound

from .revisions import get_source_diff, get_source_edit, get_source_source
from .titles import get_pages
from pukiWikiDumper.utils.util import load_pages, smkdirs, uopen
from pukiWikiDumper.utils.util import print_with_lock as print


sub_thread_error = None


def dump_content(puki_url: str = '', dumpDir: str = '', session: Session = None,
                threads: int = 1, ignore_errors: bool = False, ignore_action_disabled_edit: bool = False,
                current_only: bool = False):
    if not dumpDir:
        raise ValueError('dumpDir must be set')

    pages = load_pages(pagesFilePath=dumpDir + '/dumpMeta/pages.jsonl')
    if pages is None:
        pages = get_pages(url=puki_url, session=session)
        with uopen(dumpDir + '/dumpMeta/pages.jsonl', 'w') as f:
            for page in pages:
                f.write(json.dumps(page, ensure_ascii=False) + '\n')

    if not len(pages):
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
                print('[',args[2],']Error in sub thread: (', e, ') ignored')
    ts = pages.copy()
    while ts:
        page = ts.pop(0)
        while threading.active_count() > threads:
            time.sleep(0.05)
        if sub_thread_error:
            raise sub_thread_error
        getSource = [get_source_source, get_source_edit, get_source_diff]
        t = threading.Thread(target=try_dump_page, args=(dumpDir,
                                                     getSource,
                                                     page,
                                                     puki_url,
                                                     session,
                                                     current_only,
                                                     ))
        print('Content: (%d/%d): [[%s]] ...' % (len(pages) - len(ts), len(pages), page))
        t.daemon = True
        t.start()

    while threading.active_count() > 1:
        time.sleep(2)
        print('Waiting for %d threads to finish' %
              (threading.active_count() - 1), end='\r')


def dump_page(dumpDir: str,
              getSource,
              page: Dict[str, str],
              puki_url: str,
              session: Session,
              current_only: bool,):
    msg_header = page["title"] + ': '
    filename = (page['title'].encode('utf-8').hex().upper()) + '.txt'
    if len(filename) > 255: # filename too long
        subdir_A = filename[:255]
        subfilename_B = filename[255:]
        smkdirs(dumpDir, '/wiki/' + subdir_A)
        filepath = dumpDir + '/wiki/' + subdir_A + '/' + subfilename_B
    else:
        filepath = dumpDir + '/wiki/' + filename
    if os.path.exists(filepath):
        print(msg_header, '    [[%s]] exists. skip' % (page['title']))
        return

    srouce = None
    err = None
    for action in getSource:
        try:
            srouce = action(puki_url, page, session=session)
            break
        except Exception as e:
            print(msg_header, str(action), '    Error in sub thread: (', e, ') ignored')
            err = e
            continue
    if srouce is None:
        raise err


    smkdirs(dumpDir, '/wiki/')

    with uopen(filepath, 'w') as f:
        f.write(srouce)

    if current_only:
        print(msg_header, '    [[%s]] saved.' % (page['title']))
        return

    # revs = get_revisions(puki_url, page, session=session, msg_header=msg_header)


    # save_page_changes(dumpDir=dumpDir, child_path=child_path, title=page, 
    #                    revs=revs, msg_header=msg_header)


    for rev in revs[1:]:
        if 'id' in rev and rev['id']:
            try:
                txt = getSource(puki_url, page, rev['id'], session=session)
                smkdirs(dumpDir, '/attic/' + child_path)
                with uopen(dumpDir + '/attic/' + page.replace(':', '/') + '.' + rev['id'] + '.txt', 'w') as f:
                    f.write(txt)
                print(msg_header, '    Revision %s of [[%s]] saved.' % (
                    rev['id'], page))
            except DispositionHeaderMissingError:
                print(msg_header, '    Revision %s of [[%s]] is empty. (probably deleted)' % (
                    rev['id'], page))
        else:
            print(msg_header, '    Revision %s of [[%s]] failed: %s' % (rev['id'], page, 'Rev id not found (please check ?do=revisions of this page)'))


            # time.sleep(1.5)

