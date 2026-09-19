from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.slug import slugify
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.location import DEFAULT_LOCATION_CONSTRAINTS, LocationConfig


def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class _LocationRow(QFrame):
    """Jeden edytowalny wiersz lokalizacji w oknie "Lokalizacje": nazwa,
    pełne godziny otwarcia na każdy dzień tygodnia (WeeklyHoursEditor),
    checkbox "24/7" (zastępuje dawne ręczne pole "Zmiana nocna" - godziny
    nocne generator wykrywa teraz sam z tych godzin otwarcia, patrz
    LocationConfig.get_night_shift_hours()) oraz progi obsady, które
    faktycznie nadpisują generator dla pracowników przypisanych do tej
    lokalizacji (patrz logic/generator/base_specs.py::_build_max_consecutive
    i logic/generator/generic_rules.py::build_min_staff_with_role) - progi,
    których generator nie czyta per-lokalizacja (min_open_staff/
    min_close_staff dla wbudowanego profilu dino_retail), celowo nie są tu
    pokazywane, bo nic by nie robiły."""

    def __init__(
        self, on_remove, name="", open_hours=None, is_24_7=False,
        max_consecutive_days=None, rule_defs=(), rule_overrides=None,
        original_key=None,
    ):
        super().__init__()
        self.setObjectName("configCard")
        self.rule_defs = list(rule_defs)
        rule_overrides = rule_overrides or {}
        # Klucz oryginalnej LocationConfig (jeśli ten wiersz reprezentuje już
        # istniejącą lokalizację) - zapisywany "w miejscu" pod tym samym
        # kluczem zamiast przeliczania go na nowo ze slugify(nazwa) przy
        # każdym zapisie, co dawniej po cichu gubiło employee.location_key
        # przypisanych pracowników przy zmianie nazwy.
        self.original_key = original_key
        outer = QVBoxLayout(self)

        top = QHBoxLayout()
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("np. Galeria Płn")
        top.addWidget(self.name_edit, 1)

        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.clicked.connect(lambda: on_remove(self))
        top.addWidget(self.remove_btn)
        outer.addLayout(top)

        self.is_24_7_check = QCheckBox("Działalność całodobowa (24/7)")
        self.is_24_7_check.setChecked(bool(is_24_7))
        self.is_24_7_check.toggled.connect(self._on_24_7_toggled)
        outer.addWidget(self.is_24_7_check)

        self.hours_editor = WeeklyHoursEditor(open_hours)
        self.hours_editor.setEnabled(not is_24_7)
        outer.addWidget(self.hours_editor)

        thresholds = QHBoxLayout()
        thresholds.addWidget(QLabel("Progi obsady dla tej lokalizacji:"))

        self.max_consecutive_spin = QSpinBox()
        self.max_consecutive_spin.setRange(1, 14)
        self.max_consecutive_spin.setFixedWidth(60)
        self.max_consecutive_spin.setValue(
            max_consecutive_days or DEFAULT_LOCATION_CONSTRAINTS["max_consecutive_days"]
        )
        thresholds.addWidget(QLabel("Dni pod rząd:"))
        thresholds.addWidget(self.max_consecutive_spin)

        self.rule_spins: dict[str, QSpinBox] = {}
        for rule_key, label, default_value in self.rule_defs:
            spin = QSpinBox()
            spin.setRange(0, 50)
            spin.setSpecialValueText(f"domyślnie ({default_value})")
            spin.setFixedWidth(120)
            spin.setValue(rule_overrides.get(rule_key, 0))
            thresholds.addWidget(QLabel(f"{label}:"))
            thresholds.addWidget(spin)
            self.rule_spins[rule_key] = spin

        thresholds.addStretch()
        outer.addLayout(thresholds)

    def _on_24_7_toggled(self, checked):
        if checked:
            self.hours_editor.set_hours({wd: ("00:00", "23:45") for wd in range(7)})
        self.hours_editor.setEnabled(not checked)

    def name(self) -> str:
        return self.name_edit.text().strip()

    def constraints_overrides(self) -> dict:
        overrides = {"max_consecutive_days": self.max_consecutive_spin.value()}
        for rule_key, spin in self.rule_spins.items():
            if spin.value():
                overrides[rule_key] = spin.value()
        return overrides


class LocationsDialog(QDialog):
    """Samodzielne okno zarządzania lokalizacjami/placówkami w ramach
    aktualnie otwartego projektu - dawniej zakładka "Lokalizacje" wewnątrz
    Konfiguracja -> Generator, wydzielona do własnego menu (Konfiguracja ->
    Lokalizacje, patrz ui/main_window.py) dla lepszej rozpoznawalności.
    Projekt ma zawsze co najmniej jedną lokalizację (patrz
    model/shop_config.py) - to okno pilnuje, żeby nie dało się usunąć
    ostatniej pozostałej."""

    def __init__(self, parent, shop_config):
        super().__init__(parent)
        self.shop_config = shop_config
        self.setWindowTitle("Lokalizacje")
        self.setModal(True)
        self.resize(720, 560)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Lokalizacje")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        hint = QLabel(
            "Osobne obiekty/placówki w ramach tego projektu (np. kilka "
            "chronionych lokalizacji), każdy z własnymi godzinami otwarcia. "
            "Zmianę nocną generator wykrywa teraz sam z godzin otwarcia "
            "(dowolna godzina między 22:00 a 6:00) - nie trzeba jej już "
            "ustawiać ręcznie. Zaznacz \"24/7\", jeśli placówka jest czynna "
            "całodobowo przez cały tydzień.\n"
            "Progi obsady poniżej nadpisują wartości domyślne tylko dla "
            "pracowników przypisanych do tej lokalizacji."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Lista lokalizacji rośnie bez ograniczeń - bez scrolla treść tego
        # okna (i przyciski Zapisz/Anuluj) wypadałyby poza ekran przy kilku
        # lokalizacjach naraz. Wzorem sidebaru głównego okna
        # (ui/main_window.py::_build_left_panel).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        outer_host = QWidget()
        scroll.setWidget(outer_host)
        outer = QVBoxLayout(outer_host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # Progi z reguł "min. N osób z rolą X" bieżącego (custom) profilu -
        # to okno nie odświeża się na żywo po zmianie profilu w Konfiguracji.
        from model.business_profile import get_custom_profile
        from model.custom_profile import RULE_TYPE_MIN_STAFF_WITH_ROLE

        self._location_rule_defs = []
        custom = get_custom_profile(self.shop_config.business_type)
        if custom is not None:
            for rule in custom.rules:
                if rule.type == RULE_TYPE_MIN_STAFF_WITH_ROLE:
                    self._location_rule_defs.append((
                        custom.rule_policy_key(rule),
                        custom.rule_label(rule),
                        rule.params.get("min_count", 1),
                    ))

        self._location_rows: list[_LocationRow] = []
        self.locations_container = QVBoxLayout()
        outer.addLayout(self.locations_container)

        for key, loc in self.shop_config.locations.items():
            self._add_location_row(
                loc.name, dict(loc.open_hours), is_24_7=loc.is_24_7,
                max_consecutive_days=loc.constraints.get("max_consecutive_days"),
                rule_overrides=loc.constraints,
                original_key=key,
            )

        add_btn = QPushButton("Dodaj lokalizację")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(lambda: self._add_location_row())
        outer.addWidget(add_btn)

        outer.addStretch()

        buttons = QDialogButtonBox()
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        root.addWidget(buttons)

    def _add_location_row(
        self, name="", open_hours=None, is_24_7=False,
        max_consecutive_days=None, rule_overrides=None, original_key=None,
    ):
        row = _LocationRow(
            self._remove_location_row, name, open_hours, is_24_7=is_24_7,
            max_consecutive_days=max_consecutive_days,
            rule_defs=self._location_rule_defs,
            rule_overrides=rule_overrides,
            original_key=original_key,
        )
        self._location_rows.append(row)
        self.locations_container.addWidget(row)
        self._update_remove_buttons()

    def _remove_location_row(self, row):
        if len(self._location_rows) <= 1:
            # Projekt musi mieć zawsze co najmniej jedną lokalizację (patrz
            # ShopConfig.__init__/from_dict) - przełącznik placówek w głównym
            # oknie na tym polega.
            return
        self._location_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._update_remove_buttons()

    def _update_remove_buttons(self):
        only_one = len(self._location_rows) <= 1
        for row in self._location_rows:
            row.remove_btn.setEnabled(not only_one)
            row.remove_btn.setToolTip(
                "Projekt musi mieć co najmniej jedną lokalizację." if only_one else ""
            )

    def _save(self):
        try:
            if not self._location_rows:
                raise ValueError("Projekt musi mieć co najmniej jedną lokalizację.")

            new_locations: dict[str, LocationConfig] = {}
            taken_keys = set()
            for row in self._location_rows:
                name = row.name()
                if not name:
                    raise ValueError("Każda lokalizacja musi mieć nazwę.")

                # Lokalizacja już istniejąca (edytowana, także po zmianie
                # nazwy) zachowuje swój klucz w miejscu - slugify(nazwa) tylko
                # dla nowo dodanych wierszy - patrz komentarz przy
                # _LocationRow.original_key.
                if row.original_key and row.original_key not in taken_keys:
                    key = row.original_key
                else:
                    key = slugify(name, taken_keys)
                taken_keys.add(key)

                hours = row.hours_editor.get_hours()
                for wd, (start, end) in hours.items():
                    if _parse_time(end) <= _parse_time(start):
                        day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                        raise ValueError(
                            f"Zamknięcie musi być później niż otwarcie tego samego dnia "
                            f"({day_names[wd]}) dla lokalizacji: {name}. Zmiany przechodzące "
                            "przez północ nie są jeszcze wspierane — dla działalności "
                            "całodobowej zaznacz \"24/7\"."
                        )

                loc = LocationConfig(
                    key=key, name=name,
                    open_hours=hours,
                    constraints=row.constraints_overrides(),
                    is_24_7=row.is_24_7_check.isChecked(),
                )
                old = self.shop_config.locations.get(row.original_key)
                if old is not None:
                    # Pola bez UI w tym oknie (dziedziny handlowe, święta,
                    # nadpisania dni, rotacja służby) - zachowane bez zmian.
                    loc.trade_sundays = old.trade_sundays
                    loc.public_holidays = old.public_holidays
                    loc.day_overrides = old.day_overrides
                    loc.duty_rotation = old.duty_rotation
                new_locations[key] = loc

            self.shop_config.locations = new_locations
        except Exception as exc:
            QMessageBox.critical(self, "Błąd konfiguracji lokalizacji", str(exc))
            return

        self.accept()
