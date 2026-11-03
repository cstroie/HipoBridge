"""
Report-editor snippets: `;name` + Tab in the editor textarea expands to a stored
text (the frontend does the expanding; this only serves the list).

`snippets.cfg` (gitignored, copy from examples/snippets.cfg): one section per
modality (same names as regions.cfg: radiography, ultrasound, ct, mri,
fluoroscopy) plus an optional `[common]` for every modality; each section is
`name = text`, multi-line values allowed (indented continuation lines, or a
literal `\\n` in a single line; both expand to newlines). A modality's snippet wins over a
common one of the same name, so `;abd` can differ between ultrasound and X-ray.
Names are lowercased by configparser. A missing or broken file yields an empty
list, never an error. The file is re-read when its mtime changes, so edits need
no restart.
"""
import configparser
import logging
import os

logger = logging.getLogger(__name__)

# Frontend modality slugs (MODALITY_INFO in static/scripts.js) -> section names.
SECTION_OF = {
    'radio': 'radiography', 'eco': 'ultrasound', 'ct': 'ct', 'irm': 'mri',
    'rads': 'fluoroscopy', 'fluoro': 'fluoroscopy',
}

_cache = {"path": None, "mtime": None, "data": {}}


def load_snippets(path: str = 'snippets.cfg') -> dict:
    """Return {section: {name: text}}; {} when the file is absent/invalid."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if not parser.read(path, encoding='utf-8'):
            return {}
    except (configparser.Error, UnicodeDecodeError) as e:
        logger.warning("Cannot parse %s: %s", path, e)
        return {}
    return {sec.lower(): {k: v.strip().replace('\\n', '\n') for k, v in parser.items(sec) if v.strip()}
            for sec in parser.sections()}


def get_snippets(modality: str = '', path: str = 'snippets.cfg') -> dict:
    """{name: text} for a frontend modality slug: [common] overlaid by its section."""
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        mtime = None
    if _cache["path"] != path or _cache["mtime"] != mtime:
        _cache.update(path=path, mtime=mtime, data=load_snippets(path))
    data = _cache["data"]
    out = dict(data.get('common', {}))
    out.update(data.get(SECTION_OF.get(modality, ''), {}))
    return out
