import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from qidian_save.desktop.panels.qidian_login_panel import QidianLoginPanel

_QT_APP = None


class FakeClient:
    def get_announcements(self):
        return []


class DesktopConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_qidian_login_panel_constructs(self):
        panel = QidianLoginPanel(FakeClient())
        self.assertEqual(panel.property("ui-role"), "feature-panel")
        self.assertEqual(panel.btn_generate.property("btn-type"), "primary")
        self.assertTrue(panel.info_display.isHidden())


if __name__ == "__main__":
    unittest.main()



class FakeApiClient:
    def __init__(self):
        self.session_calls = []

    def get_usage(self):
        return {"chaptersUsed": 0, "limit": 1000}

    def get_announcements(self):
        return []

    def get_apk_login_session(self, session_id):
        self.session_calls.append(session_id)
        return {"sessionId": session_id, "stage": "authenticated", "expiresAt": "2999-01-01T00:00:00"}


def test_main_window_registers_apk_decrypt_backup_panel():
    from qidian_save.desktop.app import MainWindow
    from qidian_save.desktop.panels.apk_backup_panel import ApkBackupPanel

    window = MainWindow(FakeApiClient(), token="test-token")
    assert "apk_backup" in window.panels
    assert isinstance(window.panels["apk_backup"], ApkBackupPanel)
    assert window.panels["apk_backup"].objectName() == "panel_apk_backup"
    assert any(window.stackedWidget.widget(i) is window.panels["apk_backup"] for i in range(window.stackedWidget.count()))
    assert not any(window.stackedWidget.widget(i) is window.panels["backup"] for i in range(window.stackedWidget.count()))


def test_main_window_wires_apk_session_into_book_detail_panel():
    from qidian_save.desktop.app import MainWindow

    window = MainWindow(FakeApiClient(), token="test-token")
    window._on_apk_session_authenticated(42)
    assert window.apk_session_id == 42
    assert window.panels["detail"].get_apk_session_id() == 42


def test_main_window_restores_cached_apk_session(tmp_path):
    from qidian_save.desktop.app import MainWindow
    from qidian_save.apk_session_cache import save_cached_session

    cache_path = tmp_path / "apk_session.json"
    save_cached_session(
        {"sessionId": 88, "stage": "authenticated", "expiresAt": "2999-01-01T00:00:00"},
        path=cache_path,
    )
    client = FakeApiClient()

    window = MainWindow(client, token="test-token", apk_session_cache_path=cache_path)

    assert client.session_calls == [88]
    assert window.apk_session_id == 88
    assert window.panels["detail"].get_apk_session_id() == 88


def test_main_window_debug_mode_registers_slow_backup_panel():
    from qidian_save.desktop.app import MainWindow

    window = MainWindow(FakeApiClient(), token="test-token", debug_mode=True)
    assert any(window.stackedWidget.widget(i) is window.panels["backup"] for i in range(window.stackedWidget.count()))


def test_login_status_navigation_widget_is_not_selectable():
    from qidian_save.desktop.app import MainWindow

    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    window = MainWindow(FakeApiClient(), token="test-token")
    status_button = window.findChild(__import__("PyQt6.QtWidgets").QtWidgets.QPushButton, "statusBarBtn")

    assert status_button is not None
    assert hasattr(status_button, "isSelectable")
    assert status_button.isSelectable is False
