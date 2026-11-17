"""Pure functions: ISO 6346 container numbers and IATA air waybill numbers. No I/O."""
from __future__ import annotations

import re

CATEGORY = {"U": "freight container", "J": "detachable freight-container equipment", "Z": "trailer or chassis"}
LENGTH = {"2": "20 ft", "3": "30 ft", "4": "40 ft", "L": "45 ft", "M": "48 ft", "N": "49 ft"}
HEIGHT = {"0": "8 ft", "2": "8 ft 6 in (standard)", "4": "4 ft 3 in (half height)", "5": "9 ft 6 in (high cube)", "6": "over 9 ft 6 in"}
TYPE_GROUP = {"G": "general purpose (dry)", "R": "refrigerated (reefer)", "U": "open top", "P": "platform / flat rack",
              "T": "tank", "B": "bulk", "S": "named cargo", "H": "thermal (insulated)", "V": "ventilated"}
_MAX_BATCH = 100


class TransportIdInputError(ValueError):
    pass


def _letter_values() -> dict[str, int]:
    vals, v = {}, 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if v % 11 == 0:
            v += 1
        vals[ch] = v
        v += 1
    return vals


LETTER = _letter_values()


def container_check_digit(first10: str) -> int:
    """ISO 6346: letter values skip multiples of 11, weight 2**position, sum mod 11, then mod 10."""
    total = 0
    for i, ch in enumerate(first10):
        total += (LETTER[ch] if ch.isalpha() else int(ch)) * (2 ** i)
    return total % 11 % 10


def _clean(raw: str) -> str:
    return re.sub(r"[\s\-_.]", "", raw).upper()


def decode_size_type(code: str) -> dict:
    code = code.upper()
    if not re.fullmatch(r"[0-9A-Z]{4}", code):
        raise TransportIdInputError("size/type code must be 4 characters, e.g. 22G1 or 45R1")
    info = {"code": code, "length": LENGTH.get(code[0], "unknown"), "height": HEIGHT.get(code[1], "unknown"),
            "type": TYPE_GROUP.get(code[2], "other / unknown")}
    return info


def validate_container(raw: str) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise TransportIdInputError("container number is empty")
    c = _clean(raw)
    out = {"input": raw, "normalised": c, "valid": False, "owner_code": None, "category": None,
           "check_digit_given": None, "check_digit_expected": None, "corrected": None, "problems": []}
    if len(c) == 10 and re.fullmatch(r"[A-Z]{4}\d{6}", c):
        exp = container_check_digit(c)
        out.update(owner_code=c[:3], category=CATEGORY.get(c[3], "invalid"), check_digit_expected=exp,
                   corrected=f"{c}{exp}")
        out["problems"].append(f"missing check digit; ISO 6346 expects {exp}")
        return out
    if not re.fullmatch(r"[A-Z]{4}\d{7}", c):
        out["problems"].append("format must be 4 letters (owner code + category U/J/Z) followed by 7 digits (6 serial + 1 check digit)")
        return out
    exp = container_check_digit(c[:10])
    given = int(c[10])
    out.update(owner_code=c[:3], category=CATEGORY.get(c[3], "invalid"), check_digit_given=given, check_digit_expected=exp)
    if c[3] not in CATEGORY:
        out["problems"].append(f"4th letter '{c[3]}' is not a valid equipment category (U, J or Z)")
    if given != exp:
        out["problems"].append(f"check digit is {given} but ISO 6346 calculates {exp}; likely typo, corrected form {c[:10]}{exp}")
        out["corrected"] = f"{c[:10]}{exp}"
    out["valid"] = not out["problems"]
    if out["valid"]:
        out["corrected"] = c
    return out


def validate_awb(raw: str) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise TransportIdInputError("AWB number is empty")
    d = re.sub(r"[\s\-_.]", "", raw)
    out = {"input": raw, "normalised": None, "valid": False, "airline_prefix": None, "serial": None,
           "check_digit_given": None, "check_digit_expected": None, "problems": []}
    if not re.fullmatch(r"\d{11}", d):
        out["problems"].append("an AWB number is 11 digits: 3-digit airline prefix + 7-digit serial + 1 check digit")
        return out
    exp = int(d[3:10]) % 7
    out.update(normalised=f"{d[:3]}-{d[3:]}", airline_prefix=d[:3], serial=d[3:10],
               check_digit_given=int(d[10]), check_digit_expected=exp)
    if int(d[10]) != exp:
        out["problems"].append(f"check digit is {d[10]} but serial mod 7 gives {exp}; corrected form {d[:3]}-{d[3:10]}{exp}")
    out["valid"] = not out["problems"]
    return out


def validate_batch(items: list[str], fn) -> list[dict]:
    if not items:
        raise TransportIdInputError("give at least one number")
    if len(items) > _MAX_BATCH:
        raise TransportIdInputError(f"at most {_MAX_BATCH} numbers per call")
    return [fn(i) for i in items]


_CONT_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{4}[\s\-]?\d{6}[\s\-]?\d?)(?!\d)")
_AWB_RE = re.compile(r"(?<!\d)(\d{3})[\s\-]?(\d{4})[\s\-]?(\d{4})(?!\d)")


def extract_ids(text: str) -> dict:
    if not text or not text.strip():
        raise TransportIdInputError("text is empty")
    if len(text) > 20000:
        raise TransportIdInputError("text longer than 20000 characters")
    seen, containers, awbs = set(), [], []
    for m in _CONT_RE.finditer(text):
        n = _clean(m.group(1))
        if n not in seen:
            seen.add(n)
            containers.append(validate_container(n))
    skipped = 0
    for m in _AWB_RE.finditer(text):
        n = "".join(m.groups())
        if n in seen:
            continue
        seen.add(n)
        res = validate_awb(n)
        before = text[max(0, m.start() - 30):m.start()].lower()
        labelled = bool(re.search(r"awb|waybill|运单|空运单", before)) or bool(re.search(r"[-\s]", m.group(0)) and "-" in m.group(0))
        if res["valid"] or labelled:
            awbs.append(res)
        else:
            skipped += 1  # unlabelled 11-digit number failing the check: probably a phone or order number
    return {"containers": containers, "awbs": awbs, "skipped_awb_like": skipped}
