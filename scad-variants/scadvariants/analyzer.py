from __future__ import annotations

import hashlib
import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


class AnalysisError(RuntimeError):
    """A .scad file could not be analysed safely."""


# ---------------------------------------------------------------------------
#  Tokenizer
# ---------------------------------------------------------------------------

_MULTI_OPS = (
    "&&", "||", "==", "!=", "<=", ">=", "++", "--", "+=", "-=", "*=", "/=",
    "%=", "<<", ">>", "=>",
)
_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_STRING_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\\": "\\",
    '"': '"',
}


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str
    start: int
    end: int
    line: int
    raw: str


@dataclass(frozen=True, slots=True)
class Comment:
    start: int
    end: int


def _decode_string(raw: str) -> str:
    # raw includes the surrounding quotes
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append(_STRING_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def tokenize(text: str) -> tuple[list[Token], list[Comment]]:
    tokens: list[Token] = []
    comments: list[Comment] = []
    i = 0
    line = 1
    n = len(text)

    while i < n:
        c = text[i]

        if c in " \t\r\f\v":
            i += 1
            continue
        if c == "\n":
            line += 1
            i += 1
            continue

        # comments -----------------------------------------------------------
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            start = i
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            comments.append(Comment(start, i))
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    line += 1
                i += 1
            if i + 1 >= n:
                raise AnalysisError(f"unterminated block comment at line {line}")
            i += 2
            comments.append(Comment(start, i))
            continue

        # strings ------------------------------------------------------------
        if c == '"':
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                if text[i] == "\n":
                    line += 1
                i += 1
            else:
                raise AnalysisError(f"unterminated string at line {line}")
            raw = text[start:i]
            try:
                value = _decode_string(raw)
            except Exception as exc:  # pragma: no cover - defensive
                raise AnalysisError(f"bad string at line {line}: {exc}") from exc
            tokens.append(Token("string", value, start, i, line, raw))
            continue

        # numbers ------------------------------------------------------------
        m = _NUMBER_RE.match(text, i)
        if m and (c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit())):
            raw = m.group(0)
            tokens.append(Token("number", raw, i, m.end(), line, raw))
            i = m.end()
            continue

        # identifiers --------------------------------------------------------
        m = _IDENT_RE.match(text, i)
        if m:
            raw = m.group(0)
            tokens.append(Token("ident", raw, i, m.end(), line, raw))
            i = m.end()
            continue

        # operators / punctuation -------------------------------------------
        op = next((o for o in _MULTI_OPS if text.startswith(o, i)), None)
        if op is None:
            op = c
        tokens.append(Token("op", op, i, i + len(op), line, op))
        i += len(op)

    return tokens, comments


def bracket_matches(tokens: Sequence[Token]) -> dict[int, int]:
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = {"(": ")", "[": "]", "{": "}"}
    stack: list[tuple[str, int]] = []
    matches: dict[int, int] = {}
    for idx, tok in enumerate(tokens):
        v = tok.value
        if v in opening:
            stack.append((v, idx))
        elif v in pairs:
            if not stack or stack[-1][0] != pairs[v]:
                raise AnalysisError(f"unbalanced '{v}' at line {tok.line}")
            _, opening_idx = stack.pop()
            matches[opening_idx] = idx
            matches[idx] = opening_idx
    if stack:
        opening_char, idx = stack[-1]
        raise AnalysisError(
            f"unclosed '{opening_char}' from line {tokens[idx].line}"
        )
    return matches


# ---------------------------------------------------------------------------
#  Switch discovery
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Switch:
    name: str
    default: str
    options: list[str]
    origin: str
    literal_span: tuple[int, int]
    line: int

    def signature(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "default": self.default,
            "options": list(self.options),
            "origin": self.origin,
        }


@dataclass(slots=True)
class ScadFile:
    path: Path
    text: str
    tokens: list[Token]
    comments: list[Comment]
    switches: list[Switch]
    dependencies: list[Path]
    raw_sha256: str = ""
    line_count: int = 0

    @property
    def relpath(self) -> str:
        return str(self.path)


@dataclass(frozen=True, slots=True)
class Variant:
    values: dict[str, str]
    variant_id: str
    label: str

    def signature(self) -> dict[str, str]:
        return dict(self.values)


def _parse_customizer_options(comment: str) -> list[str]:
    m = re.search(r"//\s*\[([^\]]*)\]", comment)
    if not m:
        return []
    body = m.group(1)
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escape = False
    for c in body:
        if escape:
            current.append(c)
            escape = False
        elif c == "\\" and quote:
            current.append(c)
            escape = True
        elif quote:
            current.append(c)
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            current.append(c)
        elif c == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(c)
    parts.append("".join(current))
    out: list[str] = []
    for part in parts:
        value = part.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and value not in out:
            out.append(value)
    return out


def _top_level_string_assignments(
    text: str, tokens: Sequence[Token]
) -> list[tuple[str, str, Token, list[str], int]]:
    """Return (name, value, string_token, customizer_options, line)."""
    found: list[tuple[str, str, Token, list[str], int]] = []
    depth = 0
    for idx, tok in enumerate(tokens):
        v = tok.value
        if v in ("{", "(", "["):
            depth += 1
            continue
        if v in ("}", ")", "]"):
            depth -= 1
            continue
        if depth != 0 or v != "=":
            continue
        if idx == 0 or idx + 2 >= len(tokens):
            continue
        prev, nxt, after = tokens[idx - 1], tokens[idx + 1], tokens[idx + 2]
        if prev.kind != "ident" or nxt.kind != "string" or after.value != ";":
            continue
        if prev.value in {
            "if", "else", "for", "module", "function", "use", "include",
            "let", "each", "assert", "echo",
        }:
            continue
        name = prev.value
        # The trailing customizer annotation, if any, is on the same line.
        line_end = text.find("\n", after.end)
        if line_end < 0:
            line_end = len(text)
        tail = text[after.end:line_end]
        options = _parse_customizer_options(tail)
        found.append((name, nxt.value, nxt, options, nxt.line))
    return found


def _switch_comparison_options(
    tokens: Sequence[Token], names: set[str]
) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {name: [] for name in names}
    for idx in range(len(tokens) - 2):
        a, op, b = tokens[idx], tokens[idx + 1], tokens[idx + 2]
        if op.value != "==":
            continue
        name: str | None = None
        value: str | None = None
        if a.kind == "ident" and a.value in names and b.kind == "string":
            name, value = a.value, b.value
        elif a.kind == "string" and b.kind == "ident" and b.value in names:
            name, value = b.value, a.value
        if name is not None and value not in options[name]:
            options[name].append(value)
    return options


# ---------------------------------------------------------------------------
#  Dependencies
# ---------------------------------------------------------------------------

_USE_RE = re.compile(r"(?m)^[ \t]*(use|include)[ \t]*<([^>\n]+)>")


def _without_comments(text: str, comments: Sequence[Comment]) -> str:
    if not comments:
        return text
    chars = list(text)
    for c in comments:
        for i in range(c.start, c.end):
            if chars[i] not in "\r\n":
                chars[i] = " "
    return "".join(chars)


def direct_dependencies(path: Path, text: str, comments: Sequence[Comment]) -> list[Path]:
    clean = _without_comments(text, comments)
    deps: list[Path] = []
    for m in _USE_RE.finditer(clean):
        raw = m.group(2).strip().strip('"')
        if not raw:
            continue
        dep = Path(raw)
        if not dep.is_absolute():
            dep = path.parent / dep
        dep = dep.resolve()
        if dep not in deps:
            deps.append(dep)
    return deps


def analyze_scad(path: Path) -> ScadFile:
    path = path.resolve()
    if not path.is_file():
        raise AnalysisError(f"file not found: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalysisError(f"{path.name}: cannot read: {exc}") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AnalysisError(f"{path.name}: not UTF-8: {exc}") from exc
    raw_sha256 = hashlib.sha256(raw).hexdigest()

    tokens, comments = tokenize(text)
    bracket_matches(tokens)  # validate brackets early

    assignments = _top_level_string_assignments(text, tokens)
    if not assignments:
        return ScadFile(
            path=path,
            text=text,
            tokens=tokens,
            comments=comments,
            switches=[],
            dependencies=direct_dependencies(path, text, comments),
            raw_sha256=raw_sha256,
            line_count=text.count("\n") + 1,
        )

    names = {name for name, *_ in assignments}
    code_options = _switch_comparison_options(tokens, names)

    switches: list[Switch] = []
    for name, default, literal_token, customizer, line in assignments:
        found = list(code_options.get(name, []))
        if customizer:
            ordered: list[str] = []
            for value in [default, *customizer, *found]:
                if value not in ordered:
                    ordered.append(value)
            options = ordered
            origin = "customizer+code" if found else "customizer"
        else:
            ordered = []
            for value in [default, *found]:
                if value not in ordered:
                    ordered.append(value)
            options = ordered
            origin = "code-comparisons"

        # A textual parameter is a switch only when the code/documentation
        # really enumerates at least two alternatives.  Numeric parameters are
        # deliberately not expanded.
        if len(options) < 2:
            continue
        switches.append(
            Switch(
                name=name,
                default=default,
                options=options,
                origin=origin,
                literal_span=(literal_token.start, literal_token.end),
                line=line,
            )
        )

    return ScadFile(
        path=path,
        text=text,
        tokens=tokens,
        comments=comments,
        switches=switches,
        dependencies=direct_dependencies(path, text, comments),
        raw_sha256=raw_sha256,
        line_count=text.count("\n") + 1,
    )


def dependency_closure(paths: Iterable[Path], max_depth: int = 20) -> list[Path]:
    seen: list[Path] = []
    queue = [(Path(p).resolve(), 0) for p in paths]
    while queue:
        path, depth = queue.pop(0)
        if path in seen or depth > max_depth:
            continue
        seen.append(path)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            _, comments = tokenize(text)
        except AnalysisError:
            continue
        for dep in direct_dependencies(path, text, comments):
            if dep not in seen:
                queue.append((dep, depth + 1))
    return seen


# ---------------------------------------------------------------------------
#  Variant enumeration
# ---------------------------------------------------------------------------

def _slug(value: str, limit: int = 48) -> str:
    out = []
    for c in value:
        if c.isascii() and (c.isalnum() or c in "-_"):
            out.append(c)
        elif c in " .":
            out.append("_")
    s = "".join(out).strip("_")
    if not s:
        s = "v"
    if len(s) > limit:
        s = s[:limit].rstrip("_") + "-" + hashlib.sha1(value.encode()).hexdigest()[:6]
    return s


def variant_stem(values: dict[str, str], limit: int = 110) -> str:
    """Filename stem for a variant (without .png/.stl)."""
    if not values:
        return "default"
    raw = "__".join(f"{name}-{value}" for name, value in values.items())
    return _slug(raw, limit)


def build_variants(switches: Sequence[Switch], max_variants: int = 64) -> list[Variant]:
    if not switches:
        return [Variant(values={}, variant_id="default", label="по умолчанию")]

    combinations = 1
    for sw in switches:
        combinations *= len(sw.options)
    if combinations > max_variants:
        raise AnalysisError(
            f"too many switch combinations: {combinations} > {max_variants}"
        )

    variants: list[Variant] = []
    used_ids: set[str] = set()
    for combo in itertools.product(*(sw.options for sw in switches)):
        values = {sw.name: value for sw, value in zip(switches, combo)}
        raw_id = "__".join(f"{name}-{value}" for name, value in values.items())
        variant_id = _slug(raw_id, 110)
        if variant_id in used_ids:
            variant_id += "-" + hashlib.sha1(raw_id.encode()).hexdigest()[:6]
        used_ids.add(variant_id)
        label = " · ".join(f'{name} = "{value}"' for name, value in values.items())
        variants.append(Variant(values=values, variant_id=variant_id, label=label))
    return variants


# ---------------------------------------------------------------------------
#  A tiny expression evaluator for if() conditions
# ---------------------------------------------------------------------------

class _Unknown:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNKNOWN"


UNKNOWN = _Unknown()


class _ParseError(Exception):
    pass


class _ExprParser:
    def __init__(self, tokens: Sequence[Token], values: dict[str, str]):
        self.tokens = tokens
        self.values = values
        self.pos = 0

    def parse(self) -> Any:
        try:
            value = self._or()
        except (_ParseError, ZeroDivisionError, TypeError, ValueError):
            return UNKNOWN
        if self.pos != len(self.tokens):
            # A ternary, array, or anything more complex: keep both branches.
            return UNKNOWN
        return value

    def _peek(self) -> str | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos].value

    def _take(self, expected: str | None = None) -> Token:
        if self.pos >= len(self.tokens):
            raise _ParseError("unexpected end")
        tok = self.tokens[self.pos]
        if expected is not None and tok.value != expected:
            raise _ParseError(f"expected {expected!r}")
        self.pos += 1
        return tok

    def _or(self) -> Any:
        left = self._and()
        while self._peek() == "||":
            self._take()
            right = self._and()
            left = _logic_or(left, right)
        return left

    def _and(self) -> Any:
        left = self._eq()
        while self._peek() == "&&":
            self._take()
            right = self._eq()
            left = _logic_and(left, right)
        return left

    def _eq(self) -> Any:
        left = self._cmp()
        while self._peek() in ("==", "!="):
            op = self._take().value
            right = self._cmp()
            if left is UNKNOWN or right is UNKNOWN:
                left = UNKNOWN
            elif op == "==":
                left = left == right
            else:
                left = left != right
        return left

    def _cmp(self) -> Any:
        left = self._add()
        while self._peek() in ("<", "<=", ">", ">="):
            op = self._take().value
            right = self._add()
            if left is UNKNOWN or right is UNKNOWN:
                left = UNKNOWN
                continue
            try:
                if op == "<":
                    left = left < right
                elif op == "<=":
                    left = left <= right
                elif op == ">":
                    left = left > right
                else:
                    left = left >= right
            except TypeError:
                left = UNKNOWN
        return left

    def _add(self) -> Any:
        left = self._mul()
        while self._peek() in ("+", "-"):
            op = self._take().value
            right = self._mul()
            if left is UNKNOWN or right is UNKNOWN:
                left = UNKNOWN
            elif op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def _mul(self) -> Any:
        left = self._unary()
        while self._peek() in ("*", "/", "%"):
            op = self._take().value
            right = self._unary()
            if left is UNKNOWN or right is UNKNOWN:
                left = UNKNOWN
            elif op == "*":
                left = left * right
            elif op == "/":
                left = left / right
            else:
                left = left % right
        return left

    def _unary(self) -> Any:
        op = self._peek()
        if op == "!":
            self._take()
            value = self._unary()
            return UNKNOWN if value is UNKNOWN else (not _truthy(value))
        if op == "-":
            self._take()
            value = self._unary()
            if value is UNKNOWN:
                return UNKNOWN
            return -value
        if op == "+":
            self._take()
            return self._unary()
        return self._primary()

    def _primary(self) -> Any:
        tok = self._take()
        if tok.kind == "string":
            return tok.value
        if tok.kind == "number":
            try:
                if any(ch in tok.value for ch in ".eE"):
                    return float(tok.value)
                return int(tok.value)
            except ValueError:
                raise _ParseError("bad number")
        if tok.kind == "ident":
            if tok.value == "true":
                return True
            if tok.value == "false":
                return False
            if tok.value == "undef":
                return UNKNOWN
            if self._peek() == "(":
                self._skip_balanced("(", ")")
                return UNKNOWN
            return self.values.get(tok.value, UNKNOWN)
        if tok.value == "(":
            value = self._or()
            self._take(")")
            return value
        if tok.value == "[":
            self._skip_balanced("[", "]")
            return UNKNOWN
        raise _ParseError(f"unexpected {tok.value!r}")

    def _skip_balanced(self, opening: str, closing: str) -> None:
        self._take(opening)
        depth = 1
        while self.pos < len(self.tokens):
            tok = self._take()
            if tok.value == opening:
                depth += 1
            elif tok.value == closing:
                depth -= 1
                if depth == 0:
                    return
        raise _ParseError("unbalanced")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    raise _ParseError("not a boolean")


def _logic_or(left: Any, right: Any) -> Any:
    if left is not UNKNOWN and _truthy(left):
        return True
    if left is not UNKNOWN and not _truthy(left):
        if right is UNKNOWN:
            return UNKNOWN
        return bool(_truthy(right))
    # left unknown
    if right is not UNKNOWN and _truthy(right):
        return True
    return UNKNOWN


def _logic_and(left: Any, right: Any) -> Any:
    if left is not UNKNOWN and not _truthy(left):
        return False
    if left is not UNKNOWN and _truthy(left):
        if right is UNKNOWN:
            return UNKNOWN
        return bool(_truthy(right))
    # left unknown
    if right is not UNKNOWN and not _truthy(right):
        return False
    return UNKNOWN


def evaluate_condition(tokens: Sequence[Token], values: dict[str, str]) -> Any:
    return _ExprParser(tokens, values).parse()


# ---------------------------------------------------------------------------
#  Inactive branch detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _ModuleSpan:
    start: int
    end: int
    params: frozenset[str]
    locals: frozenset[str]


def _module_spans(tokens: Sequence[Token], matches: dict[int, int]) -> list[_ModuleSpan]:
    spans: list[_ModuleSpan] = []
    for idx, tok in enumerate(tokens):
        if tok.kind != "ident" or tok.value != "module":
            continue
        if idx + 2 >= len(tokens):
            continue
        name_tok, open_tok = tokens[idx + 1], tokens[idx + 2]
        if name_tok.kind != "ident" or open_tok.value != "(":
            continue
        close = matches.get(idx + 2)
        if close is None:
            continue
        # Find the body opening brace after the parameter list.
        body_open = None
        for j in range(close + 1, min(len(tokens), close + 4)):
            if tokens[j].value == "{":
                body_open = j
                break
        if body_open is None or body_open not in matches:
            continue
        params: set[str] = set()
        for tok in tokens[idx + 3:close]:
            if tok.kind == "ident" and tok.value not in {"true", "false", "undef"}:
                params.add(tok.value)
        local_names: set[str] = set()
        body_end = matches[body_open]
        for j in range(body_open + 1, body_end):
            if (
                tokens[j].kind == "ident"
                and j + 1 < body_end
                and tokens[j + 1].value == "="
            ):
                local_names.add(tokens[j].value)
        spans.append(
            _ModuleSpan(
                start=body_open,
                end=body_end,
                params=frozenset(params),
                locals=frozenset(local_names),
            )
        )
    return spans


def _parse_statement_end(
    tokens: Sequence[Token], matches: dict[int, int], start: int
) -> int:
    if start >= len(tokens):
        return len(tokens)
    if tokens[start].value == "{":
        return matches.get(start, len(tokens)) + 1

    if tokens[start].value == "if":
        # if (...) statement [else statement]
        if start + 1 < len(tokens) and tokens[start + 1].value == "(":
            close = matches.get(start + 1)
            if close is None:
                return len(tokens)
            then_end = _parse_statement_end(tokens, matches, close + 1)
            if then_end < len(tokens) and tokens[then_end].value == "else":
                return _parse_statement_end(tokens, matches, then_end + 1)
            return then_end
        return len(tokens)

    depth = 0
    j = start
    while j < len(tokens):
        v = tokens[j].value
        if v in ("(", "["):
            depth += 1
        elif v in (")", "]"):
            if depth > 0:
                depth -= 1
        elif v == "{":
            if depth == 0:
                return matches.get(j, len(tokens)) + 1
            depth += 1
        elif v == "}":
            if depth == 0:
                return j
            depth -= 1
        elif v == ";" and depth == 0:
            return j + 1
        j += 1
    return len(tokens)


def _shadowed(
    idx: int, spans: Sequence[_ModuleSpan], switch_names: set[str]
) -> bool:
    for span in spans:
        if span.start <= idx <= span.end and (span.params | span.locals) & switch_names:
            return True
    return False


def inactive_ranges(
    tokens: Sequence[Token], matches: dict[int, int], values: dict[str, str]
) -> list[tuple[int, int]]:
    """Character ranges that are statically unreachable for this variant."""
    if not values:
        return []
    switch_names = set(values)
    modules = _module_spans(tokens, matches)
    ranges: list[tuple[int, int]] = []

    for idx, tok in enumerate(tokens):
        if tok.kind != "ident" or tok.value != "if":
            continue
        if idx + 1 >= len(tokens) or tokens[idx + 1].value != "(":
            continue
        close = matches.get(idx + 1)
        if close is None:
            continue
        if _shadowed(idx, modules, switch_names):
            continue
        condition = tokens[idx + 2:close]
        result = evaluate_condition(condition, values)
        if result is UNKNOWN:
            continue
        try:
            want_then = _truthy(result)
        except _ParseError:
            continue

        then_start = close + 1
        then_end = _parse_statement_end(tokens, matches, then_start)
        else_start = None
        else_end = None
        if then_end < len(tokens) and tokens[then_end].value == "else":
            else_start = then_end + 1
            else_end = _parse_statement_end(tokens, matches, else_start)

        if want_then and else_start is not None and else_end is not None:
            ranges.append((tokens[else_start].start, tokens[else_end - 1].end))
        elif not want_then:
            ranges.append((tokens[then_start].start, tokens[then_end - 1].end))
    return ranges


def _in_ranges(start: int, ranges: Sequence[tuple[int, int]]) -> bool:
    for a, b in ranges:
        if a <= start < b:
            return True
    return False


# ---------------------------------------------------------------------------
#  Stable per-variant hashing
# ---------------------------------------------------------------------------

HASH_SCHEMA = "scad-variants/4"


@dataclass(frozen=True, slots=True)
class _Definition:
    name: str
    start: int
    end: int  # inclusive token index


@dataclass(frozen=True, slots=True)
class _Assignment:
    name: str
    start: int
    end: int  # inclusive token index


def _token_depths(tokens: Sequence[Token]) -> list[int]:
    depth = 0
    out: list[int] = []
    for tok in tokens:
        out.append(depth)
        if tok.value in ("{", "(", "["):
            depth += 1
        elif tok.value in ("}", ")", "]"):
            depth = max(0, depth - 1)
    return out


def _projection_nodes(
    tokens: Sequence[Token], matches: dict[int, int]
) -> tuple[dict[str, _Definition], dict[str, _Assignment], list[int]]:
    depths = _token_depths(tokens)
    definitions: dict[str, _Definition] = {}
    assignments: dict[str, _Assignment] = {}

    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if depths[i] != 0 or tok.kind != "ident":
            i += 1
            continue
        if tok.value == "module" and i + 2 < n:
            name_tok, open_tok = tokens[i + 1], tokens[i + 2]
            if name_tok.kind == "ident" and open_tok.value == "(":
                close = matches.get(i + 2)
                if close is not None:
                    body = None
                    for j in range(close + 1, min(n, close + 4)):
                        if tokens[j].value == "{":
                            body = j
                            break
                    if body is not None and body in matches:
                        definitions[name_tok.value] = _Definition(
                            name=name_tok.value,
                            start=i,
                            end=matches[body],
                        )
                        i = matches[body] + 1
                        continue
        if tok.value == "function" and i + 2 < n:
            name_tok = tokens[i + 1]
            if name_tok.kind == "ident" and tokens[i + 2].value == "(":
                close = matches.get(i + 2)
                if close is not None:
                    # function ... = expression ;
                    depth = 0
                    j = close + 1
                    while j < n:
                        v = tokens[j].value
                        if v in ("(", "[", "{"):
                            depth += 1
                        elif v in (")", "]", "}"):
                            depth = max(0, depth - 1)
                        elif v == ";" and depth == 0:
                            definitions[name_tok.value] = _Definition(
                                name=name_tok.value,
                                start=i,
                                end=j,
                            )
                            i = j + 1
                            break
                        j += 1
                    if name_tok.value in definitions:
                        continue
        if i + 1 < n and tokens[i + 1].value == "=":
            depth = 0
            j = i + 1
            while j < n:
                v = tokens[j].value
                if v in ("(", "[", "{"):
                    depth += 1
                elif v in (")", "]", "}"):
                    depth = max(0, depth - 1)
                elif v == ";" and depth == 0:
                    assignments[tok.value] = _Assignment(
                        name=tok.value,
                        start=i,
                        end=j,
                    )
                    i = j
                    break
                j += 1
        i += 1

    stmt_tokens: list[int] = []
    for idx in range(n):
        if depths[idx] != 0:
            # Still part of a top-level statement body for brace-less ifs?
            # We only exclude complete definition/assignment ranges below.
            pass
        covered = False
        for node in itertools.chain(definitions.values(), assignments.values()):
            if node.start <= idx <= node.end:
                covered = True
                break
        if not covered:
            stmt_tokens.append(idx)
    return definitions, assignments, stmt_tokens


def _active_indices(
    scad: ScadFile,
    values: dict[str, str],
    matches: dict[int, int],
) -> set[int]:
    excluded = inactive_ranges(scad.tokens, matches, values)
    return {
        idx
        for idx, tok in enumerate(scad.tokens)
        if not _in_ranges(tok.start, excluded)
    }


def canonical_tokens(
    scad: ScadFile, values: dict[str, str] | None = None
) -> bytes:
    """Token stream with comments, dead branches and unused code removed.

    A variant only depends on the top-level assignments and module/function
    definitions that are actually reachable from the code that runs for that
    switch value.  Formatting and comments never affect the cache key.
    """
    values = values or {}
    matches = bracket_matches(scad.tokens)
    active = _active_indices(scad, values, matches)
    definitions, assignments, stmt_tokens = _projection_nodes(
        scad.tokens, matches
    )

    def is_active(idx: int) -> bool:
        return idx in active

    included_assign: set[str] = {name for name in assignments if name.startswith("$")}
    included_defs: set[str] = set()
    scanned: set[int] = set()
    queue: list[int] = list(stmt_tokens)

    def scan_indices(indices: Iterable[int]) -> None:
        for idx in indices:
            if idx in scanned or not is_active(idx):
                continue
            scanned.add(idx)
            tok = scad.tokens[idx]
            if tok.kind != "ident":
                continue
            name = tok.value
            if name in definitions and idx + 1 < len(scad.tokens) and scad.tokens[idx + 1].value == "(":
                if name not in included_defs:
                    included_defs.add(name)
                    node = definitions[name]
                    queue.extend(range(node.start, node.end + 1))
            if name in assignments and name not in included_assign:
                included_assign.add(name)
                node = assignments[name]
                queue.extend(range(node.start, node.end + 1))

    # Explicit global special variables are always part of the environment.
    for name in included_assign:
        node = assignments[name]
        queue.extend(range(node.start, node.end + 1))

    while queue:
        idx = queue.pop()
        scan_indices([idx])

    selected: set[int] = {idx for idx in stmt_tokens if is_active(idx)}
    for name in included_assign:
        node = assignments[name]
        selected.update(i for i in range(node.start, node.end + 1) if is_active(i))
    for name in included_defs:
        node = definitions[name]
        selected.update(i for i in range(node.start, node.end + 1) if is_active(i))

    switch_literals = {
        sw.literal_span for sw in scad.switches if sw.name in values
    }
    literal_to_name = {
        sw.literal_span: sw.name for sw in scad.switches
    }

    h = hashlib.sha256()
    for idx in sorted(selected):
        tok = scad.tokens[idx]
        if (tok.start, tok.end) in switch_literals:
            value = values.get(literal_to_name[(tok.start, tok.end)], tok.value)
        else:
            value = tok.value
        h.update(tok.kind.encode())
        h.update(b"\x1f")
        h.update(value.encode("utf-8", "surrogatepass"))
        h.update(b"\x1e")
    return h.digest()


def _dependency_fingerprint(
    paths: Sequence[Path], cache: dict[Path, bytes] | None = None
) -> bytes:
    cache = cache if cache is not None else {}
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path).replace("\\", "/").encode("utf-8"))
        h.update(b"\x1f")
        data = cache.get(path)
        if data is None:
            if not path.is_file():
                data = b"<missing>"
            else:
                try:
                    text = path.read_text(encoding="utf-8-sig")
                    tokens, _ = tokenize(text)
                    hh = hashlib.sha256()
                    for tok in tokens:
                        hh.update(tok.kind.encode())
                        hh.update(b"\x1f")
                        hh.update(tok.value.encode("utf-8", "surrogatepass"))
                        hh.update(b"\x1e")
                    data = hh.digest()
                except (OSError, UnicodeDecodeError, AnalysisError):
                    data = b"<unreadable>"
            cache[path] = data
        h.update(data)
        h.update(b"\x1e")
    return h.digest()


def variant_key(
    scad: ScadFile,
    values: dict[str, str],
    deps: Sequence[Path],
    render_config: dict[str, Any],
    dependency_cache: dict[Path, bytes] | None = None,
) -> str:
    h = hashlib.sha256()
    h.update(HASH_SCHEMA.encode())
    h.update(b"\0")
    payload = {
        "render": render_config,
        "values": {name: values[name] for name in sorted(values)},
    }
    h.update(repr(sorted(payload["render"].items())).encode("utf-8"))
    h.update(repr(sorted(payload["values"].items())).encode("utf-8"))
    h.update(canonical_tokens(scad, values))
    h.update(_dependency_fingerprint(deps, dependency_cache))
    return h.hexdigest()


def geometry_signature(
    scad: ScadFile,
    values: dict[str, str],
    deps: Sequence[Path],
    dependency_cache: dict[Path, bytes] | None = None,
) -> str:
    """Hash of the actual reachable model, ignoring switch labels.

    Two different switch combinations with the same signature produce the same
    geometry and can share one render.
    """
    h = hashlib.sha256()
    h.update(HASH_SCHEMA.encode())
    h.update(b"geometry\0")
    h.update(canonical_tokens(scad, values))
    h.update(_dependency_fingerprint(deps, dependency_cache))
    return h.hexdigest()


def source_text_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "<missing>"
