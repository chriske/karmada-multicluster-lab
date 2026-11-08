#!/usr/bin/env python3
"""Validate no legacy cluster identifiers remain in v2 source files."""
from pathlib import Path
import os
import re,sys
root=Path(__file__).resolve().parents[1]
allowed={'karmada-mgmt','dc-primary','dc-secondary','cloud-azure'}
legacy=re.compile(r'(?<![A-Za-z0-9-])(?:member[123]|kind-host|karmada-host|kind-east|kind-west|kind-cloud)(?![A-Za-z0-9-])')
problems=[]
for directory, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in {'.git', '.runtime', '.venv', '__pycache__'}]
    for name in files:
        p = Path(directory) / name
        if p.suffix not in {'.yaml', '.yml', '.json', '.py', '.md', '.env', '.sh', ''} or name == 'check_cluster_names.py':
            continue
        try:
            content = p.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            print(f'Cannot check non-UTF-8 source file: {p.relative_to(root)}', file=sys.stderr)
            sys.exit(1)
        m = legacy.search(content)
        if m:
            problems.append(f'{p.relative_to(root)}: {m.group()}')
if problems:
    print('Legacy cluster names found:\n'+'\n'.join(problems));sys.exit(1)
print('OK – canonical names only:',', '.join(sorted(allowed)))
