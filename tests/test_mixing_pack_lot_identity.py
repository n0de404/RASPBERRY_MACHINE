import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENT_DIR = os.path.join(ROOT, "client")
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

import client as production_client
import mixing_client


class MixingPackLotIdentityTests(unittest.TestCase):
    @staticmethod
    def _client():
        instance = mixing_client.MixingClientUI.__new__(mixing_client.MixingClientUI)
        instance.state = SimpleNamespace(production_session_id="SESSION-1")
        instance._used_pack_qr_keys = set()
        return instance

    @staticmethod
    def _row(lot):
        return {
            "product_p": "00000000123",
            "index": "1",
            "po_number": "000001542",
            "lot_number": lot,
        }

    def test_same_series_is_distinct_for_different_mixing_lots(self):
        client = self._client()
        first = client._pack_history_key(self._row("20261029000001"))
        second = client._pack_history_key(self._row("20261029000002"))

        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("|LOT:20261029000001"))
        self.assertTrue(second.endswith("|LOT:20261029000002"))

    def test_same_series_and_same_lot_remains_duplicate(self):
        client = self._client()
        first = client._pack_history_key(self._row("20261029000001"))
        second = client._pack_history_key(dict(self._row("20261029000001")))

        self.assertEqual(first, second)

    def test_normal_client_identity_is_unchanged(self):
        client = self._client()
        first = production_client.ClientUI._pack_history_key(
            client, self._row("20261029000001")
        )
        second = production_client.ClientUI._pack_history_key(
            client, self._row("20261029000002")
        )

        self.assertEqual(first, second)
        self.assertNotIn("|LOT:", first)

    def test_legacy_key_blocks_same_lot_but_allows_new_lot(self):
        client = self._client()
        legacy_key = production_client.ClientUI._pack_history_key(
            client, self._row("20261029000001")
        )
        saved = {
            legacy_key: {
                **self._row("20261029000001"),
                "raw_scan": "",
            }
        }
        same_lot_key = client._pack_history_key(self._row("20261029000001"))
        new_lot_key = client._pack_history_key(self._row("20261029000002"))

        with patch.object(
            production_client, "_load_scanned_pack_qr_keys_json", return_value=saved
        ):
            self.assertTrue(client._pack_qr_was_used_permanently(same_lot_key))
            self.assertFalse(client._pack_qr_was_used_permanently(new_lot_key))


if __name__ == "__main__":
    unittest.main()
