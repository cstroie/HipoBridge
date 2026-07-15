"""JSON-schema -> GBNF grammar conversion.

Backend-agnostic on purpose: `InProcessBackend` wraps the returned string in
`LlamaGrammar.from_string()`, `ServerBackend` sends it as-is in the request
payload (`grammar` field or `response_format`, per `server_grammar_mode`).

Grammar guarantees *shape*, not *semantic correctness* — pydantic validation
after generation still catches malformed content (bad date format,
out-of-range values, unexpected enum).

Covers the subset of JSON Schema that pydantic's `model_json_schema()`
actually emits for the schemas in `llm/schemas.py`: object/properties/
required, string/integer/number/boolean, array + items, enum, anyOf
(used for `X | None`), and `$defs`/`$ref`.
"""
import json
import re

_PRIMITIVE_RULES = {
    "boolean": r'"true" | "false"',
    "null": r'"null"',
    "number": r'("-"? ([0-9] | [1-9] [0-9]*)) ("." [0-9]+)? (("e" | "E") ("-" | "+")? [0-9]+)?',
    "integer": r'"-"? ([0-9] | [1-9] [0-9]*)',
    "string": r'"\"" ( [^"\\\x7F\x00-\x1F] | "\\" (["\\bfnrt] | "u" [0-9a-fA-F]{4}) )* "\""',
}


class _GrammarBuilder:
    def __init__(self, schema: dict):
        self._root_schema = schema
        self._defs = schema.get("$defs", schema.get("definitions", {}))
        self._rules: dict[str, str] = {}
        # Bounded to 0-or-1 whitespace char, not [ \t\n]* — an unbounded
        # repeat gives small/undertrained models an escape hatch to loop on
        # whitespace forever instead of committing to content, since "more
        # whitespace" stays grammatically valid at every ws expansion point.
        # Confirmed empirically against a real LFM2.5-230M llama-server: `*`
        # ran the model out of its token budget emitting spaces after `:`.
        self._rules["ws"] = r'[ \t\n]?'
        for name, body in _PRIMITIVE_RULES.items():
            self._rules[name] = body

    def _add_rule(self, name: str, body: str) -> str:
        # Sanitize the rule *identifier* only — never the JSON content it
        # matches. Confirmed empirically against a real llama-server build:
        # a GBNF rule name containing '_' makes that rule silently fail to
        # apply, degrading the whole grammar to unconstrained generation
        # with no error surfaced (the server still echoes the grammar back
        # as "accepted"). Field names like `body_region` are common in our
        # schemas, so this isn't a hypothetical edge case.
        name = name.replace("_", "-")
        candidate = name
        i = 0
        while candidate in self._rules and self._rules[candidate] != body:
            i += 1
            candidate = f"{name}-{i}"
        self._rules[candidate] = body
        return candidate

    def _resolve_ref(self, ref: str) -> dict:
        key = ref.rsplit("/", 1)[-1]
        if key not in self._defs:
            raise ValueError(f"unresolved $ref: {ref}")
        return self._defs[key]

    def visit(self, schema: dict, name: str = "root") -> str:
        if "$ref" in schema:
            return self.visit(self._resolve_ref(schema["$ref"]), name)

        if "const" in schema:
            return self._add_rule(name, _gbnf_literal(json.dumps(schema["const"])))

        if "enum" in schema:
            alts = " | ".join(_gbnf_literal(json.dumps(v)) for v in schema["enum"])
            return self._add_rule(name, alts)

        if "anyOf" in schema or "oneOf" in schema:
            options = schema.get("anyOf") or schema.get("oneOf")
            alts = " | ".join(self.visit(o, f"{name}-alt") for o in options)
            return self._add_rule(name, alts)

        schema_type = schema.get("type")

        if schema_type == "object" or "properties" in schema:
            return self._visit_object(schema, name)

        if schema_type == "array":
            items_schema = schema.get("items", {})
            item_rule = self.visit(items_schema, f"{name}-item")
            body = (
                f'"[" ws ({item_rule} (ws "," ws {item_rule})*)? ws "]"'
            )
            return self._add_rule(name, body)

        if schema_type in _PRIMITIVE_RULES:
            return schema_type

        if schema_type == "string" and "format" in schema:
            return "string"

        # Fallback: any JSON value (unconstrained) — keeps unknown schema
        # fragments from crashing the converter; pydantic still validates
        # semantic correctness after generation.
        return self._add_rule(name, "string | number | boolean | null")

    def _visit_object(self, schema: dict, name: str) -> str:
        # All properties are emitted as required keys in the grammar, even
        # when pydantic marks them optional — the model is instructed to use
        # `null` for unstated fields (see llm/prompts), rather than omitting
        # the key, which keeps comma placement in the generated grammar
        # trivial instead of needing GBNF's awkward optional-tail encoding.
        properties: dict = schema.get("properties", {})
        if not properties:
            return self._add_rule(name, r'"{" ws "}"')

        parts = []
        for prop_name, prop_schema in properties.items():
            value_rule = self.visit(prop_schema, f"{name}-{prop_name}")
            key_literal = _gbnf_literal(json.dumps(prop_name))
            parts.append(f'{key_literal} ws ":" ws {value_rule}')

        body = '"{" ws ' + ' ws "," ws '.join(parts) + ' ws "}"'
        return self._add_rule(name, body)

    def build(self, root_schema: dict) -> str:
        root_rule = self.visit(root_schema, "root")
        self._rules["root"] = self._rules.pop(root_rule) if root_rule != "root" else self._rules["root"]
        lines = [f"{n} ::= {b}" for n, b in self._rules.items() if n != "root"]
        lines.insert(0, f"root ::= {self._rules['root']}")
        return "\n".join(lines) + "\n"


def to_gbnf(json_schema: dict) -> str:
    """Convert a JSON schema (as produced by `BaseModel.model_json_schema()`)
    into a GBNF grammar string constraining generation to that shape."""
    builder = _GrammarBuilder(json_schema)
    return builder.build(json_schema)


_RULE_DEF_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*::=', re.MULTILINE)
_RULE_REF_RE = re.compile(r'(?<![:"])\b[A-Za-z_][A-Za-z0-9_-]*\b(?!\s*::=)')
_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_CHAR_CLASS_RE = re.compile(r'\[(?:[^\]\\]|\\.)*\]')


def _gbnf_literal(text: str) -> str:
    """Escape arbitrary text into a GBNF string literal matching it exactly.

    `json.dumps(x)` alone is NOT a GBNF literal for `x` — its surrounding
    quotes get consumed as GBNF's own literal delimiters, so embedding
    `json.dumps("type")` (-> `"type"`) directly into a rule body produces a
    grammar matching the *bare* word `type`, not the JSON-quoted key
    `"type"`. Confirmed empirically: this bug made a real llama-server
    grammar-constrained call demand unquoted keys/values, which the model
    couldn't satisfy naturally and produced garbled/unconstrained-looking
    output despite the grammar "compiling" fine.
    """
    escaped = text.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'

# GBNF keywords/character-class fragments that look like bare identifiers
# but aren't rule references.
_NON_RULE_TOKENS = {"ws"}


def validate_gbnf(grammar: str) -> None:
    """Structural self-check: every rule referenced by name is defined, and
    quotes/brackets balance. Not a full GBNF parser (no llama.cpp available
    in this environment to cross-check against) — catches the class of bugs
    a hand-rolled generator is prone to (typo'd/omitted rule names,
    unbalanced literals) before they reach a real grammar-constrained call.
    """
    defined = set(_RULE_DEF_RE.findall(grammar))
    if "root" not in defined:
        raise ValueError("grammar has no root rule")

    # Strip string literals and [...] character classes so their contents
    # don't get mistaken for rule references, then collect every remaining
    # bare-identifier token.
    stripped = _STRING_LITERAL_RE.sub('""', grammar)
    stripped = _CHAR_CLASS_RE.sub('[]', stripped)
    for line in stripped.splitlines():
        if "::=" not in line:
            continue
        _, _, body = line.partition("::=")
        for token in _RULE_REF_RE.findall(body):
            if token in defined:
                continue
            raise ValueError(f"grammar references undefined rule: {token!r}")

    for open_c, close_c in (("(", ")"), ("[", "]")):
        if grammar.count(open_c) != grammar.count(close_c):
            raise ValueError(f"unbalanced {open_c!r}/{close_c!r} in grammar")
    if grammar.count('"') % 2 != 0:
        raise ValueError("unbalanced quotes in grammar")
