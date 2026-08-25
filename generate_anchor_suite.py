#!/usr/bin/env python3
"""Generate a CAPL suite file from STLA_Testsuite.xml for a given FNID number using Diag_Anchor 3.can.

Usage:
    python generate_anchor_suite.py 1355
    python generate_anchor_suite.py 1355.can
    python generate_anchor_suite.py 1355 --xml C:\\path\\to\\STLA_Testsuite.xml
    python generate_anchor_suite.py 1355 --xml C:\\path\\to\\STLA_Testsuite.xml --anchor C:\\path\\to\\Diag_Anchor 3.can
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


def parse_file_number(raw: str) -> str:
    value = raw.strip()
    if value.lower().endswith(".can"):
        value = value[:-4]
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"Invalid file number: {raw!r}. Provide a number like 1355 or a filename like 1355.can.")
    return value


def locate_group(root: ET.Element, fnid_number: str) -> ET.Element:
    ident = f"FNID_{fnid_number}"
    for tg in root.iter("testgroup"):
        if tg.get("ident") == ident:
            return tg
    raise RuntimeError(f"FNID_{fnid_number} not found in STLA_Testsuite.xml")


def get_case_name(case: ET.Element) -> str:
    name = case.get("name") or ""
    return name.strip()


def load_anchor_case_map(anchor_path: Path) -> dict[str, str]:
    """Extract all anchor testcase blocks as {name: body_text}."""
    content = anchor_path.read_text(encoding='utf-8', errors='ignore')
    anchor_map = {}
    
    # Find all testcase blocks - handle cases with comments between signature and opening brace
    # Pattern: testcase NAME() [optional comment lines] { body }
    pattern = r'testcase\s+(TCS_PK_FCA[A-Za-z0-9_]*)\(\)[^\{]*\{(.*?)\n\s*\}'
    for match in re.finditer(pattern, content, re.DOTALL):
        case_name = match.group(1)
        body = match.group(2)
        anchor_map[case_name] = body
    
    return anchor_map


def normalize_anchor_signature(name: str) -> tuple[str, ...]:
    """Extract keywords from a test case name for matching."""
    parts = name.replace("_", " ").lower().split()
    return tuple(p for p in parts if p and len(p) > 2)


def resolve_anchor_case_template(case_name: str, anchor_map: dict[str, str]) -> tuple[str, str] | None:
    """Find matching anchor case by numeric suffix. No fallback - numeric suffix must match exactly."""
    if not anchor_map:
        return None

    if case_name in anchor_map:
        return case_name, anchor_map[case_name]

    # Try matching by numeric suffix (last number in the name)
    ident = re.search(r"_(\d+)$", case_name)
    ident_num = ident.group(1) if ident else None

    if ident_num:
        for anchor_name, body in anchor_map.items():
            if anchor_name.endswith(f"_{ident_num}"):
                return anchor_name, body

    # No match found - return None strictly (no keyword fallback)
    return None


def render_anchor_case(case_name: str, fnid_number: str, anchor_name: str, anchor_body: str) -> list[str]:
    """Render a testcase in the Anchor3 format with proper indentation and spacing."""
    lines = [
        f"testcase {case_name}()",
        "{",
        f'  setLogFileName("reports\\Diag\\{fnid_number}\\{case_name}.asc");',
        "",
        "  PreCondition(Anchor3);",
        "",
        '  testCaseComment("Actions");',
    ]

    body_lines = anchor_body.strip().splitlines()

    for raw in body_lines:
        s = raw.strip()
        if not s:
            continue

        if s.startswith("Precondition") or s.startswith("Postcondition"):
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
                # NO blank line after TestStep - request follows immediately
            continue

        if s.startswith("Security_Seed_Key_Access("):
            lines.append('  ' + s)
            lines.append("")  # Add blank line AFTER Security call
            continue

        if s.startswith("SendDiag_Request_Verify_Response("):
            m = re.search(r'SendDiag_Request_Verify_Response\(([^,]+),\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', s)
            if m:
                req, resp = m.group(2), m.group(3)
                if resp.startswith("7F "):
                    lines.append(f'  SendDiag_Request_Neg(0, "Anchor3","{req}","{resp}");')
                else:
                    length = len(resp.replace(" ", "")) // 2
                    lines.append(f'  SendDiag_Request_Verify_and_GetResponse("Anchor3","{req}","{resp}",{length});')
                lines.append("")  # Add blank line AFTER request
            continue

        if s.startswith("SendDiag_Request_Verify_Negative_Response("):
            m = re.search(r'SendDiag_Request_Verify_Negative_Response\(([^,]+),\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', s)
            if m:
                req, resp = m.group(2), m.group(3)
                lines.append(f'  SendDiag_Request_Neg(0, "Anchor3","{req}","{resp}");')
                lines.append("")  # Add blank line AFTER request
            continue

        if s.startswith("SendDiag_Request_Verify_and_GetResponse("):
            lines.append('  ' + s)
            lines.append("")  # Add blank line AFTER request
            continue

        if s.startswith("SendDiag_Request"):
            lines.append('  ' + s)
            lines.append("")  # Add blank line AFTER request

    # Remove trailing blank lines before PostCondition
    while lines and lines[-1] == "":
        lines.pop()

    lines.append("")
    lines.append("  PostCondition(Anchor3);")
    lines.append("}")
    lines.append("")
    return lines


def generate_suite_file(fnid_number: str, xml_path: Path, anchor_path: Path, output_path: Path) -> None:
    """Main entry point: generate the suite file."""
    # Parse XML
    root = ET.parse(str(xml_path)).getroot()
    group = locate_group(root, fnid_number)
    
    # Get test case names from XML
    xml_cases = []
    for case in group.findall("capltestcase"):
        name = get_case_name(case)
        if name:
            xml_cases.append(name)
    
    print(f"xml_cases={len(xml_cases)}")
    
    # Load anchor case map
    anchor_map = load_anchor_case_map(anchor_path)
    
    # Generate test cases - allow partial generation
    blocks = {}
    missing_cases = []
    
    for case_name in xml_cases:
        anchor_match = resolve_anchor_case_template(case_name, anchor_map)
        
        if anchor_match:
            anchor_name, anchor_body = anchor_match
            if not anchor_body or not anchor_body.strip():
                missing_cases.append(f"{case_name} (found anchor '{anchor_name}' but body is empty)")
            else:
                case_lines = render_anchor_case(case_name, fnid_number, anchor_name, anchor_body)
                blocks[case_name] = "\n".join(case_lines)
        else:
            missing_cases.append(case_name)
    
    generated_case_count = len(blocks)
    print(f"generated_case_count={generated_case_count}")
    
    # Report missing cases but continue with partial generation
    if missing_cases:
        print(f"WARNING: {len(missing_cases)} case(s) not found in anchor file:")
        for missing in missing_cases:
            print(f"  - {missing}")
    
    # Write output file with whatever cases were generated
    if generated_case_count > 0:
        title_line = f"/// <{fnid_number}_TSU_PK_FCA_AnchorUDSServer>\n"
        separator = "//********************************************TSU_" + fnid_number + "*******************************************************************************//\n"
        
        output_content = separator + "\n"
        for case_name in xml_cases:
            if case_name in blocks:
                output_content += blocks[case_name] + "\n"
        
        output_path.write_text(output_content, encoding='utf-8')
        print(f"output_file={output_path}")
        print(f"PARTIAL_GENERATION_OK ({generated_case_count}/{len(xml_cases)} cases)")
    else:
        print("ERROR: No cases could be generated")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Generate CAPL suite file from Anchor3 cases")
    parser.add_argument("fnid", help="FNID number (e.g., 1355, 1357, 1316)")
    parser.add_argument("--xml", default="STLA_Testsuite.xml", help="Path to STLA_Testsuite.xml")
    parser.add_argument("--anchor", default="Diag_Anchor 3.can", help="Path to Diag_Anchor 3.can")
    
    args = parser.parse_args()
    
    fnid_number = parse_file_number(args.fnid)
    xml_path = Path(args.xml)
    anchor_path = Path(args.anchor)
    output_path = Path(fnid_number + ".can")
    
    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")
    if not anchor_path.exists():
        raise FileNotFoundError(f"Anchor file not found: {anchor_path}")
    
    generate_suite_file(fnid_number, xml_path, anchor_path, output_path)


if __name__ == "__main__":
    main()
