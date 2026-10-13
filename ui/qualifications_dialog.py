"""Plik -> "Kwalifikacje": katalog kwalifikacji projektu
(MonthlyProject.qualifications) - z niego powstają wiersze kwalifikacji w
oknie pracownika (ui/employee_dialog.py), ikony w siatce i kolumna "Flagi".

Okno pracuje na kopii - zmiany trafiają do projektu dopiero po "Zapisz"
(patrz `qualifications` po accept()). Klucz nowej kwalifikacji powstaje z
nazwy przy zapisie i potem się nie zmienia, więc zmiana nazwy nie psuje
przypisań pracowników ani reguł profilu. Usunąć można tylko kwalifikację,
której nie ma żaden pracownik i która nie pochodzi z profilu (patrz
MonthlyProject.protected_qualifications)."""

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from model.qualification import (
    FIXED_LEVEL_COUNTS,
    KIND_LABELS,
    KIND_ROLE,
    KINDS,
    Qualification,
    QualificationLevel,
)
from ui.emoji_palette import ROLE_ICON_PALETTE
from ui.slug import slugify

BUILTIN_ICON_LABEL = "Wbudowana ikona"

_POLISH_ASCII = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def new_qualification_key(name: str, taken: set) -> str:
    """Stały klucz nowej kwalifikacji z jej nazwy ("Wózek widłowy" ->
    "wozek_widlowy"), unikalny w katalogu."""
    return slugify(name.translate(_POLISH_ASCII), taken)


def levels_from_text(text: str) -> tuple:
    """Poziomy z pola tekstowego: jedna nazwa na linię, od najniższego -
    wartości 1, 2, 3... Puste = kwalifikacja bez poziomów."""
    names = [line.strip() for line in text.splitlines() if line.strip()]
    return tuple(QualificationLevel(value, name) for value, name in enumerate(names, start=1))


def levels_to_text(levels) -> str:
    return "\n".join(level.name for level in levels)


class QualificationsDialog(QDialog):
    def __init__(self, parent, qualifications: dict, usage: dict | None = None, protected=frozenset()):
        super().__init__(parent)
        self.setWindowTitle("Kwalifikacje")
        self.setModal(True)
        self.resize(780, 500)

        # [klucz albo None (nowa), Qualification] - kolejność = kolejność katalogu.
        self._items = [[key, qualification] for key, qualification in qualifications.items()]
        self._original_levels = {key: qualification.levels for key, qualification in qualifications.items()}
        self._usage = usage or {}
        self._protected = set(protected)
        self._current = -1
        self._loading = False
        self.qualifications: dict = {}

        root = QVBoxLayout(self)
        hint = QLabel(
            "Kwalifikacje projektu - role, umiejętności i uprawnienia, które "
            "przypisujesz pracownikom w ich danych. Generator i reguły profilu "
            "odwołują się do nich, więc kwalifikacji z profilu nie da się usunąć, "
            "tylko zmienić nazwę, ikonę czy poziomy."
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
        add_btn = QPushButton("Dodaj kwalifikację")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self._add)
        buttons.addWidget(add_btn)
        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.clicked.connect(self._remove)
        buttons.addWidget(self.remove_btn)
        left.addLayout(buttons)
        body.addLayout(left, 2)

        self.form_card = QFrame()
        self.form_card.setObjectName("configCard")
        form = QFormLayout(self.form_card)
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.code_edit.setMaxLength(6)
        self.code_edit.setPlaceholderText("np. OTW")
        self.icon_combo = QComboBox()
        self.kind_combo = QComboBox()
        for kind in KINDS:
            self.kind_combo.addItem(KIND_LABELS[kind], kind)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Podpowiedź w oknie pracownika")
        self.validity_check = QCheckBox("Wymaga daty ważności (np. uprawnienie z terminem)")
        self.levels_edit = QPlainTextEdit()
        self.levels_edit.setPlaceholderText("Bez poziomów - pracownik ma kwalifikację albo nie.")
        self.levels_edit.setFixedHeight(90)
        self.levels_hint = QLabel(
            "Jeden poziom na linię, od najniższego (np. „Pomocniczo”, potem „Pełna obsługa”)."
        )
        self.levels_hint.setObjectName("mutedHint")
        self.levels_hint.setWordWrap(True)
        self.usage_label = QLabel()
        self.usage_label.setObjectName("mutedHint")
        self.usage_label.setWordWrap(True)

        form.addRow("Nazwa:", self.name_edit)
        form.addRow("Kod:", self.code_edit)
        form.addRow("Ikona:", self.icon_combo)
        form.addRow("Rodzaj:", self.kind_combo)
        form.addRow("Opis:", self.description_edit)
        form.addRow("", self.validity_check)
        form.addRow("Poziomy:", self.levels_edit)
        form.addRow("", self.levels_hint)
        form.addRow("", self.usage_label)
        body.addWidget(self.form_card, 3)
        root.addLayout(body, 1)

        for edit in (self.name_edit, self.code_edit, self.description_edit):
            edit.textEdited.connect(self._on_edited)
        self.icon_combo.currentIndexChanged.connect(self._on_edited)
        self.kind_combo.currentIndexChanged.connect(self._on_edited)
        self.validity_check.toggled.connect(self._on_edited)
        self.levels_edit.textChanged.connect(self._on_edited)

        box = QDialogButtonBox()
        box.addButton("Zapisz", QDialogButtonBox.AcceptRole)
        box.addButton("Anuluj", QDialogButtonBox.RejectRole)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        for _key, qualification in self._items:
            self.list.addItem(self._label(qualification))
        if self._items:
            self.list.setCurrentRow(0)
        self._update_enabled()

    @staticmethod
    def _label(qualification: Qualification) -> str:
        name = qualification.name.strip() or "(bez nazwy)"
        icon = qualification.icon if qualification.icon and not qualification.icon.startswith("builtin:") else ""
        return f"{icon} {name}".strip()

    def _current_item(self):
        return self._items[self._current] if 0 <= self._current < len(self._items) else None

    def _can_remove(self, item) -> bool:
        key, _qualification = item
        return key is None or (key not in self._protected and not self._usage.get(key, (0, 0))[0])

    def _update_enabled(self):
        item = self._current_item()
        self.form_card.setEnabled(item is not None)
        self.remove_btn.setEnabled(item is not None and self._can_remove(item))

    def _fill_icons(self, icon: str):
        self.icon_combo.clear()
        self.icon_combo.addItem("(brak)", "")
        if icon.startswith("builtin:"):
            self.icon_combo.addItem(BUILTIN_ICON_LABEL, icon)
        for emoji, description in ROLE_ICON_PALETTE:
            self.icon_combo.addItem(f"{emoji}  {description}", emoji)
        idx = self.icon_combo.findData(icon)
        if idx < 0:  # emoji spoza palety - zostaje
            self.icon_combo.addItem(icon, icon)
            idx = self.icon_combo.count() - 1
        self.icon_combo.setCurrentIndex(idx)

    def _on_row_changed(self, row: int):
        self._current = row
        item = self._current_item()
        self._loading = True
        try:
            qualification = item[1] if item else Qualification(id="", name="")
            self.name_edit.setText(qualification.name)
            self.code_edit.setText(qualification.code)
            self._fill_icons(qualification.icon)
            self.kind_combo.setCurrentIndex(max(self.kind_combo.findData(qualification.kind), 0))
            self.description_edit.setText(qualification.description)
            self.validity_check.setChecked(qualification.requires_validity)
            self.levels_edit.setPlainText(levels_to_text(qualification.levels))
            self.usage_label.setText(self._usage_text(item))
        finally:
            self._loading = False
        self._update_enabled()

    def _usage_text(self, item) -> str:
        if item is None:
            return ""
        key = item[0]
        count = self._usage.get(key, (0, 0))[0] if key else 0
        parts = [f"Ma ją pracowników: {count}." if count else "Nikt jej jeszcze nie ma."]
        if key in self._protected:
            parts.append("Pochodzi z profilu albo z reguły profilu - nie można jej usunąć.")
        return " ".join(parts)

    def _on_edited(self, *_):
        item = self._current_item()
        if self._loading or item is None:
            return
        item[1] = replace(
            item[1],
            name=self.name_edit.text(),
            code=self.code_edit.text(),
            icon=self.icon_combo.currentData() or "",
            kind=self.kind_combo.currentData() or KIND_ROLE,
            description=self.description_edit.text(),
            requires_validity=self.validity_check.isChecked(),
            levels=levels_from_text(self.levels_edit.toPlainText()),
        )
        self.list.item(self._current).setText(self._label(item[1]))

    def _add(self):
        self._items.append([None, Qualification(id="", name="")])
        self.list.addItem(self._label(self._items[-1][1]))
        self.list.setCurrentRow(len(self._items) - 1)
        self.name_edit.setFocus()

    def _remove(self):
        item = self._current_item()
        if item is None or not self._can_remove(item):
            return
        question = f"Usunąć kwalifikację „{self._label(item[1])}”?"
        if QMessageBox.question(self, "Usuń kwalifikację", question) != QMessageBox.Yes:
            return
        row = self._current
        del self._items[row]
        self.list.takeItem(row)
        self._on_row_changed(self.list.currentRow())

    def _error(self, row, message):
        self.list.setCurrentRow(row)
        QMessageBox.critical(self, "Błąd", message)

    def _save(self):
        taken = {key for key, _q in self._items if key}
        result = {}
        names = set()
        for row, (key, qualification) in enumerate(self._items):
            name = qualification.name.strip()
            if not name:
                return self._error(row, "Kwalifikacja musi mieć nazwę.")
            if name.casefold() in names:
                return self._error(row, f"Dwie kwalifikacje mają nazwę „{name}”.")
            names.add(name.casefold())
            if key is None:
                key = new_qualification_key(name, taken)
                taken.add(key)
            levels = qualification.levels
            fixed = FIXED_LEVEL_COUNTS.get(key)
            if fixed is not None and len(levels) != fixed:
                return self._error(
                    row,
                    f"„{name}” musi mieć {fixed} poziomy (generator czyta je na sztywno) - "
                    "możesz zmienić tylko ich nazwy.",
                )
            used_level = self._usage.get(key, (0, 0))[1] if levels != self._original_levels.get(key) else 0
            if levels and used_level > len(levels):
                return self._error(
                    row,
                    f"„{name}”: pracownicy mają poziom {used_level}, a zostało tylko {len(levels)} poziomów. "
                    "Najpierw zmień poziom tym pracownikom.",
                )
            if not levels and used_level > 1:
                return self._error(
                    row,
                    f"„{name}”: pracownicy mają poziom {used_level} - nie można usunąć poziomów.",
                )
            qualification = replace(
                qualification, id=key, name=name, code=qualification.code.strip(),
                description=qualification.description.strip(),
            )
            try:
                qualification.validate()
            except ValueError as exc:
                return self._error(row, f"„{name}”: {exc}")
            result[key] = qualification
        self.qualifications = result
        self.accept()
