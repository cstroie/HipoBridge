#!/usr/bin/env python3
"""HTML to Markdown and Markdown to HTML conversion utilities.

Copyright (C) 2025 Costin Stroie <costinstroie@eridu.eu.org>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Bidirectional conversion between HTML and Markdown.
Designed for the specific HTML structures produced by Hipocrate
(Microsoft Office artifacts, nested formatting, medical record conventions).
"""

import re
import html as html_module
from bs4 import BeautifulSoup, Comment


# Block-level tags that must not be wrapped in <p>
_BLOCK_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
               'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote',
               'div', 'pre')
_BLOCK_START_RE = re.compile(
    r'^</?(' + '|'.join(_BLOCK_TAGS) + r')[\s>]', re.IGNORECASE
)


def html_to_markdown(html_content: str) -> str:
    """Convert Hipocrate HTML to clean Markdown text.

    Handles Microsoft Office artifacts, icon-only <i> tags, nested headings,
    Word-style list paragraphs (MsoListParagraph), and common medical record
    formatting patterns found in epicrisis HTML.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove non-content elements entirely (textarea duplicates the raw HTML
        # as editable text; script/style have no narrative content)
        for tag in soup.find_all(['script', 'style', 'textarea']):
            tag.decompose()

        # Remove XML processing instructions and HTML comments
        for node in soup.find_all(re.compile(r'^\?xml')):
            node.decompose()
        for node in soup.find_all(string=lambda t: isinstance(t, Comment)):
            node.extract()

        # MS-Office namespace tags: empty → gone, non-empty → unwrap
        for tag in soup.find_all('o:p'):
            if tag.get_text(strip=True):
                tag.unwrap()
            else:
                tag.decompose()
        for tag in soup.find_all(['xml:namespace']):
            tag.decompose()

        # mso-spacerun spans are padding-only → single space
        for span in soup.find_all(True, style=re.compile(r'mso-spacerun', re.I)):
            span.replace_with(' ')

        # Mark Word list paragraphs before any structural processing so we can
        # detect them later even after class attributes are gone
        _list_cls = re.compile(r'MsoListParagraph', re.I)
        for p in soup.find_all('p', class_=_list_cls):
            p['data-md-list'] = '1'

        # Word list-bullet spans (mso-list: Ignore) contain the "-" glyph and
        # spacer — decompose them; we emit the "- " prefix ourselves below
        for span in soup.find_all(True, attrs={'style': re.compile(r'mso-list\s*:\s*Ignore', re.I)}):
            span.decompose()

        # Unwrap a single wrapping <b> that encloses the entire body content
        container = soup.find('body') or soup
        element_children = [c for c in container.children
                            if hasattr(c, 'name') and c.name]
        if len(element_children) == 1 and element_children[0].name == 'b':
            element_children[0].unwrap()

        # Process inline elements BEFORE block elements so that unwrapping
        # <p> doesn't move <b> to body level and trigger the wrapper check.

        # Bold — skip empty tags and pure-wrapper <b> (only child of body)
        for b in soup.find_all(['b', 'strong']):
            if not b.get_text(strip=True):
                b.unwrap()
                continue
            parent = b.parent
            siblings = [c for c in parent.children
                        if hasattr(c, 'name') and c.name]
            is_wrapper = (parent.name in ('body',) or parent == soup) \
                         and len(siblings) == 1
            if not is_wrapper:
                b.insert_before('**')
                b.insert_after('**')
            b.unwrap()

        # Italic — skip <i> tags with no visible text (icon elements)
        for i_tag in soup.find_all(['i', 'em']):
            if not i_tag.get_text(strip=True):
                i_tag.decompose()
                continue
            i_tag.insert_before('*')
            i_tag.insert_after('*')
            i_tag.unwrap()

        # Underline → italic (Markdown has no underline); skip empty
        for u in soup.find_all('u'):
            if not u.get_text(strip=True):
                u.decompose()
                continue
            u.insert_before('*')
            u.insert_after('*')
            u.unwrap()

        # Headings → replace the whole tag with a markdown text node so that
        # surrounding block elements (p, td) don't swallow the # prefix.
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(tag.name[1])
            text = tag.get_text()
            tag.replace_with(f'\n\n{"#" * level} {text}\n\n')

        # Paragraphs: list items get a tight "- " prefix; others get \n\n after
        for p in soup.find_all('p'):
            if p.get('data-md-list'):
                p.insert_before('\n- ')
            else:
                p.insert_after('\n\n')
            p.unwrap()

        # Line breaks
        for br in soup.find_all('br'):
            br.replace_with('\n')

        # Block-level divs: unwrap with a paragraph break so outer wrappers
        # don't run content together
        for div in soup.find_all('div'):
            div.insert_after('\n\n')
            div.unwrap()

        # Extract text directly from the modified soup
        text = soup.get_text()

        # Decode entities and normalise whitespace
        text = html_module.unescape(text)
        text = text.replace('\xa0', ' ').replace('&nbsp;', ' ').replace('&amp;nbsp;', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        # Collapse over-nested emphasis markers (bold+italic+underline stacking
        # produces ****, ***** etc. — cap at *** which is bold+italic)
        text = re.sub(r'\*{4,}', '***', text)
        # Tidy list items: collapse whitespace/newlines between "- " and content
        text = re.sub(r'^- *\n+', '- ', text, flags=re.MULTILINE)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    except Exception:
        # Fallback: strip all tags and return plain text
        cleaned = html_module.unescape(html_content)
        cleaned = cleaned.replace('\xa0', ' ').replace('&nbsp;', ' ')
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        return re.sub(r'\s+', ' ', cleaned).strip()


def markdown_to_html(markdown_text: str) -> str:
    """Convert simple Markdown to HTML.

    Supported syntax: headings (#–######), bold (**/**__), italic (*/_),
    unordered lists (- /*), ordered lists (1.), paragraphs, line breaks.
    """
    # Escape HTML special characters first so they survive regex substitutions
    result = (markdown_text
              .replace('&', '&amp;')
              .replace('<', '&lt;')
              .replace('>', '&gt;'))

    # --- Headings (most specific first) ---
    for level in range(6, 0, -1):
        result = re.sub(
            r'^#{' + str(level) + r'} (.*)$',
            lambda m, lv=level: f'<h{lv}>{m.group(1)}</h{lv}>',
            result, flags=re.MULTILINE
        )

    # --- Bold before italic to avoid * interference ---
    # Temporarily replace bold markers with sentinels so the italic pass
    # doesn't see the asterisks left by bold.
    result = re.sub(r'\*\*(.*?)\*\*', lambda m: f'\x02B\x03{m.group(1)}\x02/B\x03', result)
    result = re.sub(r'__(.*?)__',     lambda m: f'\x02B\x03{m.group(1)}\x02/B\x03', result)

    # --- Italic (single * or _) ---
    result = re.sub(r'\*(.*?)\*', r'<em>\1</em>', result)
    result = re.sub(r'_(.*?)_',   r'<em>\1</em>', result)

    # --- Restore bold ---
    result = result.replace('\x02B\x03', '<strong>').replace('\x02/B\x03', '</strong>')

    # --- Unordered lists ---
    # Mark items with a sentinel tag so ordered-list grouping won't touch them
    result = re.sub(r'^\s*[-*]\s+(.*)$', r'<_ul_li>\1</_ul_li>', result, flags=re.MULTILINE)
    result = re.sub(
        r'(<_ul_li>.*?</_ul_li>\n?)+',
        lambda m: '<ul>\n' + m.group(0).replace('_ul_li', 'li') + '</ul>\n',
        result, flags=re.DOTALL
    )

    # --- Ordered lists ---
    result = re.sub(r'^\s*\d+\.\s+(.*)$', r'<_ol_li>\1</_ol_li>', result, flags=re.MULTILINE)
    result = re.sub(
        r'(<_ol_li>.*?</_ol_li>\n?)+',
        lambda m: '<ol>\n' + m.group(0).replace('_ol_li', 'li') + '</ol>\n',
        result, flags=re.DOTALL
    )

    # --- Paragraphs ---
    # Split on blank lines; only wrap chunks that contain no block-level tags.
    chunks = result.split('\n\n')
    wrapped = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        # Check every line: if any line starts a block tag, don't wrap
        lines = stripped.splitlines()
        has_block = any(_BLOCK_START_RE.match(line.strip()) for line in lines)
        wrapped.append(stripped if has_block else f'<p>{stripped}</p>')
    result = '\n'.join(wrapped)

    # --- Inline line breaks ---
    # Insert <br> for single newlines, but only between non-tag characters.
    # Process line-by-line so we never inject <br> inside a tag's own text.
    result = re.sub(r'([^\n>])\n([^\n<])', r'\1<br>\2', result)

    return result
