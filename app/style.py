"""全局样式表。透明度只作用于背景，文字保持高对比以保证可读性。"""

FONT = '"Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif'


def build_qss(bg_alpha: float) -> str:
    a = max(0.10, min(0.80, float(bg_alpha)))
    bg = int(round(a * 255))
    subtle = f"rgba(255,255,255,{int(16 + a * 20)})"
    border = f"rgba(255,255,255,{int(26 + a * 26)})"

    return f"""
* {{
    font-family: {FONT};
    font-size: 12px;
    color: #e9e9ef;
}}
#root {{
    background-color: rgba(20, 21, 27, {bg});
    border: 1px solid {border};
    border-radius: 12px;
}}
#root[alert="true"] {{ border: 1px solid #ef4444; }}
#topbar, #bottombar, #capwrap, #clipbar {{
    background: transparent;
}}
QLabel {{ background: transparent; }}
#brand {{
    font-weight: 600;
    color: #ffffff;
    letter-spacing: 0.5px;
}}
#counter {{
    color: #ffb454;
    font-weight: 600;
}}
#hint {{
    color: #9aa0ad;
}}
QLineEdit, QPlainTextEdit {{
    background-color: {subtle};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 5px 8px;
    color: #f2f2f7;
    selection-background-color: #3b6ef6;
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid rgba(110,150,255,180);
}}
QPushButton {{
    background-color: {subtle};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 10px;
    color: #e9e9ef;
}}
QPushButton:hover {{ background-color: rgba(255,255,255,52); }}
QPushButton:pressed {{ background-color: rgba(255,255,255,36); }}
QPushButton#primary {{
    background-color: #3b6ef6;
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background-color: #5285ff; }}
QPushButton#ghost {{
    background: transparent;
    border: none;
    color: #9aa0ad;
    padding: 2px 6px;
}}
QPushButton#ghost:hover {{ color: #ffffff; background-color: rgba(255,255,255,40); }}
QPushButton#ghost:checked {{
    color: #ffffff;
    background-color: rgba(59,110,246,200);
    border-radius: 6px;
}}
QPushButton#danger:hover {{ background-color: rgba(239,68,68,190); color: #fff; }}
QTableWidget {{
    background: transparent;
    border: none;
    gridline-color: transparent;
    outline: 0;
    color: #e9e9ef;
}}
QTableWidget::item {{
    padding: 2px 6px;
    border-bottom: 1px solid rgba(255,255,255,20);
}}
QTableWidget::item:selected {{
    background-color: rgba(59,110,246,110);
}}
QHeaderView {{
    background: transparent;
    border: none;
}}
QHeaderView::section {{
    background-color: rgba(255,255,255,22);
    color: #b9bfcc;
    border: none;
    border-right: 1px solid rgba(255,255,255,16);
    padding: 6px 8px;
    font-weight: 500;
}}
QScrollBar:vertical {{
    background: transparent; width: 12px; margin: 1px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,54); border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,90); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{
    background-color: #22232b;
    border: 1px solid rgba(255,255,255,40);
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: rgba(59,110,246,160); }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,30); margin: 4px 8px; }}
QCheckBox {{ background: transparent; }}
QDialog {{ background-color: #1d1e25; }}
QComboBox, QSpinBox, QTimeEdit {{
    background-color: rgba(255,255,255,26);
    border: 1px solid rgba(255,255,255,40);
    border-radius: 6px;
    padding: 3px 6px;
    color: #f2f2f7;
}}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,40); border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 12px; margin: -5px 0; border-radius: 6px; background: #6e96ff;
}}
QToolTip {{
    background-color: #22232b; color: #e9e9ef;
    border: 1px solid rgba(255,255,255,50); padding: 4px;
}}
"""
