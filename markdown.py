#!/usr/bin/env python3
""" Markdown conversion """

from typing import Dict, Any, Optional, List
import re
from bs4 import BeautifulSoup, Comment
import html

def html_to_markdown(html_content: str) -> str:
    """Convert HTML content to clean markdown text.

    Processes HTML content by removing unnecessary tags, converting formatting
    elements to markdown syntax, and normalizing whitespace.

    Args:
        html_content: HTML content to convert

    Returns:
        Clean markdown text
    """

    try:
        # Parse the HTML content
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove XML namespace declarations and processing instructions
        for ns_decl in soup.find_all(re.compile(r'^\?xml')):
            ns_decl.decompose()

        # Remove Microsoft Office specific tags
        for tag in soup.find_all(['o:p', 'xml:namespace']):
            tag.decompose()

        # Remove wrapping <b> tags that might enclose the entire content
        # Check if there's a single <b> tag that contains everything
        body_content = soup.find('body')
        if body_content:
            content_children = list(body_content.children)
            if len(content_children) == 1 and content_children[0].name == 'b':
                # If the only child is a <b> tag, unwrap it
                content_children[0].unwrap()
        else:
            # If no body tag, check if the soup itself has a single <b> child
            root_children = list(soup.children)
            # Filter out text nodes that are only whitespace
            element_children = [child for child in root_children if hasattr(child, 'name') and child.name]
            if len(element_children) == 1 and element_children[0].name == 'b':
                # If the only element child is a <b> tag, unwrap it
                element_children[0].unwrap()

        # Convert common HTML elements to markdown
        # Headings
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(tag.name[1])
            tag.insert_before('#' * level + ' ')
            tag.insert_after('\n\n')
            tag.unwrap()

        # Paragraphs
        for p in soup.find_all('p'):
            p.insert_after('\n\n')
            p.unwrap()

        # Line breaks
        for br in soup.find_all('br'):
            br.replace_with('\n')

        # Bold (but skip if it's a wrapper tag)
        for b in soup.find_all(['b', 'strong']):
            # Check if this is a wrapper tag (contains all other content)
            parent_children = list(b.parent.children)
            # Filter out text nodes that are only whitespace
            element_children = [child for child in parent_children if hasattr(child, 'name') and child.name]

            # Skip if this is a wrapper tag (only child element in parent)
            is_wrapper = (b.parent.name == 'body' or b.parent == soup) and len(element_children) == 1
            if not is_wrapper:
                b.insert_before('**')
                b.insert_after('**')
            b.unwrap()

        # Italic
        for i in soup.find_all(['i', 'em']):
            i.insert_before('*')
            i.insert_after('*')
            i.unwrap()

        # Underline (convert to italic as markdown doesn't have underline)
        for u in soup.find_all('u'):
            u.insert_before('*')
            u.insert_after('*')
            u.unwrap()

        # Remove excessive whitespace and HTML entities
        text = soup.get_text()
        # Decode HTML entities
        text = html.unescape(text)
        # Remove various forms of non-breaking spaces
        text = text.replace('\xa0', ' ')  # &nbsp; character entity
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;nbsp;', ' ')
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()

        return text
    except Exception as e:
        # If parsing fails, return cleaned text
        # Decode HTML entities
        cleaned_text = html.unescape(html_content)
        # Remove various forms of non-breaking spaces
        cleaned_text = cleaned_text.replace('\xa0', ' ')  # &nbsp; character entity
        cleaned_text = cleaned_text.replace('&nbsp;', ' ')
        cleaned_text = cleaned_text.replace('&amp;nbsp;', ' ')
        return re.sub(r'\s+', ' ', cleaned_text.strip())

def markdown_to_html(markdown_text: str) -> str:
    """Convert simple markdown to basic HTML.

    Supports:
    - Paragraphs (double newlines)
    - Line breaks (single newlines)
    - Bold text (**text** or __text__)
    - Italic text (*text* or _text_)
    - Headers (# Header, ## Header, etc.)
    - Unordered lists (- item or * item)
    - Ordered lists (1. item, 2. item, etc.)

    Args:
        markdown_text: Markdown text to convert

    Returns:
        HTML representation of the markdown
    """
    import re

    # Escape HTML characters
    html = markdown_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Headers (# Header, ## Header, etc.)
    html = re.sub(r'^###### (.*)$', r'<h6>\1</h6>', html, flags=re.MULTILINE)
    html = re.sub(r'^##### (.*)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
    html = re.sub(r'^#### (.*)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.*)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Bold (**text** or __text__)
    html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)

    # Italic (*text* or _text_)
    html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
    html = re.sub(r'_(.*?)_', r'<em>\1</em>', html)

    # Unordered lists (- item or * item)
    html = re.sub(r'^\s*[-*]\s+(.*)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>\s*)+', r'<ul>\n\g<0></ul>\n', html)

    # Ordered lists (1. item, 2. item, etc.)
    html = re.sub(r'^\s*\d+\.\s+(.*)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>\s*)+', r'<ol>\n\g<0></ol>\n', html)

    # Paragraphs (separated by double newlines)
    paragraphs = html.split('\n\n')
    html = '\n'.join([f'<p>{p}</p>' if not p.startswith(('<h', '<ul', '<ol')) else p for p in paragraphs if p.strip()])

    # Line breaks (single newlines within paragraphs, but not between block elements)
    # Split by block elements to avoid adding <br> between them
    parts = re.split(r'(<(?:h[1-6]|ul|ol|li|p)[^>]*>.*?</(?:h[1-6]|ul|ol|li|p)>)', html, flags=re.DOTALL)
    for i, part in enumerate(parts):
        # Only add <br> tags within paragraph content (not between block elements)
        if not re.match(r'^<(?:h[1-6]|ul|ol|li|p)[^>]*>.*</(?:h[1-6]|ul|ol|li|p)>$', part.strip()):
            # Replace single newlines with <br> but preserve paragraph breaks
            part = re.sub(r'([^\n])\n([^\n])', r'\1<br>\2', part)
            parts[i] = part
    html = ''.join(parts)

    return html
