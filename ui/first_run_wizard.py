"""First-launch quick setup: instead of landing on an empty main window, a
brand-new install walks the user through a short, explained multi-step flow
that creates their first project (nazwa placówki, branża, cechy zależne od
branży, zasady generatora).

Wired in from MainWindow._maybe_show_first_run_wizard (see ui/main_window.py):
runs before the tutorial overlay, and its close (finished OR cancelled) is
what lets the tutorial start next - never both at once.

This dialog only *collects* the result (mirrors ui/new_project_dialog.py);
MainWindow._apply_first_run_wizard_result does the actual project creation,
same division of responsibility as NewProjectDialog/_open_new_project.
"""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from model.business_profile import get_custom_profile, get_profile
from model.constraint_policy import ConstraintPolicy
from ui.business_profile_picker import BusinessProfilePicker

POLICY_OPTIONS = (
    ("Preferowane", ConstraintPolicy.PREFERRED),
    ("Wymagane", ConstraintPolicy.MANDATORY),
    ("Wyłączone", ConstraintPolicy.DISABLED),
)

STEP_WELCOME, STEP_BASICS, STEP_BRANCH, STEP_FEATURES, STEP_RULES = range(5)


class FirstRunWizardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Szybka konfiguracja")
        self.setModal(True)
        self.resize(620, 560)

        # Wypełnione dopiero przez _finish() - None dopóki użytkownik nie
        # przejdzie (albo nie pominie) całego kreatora. Anulowanie w
        # dowolnym momencie zostawia to None, jak dziś przy braku projektu.
        self.result_name = ""
        self.result_year = date.today().year
        self.result_month = date.today().month
        self.result_business_type = None
        self.result_policy_overrides: dict[str, ConstraintPolicy] = {}
        self.completed = False

        self._step_index = STEP_WELCOME
        self._feature_checks: dict[str, QCheckBox] = {}
        self._policy_selectors: dict[str, QComboBox] = {}

        self._build_ui()
        self._show_step(STEP_WELCOME)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("Szybka konfiguracja")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self._build_step_welcome())
        self.stack.addWidget(self._build_step_basics())
        self.stack.addWidget(self._build_step_branch())
        self.stack.addWidget(self._build_step_features())
        self.stack.addWidget(self._build_step_rules())

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Wstecz")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.clicked.connect(self._go_back)
        nav.addWidget(self.back_btn)

        nav.addStretch()

        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        nav.addWidget(self.cancel_btn)

        self.skip_rules_btn = QPushButton("Pomiń — użyj wartości domyślnych")
        self.skip_rules_btn.setObjectName("secondaryButton")
        self.skip_rules_btn.clicked.connect(lambda: self._finish(apply_rule_overrides=False))
        nav.addWidget(self.skip_rules_btn)

        self.next_btn = QPushButton("Dalej")
        self.next_btn.setObjectName("primaryButton")
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.next_btn)

        root.addLayout(nav)

    @staticmethod
    def _wrap_page(*widgets) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)
        for w in widgets:
            layout.addWidget(w)
        layout.addStretch()
        return page

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("mutedHint")
        label.setWordWrap(True)
        return label

    def _build_step_welcome(self):
        heading = QLabel("Witaj w Grafiku!")
        heading.setObjectName("groupLabel")
        return self._wrap_page(
            heading,
            self._hint(
                "Zanim zaczniesz, skonfigurujmy Twoją pierwszą placówkę. To "
                "zajmie chwilę - w każdym kroku możesz cofnąć się i poprawić "
                "wybór, a na końcu zasady generatora można pominąć i "
                "dostosować później w menu \"Konfiguracja\"."
            ),
        )

    def _build_step_basics(self):
        heading = QLabel("Nazwa i okres")
        heading.setObjectName("groupLabel")

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("np. Dino Nowa Sól")
        form.addRow("Nazwa placówki:", self.name_edit)

        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(self.result_year)
        form.addRow("Rok:", self.year_spin)

        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(self.result_month)
        form.addRow("Miesiąc:", self.month_spin)

        form_widget = QWidget()
        form_widget.setLayout(form)

        return self._wrap_page(
            heading,
            self._hint("Nazwa jest tylko opisowa - pomaga odróżnić projekty, nie wpływa na generator."),
            form_widget,
        )

    def _build_step_branch(self):
        heading = QLabel("Branża")
        heading.setObjectName("groupLabel")

        self.profile_picker = BusinessProfilePicker(self)

        return self._wrap_page(
            heading,
            self._hint(
                "Wybierz profil działalności najbliższy tej placówce - decyduje "
                "o tym, jakie role, zasady i wiersze podsumowania zobaczysz w "
                "grafiku. \"Sklep (Dino)\" to gotowy, w pełni skonfigurowany "
                "profil retail; dla innej działalności (np. ochrona) użyj \"+ "
                "Nowa branża...\", żeby zbudować własny."
            ),
            self.profile_picker,
        )

    def _build_step_features(self):
        heading = QLabel("Cechy tej placówki")
        heading.setObjectName("groupLabel")
        self._features_hint = self._hint("")
        self._features_card = QFrame()
        self._features_card.setObjectName("configCard")
        self._features_layout = QVBoxLayout(self._features_card)
        return self._wrap_page(heading, self._features_hint, self._features_card)

    def _build_step_rules(self):
        heading = QLabel("Zasady generatora")
        heading.setObjectName("groupLabel")
        hint = self._hint(
            "Jak bardzo generator ma pilnować każdej zasady: \"Wymagane\" nigdy "
            "nie zostanie złamane (a jeśli to niemożliwe, generowanie się nie "
            "powiedzie), \"Preferowane\" generator stara się spełnić, ale ustąpi "
            "gdy trzeba, \"Wyłączone\" całkiem ignoruje. Możesz też pominąć ten "
            "krok i zostawić rozsądne wartości domyśle - zmienisz je później w "
            "\"Konfiguracja\" → \"Zasady generatora\"."
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        host = QWidget()
        scroll.setWidget(host)
        self._rules_layout = QGridLayout(host)
        self._rules_layout.setHorizontalSpacing(12)
        self._rules_layout.setVerticalSpacing(7)

        return self._wrap_page(heading, hint, scroll)

    # ------------------------------------------------------------------
    # Step transitions
    # ------------------------------------------------------------------

    def _current_profile(self):
        key = self.profile_picker.selected_key()
        return get_profile(key), key

    def _rebuild_features_step(self):
        while self._features_layout.count():
            item = self._features_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._feature_checks.clear()

        profile, _ = self._current_profile()
        policy_label_map = dict(profile.policy_labels)

        # Przełączalne cechy = wyróżnione role z RoleDef.linked_policy (dziś
        # tylko "meat" u Dino) - jedyny mechanizm, który realnie coś w
        # generatorze/UI włącza lub wyłącza. Role bez linked_policy (np.
        # kierowniczka) są zawsze dostępne i przypisuje się je per pracownik
        # w oknie "Pracownicy", więc nie mają tu przełącznika.
        seen = set()
        for role in profile.roles:
            if not role.linked_policy or role.linked_policy in seen:
                continue
            seen.add(role.linked_policy)
            label = policy_label_map.get(role.linked_policy, role.linked_policy)
            check = QCheckBox(f"{label}")
            check.setChecked(
                self.result_policy_overrides.get(role.linked_policy)
                != ConstraintPolicy.DISABLED
            )
            self._features_layout.addWidget(check)
            self._feature_checks[role.linked_policy] = check

        if self._feature_checks:
            self._features_hint.setText(
                "Odznacz to, czego ta placówka nie ma - odpowiadające role i "
                "zasady znikną z generatora i formularza pracownika."
            )
        else:
            self._features_hint.setText(
                "Ten profil nie ma dodatkowych przełączalnych cech - role "
                "specyficzne dla konkretnego pracownika (np. kierowniczka) "
                "przypisuje się później, w oknie \"Pracownicy\"."
            )
            none_label = QLabel("(brak)")
            none_label.setObjectName("mutedHint")
            self._features_layout.addWidget(none_label)

    def _rebuild_rules_step(self):
        while self._rules_layout.count():
            item = self._rules_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._policy_selectors.clear()

        profile, business_type = self._current_profile()
        custom = get_custom_profile(business_type)

        if custom is not None:
            from logic.generator.custom_profile_wiring import default_policies
            defaults = default_policies(custom)
        else:
            from model.shop_config import ShopConfig
            # dino_retail's real default policies live on a fresh ShopConfig
            # (model/shop_config.py::__init__) - reuse it instead of
            # duplicating that dict here.
            defaults = ShopConfig(self.result_year, self.result_month).constraint_policies

        for row, (policy_name, label) in enumerate(profile.policy_labels):
            selector = QComboBox()
            selector.setMinimumWidth(130)
            for text, value in POLICY_OPTIONS:
                selector.addItem(text, value)
            current = self.result_policy_overrides.get(
                policy_name, defaults.get(policy_name, ConstraintPolicy.PREFERRED)
            )
            selector.setCurrentIndex(selector.findData(current))
            if policy_name == "balance":
                selector.setEnabled(False)
                selector.setToolTip("Bilans godzin zawsze pozostaje preferowany.")
            self._rules_layout.addWidget(QLabel(label + ":"), row, 0)
            self._rules_layout.addWidget(selector, row, 1)
            self._policy_selectors[policy_name] = selector

    def _show_step(self, index: int):
        self._step_index = index
        self.stack.setCurrentIndex(index)

        if index == STEP_FEATURES:
            self._rebuild_features_step()
        elif index == STEP_RULES:
            self._rebuild_rules_step()

        self.back_btn.setVisible(index != STEP_WELCOME)
        self.skip_rules_btn.setVisible(index == STEP_RULES)
        self.next_btn.setText("Zakończ" if index == STEP_RULES else "Dalej")

    def _go_back(self):
        if self._step_index > STEP_WELCOME:
            self._show_step(self._step_index - 1)

    def _go_next(self):
        if self._step_index == STEP_BASICS:
            if not self.name_edit.text().strip():
                QMessageBox.warning(self, "Szybka konfiguracja", "Podaj nazwę placówki.")
                return
        elif self._step_index == STEP_FEATURES:
            self._collect_feature_overrides()
        elif self._step_index == STEP_RULES:
            self._finish(apply_rule_overrides=True)
            return

        self._show_step(self._step_index + 1)

    def _collect_feature_overrides(self):
        for policy_name, check in self._feature_checks.items():
            self.result_policy_overrides[policy_name] = (
                ConstraintPolicy.DISABLED if not check.isChecked() else ConstraintPolicy.PREFERRED
            )

    def _finish(self, apply_rule_overrides: bool):
        if apply_rule_overrides:
            for policy_name, selector in self._policy_selectors.items():
                self.result_policy_overrides[policy_name] = selector.currentData()

        self.result_name = self.name_edit.text().strip()
        self.result_year = self.year_spin.value()
        self.result_month = self.month_spin.value()
        self.result_business_type = self.profile_picker.selected_key()
        self.completed = True
        self.accept()
