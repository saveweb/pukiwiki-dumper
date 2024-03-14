from pukiWikiDumper.utils.util import url2prefix


def test_url2prefix():
    # TODO: add test
    pass
    tests_slugify = {
        'https://苟.com:123/~11.22利.国3/家-！!🌚/asd?das#jbcdbd':
        'xn--ui1a.com_123_11_22li_guo_3_jia'
    }
    for url, prefix in tests_slugify.items():
        assert url2prefix(url, ascii_slugify=True) == prefix