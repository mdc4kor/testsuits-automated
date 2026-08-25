import re
from pathlib import Path

content = Path('Diag_Anchor 3.can').read_text(encoding='utf-8', errors='ignore')
pattern = r'testcase\s+(TCS_PK_FCA[A-Za-z0-9_]*)\(\)'
matches = re.findall(pattern, content)

suffixes = set()
for name in matches:
    m = re.search(r'_(\d+)$', name)
    if m:
        suffixes.add(m.group(1))

print(f'Total anchor cases: {len(matches)}')
print(f'Unique numeric suffixes: {len(sorted(suffixes))}')
print(f'First 10 suffixes: {sorted(suffixes)[:10]}')

# Check for specific values
target_suffixes = ['21215', '21282', '21221', '54340', '54442']
for s in target_suffixes:
    exists = "YES" if s in suffixes else "NO"
    print(f'  {s}: {exists}')
