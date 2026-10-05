"""Plik -> "Dane firmy": lista firm (dowolnie wiele) z danymi NIP, nazwa,
adres, telefon, e-mail - na razie używane tylko w nagłówku wniosków
urlopowych (export/leave_request_exporter.py). Pracownik wskazuje swoją firmę
w EmployeeDialog -> "Zaawansowane". Okno pracuje na kopiach - zmiany trafiają
do projektu dopiero po "Zapisz" (patrz `companies` po accept())."""

from dataclasses import replace

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from model.company import COMPANY_FIELDS, Company

_FIELD_LABELS = {
    "name": "Nazwa:",
    "nip": "NIP:",
    "street": "Adres:",
    "postal_code": "Kod pocztowy:",
    "city": "Miejscowość:",
    "phone": "Telefon:",
    "email": "E-mail:",
}

_FIELD_PLACEHOLDERS = {
    "nip": "000-000-00-00",
    "street": "ulica, nr budynku / lokalu",
    "postal_code": "00-000",
    "phone": "np. 61 123 45 67",
    "email": "np. kadry@firma.pl",
}


class CompaniesDialog(QDialog):
    def __init__(self, parent, companies: dict[str, Company], employee_counts: dict[str, int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Dane firmy")
        self.setModal(True)
        self.resize(760, 440)

        self._companies = [replace(company) for company in companies.values()]
        self._employee_counts = employee_counts or {}
        self._current = -1
        self.companies: dict[str, Company] = {}

        root = QVBoxLayout(self)
        hint = QLabel(
            "Dane firm używane w nagłówku wniosków urlopowych. Firmę pracownika "
            "wybierasz w jego danych: Zaawansowane -> Firma."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        add_btn = QPushButton("Dodaj firmę")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self._add_company)
        buttons.addWidget(add_btn)
        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.clicked.connect(self._remove_company)
        buttons.addWidget(self.remove_btn)
        left.addLayout(buttons)
        body.addLayout(left, 2)

        self.form_card = QFrame()
        self.form_card.setObjectName("configCard")
        form = QFormLayout(self.form_card)
        form.setSpacing(10)
        self.fields: dict[str, QLineEdit] = {}
        for name in COMPANY_FIELDS:
            edit = QLineEdit()
            edit.setPlaceholderText(_FIELD_PLACEHOLDERS.get(name, ""))
            edit.textEdited.connect(self._on_field_edited)
            form.addRow(_FIELD_LABELS[name], edit)
            self.fields[name] = edit
        self.fields["postal_code"].setMaxLength(6)
        body.addWidget(self.form_card, 3)
        root.addLayout(body, 1)

        box = QDialogButtonBox()
        box.addButton("Zapisz", QDialogButtonBox.AcceptRole)
        box.addButton("Anuluj", QDialogButtonBox.RejectRole)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        for company in self._companies:
            self.list.addItem(self._label(company))
        if self._companies:
            self.list.setCurrentRow(0)
        self._update_enabled()

    @staticmethod
    def _label(company: Company) -> str:
        return company.name.strip() or "(bez nazwy)"

    def _update_enabled(self):
        has_current = 0 <= self._current < len(self._companies)
        self.form_card.setEnabled(has_current)
        self.remove_btn.setEnabled(has_current)

    def _on_row_changed(self, row: int):
        self._current = row
        company = self._companies[row] if 0 <= row < len(self._companies) else None
        for name, edit in self.fields.items():
            edit.setText(getattr(company, name) if company else "")
        self._update_enabled()

    def _on_field_edited(self, *_):
        if not 0 <= self._current < len(self._companies):
            return
        company = self._companies[self._current]
        for name, edit in self.fields.items():
            setattr(company, name, edit.text())
        self.list.item(self._current).setText(self._label(company))

    def _add_company(self):
        self._companies.append(Company())
        self.list.addItem(self._label(self._companies[-1]))
        self.list.setCurrentRow(len(self._companies) - 1)
        self.fields["name"].setFocus()

    def _remove_company(self):
        row = self._current
        if not 0 <= row < len(self._companies):
            return
        company = self._companies[row]
        count = self._employee_counts.get(company.key, 0)
        question = f"Usunąć firmę „{self._label(company)}”?"
        if count:
            question += f"\n\nJest przypisana do pracowników: {count}. Stracą przypisanie do firmy."
        if QMessageBox.question(self, "Usuń firmę", question) != QMessageBox.Yes:
            return
        del self._companies[row]
        self.list.takeItem(row)
        self._on_row_changed(self.list.currentRow())

    def _save(self):
        for row, company in enumerate(self._companies):
            for name in COMPANY_FIELDS:
                setattr(company, name, getattr(company, name).strip())
            try:
                company.validate()
            except ValueError as exc:
                self.list.setCurrentRow(row)
                QMessageBox.critical(self, "Błąd", f"{self._label(company)}: {exc}")
                return
        self.companies = {company.key: company for company in self._companies}
        self.accept()
