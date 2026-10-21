import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import server


class DashboardPartShortageTests(unittest.TestCase):
    def setUp(self):
        server._DASHBOARD_PART_SHORTAGE_CACHE.clear()

    @staticmethod
    def session_row():
        return {
            "production_session_id": "TEST-CARRYOVER-SHORTAGE",
            "product_sku": "FINISHED-PRODUCT",
            "job_payload": {
                "data": {
                    "job": {"product_sku": "FINISHED-PRODUCT"},
                    "parts": [
                        {"part_product_id": 8335, "sku": "RESIN-25KG", "name": "Resin"},
                        {"part_product_id": 3270, "sku": "STICKER", "name": "Sticker"},
                    ],
                }
            },
            "raw_material_logs": [
                {"material_product_id": 8335, "material_sku": "RESIN-25KG", "qty": 25, "source": "FINISH_SHIFT_PART_CARRYOVER"},
                {"material_product_id": 8335, "material_sku": "RESIN-25KG", "qty": 25, "source": "RAW_MATERIAL"},
                {"material_product_id": 3270, "material_sku": "STICKER", "qty": 1088, "source": "FINISH_SHIFT_PART_CARRYOVER"},
                {"material_product_id": 3270, "material_sku": "STICKER", "qty": 1000, "source": "RAW_MATERIAL"},
            ],
            "product_pack_history_logs": [{
                "raw_part_consumption": [
                    {"material_product_id": 8335, "material_sku": "RESIN-25KG", "used_qty_kg": 38.73792},
                    {"material_product_id": 3270, "material_sku": "STICKER", "used_qty": 1248},
                ]
            }],
        }

    def test_current_shift_shortage_includes_available_carryover(self):
        result = server._dashboard_product_part_shortages(
            self.session_row(), include_prior_partials=False
        )
        self.assertEqual(result, {"count": 0, "names": [], "details": []})

    def test_dashboard_table_excludes_running_product_from_required_inputs(self):
        script = server.DASHBOARD_JAVASCRIPT
        self.assertIn("function dashboardPartIsRunningProductOrMold(part, item)", script)
        self.assertIn(
            ".filter(part => !dashboardPartIsRunningProductOrMold(part, item))",
            script,
        )


if __name__ == "__main__":
    unittest.main()
