"""Opt-in integration smoke against a running isolated Gbrain Compose sandbox.

Uses only fictional sessions. Creates three scoped OAuth clients in that sandbox.
Run: python scripts/smoke-gbrain.py --gbrain-binary /absolute/gbrain
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from gm_nightly.cli import main
from gm_nightly.config import load_config
from gm_nightly.employee import load_credentials
from gm_nightly.gbrain import Gbrain, GbrainError
from gm_nightly.storage import atomic_json

parser = argparse.ArgumentParser()
parser.add_argument('--gbrain-binary', required=True)
parser.add_argument('--container', default='gm-nightly-sandbox-trainer-1')
parser.add_argument('--root', type=Path, default=Path('.gm/smoke'))
args = parser.parse_args()
os.umask(0o077)
root = args.root.resolve()
root.mkdir(parents=True, exist_ok=True)


def docker(*command, content=None):
    result = subprocess.run(['docker', 'exec', '-i', args.container, *command], input=content,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Sandbox command failed: ' + command[0])
    return result.stdout


for employee, convention in [('alice', 'two reviewers'), ('bob', 'a staging smoke test'), ('carol', 'a rollback plan')]:
    directory = root / employee
    directory.mkdir(exist_ok=True)
    credential = directory / 'handoff.json'
    if not credential.exists():
        remote_path = '/training/smoke-' + employee + '.json'
        docker('gm-nightly', '--config', '/training/gm-nightly.toml', 'server', 'invite', employee, '--output', remote_path)
        atomic_json(credential, json.loads(docker('cat', remote_path)))
    profile = directory / 'employee.toml'
    if not profile.exists():
        code = main(['employee', 'install', '--company', 'gm-nightly-demo', '--employee-id', employee,
                     '--company-url', 'http://localhost:3131', '--credentials', str(credential),
                     '--gbrain-home', str(directory / 'personal'), '--gbrain-binary', args.gbrain_binary,
                     '--output', str(profile), '--app-settings', str(directory / 'app.json'),
                     '--share-project', str(directory / 'project')])
        if code:
            raise RuntimeError('Employee onboarding failed')
    # Add only the synthetic source; never discover this machine's real agent histories.
    trace = directory / 'trace.jsonl'
    trace.write_text(json.dumps({'type':'message', 'cwd':str(directory / 'project'),
                                'message':{'role':'user','content':f'We always require {convention} before a production deployment.'}})+'\n')
    text = profile.read_text()
    if 'capture_sources' not in text:
        text = text.replace('[capture]', '[capture]\ncapture_sources = [{kind = "jsonl", path = '+json.dumps(str(trace))+'}]')
        profile.write_text(text)
    os.environ.pop('GBRAIN_REMOTE_CLIENT_SECRET', None)
    assert main(['--config', str(profile), 'employee', 'watch', '--once', '--force']) == 0
    assert main(['--config', str(profile), 'employee', 'relay']) == 0
    config = load_config(profile)
    load_credentials(config)
    company = Gbrain(config.gbrain_command, config.company_home, config.company_source, remote=True)
    # The upstream server itself must enforce the employee prefix.
    try:
        company.put('employees/not-' + employee + '/forbidden', 'This write must be rejected.')
    except GbrainError:
        pass
    else:
        raise AssertionError('Upstream write fence failed')
    print('PASS', employee, 'onboarding, compiled relay, duplicate retry, upstream write fence', flush=True)

rows = json.loads(docker('gbrain', 'call', '--source', 'shared', 'list_pages', '{"source_id":"shared","tag":"gm-nightly-share","limit":100}'))
assert len(rows) == 3, len(rows)
for row in rows:
    content = json.loads(docker('gbrain', 'call', '--source', 'shared', 'get_page', json.dumps({'slug':row['slug'],'source_id':'shared'})))
    assert 'compiled_truth' in content
    assert 'trace.jsonl' not in content['compiled_truth']
print('PASS official company Gbrain contains exactly three synthetic compiled pages')
