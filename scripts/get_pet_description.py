"""Resolve an explicit description or the exact game introduction on BWIKI."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


SELECTOR = '#rocodex-pAppear > div.roco-desc > span:nth-child(2)'
BASE_URL = 'https://wiki.biligame.com/nrc/'
SKILL_ROOT = Path(__file__).resolve().parents[1]
MAX_HTML_BYTES = 4 * 1024 * 1024
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
             'link', 'meta', 'param', 'source', 'track', 'wbr'}


class DescriptionError(ValueError):
    """No verified description is available; do not invent replacement prose."""


@dataclass
class Element:
    tag: str
    attrs: dict
    parent: Element | None = None
    children: list = field(default_factory=list)
    element_index: int = 0
    element_children: int = 0

    def text_content(self):
        return ''.join(child if isinstance(child, str) else child.text_content()
                       for child in self.children)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element('document', {})
        self.stack = [self.root]
        self.elements = []

    def handle_starttag(self, tag, attrs):
        parent = self.stack[-1]
        parent.element_children += 1
        node = Element(tag, dict(attrs), parent, element_index=parent.element_children)
        parent.children.append(node)
        self.elements.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def extract_description(html, pet_name):
    parser = PageParser()
    parser.feed(html)
    parser.close()
    headings = [node for node in parser.elements
                if node.tag == 'h1' and node.attrs.get('id') == 'firstHeading']
    if len(headings) != 1:
        raise DescriptionError('无法唯一确认 Wiki 页面主标题；可能遇到拦截页或页面结构变化')
    heading = headings[0].text_content().strip()
    if heading != pet_name:
        raise DescriptionError(f'Wiki 名称不符：请求 {pet_name!r}，页面为 {heading!r}')
    matches = []
    for node in parser.elements:
        parent = node.parent
        if (node.tag == 'span' and node.element_index == 2 and parent is not None
                and parent.tag == 'div' and 'roco-desc' in parent.attrs.get('class', '').split()
                and parent.parent is not None and parent.parent.attrs.get('id') == 'rocodex-pAppear'):
            matches.append(node)
    if len(matches) != 1:
        raise DescriptionError(f'介绍选择器应唯一命中，实际为 {len(matches)}：{SELECTOR}')
    description = matches[0].text_content().strip()
    if not description:
        raise DescriptionError('图鉴介绍为空；请用户提供描述，不自动编写')
    return description, heading


def fetch_wiki_description(pet_name, timeout=20):
    url = BASE_URL + urllib.parse.quote(pet_name, safe='')
    request = urllib.request.Request(url, headers={
        'User-Agent': 'rocom-codex-pets-gen/1.2 (+https://github.com/ElliottZhao666666/rocom-codex-pets-gen)',
        'Accept': 'text/html',
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                parsed = urllib.parse.urlsplit(final_url)
                if parsed.scheme != 'https' or parsed.hostname != 'wiki.biligame.com' or not parsed.path.startswith('/nrc/'):
                    raise DescriptionError('Wiki 请求跳转到预期站点或栏目之外')
                if response.headers.get_content_type() != 'text/html':
                    raise DescriptionError('Wiki 没有返回 HTML 页面')
                data = response.read(MAX_HTML_BYTES+1)
                if len(data) > MAX_HTML_BYTES:
                    raise DescriptionError('Wiki 页面超过读取上限')
                encoding = response.headers.get_content_charset() or 'utf-8'
            description, heading = extract_description(data.decode(encoding), pet_name)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504) or attempt == 2:
                raise DescriptionError('读取 Wiki 图鉴失败：'+str(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise DescriptionError('读取 Wiki 图鉴失败：'+str(exc)) from exc
        except (UnicodeError, LookupError) as exc:
            raise DescriptionError('Wiki 页面编码无法解析：'+str(exc)) from exc
        time.sleep(.25*(attempt+1))
    return {
        'schema': 'rocom.pet-description.v1', 'description': description,
        'source': {'kind': 'biligame_wiki', 'pet_name': pet_name, 'url': final_url,
                   'selector': SELECTOR, 'page_heading': heading,
                   'fetched_at': datetime.now(timezone.utc).isoformat(),
                   'html_sha256': hashlib.sha256(data).hexdigest()},
    }


def resolve_description(pet_name, supplied=None, fetcher=fetch_wiki_description):
    if supplied is not None:
        return {'schema': 'rocom.pet-description.v1', 'description': supplied,
                'source': {'kind': 'user_prompt', 'pet_name': pet_name,
                           'explicit_empty': supplied == ''}}
    return fetcher(pet_name)


def checked_output(path, input_root=None):
    output = Path(path).resolve()
    for root in (SKILL_ROOT, input_root):
        if root is not None and output.is_relative_to(Path(root).resolve()):
            raise DescriptionError('描述记录必须保存到 skill 源码和原始输入目录之外')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('--input', type=Path, help='已标准化的单实体目录；从 entity.json 读取原名')
    identity.add_argument('--name', help='已确认的中文精灵原名；供独立检查页面使用')
    supplied = parser.add_mutually_exclusive_group()
    supplied.add_argument('--description', help='仅在用户明确指定描述时传入；空字符串也优先使用')
    supplied.add_argument('--description-file', type=Path, help='UTF-8 用户指定描述文本，原样保留')
    parser.add_argument('--json-out', type=Path, help='私有制作记录文件，必须在源码和输入目录外')
    args = parser.parse_args(argv)
    try:
        destination = checked_output(args.json_out, args.input) if args.json_out else None
        entity = None
        if args.input:
            from validate_input import validate_input
            _, entity, _ = validate_input(args.input)
            name = entity['name']
        else:
            name = args.name.strip()
        if not name:
            raise DescriptionError('中文精灵原名不能为空')
        description = args.description
        if args.description_file is not None:
            description = args.description_file.read_text(encoding='utf-8')
        result = resolve_description(name, description)
        if entity is not None:
            result['identity'] = entity['identity']
        result = {'ok': True, **result}
        encoded = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(encoded, encoding='utf-8')
        print(encoded, end='')
        return 0
    except DescriptionError as exc:
        print(json.dumps({'ok': False, 'status': 'needs_description', 'error': str(exc)}, ensure_ascii=False))
        return 2
    except (OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'status': 'invalid_input', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
