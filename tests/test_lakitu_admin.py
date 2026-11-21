"""Lakitu observer never fabricates native lobby/player identities."""
import unittest
from unittest.mock import patch
from server import lakitu_admin as admin
from fastapi import HTTPException


class LakituObserverTests(unittest.TestCase):
    @patch.object(admin, "command", return_value="")
    def test_offline_snapshot_is_explicit(self, _):
        with patch.object(admin, "ROOT", __import__("pathlib").Path("/unavailable-lakitu-test")):
            result = admin.snapshot()
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "offline")
        self.assertEqual(result["telemetry_scope"], "process-only")
        self.assertEqual(result["lobbies"], [])
        self.assertEqual(result["players"], [])
        self.assertEqual(result["capabilities"], [])

    def test_missing_admin_token_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            admin.authorize(None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_safe_capability_is_never_advertised(self):
        with patch.object(admin, "command", return_value=""):
            self.assertEqual(admin.snapshot()["capabilities"], [])


if __name__ == "__main__":
    unittest.main()
