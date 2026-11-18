import ast
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock


class SupervisorReviewIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'client/client.py').read_text(encoding='utf-8'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_authorized_person_from_scan')
        ns = {'Optional': object, 'Dict': dict, 'datetime': datetime,
              'SUPERVISOR_BADGES': {}, 'QC_BADGES': {}}
        method.returns = None
        for arg in method.args.args:
            arg.annotation = None
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<review-identity>', 'exec'), ns)
        cls.authorize = staticmethod(ns['_authorized_person_from_scan'])

    def client(self):
        c = Mock()
        c._clean_badge_scan_code.side_effect = lambda raw: raw.strip()
        c._user_qr_profiles_cache = [
            {'id_number': 'svisorreview~1', 'name': 'SUPERVISOR REVIEW', 'role': 'Supervisor'},
            {'id_number': '80033', 'name': 'RONNEL GALANG', 'role': 'Supervisor'},
        ]
        c._daily_role_assignments_cache = {}
        c._role_caps_from_text.return_value = {'supervisor'}
        return c

    def test_review_command_cannot_identify_a_supervisor_even_if_registered(self):
        for raw in ['svisorreview~1', 'SVISORREVIEW~1', ' svisorreview~1 ']:
            self.assertIsNone(self.authorize(self.client(), raw))

    def test_personal_badge_keeps_supervisor_name(self):
        result = self.authorize(self.client(), '80033')
        self.assertEqual(result['name'], 'RONNEL GALANG')
        self.assertEqual(result['code'], '80033')
        self.assertEqual(result['can_supervisor'], '1')


if __name__ == '__main__':
    unittest.main()
