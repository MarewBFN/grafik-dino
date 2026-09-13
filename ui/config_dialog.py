import calendar
import os

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
)
from ui.time_input import TimeInputWidget
from ui.tutorial_overlay import TutorialOverlay, TutorialStep
from model.constraint_policy import ConstraintPolicy

CONFIG_TUTORIAL_FLAG = "config_tutorial_seen.flag"


POLICY_OPTIONS = (
    ("Preferowane", ConstraintPolicy.PREFERRED),
    ("Wymagane", ConstraintPolicy.MANDATORY),
    ("Wyłączone", ConstraintPolicy.DISABLED),
)

REST_11H_MODE_OPTIONS = (
    ("Standardowy (dokładny)", "standard"),
    ("Uproszczony (2 zmiany — szybszy)", "simplified"),
)

POLICY_LABELS = (
    ("rest_11h", "Odpoczynek 11 h"),
    ("open", "Obsada otwarcia"),
    ("close", "Obsada zamknięcia"),
    ("meat", "Mięso na zmianach"),
    ("meat_coverage", "Mięso przez cały dzień"),
    ("availability", "Dostępność pracownika"),
    ("no_night", "Zakaz pracy nocnej"),
    ("no_afternoon", "Zakaz pracy popołudniami"),
    ("monthly_hours", "Godziny miesięczne"),
    ("balance", "Bilans godzin"),
    ("max_consecutive", "Dni pod rząd"),
)

def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class ConfigDialog(QDialog):
    def __init__(self, parent, shop_config):
        super().__init__(parent)
        self.shop_config = shop_config
        self.setWindowTitle("Konfiguracja")
        self.setModal(True)
        self.resize(720, 560)

        # Wygląd (karty, checkboxy, kolory) pochodzi teraz w całości ze
        # wspólnego arkusza stylów aplikacji (ui/theme.py) — to okno nie
        # definiuje już własnego, osobnego setStyleSheet().
        self._build_ui()
        QTimer.singleShot(0, self._maybe_show_tutorial)

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Konfiguracja sklepu")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        self.tabs = QTabWidget()
        tabs = self.tabs
        root.addWidget(tabs, 1)

        tabs.addTab(self._build_hours_tab(), "Godziny otwarcia")
        tabs.addTab(self._build_sundays_tab(), "Niedziele handlowe")
        tabs.addTab(self._build_limits_tab(), "Limity")
        tabs.addTab(self._build_generator_rules_tab(), "Zasady generatora")

        buttons = QDialogButtonBox()
        help_btn = QPushButton("Pomoc")
        help_btn.setObjectName("secondaryButton")
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("secondaryButton")
        save_btn = QPushButton("Zapisz")
        save_btn.setObjectName("primaryButton")
        buttons.addButton(help_btn, QDialogButtonBox.HelpRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        buttons.addButton(save_btn, QDialogButtonBox.AcceptRole)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        help_btn.clicked.connect(self._open_tutorial)
        root.addWidget(buttons)

    def _build_hours_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        card = QFrame()
        card.setObjectName("configCard")
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self.open_edits = {}
        days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]

        for row, name in enumerate(days):
            label = QLabel(name)
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label, row, 0)

            start, end = self.shop_config.open_hours[row]

            start_edit = TimeInputWidget()
            start_edit.set_time_str(start)

            end_edit = TimeInputWidget()
            end_edit.set_time_str(end)

            layout.addWidget(start_edit, row, 1)
            layout.addWidget(QLabel("—"), row, 2, Qt.AlignCenter)
            layout.addWidget(end_edit, row, 3)

            self.open_edits[row] = (start_edit, end_edit)

        outer.addWidget(card)

        hint = QLabel(
            "Godziny pracy dla pojedynczego dnia możesz zmienić ręcznie, "
            "klikając dwukrotnie na nagłówek tego dnia w grafiku (np. „Wt 22”)."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        outer.addStretch()
        return page

    def _build_sundays_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        info = QLabel("Zaznacz niedziele handlowe w tym miesiącu:")
        info.setStyleSheet("color: #6b7280; margin-bottom: 5px;")
        layout.addWidget(info)

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
            card = QFrame()
            card.setObjectName("configCard")
            card_layout = QHBoxLayout(card)
            
            date_str = f"{day:02d}.{self.shop_config.month:02d}.{self.shop_config.year}"
            box = QCheckBox(f"Niedziela {date_str}")
            box.setCursor(Qt.PointingHandCursor)
            box.setChecked(day in self.shop_config.trade_sundays)
            
            self.sunday_checks[day] = box
            card_layout.addWidget(box)
            layout.addWidget(card)

        layout.addStretch()
        return page

    def _build_limits_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Sekcja: Ogólne ---
        gen_label = QLabel("LIMITY CZASU PRACY")
        gen_label.setObjectName("groupLabel")
        layout.addWidget(gen_label)

        form_gen = QFormLayout()
        self.max_consecutive = QSpinBox()
        self.max_consecutive.setRange(1, 14)
        self.max_consecutive.setFixedWidth(70)
        self.max_consecutive.setValue(self.shop_config.constraints.get("max_consecutive_days", 4))
        form_gen.addRow("Maksymalna liczba dni pod rząd:", self.max_consecutive)
        layout.addLayout(form_gen)

        # Jedna karta na obie flagi zamiast osobnej ramki na każdy checkbox.
        flags_card = QFrame()
        flags_card.setObjectName("configCard")
        flags_layout = QVBoxLayout(flags_card)
        flags_layout.setSpacing(10)

        self.force_fulltime_845 = QCheckBox("Wymuś 8h 30 min dla pracowników pełnoetatowych")
        self.force_fulltime_845.setCursor(Qt.PointingHandCursor)
        self.force_fulltime_845.setChecked(
            self.shop_config.constraints.get("force_fulltime_845", True)
        )
        flags_layout.addWidget(self.force_fulltime_845)

        self.hl_consecutive = QCheckBox("Podświetlaj przekroczenie limitu dni pod rząd")
        self.hl_consecutive.setCursor(Qt.PointingHandCursor)
        self.hl_consecutive.setChecked(
            self.shop_config.constraints.get("highlight_max_consecutive", False)
        )
        flags_layout.addWidget(self.hl_consecutive)

        layout.addWidget(flags_card)

        # --- Sekcja: Obsada ---
        staff_label = QLabel("MINIMALNA OBSADA PRACOWNIKÓW")
        staff_label.setObjectName("groupLabel")
        layout.addWidget(staff_label)

        form_staff = QFormLayout()
        self.min_open = QSpinBox()
        self.min_open.setRange(1, 10)
        self.min_open.setFixedWidth(70)
        self.min_open.setValue(self.shop_config.constraints.get("min_open_staff", 3))

        self.min_close = QSpinBox()
        self.min_close.setRange(1, 10)
        self.min_close.setFixedWidth(70)
        self.min_close.setValue(self.shop_config.constraints.get("min_close_staff", 3))

        form_staff.addRow("Pracowników na otwarciu (rano):", self.min_open)
        form_staff.addRow("Pracowników na zamknięciu (wieczór):", self.min_close)
        layout.addLayout(form_staff)

        layout.addStretch()
        return page

    def _build_generator_rules_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Sekcja: polityki constraintów generatora ---
        policy_label = QLabel("ZASADY GENERATORA")
        policy_label.setObjectName("groupLabel")
        layout.addWidget(policy_label)

        policy_info = QLabel(
            "Wymagane: reguła musi być spełniona. "
            "Preferowane: solver może ją naruszyć za karę."
        )
        policy_info.setStyleSheet("color: #6b7280; font-size: 11px;")
        policy_info.setWordWrap(True)
        layout.addWidget(policy_info)

        form_solver = QFormLayout()
        self.solver_time_limit = QSpinBox()
        self.solver_time_limit.setRange(5, 600)
        self.solver_time_limit.setSuffix(" s")
        self.solver_time_limit.setFixedWidth(90)
        self.solver_time_limit.setValue(
            self.shop_config.constraints.get("solver_time_limit_seconds", 60)
        )
        self.solver_time_limit.setToolTip(
            "Ile czasu solver ma na znalezienie grafiku, zanim zwróci najlepszy "
            "znaleziony wynik. Dłuższy limit daje lepsze rozwiązania, ale wydłuża "
            "generowanie — przydatne do zwiększenia na słabszym sprzęcie."
        )
        form_solver.addRow("Limit czasu generatora:", self.solver_time_limit)
        layout.addLayout(form_solver)

        policy_grid = QGridLayout()
        policy_grid.setHorizontalSpacing(12)
        policy_grid.setVerticalSpacing(7)
        self.policy_selectors = {}
        split_at = (len(POLICY_LABELS) + 1) // 2

        for index, (policy_name, label) in enumerate(POLICY_LABELS):
            row = index % split_at
            column = (index // split_at) * 2
            selector = QComboBox()
            selector.setMinimumWidth(125)
            for text, value in POLICY_OPTIONS:
                selector.addItem(text, value)
            current_policy = self.shop_config.constraint_policies.get(
                policy_name, ConstraintPolicy.PREFERRED
            )
            if policy_name == "balance":
                current_policy = ConstraintPolicy.PREFERRED
            selector.setCurrentIndex(selector.findData(current_policy))
            if policy_name == "balance":
                selector.setEnabled(False)
                selector.setToolTip("Bilans godzin zawsze pozostaje preferowany.")
            policy_grid.addWidget(QLabel(label + ":"), row, column)
            policy_grid.addWidget(selector, row, column + 1)
            self.policy_selectors[policy_name] = selector

        rest_row = len(POLICY_LABELS) % split_at
        rest_column = (len(POLICY_LABELS) // split_at) * 2
        self.rest_11h_mode_selector = QComboBox()
        self.rest_11h_mode_selector.setMinimumWidth(125)
        for text, value in REST_11H_MODE_OPTIONS:
            self.rest_11h_mode_selector.addItem(text, value)
        current_mode = self.shop_config.constraints.get("rest_11h_mode", "standard")
        self.rest_11h_mode_selector.setCurrentIndex(
            self.rest_11h_mode_selector.findData(current_mode)
        )
        self.rest_11h_mode_selector.setToolTip(
            "Standardowy: dokładne godziny zmian.\n"
            "Uproszczony: tylko klasa zmiany (rano/popołudnie) — po zmianie "
            "popołudniowej następny dzień może być tylko popołudniowy albo wolny. "
            "Szybszy na słabszym sprzęcie; sensowny tylko dla sklepów z dokładnie "
            "dwoma typami zmian."
        )
        policy_grid.addWidget(QLabel("Tryb liczenia odpoczynku 11h:"), rest_row, rest_column)
        policy_grid.addWidget(self.rest_11h_mode_selector, rest_row, rest_column + 1)

        layout.addLayout(policy_grid)

        hint = QLabel(
            "Te reguły możesz swobodnie zmieniać i testować, jak zachowuje się "
            "generator dla różnych ustawień — dopasuj je do specyfiki własnej "
            "placówki. Zmiana reguły nie wpływa na już wygenerowany grafik, "
            "dopóki nie klikniesz „Generuj grafik” ponownie."
        )
        hint.setObjectName("mutedHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()
        return page

    def _build_tutorial_steps(self):
        return [
            TutorialStep(
                "Konfiguracja sklepu",
                "Tutaj ustawiasz zasady, według których generator układa grafik: "
                "godziny otwarcia, niedziele handlowe, limity i zasady generatora.",
            ),
            TutorialStep(
                "Godziny otwarcia",
                "Ustaw godziny pracy sklepu osobno dla każdego dnia tygodnia.",
                target=self.tabs,
                on_show=lambda: self.tabs.setCurrentIndex(0),
            ),
            TutorialStep(
                "Niedziele handlowe",
                "Zaznacz, które niedziele w tym miesiącu są handlowe — tylko one "
                "będą uwzględnione przy generowaniu grafiku.",
                target=self.tabs,
                on_show=lambda: self.tabs.setCurrentIndex(1),
            ),
            TutorialStep(
                "Limity",
                "Maksymalna liczba dni z rzędu oraz minimalna liczba pracowników "
                "na otwarciu i zamknięciu sklepu.",
                target=self.tabs,
                on_show=lambda: self.tabs.setCurrentIndex(2),
            ),
            TutorialStep(
                "Limit czasu generatora",
                "Ile czasu solver ma na znalezienie grafiku. Dłuższy limit daje "
                "lepsze wyniki, ale wydłuża generowanie.",
                target=self.solver_time_limit,
                on_show=lambda: self.tabs.setCurrentIndex(3),
            ),
            TutorialStep(
                "Zasady generatora",
                "Dla każdej reguły wybierz Wymagane (musi być spełniona) albo "
                "Preferowane (solver może ją naruszyć, jeśli nie ma innego wyjścia) — "
                "śmiało testuj różne ustawienia i dopasuj je do swojej placówki.",
                target=self.policy_selectors["rest_11h"],
                on_show=lambda: self.tabs.setCurrentIndex(3),
            ),
        ]

    def _start_tutorial(self, on_finished=None):
        existing = getattr(self, "_tutorial_overlay", None)
        if existing is not None:
            existing.deleteLater()
        self._tutorial_overlay = TutorialOverlay(self, self._build_tutorial_steps(), on_finished=on_finished)
        self._tutorial_overlay.start()

    def _open_tutorial(self):
        self._start_tutorial()

    def _maybe_show_tutorial(self):
        if os.path.exists(CONFIG_TUTORIAL_FLAG):
            return

        def mark_seen():
            try:
                with open(CONFIG_TUTORIAL_FLAG, "w") as f:
                    f.write("seen")
            except OSError:
                pass

        self._start_tutorial(on_finished=mark_seen)

    def _save(self):
        try:
            for wd, (start_input, end_input) in self.open_edits.items():
                start_str = start_input.get_time_str()
                end_str = end_input.get_time_str()
                
                start_qt = _parse_time(start_str)
                end_qt = _parse_time(end_str)

                if end_qt <= start_qt:
                    day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                    raise ValueError(f"Zamknięcie musi być później niż otwarcie w dniu: {day_names[wd]}.")
                
                self.shop_config.open_hours[wd] = (start_str, end_str)

            self.shop_config.trade_sundays = {
                day for day, box in self.sunday_checks.items() if box.isChecked()
            }

            self.shop_config.constraints["max_consecutive_days"] = self.max_consecutive.value()
            self.shop_config.constraints["min_open_staff"] = self.min_open.value()
            self.shop_config.constraints["min_close_staff"] = self.min_close.value()
            self.shop_config.constraints["enforce_11h_rest"] = True
            self.shop_config.constraints["enforce_meat_coverage"] = True
            self.shop_config.constraints["force_fulltime_845"] = self.force_fulltime_845.isChecked()
            self.shop_config.constraints["highlight_max_consecutive"] = self.hl_consecutive.isChecked()
            self.shop_config.constraints["rest_11h_mode"] = self.rest_11h_mode_selector.currentData()
            self.shop_config.constraints["solver_time_limit_seconds"] = self.solver_time_limit.value()
            for policy_name, selector in self.policy_selectors.items():
                self.shop_config.constraint_policies[policy_name] = selector.currentData()
            self.shop_config.constraint_policies["balance"] = ConstraintPolicy.PREFERRED
        except Exception as exc:
            QMessageBox.critical(self, "Błąd konfiguracji", str(exc))
            return

        self.accept()
