"""Okno "Wnioski urlopowe" (menu Plik -> "Wnioski urlopowe..." albo przycisk
na pasku pod grafikiem, ui/main_window.py::_open_leave_requests_dialog) -
lista wszystkich wniosków urlopowych bieżącego miesiąca dla bieżącej
placówki (logic/leave_requests.py::build_leave_requests) z podglądem
zaznaczonego wniosku i wyborem, które zapisać do PDF.

Wnioski zapisane wcześniej zostają na liście (z dopiskiem "zapisany"), ale
nie są domyślnie zaznaczone do zapisu."""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from export.leave_request_exporter import export_leave_requests_to_pdf, format_date, render_leave_request_image
from logic.leave_requests import format_days, requests_noun

_COLUMNS = ("Pracownik", "Okres urlopu", "Dni", "Status")


class LeaveRequestsDialog(QDialog):
    """`load_requests()` zwraca aktualną listę LeaveRequest, `on_saved(requests)`
    zapamiętuje zapisane wnioski - po zapisie lista jest wczytywana od nowa,
    więc właśnie zapisane wnioski od razu tracą zaznaczenie."""

    def __init__(self, parent, load_requests, on_saved, default_file_name: str):
        super().__init__(parent)
        self.setWindowTitle("Wnioski urlopowe")
        self.resize(1180, 760)

        self._load_requests = load_requests
        self._on_saved = on_saved
        self._default_file_name = default_file_name
        self._generated_on = date.today()
        self.requests = []

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_preview(row))
        self.table.itemChanged.connect(lambda _item: self._update_save_button())
        left.addWidget(self.table, 1)

        self.empty_label = QLabel("Brak urlopów zaznaczonych w tym miesiącu dla tej placówki.")
        self.empty_label.setObjectName("mutedHint")
        self.empty_label.setWordWrap(True)
        left.addWidget(self.empty_label)

        selection_row = QHBoxLayout()
        select_all_btn = QPushButton("Zaznacz wszystkie")
        select_all_btn.setObjectName("secondaryButton")
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        selection_row.addWidget(select_all_btn)
        select_none_btn = QPushButton("Odznacz wszystkie")
        select_none_btn.setObjectName("secondaryButton")
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        selection_row.addWidget(select_none_btn)
        selection_row.addStretch(1)
        left.addLayout(selection_row)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self._save_checked)
        self.save_btn.setDefault(True)
        buttons_row.addWidget(self.save_btn)
        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.reject)
        buttons_row.addWidget(close_btn)
        left.addLayout(buttons_row)

        layout.addLayout(left, 1)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMinimumWidth(660)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll.setWidget(self.preview_label)
        layout.addWidget(self.preview_scroll, 0)

        self.reload()

    def reload(self):
        self.requests = list(self._load_requests())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.requests))
        for row, request in enumerate(self.requests):
            name_item = QTableWidgetItem(request.employee.display_name())
            name_item.setFlags(name_item.flags() | Qt.ItemIsUserCheckable)
            name_item.setCheckState(Qt.Unchecked if request.printed else Qt.Checked)
            self.table.setItem(row, 0, name_item)
            if request.start_day == request.end_day:
                period = format_date(request.start_date)
            else:
                period = f"{format_date(request.start_date)} – {format_date(request.end_date)}"
            self.table.setItem(row, 1, QTableWidgetItem(period))
            self.table.setItem(row, 2, QTableWidgetItem(format_days(request.days)))
            self.table.setItem(row, 3, QTableWidgetItem("zapisany" if request.printed else "oczekuje"))
        self.table.blockSignals(False)

        self.empty_label.setVisible(not self.requests)
        if self.requests:
            self.table.setCurrentCell(0, 0)
            self._show_preview(0)
        else:
            self._show_preview(-1)
        self._update_save_button()

    def checked_requests(self) -> list:
        return [
            request for row, request in enumerate(self.requests)
            if self.table.item(row, 0).checkState() == Qt.Checked
        ]

    def _set_all_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def _update_save_button(self):
        count = len(self.checked_requests())
        self.save_btn.setText(f"Zapisz zaznaczone ({count})...")
        self.save_btn.setEnabled(count > 0)

    def _show_preview(self, row: int):
        if row < 0 or row >= len(self.requests):
            self.preview_label.setPixmap(QPixmap())
            return
        image = render_leave_request_image(self.requests[row], self._generated_on)
        self.preview_label.setPixmap(QPixmap.fromImage(image))

    def _save_checked(self):
        requests = self.checked_requests()
        if not requests:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz wnioski urlopowe", self._default_file_name, "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            saved = export_leave_requests_to_pdf(requests, path, self._generated_on)
        except Exception as error:
            QMessageBox.critical(self, "Błąd zapisu", str(error))
            return
        if not saved:
            QMessageBox.critical(self, "Błąd zapisu", f"Nie udało się zapisać pliku:\n{path}")
            return

        self._on_saved(requests)
        self.reload()
        QMessageBox.information(
            self, "Wnioski urlopowe", f"Zapisano {len(requests)} {requests_noun(len(requests))} do pliku:\n{path}",
        )
