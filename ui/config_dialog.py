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
from logic.utils.time_utils import month_scope_note
from ui.duty_rotation_editor import DutyRotationEditor
from ui.locations_dialog import round_clock_ui_enabled
from ui.time_input import TimeInputWidget
from ui.tutorial_overlay import TutorialOverlay, TutorialStep
from ui.profile_wizard_dialog import ProfileWizardDialog
from ui.weekly_hours_editor import WeeklyHoursEditor
from model.constraint_policy import ConstraintPolicy
from model.business_profile import DEFAULT_BUSINESS_TYPE, get_profile, visible_profiles
from model.location import normalize_duty_rotation
from release_channel import RELEASE_CHANNEL
from logic.generator.opening_hours_coverage import (
    DEFAULT_MAX_STAFF,
    MAX_STAFF_CONSTRAINT_KEY,
    MAX_STAFF_POLICY,
    profile_uses_opening_hours_model,
)

CONFIG_TUTORIAL_FLAG = "config_tutorial_seen.flag"


POLICY_OPTIONS = (
    ("Preferowane", ConstraintPolicy.PREFERRED),
    ("Wymagane", ConstraintPolicy.MANDATORY),
    ("Wyłączone", ConstraintPolicy.DISABLED),
)

# Wariant bez "Wymagane" - dla zasad, gdzie twardy wymóg ryzykowałby
# niewykonalność całego miesiąca (ten sam powód, dla którego priorytet
# "Umowa" w priority_hours_constraint.py też nigdy nie jest MANDATORY).
POLICY_OPTIONS_TWO_STATE = (
    ("Preferowane", ConstraintPolicy.PREFERRED),
    ("Wyłączone", ConstraintPolicy.DISABLED),
)
POLICY_TWO_STATE_NAMES = {"nominal_hours_no_umowa"}

# Jednozdaniowy opis każdego stanu (Wymagane/Preferowane/Wyłączone) - pokazywany
# jako tooltip przy najechaniu na opcję w rozwiniętej liście selektora zasady
# (patrz _apply_policy_state_tooltips niżej). {rule} podstawia nazwę zasady z
# policy_labels (np. "Odpoczynek 11 h"), więc tekst ma sens dla KAŻDEJ zasady,
# także tych dołożonych dynamicznie przez kreator profilu custom.
POLICY_STATE_TOOLTIPS = {
    ConstraintPolicy.MANDATORY: (
        "Wymagane: generator nigdy nie złamie zasady „{rule}” - jeśli się nie da "
        "jej spełnić, grafik się nie wygeneruje."
    ),
    ConstraintPolicy.PREFERRED: (
        "Preferowane: generator stara się spełnić zasadę „{rule}”, ale może ją "
        "naruszyć, gdy nie da się inaczej."
    ),
    ConstraintPolicy.DISABLED: (
        "Wyłączone: generator całkowicie ignoruje zasadę „{rule}”, jakby jej "
        "w ogóle nie było."
    ),
}


def _apply_policy_state_tooltips(selector: QComboBox, label: str) -> None:
    """Dopina do każdej opcji tego selektora (Wymagane/Preferowane/Wyłączone)
    tooltip tłumaczący, co ta konkretna zasada `label` robi w tym stanie -
    widoczny po najechaniu myszą na opcję w rozwiniętej liście. Dodatkowo
    tooltip samego (zamkniętego) selektora pokazuje opis aktualnie wybranego
    stanu i odświeża się przy zmianie."""
    for i in range(selector.count()):
        value = selector.itemData(i)
        template = POLICY_STATE_TOOLTIPS.get(value)
        if template:
            selector.setItemData(i, template.format(rule=label), Qt.ToolTipRole)

    def _update_widget_tooltip():
        template = POLICY_STATE_TOOLTIPS.get(selector.currentData())
        if template:
            selector.setToolTip(template.format(rule=label))

    selector.currentIndexChanged.connect(_update_widget_tooltip)
    _update_widget_tooltip()


def _rule_label_widget(label: str, description: str) -> QWidget:
    """Etykieta wiersza reguły (policy_form.addRow()) - nazwa reguły plus,
    gdy jest opis (BusinessProfile.policy_descriptions), ikonka "?" w kółku
    z tym opisem jako tooltip. To osobny tooltip od _apply_policy_state_tooltips
    wyżej: tamten tłumaczy co znaczy Wymagane/Preferowane/Wyłączone DLA tej
    reguły, ten tłumaczy, co reguła w ogóle ROBI (np. "Dostępność
    pracownika" -> "Nie przydziela pracownikowi zmian poza godzinami, w
    których zgłosił dostępność."). Brak opisu (nierozpoznana dynamiczna
    reguła profilu custom) = sama etykieta, bez ikonki."""
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    row.addWidget(QLabel(label + ":"))
    if description:
        badge = QLabel("?")
        badge.setFixedSize(16, 16)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            "QLabel { border: 1px solid #9ca3af; border-radius: 8px; "
            "color: #6b7280; font-size: 10px; font-weight: bold; }"
        )
        badge.setToolTip(description)
        row.addWidget(badge)
    row.addStretch()
    return host

# Zasady, których starsze projekty nie mają jeszcze zapisanych - brak wpisu
# ma znaczyć to samo co w generatorze (inaczej samo otwarcie i zapisanie
# Konfiguracji po cichu włączyłoby zasadę).
POLICY_MISSING_DEFAULTS = {
    "hours_equalization": ConstraintPolicy.DISABLED,
    # Zasada dodana po zapisaniu starszych projektów - brak wpisu generator
    # traktuje jako Wymaganą (logic/generator/opening_hours_coverage.py).
    "opening_hours_coverage": ConstraintPolicy.MANDATORY,
    # "Maks. obsada naraz" - brak wpisu = Preferowana (jak w generatorze).
    MAX_STAFF_POLICY: ConstraintPolicy.PREFERRED,
}

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
    def __init__(self, parent, shop_config, location_key=None):
        super().__init__(parent)
        self.shop_config = shop_config
        # Zakładka "Godziny otwarcia" edytuje godziny TEJ lokalizacji wprost
        # (dokładnie te same dane co Konfiguracja -> Lokalizacje), zamiast
        # osobnego, projektowego ShopConfig.open_hours - patrz _build_hours_tab/
        # _save(). location_key=None (np. stare wywołania/testy) -> fallback
        # na project-wide ShopConfig.open_hours jak dawniej.
        self.location = shop_config.locations.get(location_key) if location_key else None
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

        scope_note = QLabel(month_scope_note(self.shop_config.year, self.shop_config.month))
        scope_note.setObjectName("quickInfoHint")
        scope_note.setWordWrap(True)
        root.addWidget(scope_note)

        # Sekcja "Nazwa i Profil placówki" schowana dla Enyo - klient ma
        # dokładnie jedną placówkę (kilka lokalizacji w jej ramach, patrz
        # ui/locations_dialog.py) i jeden gotowy profil "Ochrona", więc nie
        # ma czego tu zmieniać (patrz też new_profile_btn/edit_profile_btn/
        # delete_profile_btn niżej, schowane tym samym wzorcem). Widgety i
        # cała logika zapisu zostają w pełni działające - tylko owinięte w
        # kontener .hide()owany, żeby nie tracić funkcjonalności na wypadek
        # powrotu do main.
        self.facility_header = QWidget()
        facility_header_layout = QVBoxLayout(self.facility_header)
        facility_header_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.facility_header)

        title = QLabel("Konfiguracja obiektu")
        title.setObjectName("sectionLabel")
        facility_header_layout.addWidget(title)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nazwa placówki:"))
        self.name_edit = QLineEdit(self.shop_config.name)
        self.name_edit.setPlaceholderText("np. Moja Firma")
        name_row.addWidget(self.name_edit, 1)
        facility_header_layout.addLayout(name_row)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profil działalności:"))
        self.business_type_selector = QComboBox()
        self.business_type_selector.setMinimumWidth(220)
        self._reload_business_type_selector()
        self.business_type_selector.currentIndexChanged.connect(self._on_business_type_changed)
        profile_row.addWidget(self.business_type_selector)

        # Zarządzanie profilami (tworzenie/edycja/kasowanie) schowane na
        # kanale Enyo - klient ma dokładnie jeden, gotowy profil "Ochrona"
        # i nie zarządza profilami przez UI (patrz ENYO_ONLY_CHANGES.md).
        # Na pozostałych kanałach (domyślnie "dino") guziki zostają widoczne
        # jak przed scaleniem z integration/enyo-only.
        show_profile_management = RELEASE_CHANNEL != "enyo"

        new_profile_btn = QPushButton("Nowy profil...")
        new_profile_btn.setObjectName("secondaryButton")
        new_profile_btn.clicked.connect(self._open_profile_wizard)
        new_profile_btn.setVisible(show_profile_management)
        profile_row.addWidget(new_profile_btn)

        self.edit_profile_btn = QPushButton("Edytuj profil...")
        self.edit_profile_btn.setObjectName("secondaryButton")
        self.edit_profile_btn.clicked.connect(self._open_profile_wizard_for_edit)
        self.edit_profile_btn.setVisible(show_profile_management)
        profile_row.addWidget(self.edit_profile_btn)

        self.delete_profile_btn = QPushButton("Usuń profil...")
        self.delete_profile_btn.setObjectName("dangerButton")
        self.delete_profile_btn.clicked.connect(self._delete_current_profile)
        self.delete_profile_btn.setVisible(show_profile_management)
        profile_row.addWidget(self.delete_profile_btn)

        self._sync_edit_profile_button()

        profile_row.addStretch()
        facility_header_layout.addLayout(profile_row)

        # Domyślnie puste - _build_sundays_tab() nadpisuje tylko gdy profil
        # faktycznie ma kalendarz handlowy (patrz niżej), a _save() zawsze
        # czyta ten słownik.
        self.sunday_checks = {}

        self.tabs = QTabWidget()
        tabs = self.tabs
        root.addWidget(tabs, 1)

        # Indeksy zakładek śledzone jawnie (zamiast zakładanych na sztywno w
        # _build_tutorial_steps()), bo "Niedziele handlowe" dodaje się
        # warunkowo - sztywne indeksy 0/1/2/3 rozjeżdżałyby się z rzeczywistą
        # zawartością self.tabs i celowały by w złą zakładkę.
        self._tab_index_hours = tabs.addTab(self._build_hours_tab(), "Godziny otwarcia")
        self._tab_index_sundays = None
        if self.profile.uses_trade_calendar:
            self._tab_index_sundays = tabs.addTab(self._build_sundays_tab(), "Niedziele handlowe")
        self.limits_tab = self._build_limits_tab()
        self._tab_index_limits = tabs.addTab(self.limits_tab, "Limity")
        self._tab_index_generator = tabs.addTab(self._build_generator_rules_tab(), "Zasady generatora")

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

        # Poniżej: self.is_24_7_check/duty_rotation_editor/round_clock_*
        # istnieją tylko gdy self.location is not None - to okno traktuje
        # tę zakładkę dokładnie jak wiersz tej samej lokalizacji w oknie
        # Lokalizacje (ui/locations_dialog.py::_LocationRow, na życzenie
        # użytkownika) - te same widgety, ta sama logika widoczności i
        # zapisu, żeby nie trzeba było przełączać się między dwoma oknami
        # dla tej samej lokalizacji. Bez odpowiednika "Usuń"/nazwy (te
        # zmieniają tożsamość lokalizacji, nie jej godziny/rotację) i bez
        # przycisku zwiń/rozwiń dla godzin (sensowny tylko przy długiej
        # LIŚCIE lokalizacji w Lokalizacje, nie w tym jednolokalizacyjnym
        # widoku).
        self.is_24_7_check = None
        if self.location is not None:
            location_label = QLabel(f"Edytujesz godziny otwarcia w placówce {self.location.name}")
            location_label.setObjectName("sectionLabel")
            outer.addWidget(location_label)

            # Ten sam widget/tooltip co ui/locations_dialog.py::_LocationRow -
            # patrz LocationConfig.is_closed_for_public_holiday(). Nad "24/7"
            # niżej (na życzenie użytkownika, 2026-09-26, dla czytelności).
            self.closed_on_public_holidays_check = QCheckBox("Zamknięte w polskie święta ustawowe")
            self.closed_on_public_holidays_check.setChecked(self.location.closed_on_public_holidays)
            self.closed_on_public_holidays_check.setToolTip(
                "Gdy zaznaczone, ta lokalizacja jest automatycznie traktowana "
                "jako nieczynna (grafik i generator) w polskie święta ustawowo "
                "wolne od pracy - obowiązuje też dla rotacji 24/7. Odznacz dla "
                "obiektów chronionych bez przerwy, również w święta. Ręczne "
                "nadpisanie konkretnego dnia (dwuklik na nagłówku w grafiku) "
                "zawsze wygrywa."
            )
            outer.addWidget(self.closed_on_public_holidays_check)

            self.is_24_7_check = QCheckBox("Działalność całodobowa (24/7)")
            self.is_24_7_check.setChecked(self.location.is_24_7)
            self.is_24_7_check.toggled.connect(self._on_hours_tab_24_7_toggled)
            outer.addWidget(self.is_24_7_check)

        hours_source = self.location.open_hours if self.location is not None else self.shop_config.open_hours
        self.hours_editor = WeeklyHoursEditor(hours_source)
        outer.addWidget(self.hours_editor)

        # "Działalność całodobowa: ustaw np. 00:00-23:45" (dawna treść tej
        # podpowiedzi) usunięte - to była instrukcja obejścia sprzed
        # dodania prawdziwego checkboxa 24/7 wyżej, dziś nieaktualna.
        self.hours_hint = QLabel(
            "Godziny pracy dla pojedynczego dnia możesz zmienić ręcznie, "
            "klikając dwukrotnie na nagłówek tego dnia w grafiku (np. „Wt 22”)."
        )
        self.hours_hint.setObjectName("mutedHint")
        self.hours_hint.setWordWrap(True)
        outer.addWidget(self.hours_hint)

        if self.location is not None:
            # Rotacja służby 24/7 - ten sam DutyRotationEditor i ten sam
            # wzorzec podpięcia pod checkbox 24/7 co w Lokalizacje.
            self.duty_rotation_editor = DutyRotationEditor(self.location.duty_rotation)
            outer.addWidget(self.duty_rotation_editor)

            # "Godzina rozpoczęcia" rotacji całodobowej (LocationConfig.
            # round_clock_start_hour) - identyczne widgety/teksty co
            # ui/locations_dialog.py::_LocationRow.
            self.round_clock_container = QWidget()
            round_clock_row = QHBoxLayout(self.round_clock_container)
            round_clock_row.setContentsMargins(0, 0, 0, 0)
            self.round_clock_check = QCheckBox("Rotacja całodobowa - godzina rozpoczęcia:")
            self.round_clock_check.setChecked(
                round_clock_ui_enabled(self.shop_config.business_type)
                and self.location.round_clock_start_hour is not None
            )
            self.round_clock_check.toggled.connect(self._update_hours_tab_round_clock_visibility)
            round_clock_row.addWidget(self.round_clock_check)
            self.round_clock_start_input = TimeInputWidget()
            self.round_clock_start_input.set_time_str(self.location.round_clock_start_hour or "08:00")
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

            self._update_hours_tab_visibility()
            self._update_hours_tab_round_clock_visibility()

        outer.addStretch()
        return page

    def _on_hours_tab_24_7_toggled(self, checked):
        """Ten sam wzorzec co _LocationRow._on_24_7_toggled w
        ui/locations_dialog.py - wpisuje 00:00-23:45 wprost do edytora
        godzin, więc _save() (który po prostu czyta hours_editor.get_hours())
        nie potrzebuje żadnej osobnej logiki dla 24/7."""
        if checked:
            self.hours_editor.set_hours({wd: ("00:00", "23:45") for wd in range(7)})
            # Patrz _LocationRow._on_24_7_toggled - 24/7 domyślnie chronione
            # także w święta.
            self.closed_on_public_holidays_check.setChecked(False)
        self.hours_editor.setEnabled(not checked)
        self._update_hours_tab_visibility()
        if not checked:
            self.round_clock_check.setChecked(False)
        self._update_hours_tab_round_clock_visibility()

    def _update_hours_tab_visibility(self):
        is_24_7 = self.is_24_7_check.isChecked()
        self.hours_editor.setVisible(not is_24_7)
        self.duty_rotation_editor.setVisible(is_24_7)

    def _update_hours_tab_round_clock_visibility(self):
        # Tylko dla Dino - patrz ui/locations_dialog.py::round_clock_ui_enabled().
        visible = round_clock_ui_enabled(self.shop_config.business_type) and self.is_24_7_check.isChecked()
        self.round_clock_container.setVisible(visible)
        self.round_clock_hint.setVisible(visible)
        self.round_clock_start_input.setVisible(self.round_clock_check.isChecked())

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
        form_solver.addRow("Limit czasu generatora (cały projekt):", self.solver_time_limit)
        advanced_layout.addLayout(form_solver)

        # Wszystko niżej - tryby zasad i ustawienia generatora - zapisywane
        # per placówka (LocationConfig.constraint_policies/.constraints), gdy
        # okno otwarto dla placówki: generator bierze je przy generowaniu jej
        # grafiku (ShopConfig.with_location_settings). Bez placówki (stare
        # wywołania/testy) - ustawienia projektu, jak dawniej.
        if self.location is not None:
            location_label = QLabel(f"PLACÓWKA: {self.location.name}")
            location_label.setObjectName("groupLabel")
            advanced_layout.addWidget(location_label)
            location_hint = QLabel(
                "Zasady i ustawienia poniżej obowiązują tylko w tej placówce - "
                "każda placówka ma własne (wybierz ją w programie, żeby je zmienić)."
            )
            location_hint.setObjectName("mutedHint")
            location_hint.setWordWrap(True)
            advanced_layout.addWidget(location_hint)
            settings = self.location.constraints
            policies = self.shop_config.effective_constraint_policies(self.location.key)
        else:
            settings = self.shop_config.constraints
            policies = self.shop_config.constraint_policies

        location_form = QFormLayout()

        # "Maks. obsada naraz" (profil Ochrony, placówki z godzinami otwarcia
        # - patrz logic/generator/opening_hours_coverage.py): liczba osób tu,
        # tryb (Wymagana/Preferowana/Wyłączona) w siatce zasad niżej. Tutaj,
        # a nie w zakładce "Limity", bo ta w tej wersji nie jest pokazywana.
        # Widżet tworzony zawsze (_save() go czyta), w formularzu tylko dla
        # profili, które tej zasady używają.
        self.max_staff = QSpinBox()
        self.max_staff.setRange(1, 10)
        self.max_staff.setFixedWidth(90)
        self.max_staff.setValue(int(settings.get(
            MAX_STAFF_CONSTRAINT_KEY, self.shop_config.constraints.get(MAX_STAFF_CONSTRAINT_KEY, DEFAULT_MAX_STAFF)
        )))
        self.max_staff.setToolTip(
            "Ile osób z jednej placówki z godzinami otwarcia (bez rotacji 24/7) "
            "może pracować jednocześnie. Tryb ustawiasz przy zasadzie "
            "„Maks. obsada naraz” niżej."
        )
        if profile_uses_opening_hours_model(self.shop_config.business_type):
            location_form.addRow("Maks. osób naraz w placówce:", self.max_staff)

        # „Dni pod rząd” - limit dni placówki (ten sam co w oknie Lokalizacje),
        # tryb przy zasadzie „Dni pod rząd” niżej; np. 2-osobowa placówka:
        # 1 dzień + Wymagane = zmiany na przemian.
        self.location_max_consecutive = None
        if self.location is not None:
            self.location_max_consecutive = QSpinBox()
            self.location_max_consecutive.setRange(1, 14)
            self.location_max_consecutive.setFixedWidth(90)
            self.location_max_consecutive.setValue(self.location.constraints.get("max_consecutive_days", 4))
            self.location_max_consecutive.setToolTip(
                "1 dzień = nikt nie pracuje dwa dni pod rząd, czyli przy dwóch "
                "osobach zmiany na przemian. Tryb ustawiasz przy zasadzie „Dni pod "
                "rząd” niżej - przy „Wymagane” urlop albo L4 jednej z dwóch osób "
                "dłuższe niż 1 dzień daje brak rozwiązania."
            )
            location_form.addRow("Maks. dni pracy pod rząd:", self.location_max_consecutive)
        advanced_layout.addLayout(location_form)

        # QFormLayout zamiast ręcznie łamanej na dwie kolumny QGridLayout
        # (poprzednia wersja pakowała wiersze w dwie pary kolumn obok siebie,
        # żeby zmieścić więcej w pionie - przy dłuższych etykietach, zwłaszcza
        # dynamicznie generowanych regułach profili custom, kolumny się
        # rozjeżdżały i całość wyglądała krzywo). Jedna kolumna, jak reszta
        # tej zakładki (form_solver wyżej) - zawsze równo wyrównana, a
        # dodatkową wysokość i tak pochłania scroll.
        policy_form = QFormLayout()
        policy_form.setHorizontalSpacing(12)
        policy_form.setVerticalSpacing(7)
        self.policy_selectors = {}
        policy_labels = self.profile.policy_labels

        for policy_name, label in policy_labels:
            selector = QComboBox()
            selector.setMinimumWidth(125)
            options = POLICY_OPTIONS_TWO_STATE if policy_name in POLICY_TWO_STATE_NAMES else POLICY_OPTIONS
            for text, value in options:
                selector.addItem(text, value)
            current_policy = policies.get(
                policy_name, POLICY_MISSING_DEFAULTS.get(policy_name, ConstraintPolicy.PREFERRED)
            )
            if policy_name == "balance" and current_policy == ConstraintPolicy.MANDATORY:
                # MANDATORY zrobiłby grafik niewykonalnym za każdym razem, gdy
                # nie da się trafić dokładnie w bilans - nigdy nie pokazujemy
                # ani nie zachowujemy tej wartości. DISABLED (np. profil
                # ochrony, gdzie klient świadomie nie chce bilansu wcale)
                # zostaje nietknięty.
                current_policy = ConstraintPolicy.PREFERRED
            if policy_name in POLICY_TWO_STATE_NAMES and current_policy == ConstraintPolicy.MANDATORY:
                # Ta zasada nie ma trybu "Wymagane" w ogóle (patrz
                # POLICY_OPTIONS_TWO_STATE) - plik zapisany/edytowany poza
                # tym oknem mógłby mimo to mieć tę wartość; traktujemy jak
                # Preferowane zamiast zostawić selector bez zaznaczenia.
                current_policy = ConstraintPolicy.PREFERRED
            selector.setCurrentIndex(selector.findData(current_policy))
            _apply_policy_state_tooltips(selector, label)
            if policy_name == "balance":
                selector.setEnabled(False)
                selector.setToolTip(
                    "Bilans godzin edytowalny tylko programowo (np. przy "
                    "definiowaniu profilu) - tu tylko podgląd."
                )
            description = self.profile.policy_descriptions.get(policy_name, "")
            policy_form.addRow(_rule_label_widget(label, description), selector)
            self.policy_selectors[policy_name] = selector

        self.rest_11h_mode_selector = QComboBox()
        self.rest_11h_mode_selector.setMinimumWidth(125)
        for text, value in REST_11H_MODE_OPTIONS:
            self.rest_11h_mode_selector.addItem(text, value)
        current_mode = settings.get("rest_11h_mode", self.shop_config.constraints.get("rest_11h_mode", "standard"))
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
        policy_form.addRow("Tryb liczenia odpoczynku 11h:", self.rest_11h_mode_selector)

        advanced_layout.addLayout(policy_form)

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
        steps = [
            TutorialStep(
                "Konfiguracja obiektu",
                "Tutaj ustawiasz zasady, według których generator układa grafik: "
                "godziny otwarcia i zasady generatora.",
            ),
            TutorialStep(
                "Godziny otwarcia",
                "Ta zakładka edytuje wprost godziny otwarcia aktualnie wybranej "
                "lokalizacji (te same dane co w oknie Lokalizacje) - osobno dla "
                "każdego dnia tygodnia. Dzień możesz też oznaczyć „Nieczynne”."
                if self.location is not None else
                "Ustaw godziny pracy obiektu osobno dla każdego dnia tygodnia.",
                target=self.tabs,
                on_show=lambda: self.tabs.setCurrentIndex(self._tab_index_hours),
            ),
        ]
        if self._tab_index_sundays is not None:
            steps.append(TutorialStep(
                "Niedziele handlowe",
                "Zaznacz, które niedziele w tym miesiącu są handlowe — tylko one "
                "będą uwzględnione przy generowaniu grafiku.",
                target=self.tabs,
                on_show=lambda: self.tabs.setCurrentIndex(self._tab_index_sundays),
            ))
        steps.append(TutorialStep(
            "Limity",
            "Maksymalna liczba dni pod rząd, standardowy wymiar zmiany dla "
            "pełnego etatu i dodatkowe flagi (np. wymuszenie 8h 30 min) - "
            "wartości domyślne dla całego projektu.",
            target=self.max_consecutive,
            on_show=lambda: self.tabs.setCurrentIndex(self._tab_index_limits),
        ))
        steps.append(TutorialStep(
            "Limit czasu generatora",
            "Ile czasu solver ma na znalezienie grafiku. Dłuższy limit daje "
            "lepsze wyniki, ale wydłuża generowanie.",
            target=self.solver_time_limit,
            on_show=lambda: self.tabs.setCurrentIndex(self._tab_index_generator),
        ))
        steps.append(TutorialStep(
            "Zasady generatora",
            "Dla każdej reguły wybierz Wymagane (musi być spełniona) albo "
            "Preferowane (solver może ją naruszyć, jeśli nie ma innego wyjścia) — "
            "śmiało testuj różne ustawienia i dopasuj je do swojej placówki.",
            target=self.policy_selectors["rest_11h"],
            on_show=lambda: self.tabs.setCurrentIndex(self._tab_index_generator),
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
                if start_str and end_str:
                    start_qt = _parse_time(start_str)
                    end_qt = _parse_time(end_str)

                    # end < start = zmiana przechodząca przez północ (ten sam
                    # zapis co LocationConfig.duty_rotation/night_shift) -
                    # calc_end()/calc_start() (model/day_schedule.py) i
                    # DaySchedule.set_hours() już to poprawnie liczą. Tylko
                    # end == start zostaje odrzucone - niejednoznaczne: nie da
                    # się odróżnić zmiany zerowej długości od pełnej doby w
                    # tym modelu godzin HH:MM bez śledzenia daty (patrz "24h" w
                    # WeeklyHoursEditor - 00:00-23:45, nie 00:00-00:00).
                    if end_qt == start_qt:
                        day_names = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                        raise ValueError(
                            f"Godzina otwarcia i zamknięcia nie mogą być takie same ({day_names[wd]}). "
                            "Dla działalności całodobowej zaznacz \"24h\" przy tym dniu."
                        )

                target_hours = self.location.open_hours if self.location is not None else self.shop_config.open_hours
                target_hours[wd] = (start_str, end_str)  # (None, None) = dzień "Nieczynne"

            selected_sundays = {
                day for day, box in self.sunday_checks.items() if box.isChecked()
            }
            self.shop_config.trade_sundays = selected_sundays
            # "Niedziele handlowe" to pojęcie projektowe (profil Dino), nie
            # per-placówka - ten tab zawsze czyta/pisze self.shop_config,
            # niezależnie od self.location. Ale generator ustala dzień
            # handlowy per pracownik przez shop.get_location(emp)
            # (ShopConfig.get_location) - dla pracownika przypisanego do
            # istniejącej lokalizacji to osobne pole LocationConfig.
            # trade_sundays, seedowane z powyższego tylko RAZ przy tworzeniu
            # projektu (_default_location_from_shop) i odtąd nigdy więcej.
            # Bez tej synchronizacji zaznaczenie niedzieli tutaj nie miało
            # żadnego efektu na wygenerowany grafik (DINO_REGRESSION_AUDIT.md,
            # punkt 2).
            for loc in self.shop_config.locations.values():
                loc.trade_sundays = set(selected_sundays)

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
                # Ten jeden checkbox pokazuje tylko PIERWSZĄ znalezioną
                # konfigurację rotacji (patrz self._duty_rotation_configs
                # wyżej) - w projekcie z kilkoma lokalizacjami o RÓŻNYCH
                # only_12_24h wymuszenie tej samej wartości na WSZYSTKICH
                # potrafiło rzucić wyjątkiem i wywalić cały zapis Konfiguracji
                # (zgłoszenie użytkownika 2026-09-26), nawet gdy użytkownik
                # otwierał zakładkę zupełnie innej lokalizacji: lokalizacja z
                # only_12_24h=True w ogóle nie ma zapisanych weekday_long/
                # weekday_short (nie są jej potrzebne), więc wymuszenie na niej
                # only_12_24h=False zawsze łamie walidację "brakuje:
                # weekday_long, weekday_short". W przeciwieństwie do
                # self.shop_config.duty_rotation wyżej (jedyny obiekt, który
                # ten checkbox naprawdę reprezentuje - błąd tam ma zostać
                # zgłoszony użytkownikowi, patrz
                # test_unchecking_without_configured_weekday_windows_shows_an_error),
                # lokalizację, na którą ten checkbox nie pasuje, zostawiamy
                # bez zmian zamiast wywalać zapis reszty Konfiguracji.
                for loc in self.shop_config.locations.values():
                    if loc.duty_rotation:
                        merged = dict(loc.duty_rotation)
                        merged["only_12_24h"] = only_12_24h_value
                        try:
                            loc.duty_rotation = normalize_duty_rotation(merged)
                        except ValueError:
                            pass

            # Zakładka "Godziny otwarcia" traktowana tak samo jak wiersz tej
            # lokalizacji w oknie Lokalizacje (na życzenie użytkownika) - ten
            # sam odczyt co ui/locations_dialog.py::LocationsDialog._save().
            # Celowo PO bloku only_12_24h wyżej: to jest ostateczny, pełny
            # zapis stanu widgetów tej karty, ma pierwszeństwo przed
            # starszym, "globalnym" przełącznikiem only_12_24h powyżej,
            # gdyby oba dotyczyły tej samej lokalizacji.
            if self.location is not None and self.is_24_7_check is not None:
                self.location.set_24_7(self.is_24_7_check.isChecked())

                duty_rotation = None
                if self.is_24_7_check.isChecked():
                    try:
                        duty_rotation = self.duty_rotation_editor.get_duty_rotation()
                    except ValueError as exc:
                        raise ValueError(
                            f"Rotacja służby 24/7 dla lokalizacji „{self.location.name}”: {exc}"
                        ) from exc
                self.location.set_duty_rotation(duty_rotation)

                if (
                    round_clock_ui_enabled(self.shop_config.business_type)
                    and self.is_24_7_check.isChecked()
                    and self.round_clock_check.isChecked()
                ):
                    self.location.round_clock_start_hour = self.round_clock_start_input.get_time_str()
                else:
                    self.location.round_clock_start_hour = None

                self.location.closed_on_public_holidays = self.closed_on_public_holidays_check.isChecked()

            self.shop_config.constraints["solver_time_limit_seconds"] = self.solver_time_limit.value()

            # Zasady i ustawienia generatora z ustawień zaawansowanych - per
            # placówka, gdy okno otwarto dla placówki (patrz
            # _build_generator_rules_tab), inaczej projektowe jak dawniej.
            if self.location is not None:
                policies, settings = self.location.constraint_policies, self.location.constraints
                settings["max_consecutive_days"] = self.location_max_consecutive.value()
            else:
                policies, settings = self.shop_config.constraint_policies, self.shop_config.constraints
            settings[MAX_STAFF_CONSTRAINT_KEY] = self.max_staff.value()
            settings["rest_11h_mode"] = self.rest_11h_mode_selector.currentData()
            for policy_name, selector in self.policy_selectors.items():
                policies[policy_name] = ConstraintPolicy(selector.currentData())
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
