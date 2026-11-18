import ast
import queue
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import Mock, sentinel


SOURCE = Path(__file__).resolve().parents[1] / 'client/client.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8-sig'))


def method(name, **extra):
    node = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(Dict=Dict, Any=Any, Optional=Optional, datetime=datetime,
                 timezone=timezone, time=time, queue=queue, SERVER_URL='http://server', **extra)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope[name]


class OfflineLinkageTests(unittest.TestCase):
    def test_uncached_lookup_probes_server_after_previous_connection_failure(self):
        client = Mock(client_config={'server_url':'http://server'}, _server_connection_ok=False)
        client._cached_job_payload.return_value = None
        payload = {'data': {'job': {'id': '120096', 'ref_no': '3-26-1524-3'}}}
        response = Mock(status_code=200)
        response.json.return_value = {'payload': payload}
        client._request_with_ui_events.return_value = response

        result = method(
            '_fetch_job_payload_from_api',
            requests=SimpleNamespace(post=sentinel.requests_post),
        )(client, '120096')

        self.assertEqual(result, payload)
        client._request_with_ui_events.assert_called_once()
        self.assertEqual(client._request_with_ui_events.call_args.kwargs['timeout'], (0.75, 15.0))
        client._cache_job_payload.assert_called_once_with(payload, '120096')

    def test_cached_offline_lookup_still_skips_network(self):
        client = Mock(client_config={'server_url':'http://server'}, _server_connection_ok=False)
        payload = {'data': {'job': {'id': '120096'}}}
        client._cached_job_payload.return_value = payload

        result = method('_fetch_job_payload_from_api')(client, '120096')

        self.assertEqual(result, payload)
        client._request_with_ui_events.assert_not_called()

    def test_offline_placeholder_preserves_scanned_identity(self):
        payload = method('_offline_linkage_payload')(Mock(), '123', 'WO-123')
        self.assertTrue(payload['_offline_linkage_pending'])
        self.assertEqual(payload['_offline_job_identifier'], '123')
        self.assertEqual(payload['data']['job']['ref_no'], 'WO-123')
        self.assertNotIn('parts', payload['data'])

    def test_reconnect_enriches_link_without_changing_allocations(self):
        row = {'job_code':'123', 'job_name':'WO-123', 'good_total':25,
               'job_payload':method('_offline_linkage_payload')(Mock(), '123', 'WO-123')}
        state = SimpleNamespace(production_session_id='PS1', linkage_jobs=[row], linkage_job_code='123')
        client = Mock(state=state, _server_connection_ok=True, _last_offline_linkage_lookup=0)
        payload = {'data':{'job':{'id':456,'ref_no':'WO-123'},'parts':[{'sku':'PART'}]}}
        client._fetch_job_payload_from_api.return_value = payload
        method('_refresh_offline_linkage_details')(client)
        self.assertEqual(row['job_code'], '123')
        self.assertEqual(row['good_total'], 25)
        self.assertIs(row['job_payload'], payload)
        client._save_active_session_snapshot.assert_called_once()
        client.sync_session_snapshot_to_server.assert_called_once()

    def test_failed_enrichment_keeps_pending_job(self):
        payload = method('_offline_linkage_payload')(Mock(), '123', 'WO-123')
        row = {'job_code':'123','job_payload':payload}
        client = Mock(state=SimpleNamespace(production_session_id='PS1',linkage_jobs=[row]),
                      _server_connection_ok=True,_last_offline_linkage_lookup=0)
        client._fetch_job_payload_from_api.return_value = None
        method('_refresh_offline_linkage_details')(client)
        self.assertIs(row['job_payload'], payload)
        client._save_active_session_snapshot.assert_not_called()


class RecoveryQueueTests(unittest.TestCase):
    def test_old_state_snapshots_skip_but_production_and_finishes_remain(self):
        client = Mock(_server_recovery_cutoff_by_session={'PS1':'2026-10-08T01:00:00+00:00'})
        check = method('_event_superseded_by_recovery_snapshot')
        item = {'created_at_utc':'2026-10-08T00:00:00+00:00','payload':{'production_session_id':'PS1'}}
        for kind in ['SESSION_SYNC','JOB_SET','OPERATOR_SET']:
            client._server_event_type_from_item.return_value = kind
            self.assertTrue(check(client,item),kind)
        for kind in ['PACK','REJECT','RAW_MATERIAL','FINISH_SHIFT','FINISH_JOB','PACK_VOID']:
            client._server_event_type_from_item.return_value = kind
            self.assertFalse(check(client,item),kind)
        client._server_event_type_from_item.return_value = 'SESSION_SYNC'
        item['created_at_utc']='2026-10-08T02:00:00+00:00'
        self.assertFalse(check(client,item))
        item['created_at_utc']='2026-10-08T00:00:00+00:00'
        item['payload']['production_session_id']='PS2'
        self.assertFalse(check(client,item))

    def test_recovery_goes_to_front_without_losing_queued_records(self):
        client = Mock(_server_recovery_snapshot_queued=False)
        client._event_queue=queue.Queue()
        client._event_queue.put({'id':'pack'})
        recovery={'id':'recovery'}
        client._build_session_recovery_event_item.return_value=recovery
        client._persist_server_event_item.return_value=True
        method('_enqueue_reconnect_session_snapshot_sync')(client)
        self.assertEqual(client._event_queue.get(),recovery)
        self.assertEqual(client._event_queue.get(),{'id':'pack'})
        self.assertEqual(client._event_queue.unfinished_tasks,2)

    def test_full_memory_queue_still_prioritizes_durable_recovery(self):
        client = Mock(_server_recovery_snapshot_queued=False)
        client._event_queue=queue.Queue(maxsize=1)
        client._event_queue.put({'id':'already-durable-pack'})
        recovery={'id':'recovery'}
        client._build_session_recovery_event_item.return_value=recovery
        client._persist_server_event_item.return_value=True
        method('_enqueue_reconnect_session_snapshot_sync')(client)
        self.assertEqual(client._event_queue.get(),recovery)
        self.assertEqual(client._event_queue.unfinished_tasks,1)
        client._remove_persisted_server_event.assert_not_called()


if __name__ == '__main__':
    unittest.main()
