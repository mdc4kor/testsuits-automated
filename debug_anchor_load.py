import re
from pathlib import Path

anchor_path = Path("Diag_Anchor 3.can")
content = anchor_path.read_text(encoding='utf-8', errors='ignore')

# Use the UPDATED pattern with \n\s*\}
pattern = r'testcase\s+(TCS_PK_FCA[A-Za-z0-9_]*)\(\)\s*\{(.*?)\n\s*\}'
anchor_map = {}
for match in re.finditer(pattern, content, re.DOTALL):
    case_name = match.group(1)
    body = match.group(2)
    anchor_map[case_name] = body

print(f"Total anchor cases loaded: {len(anchor_map)}")

# Look for 29555
found_29555 = [name for name in anchor_map if '29555' in name]
print(f"\nCases with suffix 29555: {found_29555}")

# Look for any TesterPresent
found_tp = [name for name in anchor_map if 'TesterPresent' in name]
print(f"\nTesterPresent cases: {len(found_tp)}")
if found_tp:
    print(f"  Examples: {found_tp[:3]}")
