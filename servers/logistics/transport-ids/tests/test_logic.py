import pytest

from vic_transport_ids.logic import (TransportIdInputError, container_check_digit, decode_size_type, extract_ids,
                                     validate_awb, validate_batch, validate_container)


def test_golden_check_digit_csqu():
    # CSQU305438: C=13,S=30,Q=28,U=32 (letter values skip 22 and 33), digits 3,0,5,4,3,8
    # 13*1+30*2+28*4+32*8+3*16+0*32+5*64+4*128+3*256+8*512 = 6185; 6185 mod 11 = 3 (11*562=6182)
    assert container_check_digit("CSQU305438") == 3


def test_golden_remainder_ten_becomes_zero():
    # sum mod 11 == 10 must map to check digit 0. Search a number with that property and confirm the rule.
    for n in range(1000000):
        c = f"ABCU{n:06d}"
        total = sum(({"A": 10, "B": 12, "C": 13, "U": 32}.get(ch) if ch.isalpha() else int(ch)) * 2 ** i for i, ch in enumerate(c))
        if total % 11 == 10:
            assert container_check_digit(c) == 0
            return
    pytest.fail("no case")


def test_valid_and_typo():
    assert validate_container("csqu 305438-3")["valid"] is True
    r = validate_container("CSQU3054384")
    assert not r["valid"] and r["corrected"] == "CSQU3054383" and r["check_digit_expected"] == 3


def test_missing_digit_and_bad_format():
    r = validate_container("CSQU305438")
    assert not r["valid"] and r["corrected"] == "CSQU3054383"
    assert not validate_container("CSQ3054383")["valid"]
    assert "category" in " ".join(validate_container("CSQX3054383")["problems"])


def test_awb_golden():
    # 1234567 mod 7: 7*176366 = 1234562, remainder 5, so 176-12345675 is valid
    assert validate_awb("176-1234 5675")["valid"] is True
    r = validate_awb("17612345676")
    assert not r["valid"] and r["check_digit_expected"] == 5
    assert not validate_awb("1761234567")["valid"]


def test_size_type():
    d = decode_size_type("45G1")
    assert d["length"] == "40 ft"  # first character 4 = 40 ft
    assert decode_size_type("22G1")["length"] == "20 ft"
    assert decode_size_type("45G1")["height"].startswith("9 ft 6")
    with pytest.raises(TransportIdInputError):
        decode_size_type("2G")


def test_extract_and_limits():
    r = extract_ids("Container CSQU3054383 and csqu3054384, AWB 176-12345675 tel 85212345678")
    assert len(r["containers"]) == 2 and len(r["awbs"]) == 2
    with pytest.raises(TransportIdInputError):
        validate_batch([], validate_awb)
    with pytest.raises(TransportIdInputError):
        validate_batch(["x"] * 101, validate_awb)


def test_extract_ignores_phone_but_checks_labelled_awb():
    r = extract_ids("tel 85212345678, PO 20261117123")
    assert r["awbs"] == [] and r["skipped_awb_like"] == 2
    r = extract_ids("MAWB 17612345676")
    assert len(r["awbs"]) == 1 and not r["awbs"][0]["valid"]
