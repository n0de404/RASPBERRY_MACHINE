"""Run the real scan-handler branches without starting Qt or client services."""
import ast
import copy
import unittest
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'client/client.py').read_text(encoding='utf-8-sig'))


def compile_method(name):
    node = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = dict(Any=Any, Optional=Optional, Decimal=Decimal, InvalidOperation=InvalidOperation)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<client-method>', 'exec'), ns)
    return ns[name]


def run_branch(nodes, **scope):
    fn = ast.parse('def run(self, s, res, raw_s, reviewer, res_pre):\n    pass').body[0]
    fn.body = copy.deepcopy(nodes)
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    ns = dict(datetime=datetime, timezone=timezone)
    exec(compile(module, '<scan-branch>', 'exec'), ns)
    ns['run'](**{key: scope.get(key) for key in ('self', 's', 'res', 'raw_s', 'reviewer', 'res_pre')})


class ScanCountingTests(unittest.TestCase):
    def client(self, multiplier=''):
        s = SimpleNamespace(butal_total=0, good_total=12, butal_by_job={}, butal_scan_logs=[],
                            job_code='123', job_name='JOB', operator_id='OP', linkage_enabled=False,
                            linkage_jobs=[], reject_multiplier_input=multiplier)
        c = Mock(state=s)
        c._reject_multiplier_value.side_effect = lambda: compile_method('_reject_multiplier_value')(c)
        c._butal_scan_quantity.side_effect = lambda q, m: compile_method('_butal_scan_quantity')(c, q, m)
        c._normalize_job_code.side_effect = lambda value: value
        c._scan_owner_context.return_value = {}
        c._clear_reject_multiplier.side_effect = lambda: setattr(s, 'reject_multiplier_input', '')
        return c

    def scan(self, c, qty):
        branch = next(n for n in ast.walk(TREE) if isinstance(n, ast.If)
                      and ast.unparse(n.test) == "res.kind == 'BUTAL'"
                      and any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                              and x.func.attr == '_butal_scan_quantity' for x in ast.walk(n)))
        run_branch(branch.body, self=c, s=c.state, res=SimpleNamespace(qty=qty), raw_s='BUTAL-QR')

    def test_whole_scan_and_multiplier_count_without_linkage(self):
        for multiplier, expected in [('', 1), ('5', 5), ('12', 12)]:
            with self.subTest(multiplier=multiplier):
                c = self.client(multiplier)
                self.scan(c, 1)
                self.assertEqual(c.state.butal_total, expected)
                self.assertEqual(c.state.butal_by_job, {'123': expected})
                self.assertEqual(c.state.butal_scan_logs[0]['qty'], expected)
                self.assertEqual(c.state.reject_multiplier_input, '')
                c.lblButal.add_points.assert_called_once_with(expected)
                c.lblTotalGood.add_points.assert_called_once_with(expected)
                self.assertEqual(c.push_event.call_args.args[0]['butal_record']['qty'], expected)

    def test_decimal_is_multiplied_before_conversion(self):
        c = self.client('4')
        self.scan(c, 0.25)
        self.assertEqual(c.state.butal_total, 1)
        self.assertEqual(c.state.butal_scan_logs[0]['base_qty'], 0.25)

    def test_invalid_quantity_never_records_zero_or_consumes_multiplier(self):
        for qty in (0, -1, 0.1, float('nan'), float('inf')):
            c = self.client('2')
            self.scan(c, qty)
            self.assertEqual(c.state.butal_total, 0)
            self.assertEqual(c.state.butal_scan_logs, [])
            self.assertEqual(c.state.reject_multiplier_input, '2')
            c.push_event.assert_not_called()
            c._show_invalid_overlay.assert_called_once()

    def test_linkage_waits_for_assignment_without_counting_twice(self):
        c = self.client('3')
        c.state.linkage_enabled = True
        c.state.linkage_jobs = [{'job_code': '456'}]
        c._butal_assignment_candidates.return_value = c.state.linkage_jobs
        self.scan(c, 2)
        self.assertEqual(c.state.pending_butal_qty, 6)
        self.assertEqual(c.state.butal_total, 0)
        c.push_event.assert_not_called()


class SupervisorRotationTests(unittest.TestCase):
    def test_legacy_operator_badge_is_checked_for_supervisor_privileges(self):
        scan = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name == 'on_scanned')
        assignment = next(n for n in scan.body if isinstance(n, ast.Assign)
                          and ast.unparse(n.targets[0]) == 'reviewer'
                          and isinstance(n.value, ast.IfExp))
        c = Mock()
        c._reviewer_from_scan.return_value = {'can_supervisor': '1'}
        run_branch([assignment], self=c, raw_s='1000001', res_pre=SimpleNamespace(kind='OPERATOR'))
        c._reviewer_from_scan.assert_called_once_with('1000001')
        c.reset_mock()
        run_branch([assignment], self=c, raw_s='butal', res_pre=SimpleNamespace(kind='BUTAL'))
        c._reviewer_from_scan.assert_not_called()

    def test_rotation_reports_durable_queue_result(self):
        branch = next(n for n in ast.walk(TREE) if isinstance(n, ast.If)
                      and ast.unparse(n.test) == 'reviewer_can_supervisor')
        for saved in (True, False):
            c = Mock()
            c.push_event.return_value = saved
            run_branch(branch.body, self=c, reviewer={'code': '123', 'name': 'Supervisor', 'role': 'SUPERVISOR'})
            self.assertEqual(c.push_event.call_args.args[0]['type'], 'SUPERVISOR_ROTATION_CHECK')
            if saved:
                c._show_info_overlay.assert_called_once()
                c._show_invalid_overlay.assert_not_called()
            else:
                c._show_invalid_overlay.assert_called_once()


if __name__ == '__main__':
    unittest.main()
