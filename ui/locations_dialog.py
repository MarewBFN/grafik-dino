import os

from PySide6.QtCore import QTime, QTimer
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

from logic.utils.time_utils import month_scope_note
from ui.duty_rotation_editor import DutyRotationEditor
from ui.slug import slugify
from ui.time_input import TimeInputWidget
from ui.tutorial_overlay import TutorialOverlay, TutorialStep
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.location import DEFAULT_LOCATION_CONSTRAINTS, LocationConfig

LOCATIONS_TUTORIAL_FLAG = "locations_tutorial_seen.flag"

# "Rotacja całodobowa - godzina rozpoczęcia" (LocationConfig.round_clock_start_hour)
# UKRYTA dla Enyo (patrz ENYO_ONLY_CHANGES.md) - specyfikację klienta (1 osoba
# na zmianie, zmiany bez zazębiania, 16h+8h / 24h albo 12h+12h) spełnia
# wyłącznie "Rotacja służby 24/7", podpięta pod ten sam checkbox 24/7. Obsadę
# kafelków round-clock wymusza tylko profil Dino, a razem z rotacją służby
# obie bramy blokowały sobie nawzajem wszystkie zmiany (generator bez
# rozwiązania). Kod zostaje - True przywraca pole (też w
# ui/config_dialog.py, który importuje tę stałą).
ROUND_CLOCK_UI_ENABLED = False


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
    LocationConfig.get_night_shift_hours()) oraz progi obsady (self.thresholds_container),
    które faktycznie nadpisują generator dla pracowników przypisanych do tej
    lokalizacji (patrz logic/generator/base_specs.py::_build_max_consecutive
    i logic/generator/generic_rules.py::build_min_staff_with_role) - schowane
    na prośbę klienta (patrz thresholds_container.hide() niżej), ale wciąż w
    pełni działające, żeby nie zgubić już zapisanych nadpisań per-lokalizacja.
    Na końcu: edytor "Rotacja służby 24/7" (patrz ui/duty_rotation_editor.py) -
    jedyne miejsce w UI, w którym da się skonfigurować LocationConfig.duty_rotation
    dla nowej albo istniejącej lokalizacji."""

    def __init__(
        self, on_remove, name="", open_hours=None, is_24_7=False,
        max_consecutive_days=None, rule_defs=(), rule_overrides=None,
        original_key=None, duty_rotation=None, round_clock_start_hour=None,
        closed_on_public_holidays=True,
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
        # Długa nazwa lokalizacji "rozjeżdżała" lewy pasek boczny i przyciski
        # menu w main_window.py (patrz też ui/marquee_text.py) - twardy limit
        # tutaj, żeby nie dało się jej w ogóle wpisać.
        self.name_edit.setMaxLength(35)
        top.addWidget(self.name_edit, 1)

        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setObjectName("dangerButton")
        self.remove_btn.clicked.connect(lambda: on_remove(self))
        top.addWidget(self.remove_btn)
        outer.addLayout(top)

        is_24_7_row = QHBoxLayout()
        self.is_24_7_check = QCheckBox("Działalność całodobowa (24/7)")
        self.is_24_7_check.setChecked(bool(is_24_7))
        self.is_24_7_check.toggled.connect(self._on_24_7_toggled)
        is_24_7_row.addWidget(self.is_24_7_check)
        is_24_7_row.addStretch()

        # Domyślnie zwinięte (self._hours_expanded=False) dla czytelności
        # listy lokalizacji - widoczne tylko gdy 24/7 wyłączone, bo dla 24/7
        # cały tydzień jest i tak zawsze 00:00-23:45 (patrz _on_24_7_toggled).
        self._hours_expanded = False
        self.toggle_hours_btn = QPushButton("Rozwiń")
        self.toggle_hours_btn.setObjectName("secondaryButton")
        self.toggle_hours_btn.clicked.connect(self._toggle_hours_expanded)
        is_24_7_row.addWidget(self.toggle_hours_btn)
        outer.addLayout(is_24_7_row)

        # Automatyczne zamknięcie w polskie święta ustawowe (biblioteka
        # `holidays`, patrz logic/utils/holidays_pl.py) - niezależne od 24/7,
        # bo dotyczy zarówno zwykłych godzin otwarcia, jak i rotacji służby
        # (LocationConfig.duty_rotation w ogóle nie zna pojęcia "godziny
        # otwarcia" - patrz LocationConfig.is_closed_for_public_holiday()).
        # Domyślnie włączone - część placówek nie wymaga ochrony w święta,
        # część (np. obiekty krytyczne) zostaje mimo to 24/7.
        self.closed_on_public_holidays_check = QCheckBox("Zamknięte w polskie święta ustawowe")
        self.closed_on_public_holidays_check.setChecked(bool(closed_on_public_holidays))
        self.closed_on_public_holidays_check.setToolTip(
            "Gdy zaznaczone, ta lokalizacja jest automatycznie traktowana "
            "jako nieczynna (grafik i generator) w polskie święta ustawowo "
            "wolne od pracy - obowiązuje też dla rotacji 24/7. Odznacz dla "
            "obiektów chronionych bez przerwy, również w święta. Ręczne "
            "nadpisanie konkretnego dnia (dwuklik na nagłówku w grafiku) "
            "zawsze wygrywa."
        )
        outer.addWidget(self.closed_on_public_holidays_check)

        self.hours_editor = WeeklyHoursEditor(open_hours)
        self.hours_editor.setEnabled(not is_24_7)
        outer.addWidget(self.hours_editor)

        # "Rotacja służby 24/7" podpięta wprost pod checkbox 24/7 wyżej,
        # zamiast osobnego przełącznika (decyzja z użytkownikiem, patrz
        # docstring DutyRotationEditor) - dla lokalizacji czynnej całodobowo
        # zwykłe godziny otwarcia i tak nie mają znaczenia (cały tydzień
        # 00:00-23:45), więc to miejsce zajmuje konfiguracja zmian rotacji.
        self.duty_rotation_editor = DutyRotationEditor(duty_rotation)
        outer.addWidget(self.duty_rotation_editor)

        # "Godzina rozpoczęcia" rotacji całodobowej - tylko dla 24/7 (patrz
        # LocationConfig.round_clock_start_hour). Domyślnie wyłączone (żeby
        # nie zmieniać zachowania istniejących lokalizacji 24/7 przy samym
        # otwarciu tego okna) - zaznaczenie włącza generator dzielący dobę
        # na kolejne zmiany zamiast dotychczasowego OPEN/CLOSE, które nie
        # jest w stanie obsadzić środka doby przy 24h otwarcia.
        self.round_clock_container = QWidget()
        round_clock_row = QHBoxLayout(self.round_clock_container)
        round_clock_row.setContentsMargins(0, 0, 0, 0)
        self.round_clock_check = QCheckBox("Rotacja całodobowa - godzina rozpoczęcia:")
        self.round_clock_check.setChecked(ROUND_CLOCK_UI_ENABLED and round_clock_start_hour is not None)
        self.round_clock_check.toggled.connect(self._update_round_clock_visibility)
        round_clock_row.addWidget(self.round_clock_check)
        self.round_clock_start_input = TimeInputWidget()
        self.round_clock_start_input.set_time_str(round_clock_start_hour or "08:00")
        round_clock_row.addWidget(self.round_clock_start_input)
        round_clock_row.addStretch()
        outer.addWidget(self.round_clock_container)

        self.round_clock_hint = QLabel(
            "Włącz, żeby generator dzielił dobę na kolejne, następujące po "
            "sobie zmiany zaczynające się o podanej godzinie (np. 08:00 → "
            "08:00–16:00, 16:00–00:00, 00:00–08:00, i tak każdego dnia "
            "miesiąca), aż wypełni całą dobę. Bez tego środek doby zostaje "
            "bez obsady - zwykłe zmiany otwarcia/zamknięcia sięgają najwyżej "
            "ok. 1,5 h od godziny otwarcia/zamknięcia, więc przy 24h otwarcia "
            "zawsze zostaje kilkugodzinna luka. Lokalizacje z konkretnymi "
            "godzinami otwarcia (nie 24/7) działają bez żadnej zmiany."
        )
        self.round_clock_hint.setObjectName("quickInfoHint")
        self.round_clock_hint.setWordWrap(True)
        outer.addWidget(self.round_clock_hint)

        self._update_hours_visibility()
        self._update_round_clock_visibility()

        # "Progi obsady dla tej lokalizacji" schowane na prośbę klienta -
        # widgety zostają w pełni działające (constraints_overrides() niżej
        # nadal je czyta, więc istniejące nadpisania per-lokalizacja
        # zapisane w projekcie nie giną przy zapisie), tylko owinięte w
        # kontener .hide()owany, tym samym wzorcem co
        # ConfigDialog.facility_header/limits_tab.
        self.thresholds_container = QWidget()
        thresholds = QHBoxLayout(self.thresholds_container)
        thresholds.setContentsMargins(0, 0, 0, 0)
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
        outer.addWidget(self.thresholds_container)
        self.thresholds_container.hide()

    def _on_24_7_toggled(self, checked):
        if checked:
            self.hours_editor.set_hours({wd: ("00:00", "23:45") for wd in range(7)})
            # Placówka 24/7 z rotacją służby jest domyślnie chroniona także w
            # święta (decyzja użytkownika 2026-09-25) - użytkownik może to
            # potem świadomie zaznaczyć z powrotem.
            self.closed_on_public_holidays_check.setChecked(False)
        self.hours_editor.setEnabled(not checked)
        self._update_hours_visibility()
        if not checked:
            self.round_clock_check.setChecked(False)
        self._update_round_clock_visibility()

    def _toggle_hours_expanded(self):
        self._hours_expanded = not self._hours_expanded
        self._update_hours_visibility()

    def _update_hours_visibility(self):
        is_24_7 = self.is_24_7_check.isChecked()
        # Dla 24/7 cały tydzień jest zawsze 00:00-23:45 - nie ma czego
        # edytować, więc ani przycisk, ani sam edytor godzin się nie
        # pokazują - to miejsce zajmuje konfiguracja rotacji służby
        # (patrz DutyRotationEditor - podpięta wprost pod ten sam checkbox).
        self.toggle_hours_btn.setVisible(not is_24_7)
        self.hours_editor.setVisible(not is_24_7 and self._hours_expanded)
        self.toggle_hours_btn.setText("Zwiń" if self._hours_expanded else "Rozwiń")
        self.duty_rotation_editor.setVisible(is_24_7)

    def _update_round_clock_visibility(self):
        # Cała sekcja (checkbox + podpowiedź) istnieje tylko dla 24/7 - dla
        # zwykłej lokalizacji ten mechanizm nie ma zastosowania (patrz
        # LocationConfig.round_clock_start_hour) - i tylko gdy nie jest
        # ukryta (ROUND_CLOCK_UI_ENABLED).
        visible = ROUND_CLOCK_UI_ENABLED and self.is_24_7_check.isChecked()
        self.round_clock_container.setVisible(visible)
        self.round_clock_hint.setVisible(visible)
        self.round_clock_start_input.setVisible(self.round_clock_check.isChecked())

    def round_clock_start_hour_value(self) -> str | None:
        if (
            not ROUND_CLOCK_UI_ENABLED
            or not self.is_24_7_check.isChecked()
            or not self.round_clock_check.isChecked()
        ):
            return None
        return self.round_clock_start_input.get_time_str()

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
        QTimer.singleShot(0, self._maybe_show_tutorial)

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
            "całodobowo przez cały tydzień."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        scope_note = QLabel(month_scope_note(self.shop_config.year, self.shop_config.month))
        scope_note.setObjectName("quickInfoHint")
        scope_note.setWordWrap(True)
        root.addWidget(scope_note)

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
                duty_rotation=loc.duty_rotation,
                round_clock_start_hour=loc.round_clock_start_hour,
                closed_on_public_holidays=loc.closed_on_public_holidays,
            )

        self.add_btn = QPushButton("Dodaj lokalizację")
        self.add_btn.setObjectName("secondaryButton")
        # Godziny z zakładki Konfiguracja -> "Godziny otwarcia" jako punkt
        # startowy dla nowej lokalizacji (patrz hint tam) - i tak od razu
        # edytowalne osobno dla tej lokalizacji poniżej, zanim się zapisze.
        self.add_btn.clicked.connect(
            lambda: self._add_location_row(open_hours=dict(self.shop_config.open_hours))
        )
        outer.addWidget(self.add_btn)

        outer.addStretch()

        buttons = QDialogButtonBox()
        help_btn = QPushButton("Pomoc")
        help_btn.setObjectName("secondaryButton")
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        self.save_btn = QPushButton("Zapisz")
        self.save_btn.setObjectName("primaryButton")
        buttons.addButton(help_btn, QDialogButtonBox.HelpRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(self.save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        help_btn.clicked.connect(self._open_tutorial)
        root.addWidget(buttons)

    def _add_location_row(
        self, name="", open_hours=None, is_24_7=False,
        max_consecutive_days=None, rule_overrides=None, original_key=None,
        duty_rotation=None, round_clock_start_hour=None,
        closed_on_public_holidays=True,
    ):
        row = _LocationRow(
            self._remove_location_row, name, open_hours, is_24_7=is_24_7,
            max_consecutive_days=max_consecutive_days,
            rule_defs=self._location_rule_defs,
            rule_overrides=rule_overrides,
            original_key=original_key,
            duty_rotation=duty_rotation,
            round_clock_start_hour=round_clock_start_hour,
            closed_on_public_holidays=closed_on_public_holidays,
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

    def _build_tutorial_steps(self):
        first_row = self._location_rows[0] if self._location_rows else None
        steps = [
            TutorialStep(
                "Lokalizacje",
                "Tutaj zarządzasz osobnymi obiektami/placówkami w ramach tego "
                "projektu - każda ma własne godziny otwarcia.",
            ),
            TutorialStep(
                "Dodaj lokalizację",
                "Kliknij, żeby dodać kolejną placówkę do projektu.",
                target=self.add_btn,
            ),
        ]
        if first_row is not None:
            steps.append(TutorialStep(
                "Działalność całodobowa (24/7)",
                "Zaznacz, jeśli ta placówka ma ciągłą obsadę (np. ochrona) - "
                "godziny otwarcia znikają (nie mają tu znaczenia), a zamiast "
                "nich pojawia się konfiguracja rotacji służby: generator "
                "przydzieli wyłącznie zmiany pokrywające całą dobę. Podaj "
                "godzinę rozpoczęcia doby i godzinę podziału - każdego dnia "
                "będzie jedna zmiana 24h albo dwie zmiany.",
                target=first_row.is_24_7_check,
            ))
            if not first_row.is_24_7_check.isChecked():
                steps.append(TutorialStep(
                    "Godziny otwarcia",
                    "Przyciskiem „Rozwiń” pokażesz godziny osobno dla każdego dnia "
                    "tygodnia. Zaznacz „Nieczynne” przy dniu, w którym placówka nie "
                    "pracuje wcale.",
                    target=first_row.toggle_hours_btn,
                ))
        steps.append(TutorialStep(
            "Zapisz",
            "Zapisz zmiany, żeby zaczęły obowiązywać w grafiku i w generatorze.",
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
        if os.path.exists(LOCATIONS_TUTORIAL_FLAG):
            return

        def mark_seen():
            try:
                with open(LOCATIONS_TUTORIAL_FLAG, "w") as f:
                    f.write("seen")
            except OSError:
                pass

        self._start_tutorial(on_finished=mark_seen)

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
                    if not start or not end:
                        continue  # dzień oznaczony "Nieczynne"
                    if _parse_time(end) <= _parse_time(start):
                        day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                        raise ValueError(
                            f"Zamknięcie musi być później niż otwarcie tego samego dnia "
                            f"({day_names[wd]}) dla lokalizacji: {name}. Zmiany przechodzące "
                            "przez północ nie są jeszcze wspierane — dla działalności "
                            "całodobowej zaznacz \"24/7\"."
                        )

                duty_rotation = None
                if row.is_24_7_check.isChecked():
                    try:
                        duty_rotation = row.duty_rotation_editor.get_duty_rotation()
                    except ValueError as exc:
                        raise ValueError(f"Rotacja służby 24/7 dla lokalizacji „{name}”: {exc}") from exc

                loc = LocationConfig(
                    key=key, name=name,
                    open_hours=hours,
                    constraints=row.constraints_overrides(),
                    is_24_7=row.is_24_7_check.isChecked(),
                    duty_rotation=duty_rotation,
                    round_clock_start_hour=row.round_clock_start_hour_value(),
                    closed_on_public_holidays=row.closed_on_public_holidays_check.isChecked(),
                )
                old = self.shop_config.locations.get(row.original_key)
                if old is not None:
                    # Pola bez UI w tym oknie (dziedziny handlowe, święta,
                    # nadpisania dni) - zachowane bez zmian.
                    loc.trade_sundays = old.trade_sundays
                    loc.public_holidays = old.public_holidays
                    loc.day_overrides = old.day_overrides
                new_locations[key] = loc

            self.shop_config.locations = new_locations
        except Exception as exc:
            QMessageBox.critical(self, "Błąd konfiguracji lokalizacji", str(exc))
            return

        self.accept()
