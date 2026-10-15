"""Small helpers that clean up text before it is saved or placed in an AI prompt."""
import re

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u2028\u2029]")
_SPACES = re.compile(r"[ \t]+")


def clean_line(value, max_len):
    """One line of plain text: no control characters, single spaces, trimmed, length-limited."""
    value = _CONTROL.sub(" ", str(value or ""))
    value = _SPACES.sub(" ", value.replace("\n", " ").replace("\r", " ")).strip()
    return value[:max_len].strip()


def clean_block(value, max_len):
    """Several lines allowed (bio, preferences), but still no control characters."""
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROL.sub(" ", value)                    # the pattern leaves "\n" alone
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:max_len].strip()


def parse_interests(raw, max_items=12, max_len=30):
    """'chess, Python , hiking' -> ['chess', 'Python', 'hiking'] (no duplicates)."""
    seen, items = set(), []
    for part in re.split(r"[,\n;]", str(raw or "")):
        item = clean_line(part, max_len)
        if item and item.lower() not in seen:
            seen.add(item.lower())
            items.append(item)
        if len(items) >= max_items:
            break
    return items
