import ast
import json
import pathlib
import subprocess
import tempfile
import typing
import re
from datetime import datetime, timezone, timedelta
import pymysql

source = pathlib.Path('server/server.py')
tree = ast.parse(source.read_text(encoding='utf-8-sig'))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_load_sql_config')
scope = {'Dict': typing.Dict, 'Any': typing.Any, 'json': json,
         'SQL_CONFIG_FILE': source.parent / 'Database/sql_config.json'}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), scope)
cfg = scope['_load_sql_config']()
connection = pymysql.connect(host=cfg['host'], port=int(cfg['port']), user=cfg['user'], password=cfg['password'], read_timeout=15)
with connection.cursor() as cursor:
    cursor.execute('SHOW BINARY LOGS')
    logs = cursor.fetchall()
connection.close()

def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'

with tempfile.TemporaryDirectory(prefix='mysql-log-check-') as directory:
    defaults = pathlib.Path(directory) / 'client.cnf'
    defaults.write_text('[client]\n' + '\n'.join(f'{key}={quote(cfg[key])}' for key in ('host', 'port', 'user', 'password')) + '\n', encoding='utf-8')
    def first_transaction(index):
        row = logs[index]
        result = subprocess.run([
            r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqlbinlog.exe',
            f'--defaults-extra-file={defaults}', '--read-from-remote-server',
            '--stop-position=237', row[0],
        ], capture_output=True, text=True, errors='replace', timeout=20)
        if result.returncode:
            raise RuntimeError(result.stderr[:500])
        match = re.search(r'^# original_commit_timestamp=(\d+)', result.stdout, re.MULTILINE)
        if not match:
            raise RuntimeError('No transaction timestamp in ' + row[0])
        return int(match.group(1)) / 1_000_000

    singapore = timezone(timedelta(hours=8))
    cutoff = datetime(2026, 10, 1, tzinfo=singapore).timestamp()
    low, high = 0, len(logs)
    while low < high:
        middle = (low + high) // 2
        if first_transaction(middle) < cutoff:
            low = middle + 1
        else:
            high = middle
    print('OLDEST', logs[0][0], datetime.fromtimestamp(first_transaction(0), singapore).isoformat())
    for index in range(max(0, low-2), min(len(logs), low+1)):
        print('BOUNDARY', logs[index][0], datetime.fromtimestamp(first_transaction(index), singapore).isoformat())
    # Preserve the crossing file in MySQL: it can contain October transactions.
    candidate_count = max(0, low-1)
    print('CONSERVATIVE_ARCHIVE_AND_PURGE_CANDIDATES', candidate_count)
    print('UNCOMPRESSED_GIB', round(sum(row[1] for row in logs[:candidate_count])/1024**3, 2))
    if candidate_count:
        print('LAST_CANDIDATE', logs[candidate_count-1][0])
        print('KEEP_BOUNDARY_FILE', logs[candidate_count][0])
