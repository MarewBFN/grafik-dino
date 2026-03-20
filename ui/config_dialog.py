import calendar

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)


def _parse_time(value: str) -> QTime:
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class ConfigDialog(QDialog):
    def __init__(self, parent, shop_config):
        super().__init__(parent)
        self.shop_config = shop_config
        self.setWindowTitle("Konfiguracja")
        self.setModal(True)
        self.resize(620, 520)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Konfiguracja sklepu")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        tabs.addTab(self._build_hours_tab(), "Godziny otwarcia")
        tabs.addTab(self._build_sundays_tab(), "Niedziele handlowe")
        tabs.addTab(self._build_constraints_tab(), "Limity")

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

    def _build_hours_tab(self):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)

        self.open_edits = {}
        days = ["Pon", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

        for row, name in enumerate(days):
            layout.addWidget(QLabel(name), row, 0)

            start, end = self.shop_config.open_hours[row]
            start_edit = QTimeEdit()
            start_edit.setDisplayFormat("HH:mm")
            start_edit.setTime(_parse_time(start))

            end_edit = QTimeEdit()
            end_edit.setDisplayFormat("HH:mm")
            end_edit.setTime(_parse_time(end))

            layout.addWidget(start_edit, row, 1)
            layout.addWidget(QLabel("—"), row, 2)
            layout.addWidget(end_edit, row, 3)

            self.open_edits[row] = (start_edit, end_edit)

        return page

    def _build_sundays_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        self.sunday_checks = {}
        cal = calendar.Calendar()

        sundays = [
            d for d, wd in cal.itermonthdays2(self.shop_config.year, self.shop_config.month)
            if d and wd == 6
        ]

        if not sundays:
            layout.addWidget(QLabel("W tym miesiącu nie ma niedziel."))
            return page

        for day in sundays:
            box = QCheckBox(f"{day:02d}.{self.shop_config.month:02d}.{self.shop_config.year}")
            box.setChecked(day in self.shop_config.trade_sundays)
            self.sunday_checks[day] = box
            layout.addWidget(box)

        layout.addStretch()
        return page

    def _build_constraints_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.max_consecutive = QSpinBox()
        self.max_consecutive.setRange(1, 14)
        self.max_consecutive.setValue(self.shop_config.constraints.get("max_consecutive_days", 4))

        self.min_open = QSpinBox()
        self.min_open.setRange(0, 20)
        self.min_open.setValue(self.shop_config.constraints.get("min_open_staff", 3))

        self.min_close = QSpinBox()
        self.min_close.setRange(0, 20)
        self.min_close.setValue(self.shop_config.constraints.get("min_close_staff", 3))

        self.rest_11h = QCheckBox("Wymuszaj 11h odpoczynku")
        self.rest_11h.setChecked(self.shop_config.constraints.get("enforce_11h_rest", True))

        self.meat_coverage = QCheckBox("Wymuszaj pokrycie mięsa")
        self.meat_coverage.setChecked(self.shop_config.constraints.get("enforce_meat_coverage", True))

        form.addRow("Max dni pod rząd", self.max_consecutive)
        form.addRow("Min. osób na otwarciu", self.min_open)
        form.addRow("Min. osób na zamknięciu", self.min_close)
        form.addRow(self.rest_11h)
        form.addRow(self.meat_coverage)

        return page

    def _save(self):
        try:
            for wd, (start_edit, end_edit) in self.open_edits.items():
                start = start_edit.time().toString("HH:mm")
                end = end_edit.time().toString("HH:mm")
                if end_edit.time() <= start_edit.time():
                    raise ValueError(f"Zamknięcie musi być później niż otwarcie w dniu {wd}.")
                self.shop_config.open_hours[wd] = (start, end)

            self.shop_config.trade_sundays = {
                day for day, box in self.sunday_checks.items() if box.isChecked()
            }

            self.shop_config.constraints["max_consecutive_days"] = self.max_consecutive.value()
            self.shop_config.constraints["min_open_staff"] = self.min_open.value()
            self.shop_config.constraints["min_close_staff"] = self.min_close.value()
            self.shop_config.constraints["enforce_11h_rest"] = self.rest_11h.isChecked()
            self.shop_config.constraints["enforce_meat_coverage"] = self.meat_coverage.isChecked()

        except Exception as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

        self.accept()
