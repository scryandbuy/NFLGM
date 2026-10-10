"""Reject unresolved merges and duplicated browser entrypoints before building."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit


MARKER = re.compile(r'^\s*(?:<{7,}(?:\s|$)|>{7,}(?:\s|$)|\|{7,}(?:\s|$)|={7,}\s*$)', re.M)


def validate_web_sources(root, sources):
    root = Path(root)
    for source in sources:
        text = (root / source).read_text(encoding='utf-8-sig')
        if match := MARKER.search(text):
            line = text.count('\n', 0, match.start()) + 1
            raise ValueError(f'{source}:{line}: unresolved merge conflict')
    class Entrypoints(HTMLParser):
        scripts = 0
        styles = 0
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'script' and urlsplit(attrs.get('src', '')).path == 'app.js':
                self.scripts += 1
            if tag == 'link' and urlsplit(attrs.get('href', '')).path == 'style.css':
                self.styles += 1
    parser = Entrypoints()
    parser.feed((root / 'docs/index.html').read_text(encoding='utf-8-sig'))
    if parser.scripts != 1 or parser.styles != 1:
        raise ValueError('docs/index.html must load app.js and style.css exactly once '
                         f'(found {parser.scripts} scripts, {parser.styles} stylesheets)')
