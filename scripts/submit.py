"""Submits the built .elf to Simantic's /simulate with the project's MCU."""

import base64
import json
import os
import urllib.error
import urllib.request

from simantic_config import ConfigError, load, warn_legacy

try:
    cfg = load(os.environ.get('CONFIG', ''))
except ConfigError as e:
    print(f'::error::{e}')
    raise SystemExit(1)
warn_legacy(cfg)

# Only simantic.yml has a trigger; with simantic.json the workflow's on: decides.
trigger = cfg['trigger'] or ('push' if cfg['legacy'] else None)
event = os.environ.get('GITHUB_EVENT_NAME', '')
if trigger == 'push' and event == 'pull_request':
    print('Skipping simulation (trigger: push only)')
    raise SystemExit(0)
if trigger == 'pull_request' and event == 'push':
    print('Skipping simulation (trigger: pull_request only)')
    raise SystemExit(0)

payload = json.dumps({
    'repo_full_name': os.environ['GITHUB_REPOSITORY'],
    'sha': os.environ['GITHUB_SHA'],
    'mcu_model': cfg['mcu'],
    'elf_base64': base64.b64encode(open(os.environ['ELF_PATH'], 'rb').read()).decode(),
    'commit_message': os.environ.get('GITHUB_REF_NAME', ''),
}).encode()
req = urllib.request.Request(
    os.environ['API_URL'] + '/simulate',
    data=payload,
    headers={
        'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
        'Content-Type': 'application/json',
    },
    method='POST',
)
try:
    with urllib.request.urlopen(req) as resp:
        print('Simulation queued:', resp.read().decode())
except urllib.error.HTTPError as e:
    print('Simantic API error', e.code, e.read().decode())
    raise SystemExit(1)
