import dataclasses
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
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
from model.business_profile import DEFAULT_BUSINESS_TYPE, get_profile
from model.constraint_policy import ConstraintPolicy
from logic.generator.duty_rotation_constraint import NIE_CHCE_24H_ROLE_KEY
from logic.utils.time_utils import month_scope_note
from ui.tutorial_overlay import TutorialOverlay, TutorialStep

EMPLOYEE_TUTORIAL_FLAG = "employee_tutorial_seen.flag"

# RoleDef.key values that map directly onto an Employee dataclass field
# (the six legacy Dino flags). Any other key lives in Employee.custom_roles
# instead, so new business profiles don't need new Employee fields.
_EMPLOYEE_FIELDS = {f.name for f in dataclasses.fields(Employee)}


class EmployeeDialog(QDialog):
    def __init__(self, parent=None, employee=None, shop_config=None, default_location_key=None):
        super().__init__(parent)
        self.employee = employee
        self.shop_config = shop_config
        self.profile = get_profile(shop_config.business_type if shop_config else None)
        self.locations = shop_config.locations if shop_config else {}
        # Lokalizacja, na którą ma się domyślnie ustawić kombo poniżej dla
        # NOWEGO pracownika (patrz _fill_from_employee) - zwykle aktualnie
        # przeglądana placówka (main_window.selected_location_key), żeby
        # dodany właśnie pracownik od razu pojawił się w widocznej tabeli
        # zamiast "zniknąć" w nieprzefiltrowanej lokalizacji.
        self.default_location_key = default_location_key
        self.role_checkboxes: dict[str, QCheckBox] = {}
        self.location_combo: QComboBox | None = None
        self.setWindowTitle("Edytuj pracownika" if employee else "Dodaj pracownika")
        self.setModal(True)
        self.setMinimumWidth(460)

        # Wygląd pochodzi ze wspólnego arkusza stylów aplikacji (ui/theme.py).
        self._build_ui()
        self._fill_from_employee()
        QTimer.singleShot(0, self._maybe_show_tutorial)

    def _role_is_hidden(self, role) -> bool:
        """True when this role's linked_policy (e.g. Dino's meat roles ->
        "meat") is DISABLED for the active project, so the checkbox for it
        shouldn't be shown at all."""
        if not role.linked_policy or not self.shop_config:
            return False
        return self.shop_config.constraint_policies.get(role.linked_policy) == ConstraintPolicy.DISABLED

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

        for role in self.profile.roles:
            if self._role_is_hidden(role):
                continue
            if role.key == NIE_CHCE_24H_ROLE_KEY:
                # Ten klucz ma dedykowany checkbox niżej (self.no_24h_check),
                # gated na _project_uses_duty_rotation() - poza rotacją 24/7
                # nic go nie czyta (patrz logic/generator/duty_rotation_constraint.py),
                # więc pokazywanie go tu drugi raz byłoby martwym duplikatem:
                # oba pisały do tego samego Employee.custom_roles["nie_chce_24h"],
                # a _save() niżej i tak zawsze nadpisywał tę wartość stanem
                # self.no_24h_check, gdy oba były widoczne naraz.
                continue
            checkbox = QCheckBox(role.label)
            if role.description:
                checkbox.setToolTip(role.description)
            flags_layout.addWidget(checkbox)
            self.role_checkboxes[role.key] = checkbox

        # Zachowania specyficzne dla konkretnych ról (wykluczanie się mięsa/
        # mięsa-lekkiego, wymuszanie wymiaru etatu kierowniczki) są pinowane
        # po kluczu roli, nie generyczną regułą - inne profile ich nie mają.
        meat_cb = self.role_checkboxes.get("is_meat")
        meat_light_cb = self.role_checkboxes.get("is_meat_light")
        if meat_cb and meat_light_cb:
            meat_cb.toggled.connect(self._on_meat_toggled)
            meat_light_cb.toggled.connect(self._on_meat_light_toggled)

        manager_cb = self.role_checkboxes.get("is_manager")
        if manager_cb:
            manager_cb.toggled.connect(self._on_manager_toggled)

        # Flaga dla rotacji służby 24/7 (patrz LocationConfig.duty_rotation,
        # logic/generator/duty_rotation_constraint.py) - osobna od systemu
        # ról profilu, bo dotyczy generatora niezależnie od tego, jakie role
        # ma dany profil. Widoczna tylko gdy projekt faktycznie używa tego
        # mechanizmu (na poziomie projektu albo którejkolwiek lokalizacji) -
        # dla profili bez rotacji nic by nie robiła.
        self.no_24h_check = None
        # Także profil Ochrony bez rotacji (placówki z godzinami otwarcia -
        # doba sob/nd to tam zmiana 24h albo dwie po 12h, patrz
        # logic/generator/opening_hours_coverage.py).
        from logic.generator.opening_hours_coverage import profile_uses_opening_hours_model
        if self._project_uses_duty_rotation() or (
            self.shop_config is not None and profile_uses_opening_hours_model(self.shop_config.business_type)
        ):
            self.no_24h_check = QCheckBox("Nie chce pracować zmian 24h")
            self.no_24h_check.setToolTip(
                "Ta osoba nie dostanie od generatora zmiany 24h w sobotę ani "
                "niedzielę - doba jest wtedy dzielona na dwie zmiany po 12h "
                "(rotacja 24/7 i placówki z dobą w godzinach otwarcia)."
            )
            flags_layout.addWidget(self.no_24h_check)

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

    def _on_meat_toggled(self, checked):
        meat_light_cb = self.role_checkboxes["is_meat_light"]
        if checked and meat_light_cb.isChecked():
            meat_light_cb.setChecked(False)

    def _on_meat_light_toggled(self, checked):
        meat_cb = self.role_checkboxes["is_meat"]
        if checked and meat_cb.isChecked():
            meat_cb.setChecked(False)

    def _on_manager_toggled(self, checked):
        # Jej zmiany są zawsze dokładnie 8h - "1/1 max 8:00" jest jedynym
        # wymiarem etatu, który tego gwarantuje (patrz force_fulltime_845).
        if checked:
            idx = self.employment_fraction.findData(1.01)
            if idx >= 0:
                self.employment_fraction.setCurrentIndex(idx)

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
        for key, checkbox in self.role_checkboxes.items():
            if key in _EMPLOYEE_FIELDS:
                checkbox.setChecked(getattr(self.employee, key, False))
            else:
                checkbox.setChecked(self.employee.custom_roles.get(key, False))
        self.monthly_target_hours.setValue(self.employee.monthly_target_hours)
        idx = self.employment_fraction.findData(self.employee.employment_fraction)
        if idx >= 0:
            self.employment_fraction.setCurrentIndex(idx)
        if self.no_24h_check is not None:
            self.no_24h_check.setChecked(self.employee.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False))
        if self.no_night_check is not None:
            self.no_night_check.setChecked(self.employee.no_night)
            self.no_afternoon_check.setChecked(self.employee.no_afternoon)
        if self.location_combo is not None:
            idx = self.location_combo.findData(self.employee.location_key)
            self.location_combo.setCurrentIndex(idx if idx >= 0 else 0)
        # Patrz komentarz przy analogicznym wywołaniu wyżej (ścieżka nowego
        # pracownika) - jawne wywołanie zamiast polegać wyłącznie na sygnale.
        self._update_no_night_afternoon_visibility()

    def _build_tutorial_steps(self):
        steps = [
            TutorialStep(
                "Dane pracownika",
                "Tutaj ustawiasz podstawowe dane pracownika: imię, nazwisko, "
                "wymiar etatu oraz role wykorzystywane przez generator.",
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
            "Role",
            "Zaznacz role tego pracownika - generator używa ich przy układaniu "
            "grafiku (np. kto ma priorytet w przydzielaniu godzin).",
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

        legacy_roles = {}
        custom_roles = {}
        for role in self.profile.roles:
            key = role.key
            if key in self.role_checkboxes:
                value = self.role_checkboxes[key].isChecked()
            else:
                # Hidden because its linked_policy is DISABLED - preserve
                # whatever the employee already had instead of silently
                # wiping it to False (e.g. turning the "meat" policy off
                # must not un-flag every meat-counter employee).
                if key in _EMPLOYEE_FIELDS:
                    value = getattr(self.employee, key, False) if self.employee else False
                else:
                    value = self.employee.custom_roles.get(key, False) if self.employee else False

            if key in _EMPLOYEE_FIELDS:
                legacy_roles[key] = value
            else:
                custom_roles[key] = value

        if self.no_24h_check is not None:
            custom_roles[NIE_CHCE_24H_ROLE_KEY] = self.no_24h_check.isChecked()
        elif self.employee is not None:
            # Checkbox niewidoczny (projekt nie używa rotacji 24/7) - nie
            # wolno cicho zgubić wartości, gdyby jednak była już ustawiona
            # (np. lokalizacja z rotacją została w międzyczasie usunięta).
            custom_roles[NIE_CHCE_24H_ROLE_KEY] = self.employee.custom_roles.get(NIE_CHCE_24H_ROLE_KEY, False)

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
                custom_roles=custom_roles,
                location_key=location_key,
                # Dane osobowe edytuje Pracownicy -> Zaawansowane, nie to
                # okno - przy edycji muszą przejść bez zmian.
                **(self.employee.personal_data() if self.employee else {}),
                **legacy_roles,
            )
            emp.validate()
        except Exception as exc:
            QMessageBox.critical(self, "Błąd", str(exc))
            return

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