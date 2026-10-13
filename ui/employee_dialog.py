import calendar
import dataclasses
from datetime import date
import os

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QComboBox,
    QFrame,
    QSpacerItem,
    QSizePolicy,
    QWidget,
)

from model.employee import Employee
from model.qualification import (
    NO_24H_QUALIFICATION,
    QUAL_MANAGER,
    QUAL_NO_24H,
    QUALIFICATION_POLICIES,
    EmployeeQualification,
    merge_catalog,
)
from model.business_profile import DEFAULT_BUSINESS_TYPE, catalog_or_default, get_profile
from model.constraint_policy import ConstraintPolicy
from logic.leave_requests import days_noun, format_days
from logic.utils.time_utils import month_scope_note
from ui.tutorial_overlay import TutorialOverlay, TutorialStep

EMPLOYEE_TUTORIAL_FLAG = "employee_tutorial_seen.flag"

# RoleDef.key profilu będące polem Employee - ograniczenia no_night/
# no_afternoon (Dino pokazuje je z profile.roles, z własnymi etykietami).
# Kwalifikacje pochodzą z katalogu projektu, nie z profile.roles.
_EMPLOYEE_FIELDS = {f.name for f in dataclasses.fields(Employee)}

DATE_FMT = "%d.%m.%Y"


def _to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def scope_summary(valid_from, valid_to, location_ids, locations) -> str:
    """Krótki opis ważności i placówek przypisania kwalifikacji."""
    if valid_from and valid_to:
        text = f"{valid_from:{DATE_FMT}} – {valid_to:{DATE_FMT}}"
    elif valid_from:
        text = f"od {valid_from:{DATE_FMT}}"
    elif valid_to:
        text = f"do {valid_to:{DATE_FMT}}"
    else:
        text = "bezterminowo"
    if location_ids:
        names = [locations[key].name if key in locations else key for key in location_ids]
        text += ", tylko: " + ", ".join(names)
    return text


class QualificationScopeDialog(QDialog):
    """Daty ważności (obie opcjonalne, włącznie) i placówki (żadna
    zaznaczona = wszystkie) jednego przypisania kwalifikacji."""

    def __init__(self, parent, qualification, valid_from, valid_to, location_ids, locations, default_month):
        super().__init__(parent)
        self.setWindowTitle(f"{qualification.name} – ważność i placówki")
        self.setModal(True)
        year, month = default_month
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.from_check, self.from_edit = self._date_row(valid_from, date(year, month, 1))
        self.to_check, self.to_edit = self._date_row(valid_to, date(year, month, calendar.monthrange(year, month)[1]))
        form.addRow("Ważna od:", self._row(self.from_check, self.from_edit))
        form.addRow("Ważna do:", self._row(self.to_check, self.to_edit))
        layout.addLayout(form)

        self.location_checks = {}
        if len(locations) > 1:
            title = QLabel("Obowiązuje w placówkach:")
            title.setObjectName("groupLabel")
            layout.addWidget(title)
            for key, location in locations.items():
                check = QCheckBox(location.name)
                check.setChecked(key in location_ids)
                layout.addWidget(check)
                self.location_checks[key] = check
            hint = QLabel("Nic nie zaznaczone = wszystkie placówki.")
            hint.setObjectName("mutedHint")
            layout.addWidget(hint)
        self._other_locations = tuple(key for key in location_ids if key not in locations)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _date_row(value, default):
        check = QCheckBox()
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setDate(_to_qdate(value or default))
        check.setChecked(value is not None)
        edit.setEnabled(value is not None)
        check.toggled.connect(edit.setEnabled)
        return check, edit

    @staticmethod
    def _row(check, edit):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(check)
        row.addWidget(edit, 1)
        return widget

    def values(self):
        """(valid_from, valid_to, location_ids)."""
        valid_from = _from_qdate(self.from_edit.date()) if self.from_check.isChecked() else None
        valid_to = _from_qdate(self.to_edit.date()) if self.to_check.isChecked() else None
        location_ids = self._other_locations + tuple(
            key for key, check in self.location_checks.items() if check.isChecked()
        )
        return valid_from, valid_to, location_ids

    def _accept(self):
        valid_from, valid_to, _ = self.values()
        if valid_from and valid_to and valid_from > valid_to:
            QMessageBox.critical(self, "Błąd", "Data „od” jest późniejsza niż data „do”.")
            return
        self.accept()


class QualificationRow(QWidget):
    """Jedna kwalifikacja z katalogu w oknie pracownika: zaznaczenie,
    poziom (gdy kwalifikacja ma skalę poziomów) i ważność/placówki."""

    def __init__(self, qualification, locations, default_month, parent=None):
        super().__init__(parent)
        self.qualification = qualification
        self.locations = locations
        self.default_month = default_month
        self.level = 1
        self.valid_from = None
        self.valid_to = None
        self.location_ids = ()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(qualification.name)
        if qualification.description:
            self.checkbox.setToolTip(qualification.description)
        layout.addWidget(self.checkbox, 1)

        self.level_combo = None
        if qualification.levels:
            self.level_combo = QComboBox()
            for level in qualification.levels:
                self.level_combo.addItem(level.name or f"Poziom {level.value}", level.value)
            # Domyślnie najwyższy poziom (Dino: "Mięso" = pełna obsługa, jak
            # dawny główny checkbox "Obsługa stoiska mięsnego").
            self.level_combo.setCurrentIndex(self.level_combo.count() - 1)
            self.level_combo.setToolTip("Poziom kwalifikacji")
            layout.addWidget(self.level_combo)

        self.scope_btn = QPushButton()
        self.scope_btn.setObjectName("secondaryButton")
        self.scope_btn.setToolTip("Daty ważności i placówki, w których kwalifikacja obowiązuje")
        self.scope_btn.clicked.connect(self._edit_scope)
        layout.addWidget(self.scope_btn)

        self.checkbox.toggled.connect(self._sync_enabled)
        self._sync_enabled()
        self._update_scope_text()

    def _sync_enabled(self):
        # Poziom i ważność widoczne tylko dla zaznaczonej kwalifikacji.
        checked = self.checkbox.isChecked()
        if self.level_combo is not None:
            self.level_combo.setVisible(checked)
        self.scope_btn.setVisible(checked)

    def _update_scope_text(self):
        self.scope_btn.setText(scope_summary(self.valid_from, self.valid_to, self.location_ids, self.locations))

    def _edit_scope(self):
        dialog = QualificationScopeDialog(
            self, self.qualification, self.valid_from, self.valid_to, self.location_ids,
            self.locations, self.default_month,
        )
        if dialog.exec() == QDialog.Accepted:
            self.valid_from, self.valid_to, self.location_ids = dialog.values()
            self._update_scope_text()

    def set_assignment(self, assignment: EmployeeQualification | None):
        self.checkbox.setChecked(assignment is not None)
        if assignment is None:
            return
        if self.level_combo is not None:
            idx = self.level_combo.findData(assignment.level)
            if idx < 0:
                # Poziom spoza skali katalogu (np. skala zmieniona później) -
                # zostaje, zamiast cicho przeskoczyć na inny.
                self.level_combo.addItem(f"Poziom {assignment.level}", assignment.level)
                idx = self.level_combo.count() - 1
            self.level_combo.setCurrentIndex(idx)
        self.level = assignment.level
        self.valid_from = assignment.valid_from
        self.valid_to = assignment.valid_to
        self.location_ids = assignment.location_ids
        self._update_scope_text()

    def assignment(self) -> EmployeeQualification | None:
        if not self.checkbox.isChecked():
            return None
        level = self.level_combo.currentData() if self.level_combo is not None else self.level
        return EmployeeQualification(
            self.qualification.id, level,
            valid_from=self.valid_from, valid_to=self.valid_to, location_ids=self.location_ids,
        )


def qualifications_after_edit(old_employee, rows: dict) -> tuple:
    """Kwalifikacje pracownika po zapisie okna: przypisania z widocznych
    wierszy (`rows`: klucz kwalifikacji -> QualificationRow) zastępują
    dotychczasowe; kwalifikacje, których okno nie pokazuje (ukryte przy
    wyłączonej zasadzie, spoza katalogu), zostają bez zmian - zero utraty
    danych."""
    old = list(old_employee.qualifications) if old_employee else []
    result = []
    for qualification in old:
        row = rows.get(qualification.qualification_id)
        if row is None:
            result.append(qualification)
            continue
        assignment = row.assignment()
        if assignment is not None:
            result.append(assignment)
    old_keys = {qualification.qualification_id for qualification in old}
    for key, row in rows.items():
        if key not in old_keys:
            assignment = row.assignment()
            if assignment is not None:
                result.append(assignment)
    return tuple(result)


class EmployeeDialog(QDialog):
    def __init__(
        self, parent=None, employee=None, shop_config=None, default_location_key=None,
        expand_contact=False, focus_field=None, companies=None, qualifications=None,
    ):
        super().__init__(parent)
        self.employee = employee
        # Firmy z Plik -> "Dane firmy" (MonthlyProject.companies) do kombo
        # "Firma" w sekcji Zaawansowane.
        self.companies = companies or {}
        self.shop_config = shop_config
        self.profile = get_profile(shop_config.business_type if shop_config else None)
        self.locations = shop_config.locations if shop_config else {}
        # Katalog kwalifikacji projektu (MonthlyProject.qualifications, id ->
        # Qualification) - z niego powstają wiersze kwalifikacji. Bez
        # katalogu (np. okno otwarte poza projektem) - domyślny katalog
        # profilu. Ten sam słownik co w projekcie: zapis dokłada do niego
        # znane programowi kwalifikacje, które okno pokazało spoza katalogu
        # ("Nie chce 24h" przy rotacji 24/7).
        self.catalog = catalog_or_default(qualifications, shop_config.business_type if shop_config else None)
        # Lokalizacja, na którą ma się domyślnie ustawić kombo poniżej dla
        # NOWEGO pracownika (patrz _fill_from_employee) - zwykle aktualnie
        # przeglądana placówka (main_window.selected_location_key), żeby
        # dodany właśnie pracownik od razu pojawił się w widocznej tabeli
        # zamiast "zniknąć" w nieprzefiltrowanej lokalizacji.
        self.default_location_key = default_location_key
        self.qualification_rows: dict[str, QualificationRow] = {}
        self.restriction_checkboxes: dict[str, QCheckBox] = {}
        self.location_combo: QComboBox | None = None
        self.vacation_days_left = 0
        self._contact_expanded = False
        self.setWindowTitle("Edytuj pracownika" if employee else "Dodaj pracownika")
        self.setModal(True)
        self.setMinimumWidth(460)

        # Wygląd pochodzi ze wspólnego arkusza stylów aplikacji (ui/theme.py).
        self._build_ui()
        self._fill_from_employee()

        # Dwuklik na komórce telefonu/e-maila/adresu w Pracownicy (patrz
        # ui/employees_dialog.py::_on_cell_double_clicked) otwiera od razu tę
        # sekcję rozwiniętą, z kursorem w odpowiednim polu - zamiast kazać
        # jeszcze raz kliknąć "Zaawansowane".
        if expand_contact:
            self._contact_expanded = True
            self.contact_card.setVisible(True)
        if focus_field is not None:
            field_widget = getattr(self, focus_field, None)
            if field_widget is not None:
                QTimer.singleShot(0, field_widget.setFocus)

        QTimer.singleShot(0, self._maybe_show_tutorial)

    def _policy_disabled(self, policy: str) -> bool:
        """True when a constraint policy (e.g. Dino's "meat") is DISABLED for
        the active project - the role/qualification tied to it isn't shown."""
        if not policy or not self.shop_config:
            return False
        return self.shop_config.constraint_policies.get(policy) == ConstraintPolicy.DISABLED

    def _visible_qualifications(self) -> list:
        """Kwalifikacje z katalogu pokazywane w oknie, w kolejności katalogu:
        - bez tych, których zasada jest Wyłączona (QUALIFICATION_POLICIES),
        - "Nie chce 24h" tylko gdy projekt używa rotacji 24/7 albo modelu
          godzin otwarcia Ochrony (poza nimi nic tej kwalifikacji nie czyta);
          wtedy także, gdy katalog jej jeszcze nie ma."""
        from logic.generator.opening_hours_coverage import profile_uses_opening_hours_model

        uses_24h = self._project_uses_duty_rotation() or (
            self.shop_config is not None and profile_uses_opening_hours_model(self.shop_config.business_type)
        )
        result = []
        for qualification in self.catalog.values():
            if self._policy_disabled(QUALIFICATION_POLICIES.get(qualification.id, "")):
                continue
            if qualification.id == QUAL_NO_24H and not uses_24h:
                continue
            result.append(qualification)
        if uses_24h and QUAL_NO_24H not in self.catalog:
            result.append(NO_24H_QUALIFICATION)
        return result

    def _project_uses_duty_rotation(self) -> bool:
        """Ten sam warunek co "Rotacja 24/7" w ui/config_dialog.py -
        projekt/którakolwiek lokalizacja ma faktycznie skonfigurowaną
        LocationConfig.duty_rotation (patrz normalize_duty_rotation)."""
        if not self.shop_config:
            return False
        if self.shop_config.get_duty_rotation():
            return True
        return any(loc.get_duty_rotation() for loc in self.shop_config.locations.values())

    def _selected_location_has_duty_rotation(self) -> bool:
        """Czy WYBRANA w combo lokalizacja (nie cały projekt, w odróżnieniu
        od _project_uses_duty_rotation powyżej) ma pełną rotację 24/7 -
        steruje widocznością no_night_check/no_afternoon_check poniżej,
        które mają sens tylko poza rotacją 24/7 (tam pracownik i tak nigdy
        nie dostanie starego typu zmiany OPEN/CLOSE/START/END/NIGHT, patrz
        add_duty_rotation_gate_constraint)."""
        if self.location_combo is None:
            return False
        key = self.location_combo.currentData()
        location = self.locations.get(key)
        return bool(location and location.get_duty_rotation())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(15)

        title = QLabel("Dane pracownika")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        if self.shop_config is not None:
            scope_note = QLabel(month_scope_note(self.shop_config.year, self.shop_config.month))
            scope_note.setObjectName("quickInfoHint")
            scope_note.setWordWrap(True)
            root.addWidget(scope_note)

        # Karta ról rośnie z liczbą ról custom profilu (kreator pozwala
        # dodać dowolnie wiele) - bez scrolla treść (i przyciski Zapisz/
        # Anuluj) wypadały poza okno. Wzorem sidebaru głównego okna
        # (ui/main_window.py::_build_left_panel).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)

        # --- Formularz ---
        form = QFormLayout()
        form.setSpacing(10)

        self.last_name = QLineEdit()
        self.first_name = QLineEdit()
        
        self.monthly_target_hours = QSpinBox()
        self.monthly_target_hours.setRange(0, 400)
        self.monthly_target_hours.setValue(160)
        self.monthly_target_hours.setSuffix(" h")

        self.employment_fraction = QComboBox()
        self.employment_fraction.addItem("1/1 (pełny etat)", 1.0)
        if self.profile.key == DEFAULT_BUSINESS_TYPE:
            # "Max 8:00" (kierowniczka - patrz _on_manager_toggled/
            # force_fulltime_845) to konwencja stricte Dino. Dla innych
            # profili 1/1 to zwykła pełna zmiana (decyzja użytkownika
            # 2026-09-28, patrz logic/utils/time_utils.py::get_effective_daily_hours) -
            # bez tej opcji w ogóle, żeby nie sugerować nieistniejącego
            # dla nich rozróżnienia.
            self.employment_fraction.addItem("1/1 (pełny etat) max 8:00", 1.01)
        self.employment_fraction.addItem("7/8", 0.875)
        self.employment_fraction.addItem("3/4", 0.75)
        self.employment_fraction.addItem("5/8", 0.625)
        self.employment_fraction.addItem("1/2 (pół etatu)", 0.5)
        self.employment_fraction.addItem("3/8", 0.375)
        self.employment_fraction.addItem("1/4", 0.25)

        form.addRow("Nazwisko:", self.last_name)
        form.addRow("Imię (opcjonalnie):", self.first_name)

        # Pole tylko do odczytu + "Zmień" (zamiast zwykłego spinboxa), żeby
        # nie dało się go przypadkiem przekręcić scrollem/strzałką przy
        # przewijaniu formularza - liczba dni urlopu zmienia się rzadko i
        # świadomie. Wartość trzymana w self.vacation_days_left, czytana w
        # _save() - ten sam wzorzec co reszta pól tego okna (zapis dopiero
        # przyciskiem "Zapisz" na dole, nie od razu).
        vacation_row = QWidget()
        vacation_row_layout = QHBoxLayout(vacation_row)
        vacation_row_layout.setContentsMargins(0, 0, 0, 0)
        vacation_row_layout.setSpacing(8)
        self.vacation_label = QLabel()
        vacation_row_layout.addWidget(self.vacation_label, 1)
        vacation_change_btn = QPushButton("Zmień")
        vacation_change_btn.setObjectName("secondaryButton")
        vacation_change_btn.clicked.connect(self._change_vacation_days)
        vacation_row_layout.addWidget(vacation_change_btn)
        form.addRow("Pozostało urlopu:", vacation_row)
        self._update_vacation_label()

        # Przywrócone dla wszystkich profili (decyzja użytkownika
        # 2026-09-28) - wpływa WYŁĄCZNIE na przeliczenie nominalnego czasu
        # pracy (shop.get_full_time_nominal_hours() * employment_fraction,
        # patrz hours_constraint.py/priority_hours_constraint.py/
        # monthly_hours_status.py), więc ma sens dla każdej branży, nie
        # tylko Dino.
        form.addRow("Wymiar etatu:", self.employment_fraction)

        if self.locations:
            # Bez opcji "Brak" - projekt ma zawsze co najmniej jedną
            # lokalizację (patrz model/shop_config.py), a tabela grafiku
            # filtruje się teraz po lokalizacji (ui/grid_view.py), więc
            # pracownik bez żadnej przypisanej byłby trwale niewidoczny w
            # każdym widoku - patrz _fill_from_employee() niżej dla wyboru
            # domyślnej wartości.
            self.location_combo = QComboBox()
            for loc in self.locations.values():
                self.location_combo.addItem(loc.name, loc.key)
            form.addRow("Lokalizacja:", self.location_combo)

        content_layout.addLayout(form)

        # --- Role i ograniczenia: jedna karta zamiast osobnej ramki na checkbox ---
        self.flags_card = QFrame()
        self.flags_card.setObjectName("configCard")
        flags_layout = QVBoxLayout(self.flags_card)
        flags_layout.setSpacing(10)

        default_month = (
            (self.shop_config.year, self.shop_config.month) if self.shop_config is not None
            else (date.today().year, date.today().month)
        )
        for qualification in self._visible_qualifications():
            row = QualificationRow(qualification, self.locations, default_month)
            flags_layout.addWidget(row)
            self.qualification_rows[qualification.id] = row

        # Kierowniczka (Dino) ma zawsze zmiany po 8h - wymusza wymiar etatu.
        manager_row = self.qualification_rows.get(QUAL_MANAGER)
        if manager_row is not None and self.profile.key == DEFAULT_BUSINESS_TYPE:
            manager_row.checkbox.toggled.connect(self._on_manager_toggled)

        no_24h_row = self.qualification_rows.get(QUAL_NO_24H)
        self.no_24h_check = no_24h_row.checkbox if no_24h_row is not None else None

        # Ograniczenia pracownika z profilu (Dino: no_night/no_afternoon z
        # własnymi etykietami) - pola Employee, nie kwalifikacje.
        for role in self.profile.roles:
            if role.key not in _EMPLOYEE_FIELDS:
                continue
            checkbox = QCheckBox(role.label)
            if role.description:
                checkbox.setToolTip(role.description)
            flags_layout.addWidget(checkbox)
            self.restriction_checkboxes[role.key] = checkbox

        # "Nie pracuje w godzinach nocnych"/"Nie pracuje na popołudniu" -
        # pola Employee.no_night/no_afternoon istnieją zawsze (patrz
        # model/employee.py), Dino pokazuje je przez generyczną pętlę ról
        # wyżej (profil dino_retail je definiuje). Dla innych profili
        # (Ochrona/Enyo) profile.roles ich nie ma, więc dedykowane
        # checkboxy tutaj - mają sens TYLKO w lokalizacji bez rotacji 24/7
        # (w rotacji pracownik i tak nigdy nie dostanie starego typu zmiany,
        # patrz _selected_location_has_duty_rotation), więc widoczność
        # przełącza się dynamicznie z wyborem lokalizacji w combo powyżej,
        # nie raz przy otwarciu okna jak no_24h_check (ten jest per PROJEKT,
        # nie per lokalizacja pracownika).
        self.no_night_check = None
        self.no_afternoon_check = None
        if self.profile.key != DEFAULT_BUSINESS_TYPE:
            self.no_night_check = QCheckBox("Nie pracuje w godzinach nocnych (22:00-6:00)")
            self.no_night_check.setToolTip(
                "Ta osoba nigdy nie dostanie od generatora zmiany dotykającej "
                "godzin nocnych (22:00-6:00). Ręczny wpis nockę nadal można "
                "wprowadzić wyjątkowo - generator go uszanuje."
            )
            flags_layout.addWidget(self.no_night_check)

            self.no_afternoon_check = QCheckBox("Nie pracuje na popołudniu")
            self.no_afternoon_check.setToolTip(
                "Ta osoba nigdy nie dostanie od generatora zmiany popołudniowej "
                "- tylko poranne. Ręczny wpis nadal można wprowadzić wyjątkowo."
            )
            flags_layout.addWidget(self.no_afternoon_check)

            if self.location_combo is not None:
                self.location_combo.currentIndexChanged.connect(
                    self._update_no_night_afternoon_visibility
                )

        content_layout.addWidget(self.flags_card)

        # --- Zaawansowane: dane kontaktowe (zwijane, domyślnie schowane) ---
        # Pod wszystkimi polami powyżej, ale NIE w dolnym pasku przycisków
        # (Usuń/Pomoc/Zapisz) - to osobna, opcjonalna sekcja tego okna, nie
        # akcja całego dialogu. Dawniej osobne okno "Pracownicy -> Zaawansowane"
        # (PersonalDataDialog, ui/employees_dialog.py) - scalone tutaj, bo
        # dane kontaktowe dotyczą tego samego pracownika co reszta karty.
        toggle_row = QHBoxLayout()
        self.contact_toggle_btn = QPushButton("Zaawansowane")
        self.contact_toggle_btn.setObjectName("secondaryButton")
        self.contact_toggle_btn.setToolTip(
            "Firma oraz dane kontaktowe: telefon, e-mail, adres - do wniosków urlopowych."
        )
        self.contact_toggle_btn.clicked.connect(self._toggle_contact_card)
        toggle_row.addWidget(self.contact_toggle_btn)
        toggle_row.addStretch()
        content_layout.addLayout(toggle_row)

        self.contact_card = QFrame()
        self.contact_card.setObjectName("configCard")
        contact_layout = QVBoxLayout(self.contact_card)
        contact_layout.setSpacing(10)

        contact_title = QLabel("Dane kontaktowe")
        contact_title.setObjectName("groupLabel")
        contact_layout.addWidget(contact_title)

        contact_hint = QLabel("Potrzebne do wniosków urlopowych. Generator grafiku ich nie używa.")
        contact_hint.setObjectName("mutedHint")
        contact_hint.setWordWrap(True)
        contact_layout.addWidget(contact_hint)

        contact_form = QFormLayout()
        contact_form.setSpacing(10)
        self.company_combo = QComboBox()
        self.company_combo.addItem("(brak)", "")
        for company in self.companies.values():
            self.company_combo.addItem(company.name, company.key)
        self.company_combo.setToolTip("Firmy dodasz w menu Plik -> Dane firmy.")
        contact_form.addRow("Firma:", self.company_combo)
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("np. 600 123 456")
        self.email = QLineEdit()
        self.email.setPlaceholderText("np. jan.kowalski@firma.pl")
        self.street = QLineEdit()
        self.street.setPlaceholderText("ulica, nr domu / mieszkania")
        self.postal_code = QLineEdit()
        self.postal_code.setPlaceholderText("00-000")
        self.postal_code.setMaxLength(6)
        self.city = QLineEdit()
        contact_form.addRow("Telefon:", self.phone)
        contact_form.addRow("E-mail:", self.email)
        contact_form.addRow("Adres:", self.street)
        contact_form.addRow("Kod pocztowy:", self.postal_code)
        contact_form.addRow("Miejscowość:", self.city)
        contact_layout.addLayout(contact_form)

        self.contact_card.setVisible(False)
        content_layout.addWidget(self.contact_card)

        content_layout.addStretch()

        # --- Dolny pasek przycisków ---
        button_row = QHBoxLayout()

        help_btn = QPushButton("Pomoc")
        help_btn.setObjectName("secondaryButton")
        help_btn.setMinimumHeight(34)
        help_btn.clicked.connect(self._open_tutorial)
        button_row.addWidget(help_btn)

        # Przycisk Usuń (w lewym rogu)
        if self.employee:
            self.delete_btn = QPushButton("Usuń pracownika")
            self.delete_btn.setObjectName("dangerButton")
            self.delete_btn.setMinimumHeight(34)
            self.delete_btn.clicked.connect(self._delete_employee)
            button_row.addWidget(self.delete_btn)

        # Spacer przesuwa resztę na prawo
        button_row.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Przyciski Zapisz / Anuluj
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Zapisz")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setMinimumHeight(34)
        self.save_btn.setMinimumWidth(100)
        self.save_btn.clicked.connect(self._save)

        button_row.addWidget(cancel_btn)
        button_row.addWidget(self.save_btn)

        root.addLayout(button_row)

    def _on_manager_toggled(self, checked):
        # Jej zmiany są zawsze dokładnie 8h - "1/1 max 8:00" jest jedynym
        # wymiarem etatu, który tego gwarantuje (patrz force_fulltime_845).
        if checked:
            idx = self.employment_fraction.findData(1.01)
            if idx >= 0:
                self.employment_fraction.setCurrentIndex(idx)

    def _toggle_contact_card(self):
        # Nie self.contact_card.isVisible() - poza pokazanym oknem to zawsze
        # False (zależy od całego łańcucha rodziców), więc drugie kliknięcie
        # nie cofałoby widoczności. Ten sam wzorzec co
        # _LocationRow._toggle_hours_expanded (ui/locations_dialog.py).
        self._contact_expanded = not self._contact_expanded
        self.contact_card.setVisible(self._contact_expanded)

    def _update_vacation_label(self):
        self.vacation_label.setText(f"{format_days(self.vacation_days_left)} {days_noun(self.vacation_days_left)}")
        # Ujemna pula = zaznaczono w grafiku więcej urlopu, niż zostało.
        self.vacation_label.setStyleSheet("color: #c62828;" if self.vacation_days_left < 0 else "")

    def _change_vacation_days(self):
        # Krok 0,5 dnia - urlop zaznaczany w grafiku odejmuje się z tą
        # dokładnością (logic/leave_requests.py::leave_day_value). Dolna
        # granica poniżej zera tylko wtedy, gdy pula już jest ujemna (więcej
        # urlopu zaznaczonego niż zostało) - inaczej okno obcięłoby ją po cichu.
        value, ok = QInputDialog.getDouble(
            self, "Pozostało urlopu", "Liczba dni urlopu:",
            self.vacation_days_left, min(0, self.vacation_days_left), 365, 1, step=0.5,
        )
        if ok:
            self.vacation_days_left = round(value * 2) / 2
            self._update_vacation_label()

    def _update_no_night_afternoon_visibility(self):
        if self.no_night_check is None:
            return
        visible = not self._selected_location_has_duty_rotation()
        self.no_night_check.setVisible(visible)
        self.no_afternoon_check.setVisible(visible)

    def _fill_from_employee(self):
        if not self.employee:
            # Nowy pracownik: kombo lokalizacji i tak zawsze ma co najmniej
            # jedną pozycję (patrz _build_ui) - ustawiamy ją od razu na
            # aktualnie przeglądaną placówkę, żeby domyślnie trafił tam,
            # gdzie użytkownik go dodaje, zamiast na pierwszą z listy.
            if self.location_combo is not None:
                idx = self.location_combo.findData(self.default_location_key or "")
                self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)
            # setCurrentIndex() only emits currentIndexChanged when the
            # index actually moves - explicit call so a new employee still
            # gets correct initial no_night/no_afternoon visibility even
            # when the default location (already selected at index 0)
            # happens to be the one with duty_rotation.
            self._update_no_night_afternoon_visibility()
            return
        self.last_name.setText(self.employee.last_name)
        self.first_name.setText(self.employee.first_name)
        assignments = {q.qualification_id: q for q in self.employee.qualifications}
        for key, row in self.qualification_rows.items():
            row.set_assignment(assignments.get(key))
        for key, checkbox in self.restriction_checkboxes.items():
            checkbox.setChecked(bool(getattr(self.employee, key)))
        self.monthly_target_hours.setValue(self.employee.monthly_target_hours)
        idx = self.employment_fraction.findData(self.employee.employment_fraction)
        if idx >= 0:
            self.employment_fraction.setCurrentIndex(idx)
        if self.no_night_check is not None:
            self.no_night_check.setChecked(self.employee.no_night)
            self.no_afternoon_check.setChecked(self.employee.no_afternoon)
        if self.location_combo is not None:
            idx = self.location_combo.findData(self.employee.location_key)
            self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.phone.setText(self.employee.phone)
        self.email.setText(self.employee.email)
        self.street.setText(self.employee.street)
        self.postal_code.setText(self.employee.postal_code)
        self.city.setText(self.employee.city)
        idx = self.company_combo.findData(self.employee.company_key)
        self.company_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.vacation_days_left = self.employee.vacation_days_left
        self._update_vacation_label()
        # Patrz komentarz przy analogicznym wywołaniu wyżej (ścieżka nowego
        # pracownika) - jawne wywołanie zamiast polegać wyłącznie na sygnale.
        self._update_no_night_afternoon_visibility()

    def _build_tutorial_steps(self):
        steps = [
            TutorialStep(
                "Dane pracownika",
                "Tutaj ustawiasz podstawowe dane pracownika: imię, nazwisko, "
                "wymiar etatu oraz kwalifikacje wykorzystywane przez generator.",
            ),
            TutorialStep(
                "Wymiar etatu",
                "Wybierz wymiar etatu pracownika - od tego zależy jego docelowa "
                "liczba godzin w miesiącu.",
                target=self.employment_fraction,
            ),
        ]
        if self.location_combo is not None:
            steps.append(TutorialStep(
                "Lokalizacja",
                "Wybierz placówkę, do której przypisany jest ten pracownik.",
                target=self.location_combo,
            ))
        steps.append(TutorialStep(
            "Kwalifikacje",
            "Zaznacz kwalifikacje tego pracownika - generator używa ich przy "
            "układaniu grafiku. Przy kwalifikacji z poziomami wybierz poziom; "
            "przycisk obok ustawia daty ważności i placówki (domyślnie "
            "bezterminowo, we wszystkich placówkach).",
            target=self.flags_card,
        ))
        if self.no_24h_check is not None:
            steps.append(TutorialStep(
                "Nie chce pracować zmian 24h",
                "Zaznacz, jeśli ta osoba nie powinna dostawać pojedynczej zmiany "
                "24h przy rotacji służby - dostanie wtedy dwie zmiany po 12h.",
                target=self.no_24h_check,
            ))
        # Krok tylko gdy logicznie widoczne (nie isVisible() - niemiarodajne
        # przed pokazaniem całego okna, patrz analogiczny komentarz przy
        # ui/main_window.py::_relayout_quick_btn_grid).
        if self.no_night_check is not None and not self._selected_location_has_duty_rotation():
            steps.append(TutorialStep(
                "Nie pracuje w nocy / popołudniami",
                "Zaznacz, jeśli ta osoba nie powinna dostawać od generatora zmian "
                "nocnych i/lub popołudniowych - widoczne tylko dla lokalizacji bez "
                "rotacji 24/7. Ręczny wpis takiej zmiany nadal będzie respektowany.",
                target=self.no_night_check,
            ))
        steps.append(TutorialStep(
            "Zapisz",
            "Zapisz dane pracownika.",
            target=self.save_btn,
        ))
        return steps

    def _start_tutorial(self, on_finished=None):
        existing = getattr(self, "_tutorial_overlay", None)
        if existing is not None:
            existing.deleteLater()
        self._tutorial_overlay = TutorialOverlay(self, self._build_tutorial_steps(), on_finished=on_finished)
        self._tutorial_overlay.start()

    def _open_tutorial(self):
        self._start_tutorial()

    def _maybe_show_tutorial(self):
        if os.path.exists(EMPLOYEE_TUTORIAL_FLAG):
            return

        def mark_seen():
            try:
                with open(EMPLOYEE_TUTORIAL_FLAG, "w") as f:
                    f.write("seen")
            except OSError:
                pass

        self._start_tutorial(on_finished=mark_seen)

    def _save(self):
        ln = self.last_name.text().strip()
        fn = self.first_name.text().strip()

        if not ln:
            QMessageBox.critical(self, "Błąd", "Nazwisko nie może być puste.")
            return

        for key, row in self.qualification_rows.items():
            assignment = row.assignment()
            if assignment is not None and row.qualification.requires_validity and assignment.valid_to is None:
                QMessageBox.critical(
                    self, "Błąd",
                    f"Kwalifikacja „{row.qualification.name}” wymaga daty ważności - ustaw „Ważna do”.",
                )
                return

        legacy_roles = {}
        for role in self.profile.roles:
            if role.key not in _EMPLOYEE_FIELDS:
                continue
            if role.key in self.restriction_checkboxes:
                legacy_roles[role.key] = self.restriction_checkboxes[role.key].isChecked()
            else:
                legacy_roles[role.key] = getattr(self.employee, role.key) if self.employee else False

        # no_night/no_afternoon - dedykowane checkboxy (patrz _build_ui),
        # widoczne/uwzględniane tylko dla WYBRANEJ lokalizacji bez rotacji
        # 24/7. Gdy niewidoczne (Dino - nie ma tych checkboxów wcale, albo
        # Enyo z lokalizacją 24/7 wybraną) - zachowaj dotychczasową wartość
        # zamiast cichego wyzerowania, tym samym wzorcem co no_24h_check
        # wyżej. Dla Dino profile.roles JUŻ ustawił legacy_roles["no_night"]/
        # ["no_afternoon"] w pętli wyżej - nadpisujemy tylko gdy dedykowany
        # checkbox faktycznie istnieje (czyli nigdy dla Dino).
        if self.no_night_check is not None:
            if not self._selected_location_has_duty_rotation():
                legacy_roles["no_night"] = self.no_night_check.isChecked()
                legacy_roles["no_afternoon"] = self.no_afternoon_check.isChecked()
            else:
                legacy_roles["no_night"] = self.employee.no_night if self.employee else False
                legacy_roles["no_afternoon"] = self.employee.no_afternoon if self.employee else False

        location_key = self.location_combo.currentData() if self.location_combo is not None else ""

        try:
            emp = Employee(
                last_name=ln,
                first_name=fn,
                monthly_target_hours=self.monthly_target_hours.value(),
                employment_fraction=self.employment_fraction.currentData(),
                qualifications=qualifications_after_edit(self.employee, self.qualification_rows),
                location_key=location_key,
                company_key=self.company_combo.currentData() or "",
                phone=self.phone.text().strip(),
                email=self.email.text().strip(),
                street=self.street.text().strip(),
                postal_code=self.postal_code.text().strip(),
                city=self.city.text().strip(),
                vacation_days_left=self.vacation_days_left,
                **legacy_roles,
            )
            emp.validate()
        except Exception as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

        merge_catalog(self.catalog, [
            row.qualification for row in self.qualification_rows.values() if row.checkbox.isChecked()
        ])
        self.employee_result = emp
        self.accept()

    def _delete_employee(self):
        reply = QMessageBox.question(
            self,
            "Usuń pracownika",
            f"Czy na pewno chcesz usunąć pracownika: {self.employee.first_name} {self.employee.last_name}?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.employee_result = None
            self.accept()