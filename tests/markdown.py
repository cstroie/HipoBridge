#!/usr/bin/env python3
"""Tests for the markdown conversion utilities."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from markdown import html_to_markdown, markdown_to_html


class TestMarkdownConversion(unittest.TestCase):
    """Test cases for the markdown conversion functions."""

    def test_html_to_markdown_basic_text(self):
        """Test basic HTML to markdown conversion."""
        html = "<p>Hello World</p>"
        expected = "Hello World"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_bold_text(self):
        """Test HTML bold tags to markdown conversion."""
        html = "<p>This is <b>bold</b> text</p>"
        expected = "This is **bold** text"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_italic_text(self):
        """Test HTML italic tags to markdown conversion."""
        html = "<p>This is <i>italic</i> text</p>"
        expected = "This is *italic* text"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_underline_text(self):
        """Test HTML underline tags to markdown conversion."""
        html = "<p>This is <u>underlined</u> text</p>"
        expected = "This is *underlined* text"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_headings(self):
        """Test HTML headings to markdown conversion."""
        html = "<h1>Main Title</h1><h2>Subtitle</h2><h3>Section</h3>"
        expected = "# Main Title\n\n## Subtitle\n\n### Section"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_line_breaks(self):
        """Test HTML line breaks to markdown conversion."""
        html = "<p>Line 1<br>Line 2</p>"
        expected = "Line 1\nLine 2"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_paragraphs(self):
        """Test HTML paragraphs to markdown conversion."""
        html = "<p>Paragraph 1</p><p>Paragraph 2</p>"
        expected = "Paragraph 1\n\nParagraph 2"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_html_entities(self):
        """Test HTML entities decoding."""
        html = "<p>Price: &lt; $100 &gt; &amp; &quot;quoted&quot;</p>"
        expected = 'Price: < $100 > & "quoted"'
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_nbsp_handling(self):
        """Test non-breaking space handling."""
        html = "<p>Text&nbsp;with&nbsp;spaces</p>"
        expected = "Text with spaces"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_complex_structure(self):
        """Test complex HTML structure conversion."""
        html = """
        <h1>Patient Report</h1>
        <p><b>Patient Name:</b> John Doe</p>
        <p><i>Diagnosis:</i> Healthy</p>
        <p>Recommendations:<br>
        1. Take medication<br>
        2. Follow-up in 2 weeks</p>
        """
        result = html_to_markdown(html)
        # Check that key elements are present
        self.assertIn("# Patient Report", result)
        self.assertIn("**Patient Name:** John Doe", result)
        self.assertIn("*Diagnosis:* Healthy", result)

    def test_html_to_markdown_microsoft_office_artifacts(self):
        """Test handling of Microsoft Office specific tags."""
        html = "<p><o:p>Office text</o:p></p>"
        expected = "Office text"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_html_to_markdown_wrapper_b_tags(self):
        """Test handling of wrapper <b> tags."""
        html = "<b>Wrapped text</b>"
        expected = "Wrapped text"
        result = html_to_markdown(html)
        self.assertEqual(result, expected)

    def test_markdown_to_html_basic_text(self):
        """Test basic markdown to HTML conversion."""
        markdown = "Hello World"
        result = markdown_to_html(markdown)
        self.assertIn("<p>Hello World</p>", result)

    def test_markdown_to_html_bold_text(self):
        """Test markdown bold to HTML conversion."""
        markdown = "This is **bold** text"
        result = markdown_to_html(markdown)
        self.assertIn("<p>This is <strong>bold</strong> text</p>", result)

    def test_markdown_to_html_italic_text(self):
        """Test markdown italic to HTML conversion."""
        markdown = "This is *italic* text"
        result = markdown_to_html(markdown)
        self.assertIn("<p>This is <em>italic</em> text</p>", result)

    def test_markdown_to_html_headings(self):
        """Test markdown headings to HTML conversion."""
        markdown = "# Main Title\n\n## Subtitle\n\n### Section"
        result = markdown_to_html(markdown)
        self.assertIn("<h1>Main Title</h1>", result)
        self.assertIn("<h2>Subtitle</h2>", result)
        self.assertIn("<h3>Section</h3>", result)

    def test_markdown_to_html_unordered_lists(self):
        """Test markdown unordered lists to HTML conversion."""
        markdown = "- Item 1\n- Item 2\n- Item 3"
        result = markdown_to_html(markdown)
        self.assertIn("<ul>", result)
        self.assertIn("<li>Item 1</li>", result)
        self.assertIn("<li>Item 2</li>", result)
        self.assertIn("<li>Item 3</li>", result)

    def test_markdown_to_html_ordered_lists(self):
        """Test markdown ordered lists to HTML conversion."""
        markdown = "1. First item\n2. Second item\n3. Third item"
        result = markdown_to_html(markdown)
        self.assertIn("<ol>", result)
        self.assertIn("<li>First item</li>", result)
        self.assertIn("<li>Second item</li>", result)
        self.assertIn("<li>Third item</li>", result)

    def test_markdown_to_html_line_breaks(self):
        """Test markdown line breaks within paragraphs."""
        markdown = "Line 1\nLine 2"
        result = markdown_to_html(markdown)
        # Should be in the same paragraph with <br> tag
        self.assertIn("Line 1<br>Line 2", result)

    def test_markdown_to_html_paragraphs(self):
        """Test markdown paragraphs to HTML conversion."""
        markdown = "Paragraph 1\n\nParagraph 2"
        result = markdown_to_html(markdown)
        # Should create separate paragraphs
        self.assertIn("<p>Paragraph 1</p>", result)
        self.assertIn("<p>Paragraph 2</p>", result)

    def test_markdown_to_html_complex_structure(self):
        """Test complex markdown structure to HTML conversion."""
        markdown = """# Patient Report

## Diagnosis
The patient is **healthy**.

### Recommendations
- Take medication
- *Follow-up* in 2 weeks

1. First visit
2. Second visit"""
        
        result = markdown_to_html(markdown)
        # Check key elements are present
        self.assertIn("<h1>Patient Report</h1>", result)
        self.assertIn("<h2>Diagnosis</h2>", result)
        self.assertIn("<strong>healthy</strong>", result)
        self.assertIn("<ul>", result)
        self.assertIn("<ol>", result)


if __name__ == '__main__':
    unittest.main()
