import ast
import unittest
from pathlib import Path
from typing import Optional


class SessionPersistenceSnapshotTests(unittest.TestCase):
    def test_session_added_during_sql_write_does_not_break_iteration(self):
        source = Path(__file__).resolve().parents[1] / "server" / "server.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_persist_active_sessions_state")
        class Session:
            def to_dict(self):
                return {"machine_code": "M1"}
        sessions = {"M1": Session(), "M2": Session()}
        writes = []
        def save(row):
            writes.append(row)
            sessions.pop("M2", None)
            sessions["M3"] = Session()
            return True
        scope = {"Optional": Optional, "SESSIONS": sessions,
                 "_upsert_active_session_sql": save, "ACTIVE_SESSIONS_JSON_DIRTY": False}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), scope)
        self.assertTrue(scope["_persist_active_sessions_state"]())
        self.assertEqual(len(writes), 2)
        self.assertTrue(scope["ACTIVE_SESSIONS_JSON_DIRTY"])


if __name__ == "__main__":
    unittest.main()
