"""Vic Transport IDs MCP server: validate container numbers (ISO 6346) and air waybill numbers (IATA). Fully offline."""
from __future__ import annotations

import json
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .logic import (CATEGORY, HEIGHT, LENGTH, TYPE_GROUP, TransportIdInputError, decode_size_type, extract_ids,
                    validate_awb, validate_batch, validate_container)

mcp = MCPServer(
    name="vic-transport-ids",
    title="Vic Transport IDs",
    description="Validate container numbers (ISO 6346 check digit), air waybill numbers (mod 7) and decode container size/type codes.",
    version=__version__,
    website_url="https://github.com/voidgazer009/vic-mcp-servers",
    instructions=(
        "Use these tools before a booking, B/L draft, customs entry or tracking lookup that contains a container or AWB "
        "number. A passing check digit only proves the number is well-formed, NOT that the container or shipment exists "
        "or where it is: say so, and send the user to the carrier or airline site for live status. Show every problem "
        "and the corrected form, but ask the user to confirm against the source document before changing anything."
    ),
)

LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class ContainerCheck(BaseModel):
    input: str = Field(description="The number as given.")
    normalised: str = Field(description="Upper-case without spaces or dashes.")
    valid: bool = Field(description="True if format and ISO 6346 check digit are correct.")
    owner_code: str | None = Field(description="3-letter owner (BIC) code, if the format allowed reading it.")
    category: str | None = Field(description="Equipment category from the 4th letter (U, J, Z).")
    check_digit_given: int | None = Field(description="Check digit in the input.")
    check_digit_expected: int | None = Field(description="Check digit ISO 6346 calculates.")
    corrected: str | None = Field(description="Number with the calculated check digit; confirm with the source document.")
    problems: list[str] = Field(description="What is wrong, empty when valid.")


class ContainerResult(BaseModel):
    results: list[ContainerCheck]
    valid_count: int
    invalid_count: int
    warnings: list[str] = Field(description="Show these to the user.")


class AwbCheck(BaseModel):
    input: str = Field(description="The number as given.")
    normalised: str | None = Field(description="Formatted 123-45678901 when 11 digits were found.")
    valid: bool = Field(description="True if 11 digits and the mod-7 check digit match.")
    airline_prefix: str | None = Field(description="3-digit IATA airline accounting code; not looked up.")
    serial: str | None = Field(description="7-digit serial number.")
    check_digit_given: int | None = Field(description="Check digit in the input.")
    check_digit_expected: int | None = Field(description="Serial number modulo 7.")
    problems: list[str] = Field(description="What is wrong, empty when valid.")


class AwbResult(BaseModel):
    results: list[AwbCheck]
    valid_count: int
    invalid_count: int
    warnings: list[str] = Field(description="Show these to the user.")


class SizeType(BaseModel):
    code: str = Field(description="The 4-character code.")
    length: str = Field(description="External length from the 1st character.")
    height: str = Field(description="Height from the 2nd character.")
    type: str = Field(description="Type group from the 3rd character.")
    note: str = Field(description="Example: 45G1 is a 40 ft high-cube dry container in the current ISO 6346 code.")
    warnings: list[str] = Field(description="Show these to the user.")


class ExtractResult(BaseModel):
    containers: list[ContainerCheck]
    awbs: list[AwbCheck]
    warnings: list[str] = Field(description="Show these to the user.")


_WARN = ("A valid check digit only proves the number is well-formed. It does not prove the container or shipment exists "
         "or where it is; check the carrier or airline tracking page.")


def _wrap(fn, *args):
    try:
        return fn(*args)
    except TransportIdInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(title="Validate container numbers", annotations=LOCAL)
def validate_container_numbers(
    numbers: Annotated[list[str], Field(min_length=1, max_length=100, description="Container numbers such as CSQU3054383; spaces and dashes are ignored. A 10-character number gets its check digit suggested.")],
) -> ContainerResult:
    """Check container numbers against ISO 6346: format, equipment category letter and the check digit, with the corrected number when it is a typo.

    Use it before filling a booking, SI or B/L, or when a customer sends a container number that looks wrong.
    """
    res = _wrap(validate_batch, numbers, validate_container)
    ok = sum(r["valid"] for r in res)
    warns = [_WARN]
    if ok < len(res):
        warns.append("Some numbers failed. Compare with the original document before using a corrected number; a wrong digit may be a different container.")
    return ContainerResult(results=[ContainerCheck(**r) for r in res], valid_count=ok, invalid_count=len(res) - ok, warnings=warns)


@mcp.tool(title="Validate air waybill numbers", annotations=LOCAL)
def validate_awb_numbers(
    numbers: Annotated[list[str], Field(min_length=1, max_length=100, description="AWB numbers like 176-1234 5675 or 17612345675: 3-digit airline prefix, 7-digit serial, 1 check digit.")],
) -> AwbResult:
    """Check air waybill numbers: 11 digits and the IATA check digit (the 7-digit serial modulo 7), returning the normalised form and the expected digit.

    Use it before tracking an air shipment or issuing an AWB reference on an invoice or packing list.
    """
    res = _wrap(validate_batch, numbers, validate_awb)
    ok = sum(r["valid"] for r in res)
    warns = [_WARN, "The airline prefix is not looked up here; check it against the IATA airline code list."]
    return AwbResult(results=[AwbCheck(**r) for r in res], valid_count=ok, invalid_count=len(res) - ok, warnings=warns)


@mcp.tool(title="Decode container size/type code", annotations=LOCAL)
def decode_container_size_type(
    code: Annotated[str, Field(min_length=4, max_length=4, pattern=r"^[0-9A-Za-z]{4}$", description="4-character ISO 6346 size/type code from the door, e.g. 22G1, 45G1, 45R1, 42U1.")],
) -> SizeType:
    """Decode a 4-character ISO 6346 size/type code (such as 45G1) into length, height and type group, e.g. 40 ft high-cube dry or reefer.

    Use it when a booking or B/L shows a code and you need to confirm it matches the equipment you ordered.
    """
    d = _wrap(decode_size_type, code)
    warns = ["Carriers sometimes use their own legacy codes (such as 40HC or 4310); confirm the equipment with the carrier."]
    if d["length"] == "unknown" or d["height"] == "unknown":
        warns.append("Length or height character is not in the standard tables; check for a typo.")
    return SizeType(**d, note="Position 1 = length, 2 = height, 3-4 = type. 22G1 is a 20 ft standard dry; 45G1 is a 40 ft high-cube dry.", warnings=warns)


@mcp.tool(title="Find and check IDs in pasted text", annotations=LOCAL)
def extract_and_validate_ids(
    text: Annotated[str, Field(min_length=1, max_length=20000, description="Any pasted text: an email, packing list or booking confirmation containing container numbers and/or AWB numbers.")],
) -> ExtractResult:
    """Scan pasted text for container numbers and 11-digit air waybill numbers and validate each one, removing duplicates.

    Use it on a forwarder email or document to catch a mistyped number in one pass. It may miss numbers split across lines.
    """
    r = _wrap(extract_ids, text)
    warns = [_WARN, "Extraction is pattern based: an unrelated 11-digit number (phone, order no.) can look like an AWB. Check the context."]
    if r["skipped_awb_like"]:
        warns.append(f"{r['skipped_awb_like']} unlabelled 11-digit number(s) failed the AWB check and were ignored (phone or order numbers?). Write 'AWB' before a number to force a check.")
    if not r["containers"] and not r["awbs"]:
        warns.append("No container or AWB-shaped numbers found.")
    return ExtractResult(containers=[ContainerCheck(**x) for x in r["containers"]], awbs=[AwbCheck(**x) for x in r["awbs"]], warnings=warns)


@mcp.resource("transport-ids://iso6346", name="iso6346-tables", title="ISO 6346 code tables", mime_type="application/json",
              description="Category letters, length and height characters and type groups used to decode container codes.")
def tables() -> str:
    return json.dumps({"category": CATEGORY, "length": LENGTH, "height": HEIGHT, "type_group": TYPE_GROUP}, ensure_ascii=False, indent=2)


@mcp.prompt(title="Check numbers before sending a booking", description="Validate every container and AWB number in a draft before it goes to the carrier.")
def pre_booking_check(draft: str) -> str:
    return (
        "Review this draft shipping document:\n\n---\n" + draft + "\n---\n\n"
        "1. Call extract_and_validate_ids on it.\n2. List every invalid number with the corrected form.\n"
        "3. If a size/type code appears, call decode_container_size_type and compare it with the equipment I ordered.\n"
        "4. Remind me that a valid number does not confirm the shipment exists. Do not send anything; give me a list of fixes."
    )


def main() -> None:
    """Entry point: stdio by default, `--http` for stateless Streamable HTTP on port 8000."""
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", stateless_http=True)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
