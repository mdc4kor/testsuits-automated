import re
from pathlib import Path
from xml.etree import ElementTree as ET

# Load XML to get all FNIDs and their case identifiers
root = ET.parse('STLA_Testsuite.xml').getroot()
fnid_to_idents = {}
for tg in root.iter('testgroup'):
    fnid = tg.get('ident', '')
    if fnid.startswith('FNID_'):
        idents = []
        for case in tg.findall('capltestcase'):
            ident = case.get('ident', '')
            if ident:
                idents.append(ident)
        fnid_to_idents[fnid] = set(idents)

# Load anchor file and extract all suffixes
content = Path('Diag_Anchor 3.can').read_text(encoding='utf-8', errors='ignore')
pattern = r'testcase\s+(TCS_PK_FCA[A-Za-z0-9_]*)\(\)'
matches = re.findall(pattern, content)

anchor_suffixes = set()
for name in matches:
    m = re.search(r'_(\d+)$', name)
    if m:
        anchor_suffixes.add(m.group(1))

# Find which FNIDs have matching cases in anchor
print("FNIDs with available anchor cases:")
print("-" * 50)
for fnid in sorted(fnid_to_idents.keys()):
    xml_idents = fnid_to_idents[fnid]
    matching = xml_idents & anchor_suffixes
    if matching:
        print(f"{fnid}: {len(matching)}/{len(xml_idents)} cases available")
        if len(matching) < 5:
            print(f"  Suffixes: {sorted(matching)}")

print("\nFNIDs with NO matching anchor cases:")
print("-" * 50)
for fnid in sorted(fnid_to_idents.keys()):
    xml_idents = fnid_to_idents[fnid]
    matching = xml_idents & anchor_suffixes
    if not matching:
        print(f"{fnid}: 0/{len(xml_idents)} cases - NONE FOUND")
