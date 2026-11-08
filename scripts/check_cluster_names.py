#!/usr/bin/env python3
"""Validate no legacy cluster identifiers remain in v2 source files."""
from pathlib import Path
import re,sys
root=Path(__file__).resolve().parents[1]
allowed={'karmada-mgmt','dc-primary','dc-secondary','cloud-azure'}
legacy=re.compile(r'(?<![A-Za-z0-9-])(?:member[123]|kind-host|karmada-host|kind-east|kind-west|kind-cloud)(?![A-Za-z0-9-])')
problems=[]
for p in root.rglob('*'):
    if not p.is_file() or p.suffix not in {'.yaml','.json','.py','.md','.env',''} or p.name=='check_cluster_names.py':continue
    m=legacy.search(p.read_text())
    if m:problems.append(f'{p.relative_to(root)}: {m.group()}')
if problems:
    print('Legacy cluster names found:\n'+'\n'.join(problems));sys.exit(1)
print('OK – canonical names only:',', '.join(sorted(allowed)))
