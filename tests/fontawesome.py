#!/usr/bin/env python3
"""static/fontawesome.css is a curated subset: every fa-* class the frontend
uses must have a rule there, or the icon renders blank."""

import os
import re
import unittest

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')
SOURCES = ('main.html', 'scripts.js')
USE = re.compile(r'(?<![\w-])fa-[a-z0-9]+(?:-[a-z0-9]+)*(?![\w-])')


class TestFontAwesomeSubset(unittest.TestCase):
    def test_every_used_class_is_defined(self):
        with open(os.path.join(STATIC, 'fontawesome.css'), encoding='utf-8') as f:
            defined = set(re.findall(r'\.(fa-[a-z0-9-]+)', f.read()))
        missing = {}
        for name in SOURCES:
            with open(os.path.join(STATIC, name), encoding='utf-8') as f:
                for lineno, line in enumerate(f, 1):
                    for cls in USE.findall(line):
                        if cls not in defined:
                            missing.setdefault(cls, f'{name}:{lineno}')
        self.assertEqual(missing, {}, 'fa-* classes missing from static/fontawesome.css (first use shown)')


if __name__ == '__main__':
    unittest.main()
