"""Shared presentation components for the desktop client."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def configure_page_layout(widget: QWidget, margins=(28, 24, 28, 24), spacing=16):
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


class PageHeader(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        eyebrow: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("ui-role", "page-header")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        copy = QVBoxLayout()
        copy.setSpacing(3)
        if eyebrow:
            label = QLabel(eyebrow.upper())
            label.setProperty("ui-role", "eyebrow")
            copy.addWidget(label)

        self.title_label = QLabel(title)
        self.title_label.setProperty("ui-role", "page-title")
        copy.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setProperty("ui-role", "page-subtitle")
        self.subtitle_label.setVisible(bool(subtitle))
        copy.addWidget(self.subtitle_label)
        layout.addLayout(copy, 1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, button: QPushButton):
        self.actions.addWidget(button)


class SurfaceCard(QFrame):
    def __init__(self, parent=None, *, inset=False):
        super().__init__(parent)
        self.setProperty("ui-role", "surface-inset" if inset else "surface-card")


class StatCard(SurfaceCard):
    def __init__(self, label: str, value: str = "--", accent: str = "accent", parent=None):
        super().__init__(parent)
        self.setProperty("ui-role", "stat-card")
        self.setProperty("accent", accent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self.label = QLabel(label)
        self.label.setProperty("ui-role", "stat-label")
        self.value = QLabel(value)
        self.value.setProperty("ui-role", "stat-value")
        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value):
        self.value.setText(str(value))


class EmptyState(SurfaceCard):
    def __init__(self, title: str, message: str = "", parent=None):
        super().__init__(parent, inset=True)
        self.setProperty("ui-role", "empty-state")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(7)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setProperty("ui-role", "empty-title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        if message:
            message_label = QLabel(message)
            message_label.setProperty("ui-role", "empty-message")
            message_label.setWordWrap(True)
            message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(message_label)
