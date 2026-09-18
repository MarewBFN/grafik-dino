import calendar
import os

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
)
from ui.tutorial_overlay import TutorialOverlay, TutorialStep
from ui.profile_wizard_dialog import ProfileWizardDialog
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.constraint_policy import ConstraintPolicy
from model.business_profile import DEFAULT_BUSINESS_TYPE, get_profile, visible_profiles
from model.location import normalize_duty_rotation

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

def _parse_time(value: str) -> QTime:
    if not value:
        return QTime(0, 0)
    hour, minute = value.split(":")
    return QTime(int(hour), int(minute))


class ConfigDialog(QDialog):
    def __init__(self, parent, shop_config):
        super().__init__(parent)
        self.shop_config = shop_config
        self.profile = get_profile(shop_config.business_type)
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

        title = QLabel("Konfiguracja obiektu")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nazwa placówki:"))
        self.name_edit = QLineEdit(self.shop_config.name)
        self.name_edit.setPlaceholderText("np. Moja Firma")
        name_row.addWidget(self.name_edit, 1)
        root.addLayout(name_row)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profil działalności:"))
        self.business_type_selector = QComboBox()
        self.business_type_selector.setMinimumWidth(220)
        self._reload_business_type_selector()
        self.business_type_selector.currentIndexChanged.connect(self._on_business_type_changed)
        profile_row.addWidget(self.business_type_selector)

        new_profile_btn = QPushButton("Nowy profil...")
        new_profile_btn.setObjectName("secondaryButton")
        new_profile_btn.clicked.connect(self._open_profile_wizard)
        profile_row.addWidget(new_profile_btn)

        self.edit_profile_btn = QPushButton("Edytuj profil...")
        self.edit_profile_btn.setObjectName("secondaryButton")
        self.edit_profile_btn.clicked.connect(self._open_profile_wizard_for_edit)
        profile_row.addWidget(self.edit_profile_btn)

        self.delete_profile_btn = QPushButton("Usuń profil...")
        self.delete_profile_btn.setObjectName("dangerButton")
        self.delete_profile_btn.clicked.connect(self._delete_current_profile)
        profile_row.addWidget(self.delete_profile_btn)

        self._sync_edit_profile_button()

        profile_row.addStretch()
        root.addLayout(profile_row)

        # Domyślnie puste - _build_sundays_tab() nadpisuje tylko gdy profil
        # faktycznie ma kalendarz handlowy (patrz niżej), a _save() zawsze
        # czyta ten słownik.
        self.sunday_checks = {}

        self.tabs = QTabWidget()
        tabs = self.tabs
        root.addWidget(tabs, 1)

        tabs.addTab(self._build_hours_tab(), "Godziny otwarcia")
        if self.profile.uses_trade_calendar:
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

    def _reload_business_type_selector(self):
        current = self.business_type_selector.currentData() or self.shop_config.business_type
        self.business_type_selector.blockSignals(True)
        self.business_type_selector.clear()
        for profile in visible_profiles():
            self.business_type_selector.addItem(profile.display_name, profile.key)
        idx = self.business_type_selector.findData(current)
        self.business_type_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.business_type_selector.blockSignals(False)
        self.business_type_selector.setEnabled(self.business_type_selector.count() > 1)

    def _on_business_type_changed(self):
        # Seed sensible default policies for a just-picked profile's rules,
        # without clobbering anything the user already tuned in a previous
        # session for it. The "Zasady generatora" tab itself was built for
        # whichever profile was active when this dialog opened and doesn't
        # re-render live - reopen Config after switching to edit these.
        from model.business_profile import get_custom_profile

        self._sync_edit_profile_button()

        business_type = self.business_type_selector.currentData()
        custom = get_custom_profile(business_type)
        if custom is None:
            return
        from logic.generator.custom_profile_wiring import default_policies
        for key, policy in default_policies(custom).items():
            self.shop_config.constraint_policies.setdefault(key, policy)

    def _on_advanced_toggled(self, checked):
        self.advanced_container.setVisible(checked)
        self.advanced_toggle_btn.setText(
            "Ukryj ustawienia zaawansowane" if checked else "Pokaż ustawienia zaawansowane"
        )

    def _sync_edit_profile_button(self):
        from model.business_profile import get_custom_profile

        business_type = self.business_type_selector.currentData()
        is_custom = get_custom_profile(business_type) is not None
        self.edit_profile_btn.setEnabled(is_custom)
        self.delete_profile_btn.setEnabled(is_custom)

    def _open_profile_wizard(self):
        wizard = ProfileWizardDialog(self)
        if wizard.exec() != QDialog.Accepted or not wizard.new_profile_key:
            return
        self._reload_business_type_selector()
        idx = self.business_type_selector.findData(wizard.new_profile_key)
        if idx >= 0:
            self.business_type_selector.setCurrentIndex(idx)

    def _open_profile_wizard_for_edit(self):
        from model.business_profile import get_custom_profile

        business_type = self.business_type_selector.currentData()
        custom = get_custom_profile(business_type)
        if custom is None:
            return

        wizard = ProfileWizardDialog(self, existing=custom)
        if wizard.exec() != QDialog.Accepted or not wizard.new_profile_key:
            return
        # Same key as before (the wizard reuses it on edit), so re-select it
        # mainly to refresh the display name shown in the dropdown.
        self._reload_business_type_selector()
        idx = self.business_type_selector.findData(wizard.new_profile_key)
        if idx >= 0:
            self.business_type_selector.setCurrentIndex(idx)

    def _delete_current_profile(self):
        from model.business_profile import get_custom_profile, unregister_custom_profile
        from model.custom_profile_store import delete_custom_profile

        business_type = self.business_type_selector.currentData()
        custom = get_custom_profile(business_type)
        if custom is None:
            return

        reply = QMessageBox.question(
            self,
            "Usuń profil",
            f"Usunąć profil \"{custom.display_name}\"? Projekty, które go już "
            "używają, przy następnym otwarciu przełączą się na profil Dino "
            "(nic w nich nie zostanie skasowane).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            delete_custom_profile(business_type)
        except OSError as exc:
            QMessageBox.critical(self, "Błąd", f"Nie udało się usunąć profilu: {exc}")
            return
        unregister_custom_profile(business_type)

        if self.shop_config.business_type == business_type:
            self.shop_config.business_type = DEFAULT_BUSINESS_TYPE

        self._reload_business_type_selector()
        self._sync_edit_profile_button()

    def _build_hours_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        self.hours_editor = WeeklyHoursEditor(self.shop_config.open_hours)
        outer.addWidget(self.hours_editor)

        hint = QLabel(
            "Godziny pracy dla pojedynczego dnia możesz zmienić ręcznie, "
            "klikając dwukrotnie na nagłówek tego dnia w grafiku (np. „Wt 22”).\n"
            "Działalność całodobowa: ustaw np. 00:00–23:45 (godziny "
            "przechodzące przez północ nie są jeszcze wspierane)."
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

        self.standard_daily_hours = QDoubleSpinBox()
        # 23.75h zamiast 24h: przy dosłownych 24h "koniec zmiany" liczony
        # jako godzina zegarowa wychodzi identyczny z "początkiem" (traci się
        # przeniesienie na kolejny dzień), więc zmiana byłaby nierozróżnialna
        # od pustej - patrz get_effective_daily_hours.
        self.standard_daily_hours.setRange(1.0, 23.75)
        self.standard_daily_hours.setSingleStep(0.25)
        self.standard_daily_hours.setSuffix(" h")
        self.standard_daily_hours.setFixedWidth(80)
        self.standard_daily_hours.setValue(self.shop_config.standard_daily_hours)
        self.standard_daily_hours.setToolTip(
            "Bazowy wymiar zmiany dla pracownika na pełnym etacie (1/1). "
            "Inne wymiary etatu to ułamek tej wartości."
        )
        form_gen.addRow("Standardowy wymiar zmiany (pełny etat):", self.standard_daily_hours)
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

        # --- Sekcja: Rotacja 24/7 (widoczna tylko gdy projekt jej faktycznie
        # używa - patrz LocationConfig.duty_rotation / ShopConfig.duty_rotation).
        # Na razie jedyny UI dla tego mechanizmu - reszta konfiguracji
        # (godziny okien) jest programowa, patrz demo/install_demo.py.
        self._duty_rotation_configs = [
            cfg for cfg in (
                self.shop_config.get_duty_rotation(),
                *(loc.get_duty_rotation() for loc in self.shop_config.locations.values()),
            )
            if cfg
        ]
        self.only_12_24h = None
        if self._duty_rotation_configs:
            duty_label = QLabel("ROTACJA 24/7")
            duty_label.setObjectName("groupLabel")
            layout.addWidget(duty_label)

            duty_card = QFrame()
            duty_card.setObjectName("configCard")
            duty_layout = QVBoxLayout(duty_card)

            self.only_12_24h = QCheckBox("Używaj tylko zmian 12/24h")
            self.only_12_24h.setCursor(Qt.PointingHandCursor)
            self.only_12_24h.setChecked(bool(self._duty_rotation_configs[0].get("only_12_24h")))
            self.only_12_24h.setToolTip(
                "Włączone: KAŻDY dzień tygodnia (nie tylko weekend) używa "
                "zmiany 24h albo dwóch zmian po 12h - zmiany 16h/8h w "
                "tygodniu nigdy się wtedy nie przydzielają."
            )
            duty_layout.addWidget(self.only_12_24h)
            layout.addWidget(duty_card)

        # --- Sekcja: Obsada (tylko dino_retail - min_open_staff/
        # min_close_staff to koncepty specyficzne dla tego profilu, patrz
        # model/constraints.py:223 - dla innych profili nie robią nic, więc
        # pokazywanie ich byłoby polem-widmo. Widżety tworzymy zawsze (żeby
        # nie trzeba było osobno zabezpieczać _save() poniżej, wzorem
        # self.only_12_24h), tylko nie trafiają do layoutu, gdy schowane -
        # patrz ENYO_ONLY_CHANGES.md.
        self.min_open = QSpinBox()
        self.min_open.setRange(1, 10)
        self.min_open.setFixedWidth(70)
        self.min_open.setValue(self.shop_config.constraints.get("min_open_staff", 3))

        self.min_close = QSpinBox()
        self.min_close.setRange(1, 10)
        self.min_close.setFixedWidth(70)
        self.min_close.setValue(self.shop_config.constraints.get("min_close_staff", 3))

        if self.shop_config.business_type == DEFAULT_BUSINESS_TYPE:
            staff_label = QLabel("MINIMALNA OBSADA PRACOWNIKÓW")
            staff_label.setObjectName("groupLabel")
            layout.addWidget(staff_label)

            form_staff = QFormLayout()
            form_staff.addRow("Pracowników na otwarciu (rano):", self.min_open)
            form_staff.addRow("Pracowników na zamknięciu (wieczór):", self.min_close)
            layout.addLayout(form_staff)

        layout.addStretch()
        return page

    def _build_generator_rules_tab(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        # policy_grid poniżej rośnie z liczbą reguł custom profilu (kreator
        # pozwala dodać dowolnie wiele) - bez scrolla ta zakładka (i przyciski
        # dialogu) wypadały poza okno. Wzorem sidebaru głównego okna
        # (ui/main_window.py::_build_left_panel).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page_layout.addWidget(scroll)

        host = QWidget()
        scroll.setWidget(host)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Sekcja: polityki constraintów generatora ---
        policy_label = QLabel("ZASADY GENERATORA")
        policy_label.setObjectName("groupLabel")
        layout.addWidget(policy_label)

        # Strojenie polityk/wag to coś, czego nowy użytkownik zwykle nie
        # potrzebuje na starcie (sensowne domyślne wartości już tam są) -
        # schowane za przełącznik, żeby zakładka nie przytłaczała przy
        # pierwszym otwarciu.
        self.advanced_toggle_btn = QPushButton("Pokaż ustawienia zaawansowane")
        self.advanced_toggle_btn.setObjectName("secondaryButton")
        self.advanced_toggle_btn.setCheckable(True)
        self.advanced_toggle_btn.setChecked(False)
        self.advanced_toggle_btn.toggled.connect(self._on_advanced_toggled)
        layout.addWidget(self.advanced_toggle_btn)

        self.advanced_container = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(15)
        self.advanced_container.setVisible(False)
        layout.addWidget(self.advanced_container)

        policy_info = QLabel(
            "Wymagane: reguła musi być spełniona. "
            "Preferowane: solver może ją naruszyć za karę."
        )
        policy_info.setStyleSheet("color: #6b7280; font-size: 11px;")
        policy_info.setWordWrap(True)
        advanced_layout.addWidget(policy_info)

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
        advanced_layout.addLayout(form_solver)

        policy_grid = QGridLayout()
        policy_grid.setHorizontalSpacing(12)
        policy_grid.setVerticalSpacing(7)
        self.policy_selectors = {}
        policy_labels = self.profile.policy_labels
        split_at = (len(policy_labels) + 1) // 2

        for index, (policy_name, label) in enumerate(policy_labels):
            row = index % split_at
            column = (index // split_at) * 2
            selector = QComboBox()
            selector.setMinimumWidth(125)
            for text, value in POLICY_OPTIONS:
                selector.addItem(text, value)
            current_policy = self.shop_config.constraint_policies.get(
                policy_name, ConstraintPolicy.PREFERRED
            )
            if policy_name == "balance" and current_policy == ConstraintPolicy.MANDATORY:
                # MANDATORY zrobiłby grafik niewykonalnym za każdym razem, gdy
                # nie da się trafić dokładnie w bilans - nigdy nie pokazujemy
                # ani nie zachowujemy tej wartości. DISABLED (np. profil
                # ochrony, gdzie klient świadomie nie chce bilansu wcale)
                # zostaje nietknięty.
                current_policy = ConstraintPolicy.PREFERRED
            selector.setCurrentIndex(selector.findData(current_policy))
            if policy_name == "balance":
                selector.setEnabled(False)
                selector.setToolTip(
                    "Bilans godzin edytowalny tylko programowo (np. przy "
                    "definiowaniu profilu) - tu tylko podgląd."
                )
            policy_grid.addWidget(QLabel(label + ":"), row, column)
            policy_grid.addWidget(selector, row, column + 1)
            self.policy_selectors[policy_name] = selector

        rest_row = len(policy_labels) % split_at
        rest_column = (len(policy_labels) // split_at) * 2
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
            "Szybszy na słabszym sprzęcie; sensowny tylko dla obiektów z dokładnie "
            "dwoma typami zmian."
        )
        policy_grid.addWidget(QLabel("Tryb liczenia odpoczynku 11h:"), rest_row, rest_column)
        policy_grid.addWidget(self.rest_11h_mode_selector, rest_row, rest_column + 1)

        advanced_layout.addLayout(policy_grid)

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
                "Konfiguracja obiektu",
                "Tutaj ustawiasz zasady, według których generator układa grafik: "
                "godziny otwarcia, niedziele handlowe, limity i zasady generatora.",
            ),
            TutorialStep(
                "Godziny otwarcia",
                "Ustaw godziny pracy obiektu osobno dla każdego dnia tygodnia.",
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
                "na otwarciu i zamknięciu.",
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
            self.shop_config.name = self.name_edit.text().strip()
            self.shop_config.business_type = self.business_type_selector.currentData()

            for wd, (start_str, end_str) in self.hours_editor.get_hours().items():
                start_qt = _parse_time(start_str)
                end_qt = _parse_time(end_str)

                if end_qt <= start_qt:
                    day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                    raise ValueError(
                        f"Zamknięcie musi być później niż otwarcie tego samego dnia ({day_names[wd]}). "
                        "Zmiany przechodzące przez północ nie są jeszcze wspierane — dla działalności "
                        "całodobowej ustaw np. 00:00–23:45."
                    )

                self.shop_config.open_hours[wd] = (start_str, end_str)

            self.shop_config.trade_sundays = {
                day for day, box in self.sunday_checks.items() if box.isChecked()
            }

            self.shop_config.constraints["max_consecutive_days"] = self.max_consecutive.value()
            self.shop_config.standard_daily_hours = self.standard_daily_hours.value()
            self.shop_config.constraints["min_open_staff"] = self.min_open.value()
            self.shop_config.constraints["min_close_staff"] = self.min_close.value()
            self.shop_config.constraints["enforce_11h_rest"] = True
            self.shop_config.constraints["enforce_meat_coverage"] = True
            self.shop_config.constraints["force_fulltime_845"] = self.force_fulltime_845.isChecked()
            self.shop_config.constraints["highlight_max_consecutive"] = self.hl_consecutive.isChecked()

            if self.only_12_24h is not None:
                only_12_24h_value = self.only_12_24h.isChecked()
                if self.shop_config.duty_rotation:
                    merged = dict(self.shop_config.duty_rotation)
                    merged["only_12_24h"] = only_12_24h_value
                    self.shop_config.duty_rotation = normalize_duty_rotation(merged)
                for loc in self.shop_config.locations.values():
                    if loc.duty_rotation:
                        merged = dict(loc.duty_rotation)
                        merged["only_12_24h"] = only_12_24h_value
                        loc.duty_rotation = normalize_duty_rotation(merged)
            self.shop_config.constraints["rest_11h_mode"] = self.rest_11h_mode_selector.currentData()
            self.shop_config.constraints["solver_time_limit_seconds"] = self.solver_time_limit.value()
            for policy_name, selector in self.policy_selectors.items():
                self.shop_config.constraint_policies[policy_name] = selector.currentData()
                # "balance" ma disabled selector (patrz konstrukcja wyżej) -
                # jego currentData() już poprawnie odzwierciedla wartość
                # ustawioną programowo (np. DISABLED dla profilu ochrony) i
                # nie trzeba (ani nie wolno) jej tu nadpisywać z powrotem na
                # PREFERRED, bo to by cofnęło taką decyzję przy każdym
                # otwarciu i zapisaniu Konfiguracji.
        except Exception as exc:
            QMessageBox.critical(self, "Błąd konfiguracji", str(exc))
            return

        self.accept()
