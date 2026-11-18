"""Copy, compress and verify one closed MySQL binlog. Never purges logs."""
import ast
import gzip
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
import typing
import pymysql

root = pathlib.Path(__file__).resolve().parents[1]
source = root / 'server/server.py'
tree = ast.parse(source.read_text(encoding='utf-8-sig'))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_load_sql_config')
scope = {'Dict': typing.Dict, 'Any': typing.Any, 'json': json,
         'SQL_CONFIG_FILE': source.parent / 'Database/sql_config.json'}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
cfg = scope['_load_sql_config']()
conn = pymysql.connect(host=cfg['host'], port=int(cfg['port']), user=cfg['user'], password=cfg['password'], read_timeout=15)
with conn.cursor() as cursor:
    cursor.execute('SHOW BINARY LOGS')
    logs = cursor.fetchall()
conn.close()
name = 'DESKTOP-55NCVQT-bin.000813'
size = next(row[1] for row in logs if row[0] == name)
assert name != logs[-1][0], 'Only closed logs may be sampled'
reserve = 10 * 1024**3
assert shutil.disk_usage(root).free > reserve + size * 2, 'Insufficient space for a safe sample'
folder = root / 'backups/mysql-september-2026-sample'
folder.mkdir(parents=True, exist_ok=True)
raw = folder / name
archive = folder / (name + '.gz')
assert not raw.exists() and not archive.exists(), 'Sample already exists; do not overwrite'
binary = r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqlbinlog.exe'

def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'

with tempfile.TemporaryDirectory(prefix='mysql-sample-') as temporary:
    defaults = pathlib.Path(temporary) / 'client.cnf'
    defaults.write_text('[client]\n' + '\n'.join(f'{key}={quote(cfg[key])}' for key in ('host', 'port', 'user', 'password')) + '\n', encoding='utf-8')
    print('Copying one closed September binlog, bytes:', size, flush=True)
    subprocess.run([binary, f'--defaults-extra-file={defaults}', '--read-from-remote-server', '--raw',
                    '--result-file=' + str(folder) + '/', name], check=True, timeout=180, stdout=subprocess.DEVNULL)
assert raw.stat().st_size == size, 'Raw backup size differs from server log size'
print('Checking binlog checksums...', flush=True)
subprocess.run([binary, '--no-defaults', '--verify-binlog-checksum', str(raw)], stdout=subprocess.DEVNULL, check=True, timeout=180)
digest = hashlib.sha256()
last = time.monotonic()
done = 0
print('Compressing with gzip level 9...', flush=True)
with raw.open('rb') as inp, gzip.open(archive, 'xb', compresslevel=9) as out:
    while chunk := inp.read(4 * 1024**2):
        assert shutil.disk_usage(root).free > reserve, 'Free space reserve reached; stopping sample'
        digest.update(chunk)
        out.write(chunk)
        done += len(chunk)
        if time.monotonic() - last > 10:
            print('Compressed', round(done / size * 100, 1), '%', flush=True)
            last = time.monotonic()
print('Verifying full decompression and SHA-256...', flush=True)
restored = hashlib.sha256()
restored_size = 0
with gzip.open(archive, 'rb') as inp:
    while chunk := inp.read(4 * 1024**2):
        restored.update(chunk)
        restored_size += len(chunk)
assert restored_size == size and restored.digest() == digest.digest(), 'Archive verification failed'
result = {'source_log': name, 'original_bytes': size, 'compressed_bytes': archive.stat().st_size,
          'raw_sha256': digest.hexdigest(), 'verified': True,
          'estimated_592_GiB_compressed_GiB': round(591.95 * archive.stat().st_size / size, 2),
          'note': 'One-file estimate only; no database logs were purged.'}
(folder / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
# Remove only our verified temporary raw copy; the MySQL original is untouched.
assert raw.resolve().parent == folder.resolve() and folder.resolve().is_relative_to(root)
raw.unlink()
print(json.dumps(result, indent=2), flush=True)
