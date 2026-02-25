"""License key validation for KodaDocs Pro tier."""

import re
from typing import Optional

# Full format pattern for Pydantic field-level validation.
# Enforces: kd_pro_ prefix + at least 20 alphanumeric/hyphen/underscore chars.
LICENSE_KEY_PATTERN = r"^kd_pro_[A-Za-z0-9_-]{20,}$"

_PREFIX_RE = re.compile(r"^kd_pro_")


def is_pro_key(key: Optional[str]) -> bool:
    """Return True if *key* looks like a valid Pro license key.

    Runtime check is prefix-only (fast).  Full format validation
    (length, charset) is enforced at the Pydantic model level via
    ``LICENSE_KEY_PATTERN``.

    >>> is_pro_key("kd_pro_" + "a" * 20)
    True
    >>> is_pro_key(None)
    False
    >>> is_pro_key("")
    False
    >>> is_pro_key("invalid")
    False
    """
    if not key:
        return False
    return bool(_PREFIX_RE.match(key))
