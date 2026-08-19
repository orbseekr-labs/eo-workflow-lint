"""Source-level suppression directives (SPECIFICATION §12).

Only the narrow ``# ewl: ignore-next-line=CODE[,CODE...]`` form is supported.
Directives are located with :mod:`tokenize` so that ``#`` characters inside
string literals cannot be mistaken for directives.
"""

from __future__ import annotations

import io
import re
import tokenize
from dataclasses import dataclass, field

from .rules import RULE_CODES

__all__ = ["SuppressionMap", "parse_suppressions"]

_DIRECTIVE_PREFIX_RE = re.compile(r"^#\s*ewl\s*:", re.IGNORECASE)
_DIRECTIVE_RE = re.compile(r"^#\s*ewl\s*:\s*ignore-next-line\s*=\s*(?P<codes>\S.*?)\s*$")


@dataclass
class SuppressionMap:
    """Maps a target source line to the reason codes suppressed on it."""

    by_line: dict[int, frozenset[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def suppresses(self, code: str, line: int) -> bool:
        return code in self.by_line.get(line, frozenset())


def parse_suppressions(source: str) -> SuppressionMap:
    """Extract suppression directives from ``source``.

    A directive applies only to the immediately following physical line, and a
    blank following line breaks the association. Malformed directives never
    suppress anything.
    """
    result = SuppressionMap()
    lines = source.splitlines()

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # The caller reports syntax errors; suppression simply contributes nothing.
        return result

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        text = token.string.strip()
        if not _DIRECTIVE_PREFIX_RE.match(text):
            continue

        directive_line = token.start[0]
        match = _DIRECTIVE_RE.match(text)
        if match is None:
            result.warnings.append(
                f"line {directive_line}: malformed eo-workflow-lint directive; ignored"
            )
            continue

        raw_codes = [part.strip() for part in match.group("codes").split(",")]
        if any(part == "" for part in raw_codes):
            result.warnings.append(
                f"line {directive_line}: malformed eo-workflow-lint directive; ignored"
            )
            continue

        known: set[str] = set()
        for code in raw_codes:
            if code in RULE_CODES:
                known.add(code)
            else:
                result.warnings.append(
                    f"line {directive_line}: unknown reason code {code!r} in suppression directive"
                )

        if not known:
            continue

        target = directive_line + 1
        if target > len(lines) or lines[target - 1].strip() == "":
            # Blank (or absent) following line breaks the directive association.
            continue

        result.by_line[target] = result.by_line.get(target, frozenset()) | frozenset(known)

    return result
