import argparse
import unittest
from unittest.mock import patch

from qidian_save import cli


class CliRegressionTests(unittest.TestCase):
    def test_cmd_decrypt_uses_path_import_and_reaches_file_check(self):
        args = argparse.Namespace(
            file="does-not-exist.qd",
            qimei36="x",
            user_id="y",
            pool_b64="z",
            output=None,
        )
        with patch.object(cli, "_get_client") as get_client:
            client = get_client.return_value
            client.decrypt_qd.side_effect = FileNotFoundError("missing")
            with self.assertRaises(FileNotFoundError):
                cli.cmd_decrypt(args)

    def test_cmd_adb_db_uses_path_import_and_handles_missing_dir(self):
        args = argparse.Namespace(dir="definitely-missing-dir")
        with patch("builtins.print") as fake_print:
            cli.cmd_adb_db(args)
        printed = "\n".join(str(call.args[0]) for call in fake_print.call_args_list if call.args)
        self.assertIn("definitely-missing-dir", printed)

    def test_adb_scan_aborts_when_device_resolution_requires_user_choice(self):
        args = argparse.Namespace(device=None)
        with patch.object(cli, "_resolve_device", return_value=None), \
             patch.object(cli, "list_devices", return_value=[
                 {"serial": "one", "status": "device"},
                 {"serial": "two", "status": "device"},
             ]), \
             patch.object(cli, "check_device", return_value=True), \
             patch.object(cli, "scan_device") as scan_device:
            cli.cmd_adb_scan(args)
        scan_device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
