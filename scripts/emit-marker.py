#!/usr/bin/env python3
"""Best-effort scenario markers sent to Loki; no client dependencies.
Does not affect scenario outcome if observability has not been installed.
"""
import json,os,sys,time,urllib.request
endpoint=os.getenv('LOKI_PUSH_URL','http://127.0.0.1:31091/loki/api/v1/push')
message=' '.join(sys.argv[1:]) or 'event'
record=json.dumps({'event':message, 'scenario':os.getenv('SCENARIO','lab'), 'source_cluster':'karmada-mgmt'},separators=(',',':'))
payload={'streams':[{'stream':{'source_type':'scenario-marker','source_cluster':'karmada-mgmt'},
                     'values':[[str(time.time_ns()),record]]}]}
request=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
try:
 with urllib.request.urlopen(request,timeout=2) as res:
  if res.status not in (200,204):raise RuntimeError(res.status)
 print('loki marker:',message)
except Exception as e:
 print('loki marker skipped:',str(e),file=sys.stderr)
