import argparse
import unittest
from unittest.mock import patch

from qidian_save import cli


class CliRegressionTests(unittest.TestCase):
    def test_backup_parser_accepts_preview_merge_and_rotating_proxies(self):
        args = cli.build_parser().parse_args([
            "backup", "123",
            "--preview",
            "--merge",
            "--proxy", "http://one.example:8080",
            "--proxy", "socks5://two.example:1080",
            "--proxy-rotate-every", "25",
        ])
        self.assertTrue(args.preview)
        self.assertTrue(args.merge)
        self.assertEqual(args.proxy, [
            "http://one.example:8080",
            "socks5://two.example:1080",
        ])
        self.assertEqual(args.proxy_rotate_every, 25)

    def test_backup_parser_rejects_non_positive_proxy_rotation(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "backup", "123", "--proxy-rotate-every", "0",
            ])

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

    def test_cmd_adb_extract_does_not_save_or_print_user_id(self):
        args = argparse.Namespace(device=None)
        saved = {}
        with patch.object(cli, "_resolve_device", return_value="dev"), \
             patch.object(cli, "check_device", return_value=True), \
             patch.object(cli, "check_root", return_value=True), \
             patch.object(cli, "extract_params", return_value={
                 "qimei36": "q",
                 "pool_b64": "p",
                 "userId": "old",
                 "errors": [],
             }), \
             patch.object(cli, "load_config", return_value={}), \
             patch.object(cli, "save_config", side_effect=lambda cfg: saved.update(cfg)), \
             patch("builtins.print") as fake_print:
            cli.cmd_adb_extract(args)

        printed = "\n".join(str(call.args[0]) for call in fake_print.call_args_list if call.args)
        self.assertNotIn("userId", printed)
        self.assertEqual(saved, {"qimei36": "q", "pool_b64": "p"})


if __name__ == "__main__":
    unittest.main()
