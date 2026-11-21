import os
import sys
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFrame, QLabel

import client as production_client


class ChoiceOverlayCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reject_cards_replace_change_color_mold_cards(self):
        ui = production_client.ClientUI()
        try:
            ui.resize(1280, 720)
            ui.show()
            self.app.processEvents()

            # Populate the compact Reject cache, then replace the shared grid
            # with the non-compact Change Color/Mold menu.
            ui._show_reject_reason_choices_overlay()
            ui._show_choice_cards_overlay(
                "CHANGE COLOR / MOLD",
                [
                    {"name": "CHANGE COLOR", "info": "Same product, different color"},
                    {"name": "CHANGE MOLD", "info": "Different product / mold"},
                ],
                footer="Scan num_1 or num_2.",
            )

            # Reopening Reject must rebuild its 21 choices and must also cancel
            # the delayed first-layout redraw belonging to the previous menu.
            ui._show_reject_reason_choices_overlay()
            QTest.qWait(140)
            self.app.processEvents()

            cards = [
                child
                for child in ui.choiceCardsWidget.findChildren(QFrame)
                if child.objectName().startswith("ScanChoiceCard")
            ]
            labels = " ".join(
                label.text().upper()
                for label in ui.choiceCardsWidget.findChildren(QLabel)
            )
            self.assertEqual(len(cards), 21)
            self.assertIn("BURN MARK", labels)
            self.assertNotIn("CHANGE COLOR", labels)
            self.assertEqual(ui.invalidTextLabel.text(), "Select Reject Detail")
        finally:
            ui.close()
            ui.deleteLater()
            self.app.processEvents()

    def test_finish_job_excess_rows_render_quantities(self):
        ui = production_client.ClientUI()
        try:
            ui.resize(1280, 720)
            self.assertNotIn("}}", ui.productPartYesCard.styleSheet())
            self.assertNotIn("}}", ui.productPartNoCard.styleSheet())
            ui._pending_finish_excess_rows = [{
                "sku": "PART-A",
                "expected_qty": 12.5,
                "actual_qty": 10.25,
                "difference_qty": -2.25,
                "print_qty": 10.25,
                "status": "ACTUAL SAVED",
                "input": "10.25",
                "unit": "kg",
            }]
            ui._pending_finish_excess_index = 0
            ui._pending_finish_excess_ready_to_print = True

            ui._render_finish_job_excess_review()

            self.assertEqual(ui.finishInventoryTable.item(0, 3).text(), "12.5 kg")
            self.assertEqual(ui.finishInventoryTable.item(0, 4).text(), "10.25 kg")
            self.assertEqual(ui.finishInventoryTable.item(0, 5).text(), "10.25 kg")
            self.assertEqual(ui.finishInventoryTable.item(0, 6).text(), "-2.25 kg")
            self.assertEqual(ui.finishInventoryTable.height(), 100)
            self.assertLessEqual(ui.finishInventoryOverlay.height(), 395)
        finally:
            ui.close()
            ui.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
