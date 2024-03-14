import argparse
import os
import sys
import time

import requests
from pukiWikiDumper.utils.dump_lock import DumpLock
from pukiWikiDumper.utils.ia_checker import any_recent_ia_item_exists
# import gzip, 7z
from pukiWikiDumper.utils.util import print_with_lock as print

from pukiWikiDumper.__version__ import DUMPER_VERSION, pukiWikiDumper_outdated_check
from pukiWikiDumper.dump.content.content import dump_content
from pukiWikiDumper.dump.html import dump_HTML
from pukiWikiDumper.dump.info import update_info
from pukiWikiDumper.dump.media import dump_attachs
from pukiWikiDumper.utils.config import update_config, running_config
from pukiWikiDumper.utils.patch import SessionMonkeyPatch
from pukiWikiDumper.utils.session import createSession, load_cookies
from pukiWikiDumper.utils.util import avoidSites, buildBaseUrl, getPukiUrl, smkdirs, standardizeUrl, uopen, url2prefix

DEFAULT_THREADS = -1 # magic number, -1 means use 1 thread.

def getArgumentParser():
    parser = argparse.ArgumentParser(description='pukiWikiDumper Version: '+ DUMPER_VERSION)
    parser.add_argument('url', help='URL of the dokuWiki (provide the doku.php URL)', type=str)

    group_download = parser.add_argument_group("Data to download", "What info download from the wiki")

    group_download.add_argument('--content', action='store_true', help='Dump content')
    group_download.add_argument('--media', action='store_true', help='Dump media')
    group_download.add_argument('--html', action='store_true', help='Dump HTML')

    parser.add_argument('--current-only', dest='current_only', action='store_true',
                        help='Dump latest revision, no history [default: false]')
    parser.add_argument(
        '--path', help='Specify dump directory [default: <site>-<date>]', type=str, default='')
    parser.add_argument(
        '--no-resume', help='Do not resume a previous dump [default: resume]', action='store_true')
    parser.add_argument(
        '--threads', help='Number of sub threads to use [default: 1], not recommended to set > 5', type=int, default=DEFAULT_THREADS)
    parser.add_argument(
        '--i-love-retro',  action='store_true', dest='user_love_retro',
        help='Do not check the latest version of pukiWikiDumper (from pypi.org) before running [default: False]')

    parser.add_argument('--insecure', action='store_true',
                        help='Disable SSL certificate verification')
    parser.add_argument('--ignore-errors', action='store_true',
                        help='!DANGEROUS! ignore errors in the sub threads. This may cause incomplete dumps.')
    parser.add_argument('--ignore-action-disabled-edit', action='store_true',
                        help='Some sites disable edit action for anonymous users and some core pages. '+
                        'This option will ignore this error and textarea not found error.'+
                        'But you may only get a partial dump. '+
                        '(only works with --content)', dest='ignore_action_disabled_edit')
    parser.add_argument('--trim-php-warnings', action='store_true', dest='trim_php_warnings',
                        help='Trim PHP warnings from requests.Response.text')

    parser.add_argument('--delay', help='Delay between requests [default: 0.0]', type=float, default=0.0)
    parser.add_argument('--retry', help='Maximum number of retries [default: 5]', type=int, default=5)
    parser.add_argument('--hard-retry', type=int, default=3, dest='hard_retry',
                        help='Maximum number of retries for hard errors [default: 3]')

    parser.add_argument('--parser', help='HTML parser [default: lxml]', type=str, default='lxml')

    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--cookies', help='cookies file')
    parser.add_argument('--auto', action='store_true', 
                        help='dump: content+media+html, threads=2, ignore-action-disable-edit. (threads is overridable)')
    parser.add_argument('-u', '--upload', action='store_true', 
                        help='Upload wikidump to Internet Archive after successfully dumped'
                        ' (only works with --auto)')
    parser.add_argument("-g", "--uploader-arg", dest="uploader_args", action='append', default=[],
                        help="Arguments for uploader.")
    parser.add_argument('--force', action='store_true', help='To dump even if a recent dump exists on IA')

    return parser


def checkArgs(args):
    if not args.content and not args.media and not args.html:
        print('Nothing to do. Use --content and/or --media and/or --html to specify what to dump.')
        return False
    if not args.url:
        print('No URL specified.')
        return False
    if args.threads < 1:
        print('Number of threads must be >= 1.')
        return False
    if args.threads > 5:
        print('Warning: threads > 5 , will bring a lot of pressure to the server.')
        print('Original site may deny your request, even ban our UA.')
        time.sleep(3)
        input('Press Enter to continue...')
    if args.ignore_errors:
        print('Warning: You have chosen to ignore errors in the sub threads. This may cause incomplete dumps.')
        time.sleep(3)
        input('Press Enter to continue...')
    if args.ignore_action_disabled_edit and not args.content:
        print('Warning: You have specified --ignore-action-disabled-edit, but you have not specified --content.')
        return False
    if args.delay < 0:
        print('Delay must be >= 0.')
        return False
    if args.delay > 0.0 and args.threads > 1:
        print(f"Warning: You have specified a delay and more than one thread ({args.threads}).")
        print("!!! Delay will be applied to each thread separately !!!")
        time.sleep(3)
        input('Press Enter to continue...')
    if args.retry < 0:
        print('Retry must be >= 0.')
        return False
    if args.upload and not args.auto:
        print('Warning: You have specified --upload, but you have not specified --auto.')
        return False
    if args.parser:
        from bs4 import BeautifulSoup, FeatureNotFound
        try:
            BeautifulSoup("", args.parser)
            running_config.html_parser = args.parser
        except FeatureNotFound:
            print(f"Parser {args.parser} not found. Please install first following "
                  "https://www.crummy.com/software/BeautifulSoup/bs4/doc/#installing-a-parser")
            return False
    return True


def getParameters():
    parser = getArgumentParser()
    args = parser.parse_args()

    if args.auto:
        args.content = True
        args.media = True
        args.html = True
        args.threads = args.threads if args.threads >= 1 else 2
        args.ignore_action_disabled_edit = True
    else:
        # reset magic number
        args.threads = args.threads if args.threads >= 1 else 1
    print('Threads:', args.threads)
    if not checkArgs(args):
        parser.print_help()
        sys.exit(1)

    return args


def dump():
    args = getParameters()
    if not args.user_love_retro:
        pukiWikiDumper_outdated_check()
    url_input = args.url

    session = createSession(retries=args.retry)

    if args.verbose:
        def print_request(r: requests.Response, *args, **kwargs):
            # TODO: use logging
            # print("H:", r.request.headers)
            for _r in r.history:
                print("Resp (history): ", _r.request.method, _r.status_code, _r.reason, _r.url)
            print(f"Resp: {r.request.method} {r.status_code} {r.reason} {r.url}")
            if r.raw._connection.sock:
                print(f"Conn: {r.raw._connection.sock.getsockname()} -> {r.raw._connection.sock.getpeername()[0]}")
        session.hooks['response'].append(print_request)

    if args.insecure:
        session.verify = False
        requests.packages.urllib3.disable_warnings()
        print("Warning: SSL certificate verification disabled.")
    session_monkey = SessionMonkeyPatch(session=session, delay=args.delay, msg='',
                                        hard_retries=args.hard_retry,
                                        trim_PHP_warnings=args.trim_php_warnings)
    session_monkey.hijack()

    std_url = standardizeUrl(url_input)
    puki_url = getPukiUrl(std_url, session=session)

    avoidSites(puki_url, session=session)

    if not args.force:
        print("Searching for recent dumps on IA...")
        if any_recent_ia_item_exists(ori_url=puki_url, days=365):
            print("A dump of this wiki was uploaded to IA in the last 365 days. Aborting.")
            sys.exit(88)

    if args.cookies:
        load_cookies(session, args.cookies)


    base_url = buildBaseUrl(puki_url)
    dumpDir = url2prefix(puki_url) + '-' + \
        time.strftime("%Y%m%d", time.gmtime()) if not args.path else args.path.rstrip('/')
    if args.no_resume:
        if os.path.exists(dumpDir):
            print(
                'Dump directory already exists. (You can use --path to specify a different directory.)')
            return 1

    smkdirs(dumpDir, '/dumpMeta')
    print('Dumping to ', dumpDir,
          '\nBase URL: ', base_url,
          '\nPukiPHP URL: ', puki_url)

    _config = {'url_input': url_input,  # type: str
               'std_url': std_url,  # type: str
               'puki_url': puki_url,  # type: str
               'base_url': base_url,  # type: str
               'pukiWikiDumper_version': DUMPER_VERSION,
               }
    update_config(dumpDir=dumpDir, config=_config)
    update_info(dumpDir, puki_url=puki_url, session=session)

    with DumpLock(dumpDir):
        if args.content:
            if os.path.exists(os.path.join(dumpDir, 'content_dumped.mark')):
                print('Content already dumped.')
            else:
                print('\nDumping content...\n')
                dump_content(puki_url=puki_url, dumpDir=dumpDir,
                            session=session, threads=args.threads,
                            ignore_errors=args.ignore_errors,
                            ignore_action_disabled_edit=args.ignore_action_disabled_edit,
                            current_only=args.current_only)
                with open(os.path.join(dumpDir, 'content_dumped.mark'), 'w') as f:
                    f.write('done')
        if args.html:
            if os.path.exists(os.path.join(dumpDir, 'html_dumped.mark')):
                print('HTML already dumped.')
            else:
                print('\nDumping HTML...\n')
                dump_HTML(puki_url=puki_url, dumpDir=dumpDir,
                        session=session, threads=args.threads,
                        ignore_errors=args.ignore_errors, current_only=args.current_only)
                with open(os.path.join(dumpDir, 'html_dumped.mark'), 'w') as f:
                    f.write('done')
        if args.media: # last, so that we can know the dump is complete.
            if os.path.exists(os.path.join(dumpDir, 'attach_dumped.mark')):
                print('Media already dumped.')
            else:
                print('\nDumping media...\n')
                dump_attachs(base_url=base_url, dumpDir=dumpDir,
                        session=session, threads=args.threads,
                        ignore_errors=args.ignore_errors)
                with open(os.path.join(dumpDir, 'attach_dumped.mark'), 'w') as f:
                    f.write('done')

    session_monkey.release()
    print('\n\n--Done--')

    if args.upload and args.auto:
        print('Uploading to Internet Archive...')
        # from dokuWikiUploader.uploader import upload
        from subprocess import call
        time.sleep(5)
        retcode = call([sys.executable, '-m', 'dokuWikiUploader.uploader', dumpDir] + args.uploader_args,
             shell=False, env=os.environ.copy())
        if retcode == 0:
            print('dokuWikiUploader: --upload: Done')
        else:
            print('dokuWikiUploader: --upload: [red] Failed [/red]!!!')
            raise RuntimeError('dokuWikiUploader: --upload: Failed!!!')

