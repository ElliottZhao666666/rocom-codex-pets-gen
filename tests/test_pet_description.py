"""Synthetic HTML and explicit-user-preference behavior; no game prose or network."""
from email.message import Message
import io
import ssl
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import get_pet_description as descriptions


def page(body='合成介绍，保留标点。', heading='示例精灵', first='<span aria-hidden="true"></span>'):
    return (f'<html><head><title>{heading} - 测试</title></head><body>'
            f'<h1 id="firstHeading">{heading}<span id="location"></span></h1>'
            '<div id="rocodex-pAppear"><img src="unused.png"/>'
            f'<div class="extra roco-desc">{first}<span>{body}</span></div></div>'
            '<div class="roco-desc"><span></span><span>不相关说明</span></div></body></html>')


class DescriptionTests(unittest.TestCase):
    def test_extracts_exact_direct_selector_and_decodes_entities(self):
        result, title = descriptions.extract_description(page('  合成&amp;<b>介绍</b>，\n第二段。  '), '示例精灵')
        self.assertEqual(result, '合成&介绍，\n第二段。')
        self.assertEqual(title, '示例精灵')

    def test_nth_child_counts_all_elements_not_only_spans(self):
        result, _ = descriptions.extract_description(page(first='<i>装饰</i>'), '示例精灵')
        self.assertEqual(result, '合成介绍，保留标点。')

    def test_nested_lookalike_is_not_a_direct_selector_match(self):
        html = page().replace('<div class="extra roco-desc">', '<section><div class="extra roco-desc">')
        html = html.replace('</span></div></div>', '</span></div></section></div>')
        with self.assertRaises(descriptions.DescriptionError):
            descriptions.extract_description(html, '示例精灵')

    def test_duplicate_selector_is_rejected(self):
        html = page().replace('</body>', '<div id="rocodex-pAppear"><div class="roco-desc"><span></span><span>另一介绍</span></div></div></body>')
        with self.assertRaisesRegex(descriptions.DescriptionError, '实际为 2'):
            descriptions.extract_description(html, '示例精灵')

    def test_missing_or_empty_introduction_is_rejected(self):
        for html in (page(' \n '), page().replace('rocodex-pAppear', 'unrelated')):
            with self.subTest(html=html):
                with self.assertRaises(descriptions.DescriptionError):
                    descriptions.extract_description(html, '示例精灵')

    def test_wrong_or_blocked_page_identity_is_rejected(self):
        for html in (page(heading='另一精灵'), '<h1>请验证后继续</h1>'):
            with self.assertRaises(descriptions.DescriptionError):
                descriptions.extract_description(html, '示例精灵')

    def test_manual_description_preserves_whitespace_and_skips_network(self):
        def forbidden(name):
            self.fail('A user description must never request Wiki')
        for value in ('用户原文。\n\n保留排版。 ', ''):
            result = descriptions.resolve_description('示例精灵', value, fetcher=forbidden)
            self.assertEqual(result['description'], value)
            self.assertEqual(result['source']['kind'], 'user_prompt')
            self.assertEqual(result['source']['explicit_empty'], value == '')

    def test_unspecified_description_calls_fetcher_with_original_name(self):
        names = []
        def fetch(name):
            names.append(name)
            return {'description': '合成介绍'}
        self.assertEqual(descriptions.resolve_description('示例精灵', fetcher=fetch)['description'], '合成介绍')
        self.assertEqual(names, ['示例精灵'])

    def test_http_fetch_encodes_name_and_records_origin_without_raw_html(self):
        class Response(io.BytesIO):
            headers = Message()
            headers['Content-Type'] = 'text/html; charset=utf-8'
            def geturl(self):
                return descriptions.BASE_URL+'%E7%A4%BA%E4%BE%8B%E7%B2%BE%E7%81%B5'
        with patch.object(descriptions.urllib.request, 'urlopen', return_value=Response(page().encode())) as opened:
            result = descriptions.fetch_wiki_description('示例精灵')
        self.assertEqual(opened.call_args.args[0].full_url, Response().geturl())
        self.assertEqual(result['source']['selector'], descriptions.SELECTOR)
        self.assertEqual(len(result['source']['html_sha256']), 64)
        self.assertNotIn('html', result)

    def test_network_failure_does_not_create_fallback_description(self):
        with patch.object(descriptions.urllib.request, 'urlopen', side_effect=TimeoutError('test')) as opened, \
                patch.object(descriptions.time, 'sleep'):
            with self.assertRaises(descriptions.DescriptionError):
                descriptions.fetch_wiki_description('示例精灵')
        self.assertEqual(opened.call_count, 3)

    def test_transient_tls_failure_is_retried_with_same_request(self):
        class Response(io.BytesIO):
            headers = Message()
            headers['Content-Type'] = 'text/html; charset=utf-8'
            def geturl(self):
                return descriptions.BASE_URL+'demo'
        failure = descriptions.urllib.error.URLError(ssl.SSLEOFError('test transient EOF'))
        with patch.object(descriptions.urllib.request, 'urlopen', side_effect=[failure, Response(page().encode())]) as opened, \
                patch.object(descriptions.time, 'sleep'):
            self.assertEqual(descriptions.fetch_wiki_description('示例精灵')['description'], '合成介绍，保留标点。')
        self.assertEqual(opened.call_count, 2)
        self.assertIs(opened.call_args_list[0].args[0], opened.call_args_list[1].args[0])

    def test_not_found_or_rate_limited_pages_are_not_retried(self):
        for code in (403, 404, 429):
            failure = descriptions.urllib.error.HTTPError('https://wiki.biligame.com/nrc/demo', code, 'test', None, None)
            with patch.object(descriptions.urllib.request, 'urlopen', side_effect=failure) as opened:
                with self.assertRaises(descriptions.DescriptionError):
                    descriptions.fetch_wiki_description('示例精灵')
            self.assertEqual(opened.call_count, 1)

    def test_output_cannot_enter_skill_or_input_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)/'input'
            for destination in (descriptions.SKILL_ROOT/'records.json', source/'records.json'):
                with self.assertRaises(descriptions.DescriptionError):
                    descriptions.checked_output(destination, source)
            self.assertEqual(descriptions.checked_output(Path(temporary)/'out.json', source),
                             (Path(temporary)/'out.json').resolve())


if __name__ == '__main__':
    unittest.main()
