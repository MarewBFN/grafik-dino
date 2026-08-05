BG_MAIN = "#f5f7fb"
BG_HEADER = "#e7edf6"
BG_WEEKEND = "#eef2f7"
BG_DISABLED = "#dde4ee"
OK_GREEN = "#d6f4dd"
WARN_YELLOW = "#fff0b3"
ERR_RED = "#ffd0cf"
SHIFT_MORNING = "#dbeafe"
SHIFT_CLOSE = "#ede9fe"
TEXT_MAIN = "#1f2937"
TEXT_MUTED = "#6b7280"
GRID_BORDER = "#cbd5e1"

BG_APP = "#f5f7fb"
BG_PANEL = "#ffffff"
BG_CARD = "#ffffff"
ACCENT = "#1d4ed8"
ACCENT_HOVER = "#1e3a8a"
ACCENT_SOFT = "#dbeafe"
SOFT_BORDER = "#d7e0ea"

APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #f5f7fb;
    color: #1f2937;
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 10pt;
}

QMenuBar {
    background: #f8fafc;
    border-bottom: 1px solid #d7e0ea;
    padding: 4px;
}

QMenuBar::item {
    padding: 6px 10px;
    border-radius: 8px;
    background: transparent;
}

QMenuBar::item:selected {
    background: #dbeafe;
}

QMenu {
    background: #ffffff;
    border: 1px solid #d7e0ea;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 18px;
    border-radius: 6px;
}

QMenu::item:selected {
    background: #dbeafe;
}

QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #d7e0ea;
    spacing: 6px;
    padding: 6px;
}

QToolButton {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 10px;
    padding: 7px 12px;
    margin: 2px;
}

QToolButton:hover {
    background: #eff6ff;
}

QToolBar#topBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1e3a8a, stop:1 #1d4ed8);
    border-bottom: none;
    spacing: 8px;
    padding: 8px 14px;
}

QToolBar#topBar QLabel#brandLabel {
    color: #ffffff;
    font-size: 15pt;
    font-weight: 800;
    letter-spacing: 0.5px;
}

QToolBar#topBar QLabel#brandPeriodLabel {
    color: #dbeafe;
    font-size: 10pt;
    font-weight: 500;
}

QToolBar#topBar QToolButton {
    background: rgba(255, 255, 255, 28);
    border: 1px solid rgba(255, 255, 255, 60);
    color: #ffffff;
    border-radius: 10px;
    padding: 7px 14px;
    font-weight: 600;
}

QToolBar#topBar QToolButton:hover {
    background: rgba(255, 255, 255, 50);
}

QToolBar#topBar::separator {
    background: rgba(255, 255, 255, 60);
    width: 1px;
    margin: 4px 6px;
}

QFrame#panelCard, QFrame#contentCard {
    background: #ffffff;
    border: 1px solid #d7e0ea;
    border-radius: 20px;
}

QFrame#sidebarHero {
    background: #eaf0fd;
    border: 1px solid #d7e5fb;
    border-radius: 16px;
}

QLabel#titleLabel {
    font-size: 26px;
    font-weight: 800;
    color: #0f172a;
}

QLabel#subtitleLabel {
    color: #64748b;
}

QLabel#sectionLabel {
    font-size: 11pt;
    font-weight: 600;
    color: #0f172a;
}

QLabel#sectionHeader {
    font-size: 9pt;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 1px;
}

QFrame#sectionDivider {
    background: #e7edf6;
    max-height: 1px;
    min-height: 1px;
    border: none;
}

QFrame#sectionAccentBar {
    background: #1d4ed8;
    border-radius: 1px;
    border: none;
}

QLabel#metricValue {
    font-size: 14pt;
    font-weight: 700;
    color: #0f172a;
}

QLabel#metricHint {
    color: #64748b;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 12px;
    padding: 9px 14px;
}

QPushButton:hover {
    background: #eff6ff;
}

QPushButton:pressed {
    background: #dbeafe;
}

QPushButton#primaryButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2f65eb, stop:1 #1d4ed8);
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2555d6, stop:1 #1a3fb3);
    border-color: #1a3fb3;
}

QPushButton#primaryButton:pressed {
    background: #1e3a8a;
}

QPushButton#secondaryButton {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    color: #1f2937;
}

QPushButton#secondaryButton:hover {
    background: #eff6ff;
    border-color: #bfdbfe;
}

QPushButton#secondaryButton:pressed {
    background: #dbeafe;
}

QPushButton:checked {
    background: #1d4ed8;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: 600;
}

QPushButton:checked:hover {
    background: #1e3a8a;
    border-color: #1e3a8a;
}

QLineEdit, QSpinBox, QComboBox, QTimeEdit, QDateEdit, QTextEdit, QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 10px;
    padding: 6px 10px;
    selection-background-color: #dbeafe;
}

QComboBox::drop-down {
    border: 0px;
    width: 24px;
}

QTableWidget {
    background: #ffffff;
    border: 1px solid #d7e0ea;
    border-radius: 14px;
    gridline-color: #d7e0ea;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}

QHeaderView::section {
    background: #e7edf6;
    border: 1px solid #d7e0ea;
    padding: 6px;
    font-weight: 600;
    color: #0f172a;
}

QScrollBar:vertical {
    background: #f1f5f9;
    width: 12px;
    margin: 12px 2px 12px 2px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 32px;
    border-radius: 6px;
}

QScrollBar:horizontal {
    background: #f1f5f9;
    height: 12px;
    margin: 2px 12px 2px 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 32px;
    border-radius: 6px;
}

QStatusBar {
    background: #f8fafc;
    border-top: 1px solid #d7e0ea;
}

QTabWidget::pane {
    border: 1px solid #d7e0ea;
    border-radius: 12px;
    top: -1px;
    background: #ffffff;
}

QTabBar::tab {
    background: #e7edf6;
    padding: 8px 14px;
    margin-right: 4px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}

QTabBar::tab:selected {
    background: #ffffff;
    font-weight: 600;
}

QCheckBox {
    spacing: 8px;
}
"""