from qidian_save import adb_utils


def test_extract_params_does_not_require_user_id(monkeypatch):
    calls = []

    monkeypatch.setattr(adb_utils, "check_root", lambda device_serial=None: True)
    monkeypatch.setattr(adb_utils, "_root_copy", lambda src, dst, device_serial=None: False)

    def fake_adb_command(cmd, timeout=10, device_serial=None):
        calls.append(cmd)
        return ""

    monkeypatch.setattr(adb_utils, "adb_command", fake_adb_command)

    result = adb_utils.extract_params()

    assert result["userId"] == ""
    assert not any("未提取到 userId" in err for err in result["errors"])
    assert not any("Android/data/com.qidian.QDReader/files/QDReader/book" in cmd for cmd in calls)
