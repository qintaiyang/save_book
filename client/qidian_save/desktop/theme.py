"""qidian_save 设计系统 — 颜色 / 圆角 / 字体 tokens 与主题管理

用法:
    from qfluentwidgets import setTheme, Theme, setThemeColor
    from .theme import LIGHT_TOKENS, DARK_TOKENS, apply_design_tokens

    # 切换暗色
    setTheme(Theme.DARK)
    apply_design_tokens(Theme.DARK)

依赖 PyQt6-Fluent-Widgets 的 setTheme / setThemeColor 机制。
"""

from qfluentwidgets import setThemeColor, Theme, qconfig

# ── iOS 色系 tokens ──────────────────────────────────────────────

LIGHT_TOKENS = {
    # 背景
    "bg_primary":     "#f5f5f7",    # iOS 系统灰底
    "bg_card":        "#ffffff",    # 卡片白
    "bg_sidebar":     "#1c1c1e",    # 侧栏深色（iOS 风格）
    "bg_input":       "#ffffff",    # 输入框
    "bg_hover":       "#f0f0f5",    # hover 高亮

    # 强调色
    "accent":         "#007aff",    # iOS 蓝
    "accent_hover":   "#0056d6",    # 深蓝 hover
    "accent_light":   "#e8f0fe",    # 浅蓝背景（选中态）

    # 文字
    "text_primary":   "#1d1d1f",    # 主文字（近黑）
    "text_secondary": "#86868b",    # 次级文字（iOS 灰）
    "text_tertiary":  "#aeaeb2",    # 第三级（占位符）
    "text_on_accent": "#ffffff",    # 强调色上的文字

    # 边框 & 分割线
    "border":         "#d2d2d7",    # 浅灰边框
    "divider":        "#e5e5ea",    # 分割线

    # 语义色
    "success":        "#34c759",    # iOS 绿
    "warning":        "#ff9500",    # iOS 橙
    "danger":         "#ff3b30",    # iOS 红
    "info":           "#007aff",    # 信息蓝

    # 阴影
    "shadow_card":    "0 2px 12px rgba(0,0,0,0.08)",
    "shadow_popup":   "0 8px 24px rgba(0,0,0,0.12)",
}

DARK_TOKENS = {
    "bg_canvas":      "#1C191F",
    "bg_navigation":  "#171419",
    "surface_raised": "#29252E",
    "surface_inset":  "#211E24",
    "border_subtle":  "#3A3440",
    "accent_highlight": "#C58BC2",
    "bg_primary":     "#1c1c1e",
    "bg_card":        "#2c2c2e",
    "bg_sidebar":     "#111111",
    "bg_input":       "#3a3a3c",
    "bg_hover":       "#3a3a3c",

    "accent":         "#0a84ff",    # 暗色 iOS 蓝
    "accent_hover":   "#409cff",
    "accent_light":   "#1a2a44",

    "text_primary":   "#f5f5f7",
    "text_secondary": "#98989d",
    "text_tertiary":  "#636366",
    "text_on_accent": "#ffffff",

    "border":         "#38383a",
    "divider":        "#38383a",

    "success":        "#30d158",
    "warning":        "#ff9f0a",
    "danger":         "#ff453a",
    "info":           "#0a84ff",

    "shadow_card":    "0 2px 12px rgba(0,0,0,0.3)",
    "shadow_popup":   "0 8px 24px rgba(0,0,0,0.4)",
}

DESIGN_TOKENS = {
    "control_height": 38,
    "qt_font_family": "Microsoft YaHei UI",
    "radius_sm":      "6px",
    "radius_md":      "10px",
    "radius_lg":      "14px",
    "radius_full":    "9999px",

    "font_family":    "'Inter', 'Noto Sans SC', 'Microsoft YaHei', -apple-system, sans-serif",
    "font_mono":      "'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace",

    "font_size_caption":  "12px",
    "font_size_body":     "14px",
    "font_size_title":    "18px",
    "font_size_display":  "24px",

    "spacing_xs":     "4px",
    "spacing_sm":     "8px",
    "spacing_md":     "16px",
    "spacing_lg":     "24px",
    "spacing_xl":     "32px",
}


def apply_design_tokens(theme: Theme):
    """应用设计系统 tokens。

    调用 setThemeColor() 让 Fluent 控件使用 iOS 色系的强调色。
    QSS 文件中的颜色通过 CSS 自定义属性（变量）读取。
    """
    accent = DARK_TOKENS["accent"] if theme == Theme.DARK else LIGHT_TOKENS["accent"]
    setThemeColor(accent)


def get_token(theme: Theme, key: str) -> str:
    """按主题取颜色 token（仅颜色），设计 token 无主题区分。"""
    if key in DESIGN_TOKENS:
        return DESIGN_TOKENS[key]
    tokens = DARK_TOKENS if theme == Theme.DARK else LIGHT_TOKENS
    return tokens.get(key, "")


def load_qss(theme: Theme = Theme.DARK) -> str:
    """加载对应主题的 QSS 文件。"""
    import os
    mode = "dark" if theme == Theme.DARK else "light"
    path = os.path.join(os.path.dirname(__file__), "style", f"{mode}.qss")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""
