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

Per-user snippets (2026-11-14): `snippets.cfg` is the shared base, edited by
hand; each user also has their own, edited from the frontend and kept in
`snippets/<username>.json` ({section: {name: text}}, gitignored). A
user's snippet wins over a shared one of the same name in the same section;
the order is shared common < shared modality < own common < own modality.
Deleting an own snippet that overrides a shared one brings the shared one
back; a shared one cannot be deleted from the frontend.
"""
import configparser
import json
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

# Frontend modality slugs (MODALITY_INFO in static/scripts.js) -> section names.
SECTION_OF = {
    'radio': 'radiography', 'eco': 'ultrasound', 'ct': 'ct', 'irm': 'mri',
    'rads': 'fluoroscopy', 'fluoro': 'fluoroscopy',
}

# Sections in the order the manager shows them, with their labels.
SECTIONS = [('common', 'Common'), ('ultrasound', 'Ultrasound'), ('radiography', 'X-Ray'),
            ('ct', 'CT'), ('mri', 'MRI'), ('fluoroscopy', 'Fluoroscopy')]
_SECTION_IDS = {sid for sid, _ in SECTIONS}
USER_DIR = 'snippets'
# What the editor's trigger accepts after ";" (SNIPPET_TRIGGER in scripts.js):
# a letter or digit, then letters, digits, "_" or "-".
_NAME_RE = re.compile(r'[^\W_][\w-]*')
MAX_NAME = 40
MAX_TEXT = 20000
MAX_PER_USER = 1000

_cache = {"path": None, "mtime": None, "data": {}}


class SnippetError(ValueError):
    """A snippet the user sent cannot be stored; the message is shown to them."""


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


def _shared(path: str) -> dict:
    """The parsed snippets.cfg, re-read when its mtime changes."""
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        mtime = None
    if _cache["path"] != path or _cache["mtime"] != mtime:
        _cache.update(path=path, mtime=mtime, data=load_snippets(path))
    return _cache["data"]


def _user_path(user: str, user_dir: str) -> str:
    """The user's file. A username is not trusted as a file name: anything
    but letters, digits, '.', '_' and '-' is hex-escaped, and a leading dot too."""
    safe = ''.join(c if (c.isascii() and (c.isalnum() or c in '._-')) else '%%%04x' % ord(c) for c in user)
    if safe.startswith('.'):
        safe = '%002e' + safe[1:]
    return os.path.join(user_dir, safe + '.json')


def load_user(user: str, user_dir: str = USER_DIR) -> dict:
    """{section: {name: text}} of one user; {} when none, unreadable or no user."""
    if not user:
        return {}
    try:
        with open(_user_path(user, user_dir), encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("Cannot read the snippets of a user: %s", e)
        return {}
    if not isinstance(data, dict):
        return {}
    return {sec: {str(k): str(v) for k, v in items.items()}
            for sec, items in data.items() if sec in _SECTION_IDS and isinstance(items, dict)}


def _save_user(user: str, data: dict, user_dir: str) -> None:
    """Write the user's file whole, through a temporary file (never half-written)."""
    os.makedirs(user_dir, exist_ok=True)
    path = _user_path(user, user_dir)
    data = {sec: items for sec, items in data.items() if items}
    fd, tmp = tempfile.mkstemp(dir=user_dir, prefix='.tmp-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clean_name(name) -> str:
    """The name as stored: stripped, without a leading ';', lowercased."""
    name = str(name or '').strip().lstrip(';').lower()
    if not name or len(name) > MAX_NAME or not _NAME_RE.fullmatch(name):
        raise SnippetError(f"A name is letters and digits, then also '_' or '-', at most {MAX_NAME} characters")
    return name


def set_snippet(user: str, section: str, name: str, text: str, rename_from: str = '',
                user_dir: str = USER_DIR) -> str:
    """Store one of the user's own snippets and return its name. With
    `rename_from` (the user's own snippet of that name in the section) it is
    renamed too; taking the name of another own snippet is refused."""
    if not user:
        raise SnippetError("No user")
    if section not in _SECTION_IDS:
        raise SnippetError("Unknown section")
    name = clean_name(name)
    text = str(text or '').replace('\r\n', '\n').strip()
    if not text:
        raise SnippetError("The text is empty")
    if len(text) > MAX_TEXT:
        raise SnippetError(f"The text is longer than {MAX_TEXT} characters")
    data = load_user(user, user_dir)
    items = data.setdefault(section, {})
    old = clean_name(rename_from) if rename_from else ''
    if old and old != name:
        if name in items:
            raise SnippetError(f"You already have ;{name} here")
        items.pop(old, None)
    if name not in items and sum(len(v) for v in data.values()) >= MAX_PER_USER:
        raise SnippetError(f"At most {MAX_PER_USER} snippets")
    items[name] = text
    _save_user(user, data, user_dir)
    return name


def delete_snippet(user: str, section: str, name: str, user_dir: str = USER_DIR) -> bool:
    """Remove one of the user's own snippets; False when they have none of that name."""
    data = load_user(user, user_dir)
    if not user or name not in data.get(section, {}):
        return False
    del data[section][name]
    _save_user(user, data, user_dir)
    return True


def list_all(user: str = '', path: str = 'snippets.cfg', user_dir: str = USER_DIR) -> dict:
    """Everything the manager shows: {'sections': [{'id', 'label', 'snippets':
    [{'name', 'text', 'mine', 'shared'}]}]}, names sorted. `mine`: the text is
    the user's own; `shared`: the shared text of that name (None when there is
    none), so an own snippet that overrides a shared one has both."""
    shared, own = _shared(path), load_user(user, user_dir)
    out = []
    for sid, label in SECTIONS:
        base, mine = shared.get(sid, {}), own.get(sid, {})
        rows = [{'name': n, 'text': mine.get(n, base.get(n)), 'mine': n in mine, 'shared': base.get(n)}
                for n in sorted(set(base) | set(mine))]
        out.append({'id': sid, 'label': label, 'snippets': rows})
    return {'sections': out}


def get_snippets(modality: str = '', path: str = 'snippets.cfg', user: str = '',
                 user_dir: str = USER_DIR) -> dict:
    """{name: text} for a frontend modality slug: [common] overlaid by its
    section, then by the user's own common and own section."""
    data, own = _shared(path), load_user(user, user_dir)
    section = SECTION_OF.get(modality, '')
    out = dict(data.get('common', {}))
    out.update(data.get(section, {}))
    out.update(own.get('common', {}))
    out.update(own.get(section, {}))
    return out
