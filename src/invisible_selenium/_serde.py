"""geckodriver's words for a request body it does not accept.

geckodriver reads the JSON Selenium sends with serde (the `webdriver` crate,
`command.rs`), so a value of the wrong type is an InvalidArgumentException
that names the value in serde's words and says where the reading stopped:
"invalid type: integer `1`, expected a string at line 1 column 21". There is
no geckodriver here, so the same words are made here, from the same JSON.

The place is in the body Selenium sends: `json.dumps` of the command's
parameters, with its default separators. After a number, a string, a boolean
or a null; before a sequence or a map, which serde refuses on its opening
bracket; after the object, for a field it lacks; after the whole body, for an
untagged enum no variant of which matched. Measured on geckodriver 0.37.1
with retail Firefox 151, 2026-10-13.
"""
from __future__ import annotations

import json
from decimal import Decimal

from .common import exceptions as exc

#: geckodriver's `AddCookieParameters`, in its order: what each field takes.
#: "string" may not be null; "option ..." may (null is absent).
COOKIE_FIELDS = (("name", "string"), ("value", "string"),
                 ("path", "option string"), ("domain", "option string"),
                 ("secure", "boolean"), ("httpOnly", "boolean"),
                 ("expiry", "option u64"), ("sameSite", "option string"))


def unexpected(value) -> str:
    """serde's name for a JSON value it did not expect (`de::Unexpected`)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean `%s`" % ("true" if value else "false")
    if isinstance(value, int):
        return "integer `%d`" % value
    if isinstance(value, float):
        # Rust prints a float without an exponent, and serde adds ".0" to a
        # whole one.
        text = format(Decimal(repr(value)), "f")
        return "floating point `%s`" % (text if "." in text else text + ".0")
    if isinstance(value, str):
        return "string %s" % json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "sequence"
    return "map"


def _column(before: str, value) -> int:
    """Where serde stops on `value`, which starts after `before`."""
    if isinstance(value, (list, tuple, dict)):
        return len(before)
    return len(before) + len(json.dumps(value))


def invalid(message: str, column: int) -> exc.InvalidArgumentException:
    return exc.InvalidArgumentException(
        "%s at line 1 column %d" % (message, column))


def _refusal(kind: str, value):
    """What serde says when `value` is read as `kind`, or None."""
    optional = kind.startswith("option ")
    kind = kind.replace("option ", "")
    if value is None:
        return None if optional else "invalid type: null, expected %s" % _expected(kind)
    if kind == "string":
        ok = isinstance(value, str)
    elif kind == "boolean":
        ok = isinstance(value, bool)
    else:  # u64
        if isinstance(value, int) and not isinstance(value, bool) and value < 0:
            return "invalid value: %s, expected u64" % unexpected(value)
        ok = (isinstance(value, int) and not isinstance(value, bool)
              and value <= 2 ** 64 - 1)
    return None if ok else "invalid type: %s, expected %s" % (
        unexpected(value), _expected(kind))


def _expected(kind: str) -> str:
    return {"string": "a string", "boolean": "a boolean"}.get(kind, kind)


def check_cookie(cookie) -> None:
    """Raise what geckodriver raises for `{"cookie": cookie}`, if anything.

    The fields are read in the order the dict has them, as serde reads the
    JSON; a key geckodriver does not know is skipped; a missing `name` or
    `value` is found at the end of the object, `name` first."""
    before = '{"cookie": '
    if isinstance(cookie, (list, tuple)):
        text = before + "["
        for i, (item, (_, kind)) in enumerate(zip(cookie, COOKIE_FIELDS)):
            text += ", " if i else ""
            refusal = _refusal(kind, item)
            if refusal:
                raise invalid(refusal, _column(text, item))
            text += json.dumps(item)
        if len(cookie) != len(COOKIE_FIELDS):
            raise invalid("invalid length %d, expected struct "
                          "AddCookieParameters with %d elements"
                          % (len(cookie), len(COOKIE_FIELDS)),
                          len(before + json.dumps(list(cookie))))
        return
    if not isinstance(cookie, dict):
        raise invalid("invalid type: %s, expected struct AddCookieParameters"
                      % unexpected(cookie), _column(before, cookie))
    kinds = dict(COOKIE_FIELDS)
    text = before + "{"
    for i, (key, value) in enumerate(cookie.items()):
        text += (", " if i else "") + json.dumps(key) + ": "
        if key in kinds:
            refusal = _refusal(kinds[key], value)
            if refusal:
                raise invalid(refusal, _column(text, value))
        text += json.dumps(value)
    for key in ("name", "value"):
        if key not in cookie:
            raise invalid("missing field `%s`" % key,
                          len(before + json.dumps(cookie)))


def check_string_or_null(field: str, value) -> None:
    """A parameter that is `Option<String>`, alone in its body, as the
    `type` of `NEW_WINDOW`."""
    refusal = _refusal("option string", value)
    if refusal:
        raise invalid(refusal, _column('{%s: ' % json.dumps(field), value))


def untagged(enum: str, body: dict) -> exc.InvalidArgumentException:
    """No variant of an untagged enum matched: serde says so after the
    whole body, as for `SWITCH_TO_FRAME`'s `FrameId`."""
    return invalid("data did not match any variant of untagged enum %s" % enum,
                   len(json.dumps(body)))
