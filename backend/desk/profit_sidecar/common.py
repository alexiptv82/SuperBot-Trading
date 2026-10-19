import hashlib
import json
import math


class Freeze(ValueError):
    """A fixed, non-sensitive reason code, safe to report publicly."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise Freeze("duplicate_json_key")
            result[k] = v
        return result

    def number(v):
        x = float(v)
        if not math.isfinite(x):
            raise Freeze("nonfinite_json")
        return x
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=number,
                          parse_constant=lambda _: (_ for _ in ()).throw(Freeze("nonfinite_json")))
    except (ValueError, UnicodeError):
        raise Freeze("invalid_json") from None


def numeric(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or (positive and value <= 0):
        raise Freeze("invalid_numeric_field")
    return value


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise Freeze("invalid_integer_field")
    return value
