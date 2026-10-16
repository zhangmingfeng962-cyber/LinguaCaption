from __future__ import annotations

from collections.abc import Callable

import regex


def wrap_text(text: str, max_chars: int, max_width: float = float("inf"),
              measure: Callable[[str], float] = len) -> list[str]:
    """Wrap at grapheme boundaries, preferring whitespace when useful.

    The limit counts visible grapheme clusters (a joined emoji counts as one).
    A single oversized cluster is returned intact instead of being corrupted.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    lines: list[str] = []
    for paragraph in text.splitlines():
        pending = regex.findall(r"\X", paragraph.strip())
        while pending:
            count = 0
            while count < min(max_chars, len(pending)):
                if count and measure("".join(pending[:count + 1])) > max_width:
                    break
                count += 1
            if count < len(pending):
                spaces = [i for i, char in enumerate(pending[:count + 1]) if char.isspace()]
                if spaces and spaces[-1] >= max(1, count // 3):
                    count = spaces[-1]
            line = "".join(pending[:count]).strip()
            if line:
                lines.append(line)
            pending = pending[count:]
            while pending and pending[0].isspace():
                pending.pop(0)
    return lines


def visible_lines(lines: list[str], maximum: int) -> list[str]:
    # Live captions retain the latest lines. Full text remains in session history.
    if len(lines) <= maximum:
        return lines
    result = lines[-maximum:]
    clusters = regex.findall(r"\X", result[0])
    result[0] = "…" + "".join(clusters[1:])
    return result
