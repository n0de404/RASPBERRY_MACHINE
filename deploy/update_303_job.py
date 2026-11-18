"""Safely enrich IMM 303's active job and synchronize it to its client."""

from __future__ import annotations

import base64
import getpass
import os
import sys

import paramiko


HOST = "192.168.13.18"
MODE = sys.argv[1] if len(sys.argv) > 1 else "inspect"

REMOTE_INSPECT = r'''
import json, os, pathlib, sqlite3

root = pathlib.Path('/home/user/Raspberry_Machine/client')
processes = []
runtime_env = {}
process_errors = []
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        args = (entry / 'cmdline').read_bytes().split(b'\0')
        executable = args[0].decode()
        command_line = b' '.join(args).decode(errors='replace')
        if 'RaspberryMachineClient' not in command_line and 'mixing_client.py' not in command_line:
            continue
        processes.append({'pid': int(entry.name), 'executable': executable, 'command_line': command_line})
        if not runtime_env:
            runtime_env = dict(
                value.decode().split('=', 1)
                for value in (entry / 'environ').read_bytes().split(b'\0')
                if b'=' in value
            )
    except (OSError, UnicodeError, ValueError) as error:
        process_errors.append({'pid': entry.name, 'error': str(error)})

preferred_data_dir = pathlib.Path(runtime_env.get(
    'MACHINE_DATA_DIR', '/home/user/.local/share/raspberry-machine-client'
))
candidates = [preferred_data_dir / 'client_runtime.sqlite3']
for base in (pathlib.Path('/home/user'), pathlib.Path('/home/pi')):
    if base.exists():
        candidates.extend(base.glob('**/client_runtime.sqlite3'))
db_path = next((path for path in candidates if path.is_file()), None)
if db_path is None:
    session_file = preferred_data_dir / 'client_active_machine_sessions.json'
    if session_file.is_file():
        raw_sessions = json.loads(session_file.read_text(encoding='utf-8'))
        if isinstance(raw_sessions, dict) and isinstance(raw_sessions.get('sessions'), dict):
            raw_sessions = raw_sessions['sessions']
        row = raw_sessions.get('M00003') if isinstance(raw_sessions, dict) else None
        if row is None and isinstance(raw_sessions, list):
            row = next((item for item in raw_sessions if isinstance(item, dict) and item.get('machine_code') == 'M00003'), None)
        queue_file = preferred_data_dir / 'server_event_queue.json'
        queue_payload = json.loads(queue_file.read_text(encoding='utf-8')) if queue_file.is_file() else []
        queued_rows = queue_payload.get('items', []) if isinstance(queue_payload, dict) else queue_payload
        print(json.dumps({
            'processes': processes,
            'data_dir': str(preferred_data_dir),
            'storage': 'json',
            'client_id': (row or {}).get('client_id'),
            'production_session_id': (row or {}).get('production_session_id'),
            'job_code': (row or {}).get('job_code'),
            'job_name': (row or {}).get('job_name'),
            'has_job_payload': bool((row or {}).get('job_payload')),
            'pack_count': (row or {}).get('pack_count'),
            'good_total': (row or {}).get('good_total'),
            'queued_events': len(queued_rows or []),
        }, separators=(',', ':')))
        raise SystemExit(0)
    known_dirs = {}
    for path in (
        pathlib.Path('/home/user/.local/share'),
        preferred_data_dir,
        pathlib.Path('/home/user/Raspberry_Machine/client/Database'),
    ):
        try:
            known_dirs[str(path)] = [item.name for item in path.iterdir()]
        except OSError as error:
            known_dirs[str(path)] = {'error': str(error)}
    print(json.dumps({'processes': processes, 'process_errors': process_errors, 'runtime_env_keys': sorted(runtime_env), 'preferred_data_dir': str(preferred_data_dir), 'database_candidates': [str(path) for path in candidates], 'known_dirs': known_dirs}))
    raise SystemExit(3)
data_dir = db_path.parent
conn = sqlite3.connect('file:' + str(db_path) + '?mode=ro', uri=True)
row = conn.execute(
    'select client_id, production_session_id, payload_json from active_sessions where machine_code=?',
    ('M00003',),
).fetchone()
payload = json.loads(row[2]) if row else {}
columns = {item[1] for item in conn.execute('pragma table_info(event_outbox)')}
event_column = 'event_type' if 'event_type' in columns else None
if event_column:
    queued = conn.execute('select event_type, count(1) from event_outbox group by event_type').fetchall()
else:
    queued = [('ALL', conn.execute('select count(1) from event_outbox').fetchone()[0])]
conn.close()
print(json.dumps({
    'processes': processes,
    'data_dir': str(data_dir),
    'client_id': row[0] if row else None,
    'production_session_id': row[1] if row else None,
    'job_code': payload.get('job_code'),
    'job_name': payload.get('job_name'),
    'has_job_payload': bool(payload.get('job_payload')),
    'pack_count': payload.get('pack_count'),
    'good_total': payload.get('good_total'),
    'queued_events': queued,
}, separators=(',', ':')))
'''

REMOTE_APPLY = r'''
import datetime, json, os, pathlib, shutil, signal, subprocess, time, urllib.request, uuid

server = 'http://192.168.10.49:8000'
data_dir = pathlib.Path('/home/user/.local/share/raspberry-machine-client')
session_file = data_dir / 'client_active_machine_sessions.json'
binary = '/home/user/Raspberry_Machine/client/dist/RaspberryMachineClient'

def get_json(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.load(response)

def post_json(url, body):
    request = urllib.request.Request(
        url,
        data=json.dumps(body, separators=(',', ':')).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.status, json.load(response)

lookup_status, lookup = post_json(server + '/api/jobs/lookup', {'job_identifier': '120096'})
job_payload = lookup.get('payload') if isinstance(lookup, dict) else None
data = job_payload.get('data') if isinstance(job_payload, dict) else None
job = data.get('job') if isinstance(data, dict) else None
assert lookup_status == 200 and isinstance(job, dict), 'BMS lookup did not return a job'
assert str(job.get('id') or '') == '120096', 'BMS returned the wrong job'
assert str(job.get('ref_no') or '') == '3-26-1524-3', 'Unexpected job reference'

server_before = get_json(server + '/api/active-sessions/M00003').get('item') or {}
raw_sessions = json.loads(session_file.read_text(encoding='utf-8'))
session_map = raw_sessions.get('sessions') if isinstance(raw_sessions, dict) and isinstance(raw_sessions.get('sessions'), dict) else raw_sessions
assert isinstance(session_map, dict) and isinstance(session_map.get('M00003'), dict), 'Local M00003 session is missing'
snapshot = dict(session_map['M00003'])
assert snapshot.get('client_id') == 'RPI-CLIENT-11', 'Unexpected client identity'
assert snapshot.get('production_session_id') == 'PS-139B4D102D394B0387F66A9AEB9B2301', 'Production session changed; refusing repair'
assert server_before.get('production_session_id') == snapshot.get('production_session_id'), 'Server/client session mismatch'
assert str(snapshot.get('job_code') or '') == '120096', 'Client moved to another job'
assert int(snapshot.get('pack_count', snapshot.get('pack_total', 0)) or 0) == 0, 'Production scans started; refusing repair'
assert int(snapshot.get('good_total') or 0) == 0, 'Production quantity changed; refusing repair'
queue_file = data_dir / 'server_event_queue.json'
queue_payload = json.loads(queue_file.read_text(encoding='utf-8')) if queue_file.is_file() else []
queue_rows = queue_payload.get('items', []) if isinstance(queue_payload, dict) else queue_payload
assert not queue_rows, 'Pending client events require review'

processes = []
runtime_env = None
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        args = (entry / 'cmdline').read_bytes().split(b'\0')
        if not args or args[0].decode() != binary:
            continue
        processes.append(int(entry.name))
        runtime_env = dict(
            value.decode().split('=', 1)
            for value in (entry / 'environ').read_bytes().split(b'\0')
            if b'=' in value
        )
    except (OSError, UnicodeError, ValueError):
        pass
assert processes and runtime_env, 'Running client process was not found'

for pid in sorted(processes, reverse=True):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(3)
assert not any(pathlib.Path('/proc/' + str(pid)).exists() for pid in processes), 'Client did not stop cleanly'

stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
backup = data_dir / ('client_active_machine_sessions.before-job-120096-' + stamp + '.json')
shutil.copy2(session_file, backup)
snapshot['job_name'] = str(job.get('ref_no'))
snapshot['job_payload'] = job_payload
snapshot['product_id'] = str(job.get('product_id') or snapshot.get('product_id') or '')
snapshot['saved_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
session_map['M00003'] = snapshot
temporary = session_file.with_suffix('.job-120096.tmp')
with temporary.open('w', encoding='utf-8') as handle:
    json.dump(raw_sessions, handle, ensure_ascii=False, indent=2)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, session_file)

event_id = 'REMOTE-JOB-ENRICH-' + uuid.uuid4().hex.upper()
created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
event_body = {
    'client_id': snapshot['client_id'],
    'machine_code': 'M00003',
    'machine_name': snapshot.get('machine_name') or 'IMM 303',
    'job_code': '120096',
    'job_name': snapshot['job_name'],
    'operator_id': snapshot.get('operator_id'),
    'production_session_id': snapshot['production_session_id'],
    'event_id': event_id,
    'event_created_at_utc': created_at,
    'event': {'type': 'SESSION_SYNC', 'session_snapshot': snapshot},
    'last_event': 'JOB DETAILS RECOVERED 120096',
}
sync_status, sync_result = post_json(server + '/api/event', event_body)
assert sync_status == 200 and sync_result.get('ok') is True, 'Server session sync failed: ' + repr(sync_result)
assert sync_result.get('ack_event_id') == event_id, 'Server did not acknowledge repair event'

clean_env = {
    key: value for key, value in runtime_env.items()
    if not key.startswith('_PYI') and key not in ('_MEIPASS2', 'LD_LIBRARY_PATH')
}
log_path = pathlib.Path('/home/user/.local/state/raspberry-machine-client/client.log')
log_path.parent.mkdir(parents=True, exist_ok=True)
log = log_path.open('ab', buffering=0)
process = subprocess.Popen(
    [binary], cwd='/home/user/Raspberry_Machine/client', env=clean_env,
    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
)
time.sleep(7)
assert process.poll() is None, 'Client failed to restart'

server_after = get_json(server + '/api/active-sessions/M00003').get('item') or {}
assert server_after.get('production_session_id') == snapshot['production_session_id']
assert str(server_after.get('job_code') or '') == '120096'
assert str(server_after.get('job_name') or '') == '3-26-1524-3'
assert bool(server_after.get('job_payload')), 'Server still has an empty job payload'
print(json.dumps({
    'ok': True,
    'machine': 'IMM 303',
    'client_id': snapshot['client_id'],
    'job_code': server_after.get('job_code'),
    'job_name': server_after.get('job_name'),
    'production_session_id': server_after.get('production_session_id'),
    'server_has_payload': bool(server_after.get('job_payload')),
    'backup': str(backup),
    'client_pid': process.pid,
}, separators=(',', ':')))
'''


def main() -> int:
    password = os.environ.get("PI_PASSWORD") or getpass.getpass("Pi password: ")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="user", password=password, timeout=8)
    try:
        if MODE not in {"inspect", "apply"}:
            raise SystemExit(f"Unsupported mode: {MODE}")
        remote_source = REMOTE_APPLY if MODE == "apply" else REMOTE_INSPECT
        encoded = base64.b64encode(remote_source.encode()).decode()
        command = f"python3 -c \"import base64;exec(base64.b64decode('{encoded}'))\""
        _, stdout, stderr = client.exec_command(command, timeout=20)
        output = stdout.read().decode(errors="replace")
        errors = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        if output:
            print(output, end="")
        if errors:
            print(errors, end="", file=sys.stderr)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
