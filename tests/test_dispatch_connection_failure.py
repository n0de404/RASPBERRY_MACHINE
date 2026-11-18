import ast
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class DispatchConnectionFailureTests(unittest.TestCase):
    def test_connection_failure_keeps_event_and_worker_alive_until_retry(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'client/client.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_event_dispatch_loop')
        stop = threading.Event()
        post = Mock(side_effect=ConnectionError('server unavailable at startup'))
        namespace = dict(queue=queue, requests=SimpleNamespace(post=post),
                         time=SimpleNamespace(sleep=lambda _: stop.set()),
                         SERVER_URL='http://server', SERVER_SYNC_PROTOCOL_VERSION=2,
                         _server_event_queue_row_is_stale=lambda _: False)
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<dispatcher>', 'exec'), namespace)
        item = {'id': 'durable-event', 'silent': True, 'payload': {'production_session_id': 'local-session', 'sync_protocol_requested': 2}}
        client = Mock()
        client._event_worker_stop = stop
        client._event_queue = queue.Queue()
        client._event_queue.put(item)
        client._server_batch_acknowledged_ids = set()
        client._normalize_server_event_item.side_effect = lambda row, **_: row
        client._event_superseded_by_recovery_snapshot.return_value = False
        client._server_event_belongs_to_current_client.return_value = True
        client._persist_server_event_item.return_value = True
        client._server_event_type_from_item.return_value = 'PACK'
        client._try_dispatch_server_event_batch.return_value = False
        client._should_persist_server_event.return_value = True
        client.client_config = {'server_url': 'http://server'}
        client.state = SimpleNamespace(production_session_id='local-session')
        namespace['_event_dispatch_loop'](client)
        post.assert_called_once()
        client._mark_persisted_server_event_failed.assert_called_once()
        client._remove_persisted_server_event.assert_not_called()
        self.assertEqual(client._event_queue.unfinished_tasks, 0)


if __name__ == '__main__':
    unittest.main()
