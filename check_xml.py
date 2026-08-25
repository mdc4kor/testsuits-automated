import xml.etree.ElementTree as ET

root = ET.parse('STLA_Testsuite.xml').getroot()
for group in root.findall('testgroup'):
    if group.get('ident') == 'FNID_3474':
        cases = group.findall('capltestcase')
        print(f'Found {len(cases)} cases in FNID_3474')
        for c in cases[:3]:
            print(f'  - {c.get("name")}')
        break
