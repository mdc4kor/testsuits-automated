#!/usr/bin/env python3
"""Generate a CAPL suite file from STLA_Testsuite.xml for a given FNID number.

Usage:
    python generate_master_suite.py 3480
    python generate_master_suite.py 3480.can
    python generate_master_suite.py 3480 --xml C:\\path\\to\\STLA_Testsuite.xml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


FORBIDDEN_PATTERNS = ()
SEVERE_PLACEHOLDER = "17"


def parse_file_number(raw: str) -> str:
    value = raw.strip()
    if value.lower().endswith(".can"):
        value = value[:-4]
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"Invalid file number: {raw!r}. Provide a number like 3480 or a filename like 3480.can.")
    return value


def locate_group(root: ET.Element, fnid_number: str) -> ET.Element:
    ident = f"FNID_{fnid_number}"
    for tg in root.iter("testgroup"):
        if tg.get("ident") == ident:
            return tg
    raise RuntimeError(f"FNID_{fnid_number} not found in STLA_Testsuite.xml")


def first_match(text: str, patterns: Iterable[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return None


def split_hex_pairs(value: str) -> list[str]:
    cleaned = value.replace(" ", "")
    return [cleaned[i : i + 2] for i in range(0, len(cleaned), 2)]


def build_request_from_name(name: str) -> str:
    """Build a generic request payload for routine-control style cases."""
    rid_match = re.search(r"RID([A-F0-9A-Z]+)", name)
    rid = rid_match.group(0) if rid_match else "RIDFA01"
    hex_part = rid[3:]
    if len(hex_part) % 2:
        hex_part = hex_part[:-1] + hex_part[-1]
    tokens = split_hex_pairs(hex_part)
    return "31 01 " + " ".join(tokens)


def build_title_text(group: ET.Element, fnid_number: str) -> str:
    title = group.get("title") or group.get("ident") or f"{fnid_number}_TSU"
    return f"/// <{title}>"


def normalize_spacing(lines: list[str]) -> str:
    """Apply the same blank-line spacing pattern used in the verified files."""
    output: list[str] = []
    for line in lines:
        if (
            line.startswith("  TestStep(")
            or line.startswith("  Security_Seed_Key_Access")
            or line.startswith("  PostCondition_MasterBLE")
        ):
            if output and output[-1] != "":
                output.append("")
        output.append(line)
    return "\n".join(output) + "\n"


def get_case_name(case: ET.Element) -> str:
    name = case.get("name") or ""
    return name.strip()


def make_long_1111_payload(prefix: str, repeat_count: int = 64) -> str:
    payload_words = ["11"] * repeat_count
    return f"{prefix} {' '.join(payload_words)}".strip()


def build_masterble_transferdata_case(case_name: str) -> list[str]:
    lines: list[str] = []
    nrc_match = re.search(r"NRC(\d+)", case_name)
    nrc = nrc_match.group(1) if nrc_match else "31"
    large_payload = make_long_1111_payload("36 01")
    large_payload_2 = make_long_1111_payload("36 02")

    lines.append('  testCaseComment("Actions");')
    lines.append('  SendTesterPresent();')
    lines.append('  TestStep("1","Send request 10 01 to enter Default Diagnostic Session");')
    lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"10 01","50 01 00 32 01 F4");')
    lines.append('  TestStep("2","Send request 10 03 to enter Default Extended Session");')
    lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"10 03","50 03 00 32 01 F4");')
    lines.append('  TestStep("3,4","Send Security Seed Request 61 and Key 62 in MasterBLE");')
    lines.append('  Security_Seed_Key_Access(DiagAnchorMaster,Physical,Bosch);')
    lines.append('  TestStep("5","Send request 10 02 to enter Default Programming Session");')
    lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"10 02","50 02 00 32 01 F4");')

    if "NRC13" in case_name:
        lines.append('  TestStep("6","Send request 34 00 14 00 00 00 00 EE");')
        lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"34 00 14 00 00 00 00 EE","74 20 00 F2");')
        lines.append('  TestStep("7","Send request 36");')
        lines.append('  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"36","7F 36 13");')
        return lines

    if "NRC24" in case_name:
        lines.append(f'  TestStep("6","Send request {large_payload}");')
        lines.append(f'  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"{large_payload}","7F 36 24");')
        lines.append('  TestStep("7","Send request 34 00 14 00 00 00 00 EE");')
        lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"34 00 14 00 00 00 00 EE","74 20 00 F2");')
        lines.append(f'  TestStep("8","Send request {large_payload}");')
        lines.append(f'  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"{large_payload}","76 01");')
        return lines

    if "NRC31" in case_name:
        lines.append('  TestStep("6","Send request 34 00 14 00 00 00 00 EE");')
        lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"34 00 14 00 00 00 00 EE","74 20 00 F2");')
        lines.append(f'  TestStep("7","Send request {large_payload}");')
        lines.append(f'  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"{large_payload}","7F 36 31");')
        return lines

    if "NRC71" in case_name:
        lines.append('  TestStep("6","Send request 34 00 14 00 00 00 00 F0");')
        lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"34 00 14 00 00 00 00 F0","74 20 00 F2");')
        lines.append(f'  TestStep("7","Send request {large_payload}");')
        lines.append(f'  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"{large_payload}","76 01");')
        lines.append(f'  TestStep("8","Send request {large_payload_2}");')
        lines.append(f'  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"{large_payload_2}","7F 36 71");')
        return lines

    if "NRC73" in case_name:
        lines.append('  TestStep("6","Send request 34 00 24 00 00 00 00 01 DE");')
        lines.append('  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"34 00 24 00 00 00 00 01 DE","74 20 00 F2");')
        lines.append(f'  TestStep("7","Send request {large_payload_2}");')
        lines.append(f'  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"{large_payload_2}","7F 36 73");')
        lines.append(f'  TestStep("8","Send request {large_payload}");')
        lines.append(f'  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"{large_payload}","76 01");')
        lines.append(f'  TestStep("9","Send request {large_payload_2}");')
        lines.append(f'  SendDiag_Request_Verify_Response(MasterBLE_Qualifier,"{large_payload_2}","76 01");')
        return lines

    if "NRC11" in case_name or "NRC7F" in case_name:
        lines.append('  TestStep("6","Send request 36 01 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11");')
        lines.append('  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"36 01 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11","7F 36 11");')
        return lines

    # Fallback for non-TransferData cases: keep the generic pattern but avoid forcing a fake "last" label.
    lines.append('  TestStep("6","Send request 36 01 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11");')
    lines.append('  SendDiag_Request_Verify_Negative_Response(MasterBLE_Qualifier,"36 01 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11","7F 36 31");')
    return lines


def build_case_block(case_name: str, fnid_number: str, title_hint: str) -> list[str]:
    lines: list[str] = []
    lines.append(f"testcase {case_name}()")
    lines.append("{")
    lines.append(f'  setLogFileName("reports\\Diag\\{fnid_number}\\{case_name}.asc");')
    lines.append("")
    lines.append("  PreCondition_MasterBLE(MasterBLE);")
    lines.append("")

    if "MasterBLETransferData_" in case_name or "MasterBLE_TransferData_" in case_name or "TransferData_" in case_name:
        lines.extend(build_masterble_transferdata_case(case_name))
        lines.append("")
        lines.append("  PostCondition_masterble();")
        lines.append("}")
        lines.append("")
        return lines

    lines.append('  testCaseComment("Actions");')

    step_no = 1
    security_needed = "0x61Security" in case_name or "0x61SecurityLevel" in case_name
    security_needed_65 = "0x65Security" in case_name or "0x65SecurityLevel" in case_name
    programming_needed = "ProgrammingSession" in case_name

    # Default MasterBLE flow requires the session setup before the request itself.
    lines.append(f'  TestStep("{step_no}","Send request 10 01 to enter Default Diagnostic Session");')
    lines.append('  SendDiag_Request_Verify_and_GetResponse("MasterBLE","10 01","50 01 00 32 01 F4", 6);')
    step_no += 1

    lines.append(f'  TestStep("{step_no}","Send request 10 03 to enter Default Extended Session");')
    lines.append('  SendDiag_Request_Verify_and_GetResponse("MasterBLE","10 03","50 03 00 32 01 F4", 6);')
    step_no += 1

    if security_needed:
        lines.append('')
        lines.append(f'  TestStep("{step_no},{step_no + 1}","Send Security Seed Request 61 and Key 62 in MasterBLE");')
        lines.append('  Security_Seed_Key_Access(MasterBLE,Physical,Bosch);')
        step_no += 2
    elif security_needed_65:
        lines.append('')
        lines.append(f'  TestStep("{step_no},{step_no + 1}","Send Security Seed Request 65 and Key 66 in MasterBLE");')
        lines.append('  Security_Seed_Key_Access(MasterBLE,Physical,Incar_1);')
        step_no += 2

    if programming_needed:
        lines.append('')
        lines.append(f'  TestStep("{step_no}","Send request 10 02 to enter Default Programming Session");')
        lines.append('  SendDiag_Request_Verify_and_GetResponse("MasterBLE","10 02","50 02 00 32 01 F4", 6);')
        step_no += 1

    nrc_match = re.search(r"NRC(\d+)", case_name)
    nrc = nrc_match.group(1) if nrc_match else "13"
    request = build_request_from_name(case_name)

    lines.append('')
    lines.append(f'  TestStep("{step_no}","Send request {request}");')
    lines.append(f'  SendDiag_Request_Neg(0, "MasterBLE","{request}","7F 31 {nrc}");')
    lines.append('')
    lines.append("  PostCondition_MasterBLE(MasterBLE);")
    lines.append("}")
    lines.append("")
    return lines


def generate_suite_file(group: ET.Element, fnid_number: str, anchor_map: dict[str, str] | None = None) -> str:
    cases = list(group.iter("capltestcase"))
    if not cases:
        raise RuntimeError(f"No capltestcase entries found under FNID_{fnid_number}")

    lines: list[str] = []
    lines.append(f"//****************************TSU_{fnid_number}******************************************************************************//")
    lines.append("")
    lines.append(build_title_text(group, fnid_number))
    lines.append("")

    anchor_map = anchor_map or {}
    for case in cases:
        case_name = get_case_name(case)
        if not case_name:
            continue

        anchor_match = resolve_anchor_case_template(case_name, anchor_map)
        if anchor_match is not None:
            anchor_name, anchor_body = anchor_match
            lines.extend(render_anchor_case(case_name, fnid_number, anchor_name, anchor_body))
            continue

        lines.extend(build_case_block(case_name, fnid_number, group.get("title") or ""))

    return normalize_spacing(lines)


def extract_case_blocks(text: str) -> dict[str, str]:
    pattern = r"testcase\s+([A-Za-z0-9_]+)\(\)\s*\{(.*?)\n\}\s*\n?"
    matches = re.findall(pattern, text, flags=re.S)
    return {name: body for name, body in matches}


def normalize_anchor_signature(name: str) -> tuple[str, ...]:
    value = re.sub(r"^TCS_PK_FCA_", "", name)
    value = value.replace("MasterBLETransferData", "TransferData")
    value = value.replace("MasterBLE_TransferData", "TransferData")
    value = value.replace("MasterBLE", "")
    value = value.replace("MasterUDSSecondaryServer", "")
    value = value.replace("MasterBLE_", "")
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    pieces = []
    for part in value.split():
        if part.isdigit() and len(part) >= 4:
            continue
        p = part.replace("ProgrammingSession", "Programming")
        p = p.replace("SecurityLevel", "Security")
        p = p.replace("NoSecurityLevel", "NoSecurity")
        p = p.replace("DefaultSession", "Default")
        p = p.replace("Extended_NoSecurity", "Extended_NoSecurity")
        if p:
            pieces.append(p)
    return tuple(pieces)


def validate_case_step_coverage(suite_text: str, anchor_cases: set[str] | None = None) -> None:
    blocks = extract_case_blocks(suite_text)
    anchor_set = set(anchor_cases or set())

    def is_anchor_case(case_name: str) -> bool:
        if case_name in anchor_set:
            return True
        match = re.search(r"_(\d+)$", case_name)
        if not match:
            return False
        ident = match.group(1)
        return any(anchor_name.endswith(f"_{ident}") for anchor_name in anchor_set)

    if anchor_cases:
        generated_family_keys = [normalize_anchor_signature(name) for name in blocks]
        matched_anchor_cases = 0
        for anchor_name in sorted(anchor_cases):
            key = normalize_anchor_signature(anchor_name)
            if not key:
                continue
            matched = False
            for gkey in generated_family_keys:
                if not gkey:
                    continue
                common = set(key) & set(gkey)
                if len(common) >= 3 and ("TransferData" in key or "TransferData" in gkey):
                    matched = True
                    break
                elif len(common) >= 2:
                    matched = True
                    break
            if matched:
                matched_anchor_cases += 1
        if matched_anchor_cases == 0:
            raise RuntimeError("No matching anchor families found in generated suite")

    for case_name, body in blocks.items():
        anchor_derived = is_anchor_case(case_name)

        if "last" in body.lower() and not anchor_derived:
            raise RuntimeError(f"Forbidden 'last' label remains in testcase {case_name}")

        transfer_like = (
            "MasterBLETransferData_" in case_name or "MasterBLE_TransferData_" in case_name or "TransferData_" in case_name
        )
        if transfer_like and not anchor_derived:
            required = [
                '10 01 to enter Default Diagnostic Session',
                '10 03 to enter Default Extended Session',
                '10 02 to enter Default Programming Session',
            ]
            for token in required:
                if token not in body:
                    raise RuntimeError(f"Missing required MasterBLE step in {case_name}: {token}")

            if "NRC31" in case_name:
                if '34 00 14 00 00 00 00 EE' not in body:
                    raise RuntimeError(f"Missing NRC31 34 00 pre-step in {case_name}")
                if '7F 36 31' not in body:
                    raise RuntimeError(f"Missing NRC31 negative response in {case_name}")

            if "NRC24" in case_name:
                if '7F 36 24' not in body:
                    raise RuntimeError(f"Missing NRC24 negative response in {case_name}")

            if "NRC71" in case_name:
                if '7F 36 71' not in body:
                    raise RuntimeError(f"Missing NRC71 negative response in {case_name}")

            if "NRC73" in case_name:
                if '7F 36 73' not in body:
                    raise RuntimeError(f"Missing NRC73 negative response in {case_name}")


def validate_suite(text: str, expected_count: int, anchor_cases: set[str] | None = None) -> None:
    case_count = len(re.findall(r"^testcase ", text, flags=re.M))
    if case_count != expected_count:
        raise RuntimeError(f"Expected {expected_count} testcase blocks, got {case_count}")

    bad_hits = 0
    for pattern in FORBIDDEN_PATTERNS:
        bad_hits += len(re.findall(re.escape(pattern), text, flags=re.I))
    if bad_hits:
        raise RuntimeError(f"Forbidden artifacts remain: {bad_hits} matches for {FORBIDDEN_PATTERNS}")

    if "last" in text.lower() and not re.search(r"MasterBLETransferData_|MasterBLE_TransferData_|TransferData_", text):
        raise RuntimeError("Forbidden 'last' label remains in generated content")

    validate_case_step_coverage(text, anchor_cases)


def load_anchor_case_names(anchor_path: Path) -> set[str]:
    if not anchor_path.exists():
        return set()
    text = anchor_path.read_text(encoding="utf-8", errors="ignore")
    return {m.group(1) for m in re.finditer(r"testcase\s+([A-Za-z0-9_]+)\(\)", text)}


def load_anchor_case_map(anchor_path: Path) -> dict[str, str]:
    if not anchor_path.exists():
        return {}
    text = anchor_path.read_text(encoding="utf-8", errors="ignore")
    return extract_case_blocks(text)


def resolve_anchor_case_template(case_name: str, anchor_map: dict[str, str]) -> tuple[str, str] | None:
    if not anchor_map:
        return None

    if case_name in anchor_map:
        return case_name, anchor_map[case_name]

    xml_key = normalize_anchor_signature(case_name)
    if not xml_key:
        return None

    best_name: str | None = None
    best_key: tuple[str, ...] | None = None
    best_score = -1
    ident = re.search(r"_(\d+)$", case_name)
    ident_num = ident.group(1) if ident else None

    for anchor_name, body in anchor_map.items():
        if ident_num and anchor_name.endswith(f"_{ident_num}"):
            return anchor_name, body

        anchor_key = normalize_anchor_signature(anchor_name)
        if not anchor_key:
            continue

        score = len(set(xml_key) & set(anchor_key))
        if score > best_score:
            best_score = score
            best_name = anchor_name
            best_key = anchor_key

    if best_name and best_key and best_score >= 3:
        return best_name, anchor_map[best_name]
    return None


def normalize_anchor_step_label(step_line: str, next_line: str | None = None) -> str:
    if 'TestStep("17"' not in step_line or 'session' not in step_line.lower():
        return step_line
    if next_line and 'Negative_Response' in next_line:
        return step_line

    payload_match = re.search(r'"([0-9A-Fa-f ]+)"', next_line or '')
    if not payload_match:
        return step_line
    payload = payload_match.group(1).replace(' ', '')
    if not payload or '7F' in payload:
        return step_line
    if len(payload) % 2:
        return step_line
    length = len(payload) // 2
    return step_line.replace('"17"', f'"{length}"', 1)


def render_anchor_case(case_name: str, fnid_number: str, anchor_name: str, anchor_body: str) -> list[str]:
    lines = [
        f"testcase {case_name}()",
        "{",
        f'  setLogFileName("reports\\Diag\\{fnid_number}\\{case_name}.asc");',
        "",
        "  PreCondition_MasterBLE(MasterBLE);",
        "",
        '  testCaseComment("Actions");',
    ]

    body_lines = anchor_body.strip().splitlines()

    for raw in body_lines:
        s = raw.strip()
        if not s:
            continue

        if s.startswith("Precondition_masterble") or s.startswith("Postcondition_masterble"):
            continue
        if s.startswith("SendTesterPresent();"):
            continue
        if s.startswith("testCaseComment("):
            continue

        if s.startswith("TestStep("):
            m = re.search(r'TestStep\("([^"]+)","([^"]+)"\)', s)
            if m:
                orig_step_num = m.group(1)
                description = m.group(2)
                lines.append(f'  TestStep("{orig_step_num}","{description}");')
            continue

        if s.startswith("Security_Seed_Key_Access("):
            lines.append('  ' + s)
            continue

        if s.startswith("SendDiag_Request_Verify_Response("):
            m = re.search(r'SendDiag_Request_Verify_Response\(MasterBLE_Qualifier,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', s)
            if m:
                req, resp = m.groups()
                if resp.startswith("7F "):
                    lines.append(f'  SendDiag_Request_Neg(0, "MasterBLE","{req}","{resp}");')
                else:
                    length = len(resp.replace(" ", "")) // 2
                    lines.append(f'  SendDiag_Request_Verify_and_GetResponse("MasterBLE","{req}","{resp}",{length});')
            continue

        if s.startswith("SendDiag_Request_Verify_Negative_Response("):
            m = re.search(r'SendDiag_Request_Verify_Negative_Response\(MasterBLE_Qualifier,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', s)
            if m:
                req, resp = m.groups()
                lines.append(f'  SendDiag_Request_Neg(0, "MasterBLE","{req}","{resp}");')
            continue

        if s.startswith("SendDiag_Request_Verify_and_GetResponse("):
            lines.append('  ' + s)
            continue

        if s.startswith("SendDiag_Request"):
            lines.append('  ' + s)

    lines.append("")
    lines.append("  PostCondition_MasterBLE(MasterBLE);")
    lines.append("}")
    lines.append("")
    return lines


def extract_testcase_blocks_balanced(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(r"^\s*testcase\s+([A-Za-z0-9_]+)\s*\(\)\s*\{", flags=re.M)
    for match in pattern.finditer(text):
        name = match.group(1)
        i = match.end()
        depth = 1
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        if depth == 0:
            blocks[name] = text[match.end() : i - 1]
    return blocks


def build_spaak_suite_tag(group: ET.Element, fnid_number: str) -> str:
    title = (group.get("title") or group.get("ident") or "").strip()
    title = re.sub(rf"[_-]?{re.escape(fnid_number)}$", "", title)
    title = title.strip("_-")
    return f"{fnid_number}_{title}" if title else fnid_number


def name_tokens(value: str) -> set[str]:
    tokens = [tok for tok in re.split(r"[_\W]+", value) if tok and not tok.isdigit()]
    return {tok.lower() for tok in tokens}


def resolve_source_case_name(xml_case_name: str, source_blocks: dict[str, str]) -> str:
    if xml_case_name in source_blocks:
        return xml_case_name

    xml_id_match = re.search(r"_(\d+)$", xml_case_name)
    if not xml_id_match:
        raise RuntimeError(f"Cannot resolve testcase source for: {xml_case_name}")
    xml_id = xml_id_match.group(1)

    candidates = [name for name in source_blocks if name.endswith(f"_{xml_id}")]
    if not candidates:
        raise RuntimeError(f"No testcase with id {xml_id} found in Masterdiag.cin for {xml_case_name}")
    if len(candidates) == 1:
        return candidates[0]

    xml_tokens = name_tokens(xml_case_name)
    best = candidates[0]
    best_score = -1
    for name in candidates:
        score = len(xml_tokens & name_tokens(name))
        if score > best_score:
            best_score = score
            best = name
    return best


def response_byte_length(resp: str) -> int:
    data = resp.strip()
    if not data:
        return 0
    parts = [p for p in data.split() if p]
    return len(parts)


def derive_positive_response_from_request(req: str) -> str | None:
    parts = [p.upper() for p in req.strip().split() if p]
    if not parts:
        return None
    sid = parts[0]
    if not re.fullmatch(r"[0-9A-F]{2}", sid):
        return None
    sid_value = int(sid, 16)
    pos_sid = sid_value + 0x40
    if not (0 <= pos_sid <= 0xFF):
        return None
    return " ".join([f"{pos_sid:02X}"] + parts[1:])


def extract_actions_region(body: str) -> list[str]:
    lines = body.splitlines()
    start = 0
    end = len(lines)

    for i, line in enumerate(lines):
        if re.search(r"testcasecomment\s*\(\s*\"actions\"\s*\)", line, flags=re.I):
            start = i + 1
            break

    for i in range(start, len(lines)):
        if re.search(r"testcasecomment\s*\(\s*\"post\s*condition", lines[i], flags=re.I):
            end = i
            break

    return lines[start:end]


def source_step_count(body: str) -> int:
    count = 0
    for raw in extract_actions_region(body):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("//") or s.startswith("/*"):
            continue
        if re.search(r"teststep\s*\(", s, flags=re.I):
            count += 1
    return count


def transform_masterdiag_actions(body: str) -> list[tuple[str, str, str, str]]:
    """Return tuples: (kind, step_label, description, payload)."""
    actions = extract_actions_region(body)
    events: list[tuple[str, str, str, str]] = []
    pending_step: tuple[str, str] | None = None

    for raw in actions:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("//") or s.startswith("/*"):
            continue

        if re.search(r"sendtesterpresent|diagstarttesterpresent", s, flags=re.I):
            continue

        step_match = re.search(r"teststep\s*\(\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"\s*\)", s, flags=re.I)
        if step_match:
            if pending_step is not None:
                events.append(("steponly", pending_step[0], pending_step[1], ""))
            pending_step = (step_match.group(1), step_match.group(2))
            after = s[step_match.end() :].strip().lstrip(";").strip()
            if not after:
                continue
            s = after

        if re.search(r"Security_Access_11_12_Leaf_8\s*\(", s):
            if pending_step:
                events.append(("security", pending_step[0], pending_step[1], ""))
                pending_step = None
            continue

        m_get = re.search(
            r"senddiag_request_verify_and_getresponse\s*\(\s*\"[^\"]*\"\s*,\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"\s*,\s*(\d+)\s*\)",
            s,
            flags=re.I,
        )
        if m_get and pending_step:
            req, resp = m_get.group(1), m_get.group(2)
            kind = "neg" if resp.strip().upper().startswith("7F ") else "pos"
            events.append((kind, pending_step[0], pending_step[1], f"{req}|||{resp}"))
            pending_step = None
            continue

        m_v = re.search(
            r"senddiag_request_verify_response\s*\(\s*\"[^\"]*\"\s*,\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"\s*\)",
            s,
            flags=re.I,
        )
        if m_v and pending_step:
            req, resp = m_v.group(1), m_v.group(2)
            kind = "neg" if resp.strip().upper().startswith("7F ") else "pos"
            events.append((kind, pending_step[0], pending_step[1], f"{req}|||{resp}"))
            pending_step = None
            continue

        m_neg_v = re.search(
            r"senddiag_request_verify_negative_response\s*\(\s*\"[^\"]*\"\s*,\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"\s*\)",
            s,
            flags=re.I,
        )
        if m_neg_v and pending_step:
            req, resp = m_neg_v.group(1), m_neg_v.group(2)
            events.append(("neg", pending_step[0], pending_step[1], f"{req}|||{resp}"))
            pending_step = None
            continue

        m_neg = re.search(
            r"senddiag_request_neg\s*\(\s*0\s*,\s*\"[^\"]*\"\s*,\s*\"([^\"]*)\"\s*,\s*\"([^\"]*)\"\s*\)",
            s,
            flags=re.I,
        )
        if m_neg and pending_step:
            req, resp = m_neg.group(1), m_neg.group(2)
            events.append(("neg", pending_step[0], pending_step[1], f"{req}|||{resp}"))
            pending_step = None
            continue

        m_len = re.search(
            r"senddiag_request_verify_response_length\s*\(\s*[^,]+\s*,\s*\"([^\"]*)\"\s*,\s*(\d+)\s*\)",
            s,
            flags=re.I,
        )
        if m_len and pending_step:
            req = m_len.group(1)
            resp = derive_positive_response_from_request(req)
            if resp is not None:
                events.append(("pos", pending_step[0], pending_step[1], f"{req}|||{resp}"))
            pending_step = None

    if pending_step is not None:
        events.append(("steponly", pending_step[0], pending_step[1], ""))

    return events


def render_spaak_master_case(case_name: str, source_body: str, fnid_number: str, suite_tag: str) -> list[str]:
    lines: list[str] = []
    lines.append(f"/// <{suite_tag}>")
    lines.append(f"testcase {case_name}()")
    lines.append("{")
    lines.append(f'  setLogFileName("reports\\Diag\\{fnid_number}\\{case_name}.asc");')
    lines.append("")
    lines.append("  PreCondition_Master(SPAAK);")
    lines.append("")

    events = transform_masterdiag_actions(source_body)
    next_step = 1
    for kind, original_label, desc, payload in events:
        step_label = str(next_step)
        next_step += 1

        lines.append(f'  TestStep("{step_label}","{desc}");')

        if kind == "security":
            lines.append("  Security_Access_11_12_Leaf_8();")
        elif kind == "steponly":
            pass
        else:
            req, resp = payload.split("|||", 1)
            if kind == "neg":
                lines.append(f'  SendDiag_Request_Neg(0, "SPAAK","{req}","{resp}");')
            else:
                if resp.strip() == "":
                    lines.append(f'  SendDiag_Request_Verify_Response("SPAAK","{req}","");')
                else:
                    length = response_byte_length(resp)
                    lines.append(f'  SendDiag_Request_Verify_and_GetResponse("SPAAK","{req}","{resp}", {length});')
        lines.append("")

    lines.append("  PostCondition_Master(SPAAK);")
    lines.append("}")
    lines.append("")
    return lines


def generate_spaak_master_suite(group: ET.Element, fnid_number: str, cin_text: str) -> str:
    source_blocks = extract_testcase_blocks_balanced(cin_text)
    cases = list(group.iter("capltestcase"))
    if not cases:
        raise RuntimeError(f"No capltestcase entries found under FNID_{fnid_number}")

    suite_tag = build_spaak_suite_tag(group, fnid_number)
    lines: list[str] = [
        f"//****************************TSU_{fnid_number}******************************************************************************//",
        "",
    ]

    for case in cases:
        xml_case_name = get_case_name(case)
        if not xml_case_name:
            continue
        source_name = resolve_source_case_name(xml_case_name, source_blocks)
        source_body = source_blocks[source_name]
        expected_steps = source_step_count(source_body)
        parsed_steps = len(transform_masterdiag_actions(source_body))
        if expected_steps != parsed_steps:
            raise RuntimeError(
                f"Step parse mismatch in {xml_case_name}: source_steps={expected_steps}, parsed_steps={parsed_steps}"
            )
        lines.extend(render_spaak_master_case(xml_case_name, source_body, fnid_number, suite_tag))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a CAPL file from FNID_<number> in STLA_Testsuite.xml.")
    parser.add_argument("file_number", help="Example: 3476 or 3476.can")
    parser.add_argument(
        "--xml",
        default="C:/Users/MDC4KOR/atm/STLA_Testsuite.xml",
        help="Path to the XML file. Default: C:/Users/MDC4KOR/atm/STLA_Testsuite.xml",
    )
    parser.add_argument(
        "--anchor",
        default="C:/Users/MDC4KOR/atm/Diag_masterBLE_anchor 2 (1).can",
        help="Optional anchor file used for recheck validation against real MasterBLE flows.",
    )
    parser.add_argument(
        "--spaak-master",
        action="store_true",
        help="Generate SPAAK Master suite by using XML membership and testcase actions from Masterdiag.cin.",
    )
    parser.add_argument(
        "--cin",
        default="C:/Users/MDC4KOR/atm/Masterdiag.cin",
        help="Path to Masterdiag.cin used when --spaak-master is enabled.",
    )
    args = parser.parse_args()

    try:
        fnid_number = parse_file_number(args.file_number)
        xml_path = Path(args.xml)
        if not xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")

        root = ET.parse(str(xml_path)).getroot()
        group = locate_group(root, fnid_number)

        if args.spaak_master:
            cin_path = Path(args.cin)
            if not cin_path.exists():
                raise FileNotFoundError(f"Masterdiag.cin not found: {cin_path}")
            cin_text = cin_path.read_text(encoding="utf-8", errors="ignore")
            suite_text = generate_spaak_master_suite(group, fnid_number, cin_text)
            expected_count = len(list(group.iter("capltestcase")))
            case_count = len(re.findall(r"^testcase ", suite_text, flags=re.M))
            if case_count != expected_count:
                raise RuntimeError(f"Expected {expected_count} testcase blocks, got {case_count}")

            out_path = Path.cwd() / f"{fnid_number}.can"
            out_path.write_text(suite_text, encoding="utf-8")

            print(f"xml_cases={expected_count}")
            print(f"generated_case_count={case_count}")
            print(f"output_file={out_path}")
            print("SPAAK_MASTER_VALIDATION_OK")
            return 0

        anchor_path = Path(args.anchor)
        anchor_map = load_anchor_case_map(anchor_path)
        suite_text = generate_suite_file(group, fnid_number, anchor_map)
        expected_count = len(list(group.iter("capltestcase")))

        anchor_cases = load_anchor_case_names(anchor_path)
        validate_suite(suite_text, expected_count, anchor_cases)

        out_path = Path.cwd() / f"{fnid_number}.can"
        out_path.write_text(suite_text, encoding="utf-8")

        print(f"xml_cases={expected_count}")
        print(f"generated_case_count={len(re.findall(r'^testcase ', suite_text, flags=re.M))}")
        print(f"output_file={out_path}")
        print(f"anchor_recheck_cases={len(anchor_cases)}")
        print("VALIDATION_OK")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
