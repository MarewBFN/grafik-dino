# Plan: generalizacja Dingo pod różne branże

Branch: `feature/business-profiles` (12 commitów względem `main` na
początek tej sesji; zmiany z sekcji 7 i 8 poniżej jeszcze
niescommitowane). Stan na dziś: `pytest tests/` → 82 passed, 1
pre-existing fail niezwiązany z tą pracą
(`test_default_shop_config_uses_soft_staff_and_availability_policies`,
istniał już na `main`).

Powód całej tej pracy: klient z firmy ochroniarskiej chce kupić lokalną
wersję Dingo, skonfigurowaną pod swoją działalność. Docelowo appka ma iść
w stronę wielobranżowego SaaS (`Dingo Online V2`) — ta generalizacja ma być
fundamentem pod to przejście, nie tylko łatką pod jednego klienta.

---

## Co zrobiliśmy

### 1. Rdzeń generalizacji (commit `b14ed11`)

- `model/business_profile.py` — `BusinessProfile`/`RoleDef`, rejestr
  `BUSINESS_PROFILES`. `dino_retail` to pierwszy, w pełni odwzorowany
  profil — dzisiejsze zachowanie Dino bez zmian.
- `logic/generator/constraint_registry.py` — `ConstraintContext`/
  `ConstraintSpec`/`apply_registry`: generyczny rejestr constraintów
  zamiast wcześniejszego ~600-liniowego, zahardkodowanego `generate()`.
- `logic/generator/dino_retail_profile.py` — wydzielone, niezmienione
  constrainty Dino (mięso, opener/closer, noc/popołudnie).
- Role (`ui/employee_dialog.py`), polityki (`ui/config_dialog.py`),
  wiersze podsumowania (`ui/grid_view.py`) sterowane profilem zamiast
  zahardkodowane.

### 2. Kreator własnych profili (commity `61e1c71`, `d2ac7ed`, `0bca725`, `24c6d43`)

- `ui/profile_wizard_dialog.py` — tworzenie **i edycja** profilu: nazwa,
  role (z ikoną z `ui/emoji_palette.py`), reguły z zamkniętego katalogu 2
  typów (`min_staff_with_role`, `role_time_restriction`).
- `model/custom_profile.py` / `model/custom_profile_store.py` — model
  reguł + trwałość w `%LOCALAPPDATA%\GrafikDino\custom_profiles.json`.
- `logic/generator/generic_rules.py` / `custom_profile_wiring.py` —
  generyczne buildery reguł + spięcie z rejestrem constraintów.
- `logic/generator/base_specs.py` — branżowo-neutralne constrainty
  (odpoczynek 11h, dni pod rząd, godziny miesięczne, bilans, dostępność)
  wydzielone i współdzielone przez `dino_retail` i profile custom.
- Przyciski "Nowy/Edytuj/Usuń profil..." w Konfiguracji i w dialogu
  Nowy projekt.
- `standard_daily_hours` realnie wpięte w `get_effective_daily_hours`
  (wcześniej zaszyte na sztywno 8h), edytowalne w Konfiguracji, max 23,75h
  (dosłowne 24h jest nierozróżnialne od pustej zmiany w modelu godzin
  HH:MM bez śledzenia daty).

### 3. Onboarding (commit `04fedee`)

- `ui/new_project_dialog.py` — wybór branży + rok/miesiąc jako pierwszy
  krok nowego projektu, zamiast cichego domyślnego `dino_retail`.

### 4. Lokalizacje / multi-placówka (commity `339fc79`, `6920577`, `e7c50f3`, `91f35fa`)

- `model/location.py` — `LocationConfig` (godziny, obsada, kalendarz).
- `ShopConfig.get_location(employee)` — resolver godzin per pracownik
  (fallback na `self`, gdy brak lokalizacji — zero zmiany dla Dino).
- Wpięte do generatora: godziny zmian, `max_consecutive_days`.
- UI: zakładka "Lokalizacje" w Konfiguracji, wybór lokalizacji w
  formularzu pracownika.

### 5. Odpięcie rzeczy "sklepowych" (commit `26d0a59`)

- `BusinessProfile.uses_trade_calendar` — niedziele handlowe/święta
  domyślnie **wyłączone** dla każdego profilu poza `dino_retail`
  (wcześniej każdy świeży projekt miał domyślnie zamknięte niedziele,
  co nie miało sensu dla całodobowej ochrony).
- `RoleDef.linked_policy` — polityka constraintu steruje widocznością w
  UI (przykład: wyłączenie polityki "mięso" chowa checkboxy
  `is_meat`/`is_meat_light` i powiązany wiersz/odznakę w gridzie).

### 6. Higiena/UX (commit `ad45fd4` i drobne po drodze)

- Scrollbary we wszystkich oknach z dynamicznie rosnącą treścią
  (kreator profilu, lokalizacje, lista profili, role pracownika).
- Ustawienia zaawansowane generatora schowane domyślnie w Konfiguracji.

### 7. Reguły z kreatora per lokalizacja (sesja 2026-09-14)

- Rozwiązanie: dokładnie ten sam mechanizm co `max_consecutive_days`
  (Etap 3d) — `LocationConfig.constraints["rule:<id>"]` nadpisuje próg
  `min_count` tylko dla pracowników przypisanych do danej lokalizacji;
  profil (i jego domyślny `min_count`) zostaje projekt-agnostyczny,
  współdzielony między projektami zamiast wiązać profil z konkretnymi
  kluczami lokalizacji.
- `logic/generator/generic_rules.py::build_min_staff_with_role` —
  grupuje pracowników z daną rolą po progu rozwiązanym z ich lokalizacji
  (`ctx.shop.get_location(emp).constraints.get(rule_key, min_count)`) i
  buduje osobny constraint per grupa/dzień, zamiast jednego globalnego
  sumowania. Brak pracowników z rolą → zachowanie jak przed zmianą
  (twardy/miękki fail na progu bazowym względem zera osób).
- `logic/generator/custom_profile_wiring.py::build_specs` — przekazuje
  `rule_key` (`"rule:<id>"`, ten sam klucz co w `constraint_policies`) do
  buildera, tylko dla `min_staff_with_role`.
- `ui/config_dialog.py` — zakładka "Lokalizacje" dostała nowe pola:
  próg "Dni pod rząd" per lokalizacja (dotąd wpięty w generator, ale bez
  UI — martwy od Etapu 3d) + jeden spinbox per reguła
  `min_staff_with_role` aktywnego profilu custom, wartość 0 = "domyślnie
  (N)". **Świadomie NIE dodano** pól `min_open_staff`/`min_close_staff`
  per lokalizacja — generator ich tam nie czyta (tylko `shop.constraints`
  na poziomie projektu, w `dino_retail_profile.py`), więc takie pole
  tylko kłamałoby użytkownikowi.
- Test: `tests/test_location_generator.py::test_min_staff_with_role_rule_is_resolved_per_employee_location`.
- `pytest tests/` → 78 passed, ten sam 1 pre-existing fail co wcześniej
  (`test_default_shop_config_uses_soft_staff_and_availability_policies`).
- Nieukończone: zakładka "Lokalizacje" (jak i "Zasady generatora") nie
  odświeża listy reguł na żywo po zmianie profilu w selektorze wyżej —
  trzeba zamknąć i otworzyć Konfigurację ponownie. Ta sama, już
  istniejąca niedogodność co dla "Zasady generatora", nie regresja.

### 8. Kreator szybkiej konfiguracji przy pierwszym uruchomieniu (sesja 2026-09-14, cd.)

- Nowy `ui/first_run_wizard.py::FirstRunWizardDialog` — 5-krokowy,
  opisany kreator: Powitanie → Nazwa placówki + okres → Branża → Cechy
  (przełączniki dla ról z `linked_policy`, dziś tylko "mięso" u Dino) →
  Zasady generatora (te same polityki MANDATORY/PREFERRED/DISABLED co w
  "Konfiguracja" → "Zasady generatora", z przyciskiem "Pomiń — użyj
  wartości domyślnych"). Anuluj w dowolnym momencie = brak utworzonego
  projektu, jak dziś przy świeżym instalu.
- `model/shop_config.py` — nowe pole `ShopConfig.name` (opisowe, nie
  wpływa na generator), zserializowane w `to_dict`/`from_dict`,
  edytowalne też później w `ConfigDialog` (nowe pole "Nazwa placówki").
  Pokazywane w tytule okna (`ui/main_window.py::_update_window_title`).
- `ui/business_profile_picker.py` — lista profili z przyciskami
  Edytuj/Usuń/"+ Nowa branża..." wydzielona z `NewProjectDialog` do
  osobnego, współdzielonego widgetu, żeby kreator i "Nowy projekt" nie
  rozjechały się w przyszłości.
- `ui/main_window.py` — poprawiony sygnał "świeży instal": `_init_state()`
  w `__init__` zawsze tworzy w pamięci pusty, domyślny `dino_retail`
  (`self.schedule` **nigdy** nie jest `None`), więc realnym sygnałem jest
  nowe `self._opened_existing_project` (czy `last_project.json`/plik z
  linii poleceń faktycznie się wczytał). Kreator odpala się tylko gdy to
  `False`; poradnik zawsze odpala się PO zamknięciu kreatora (albo od
  razu, jeśli `_opened_existing_project` było `True` i kreatora nie było
  po co pokazywać) - nigdy oba naraz.
- Test: `tests/test_first_run_wizard.py` (walidacja nazwy, przełącznik
  cech → DISABLED polityki, pominięcie kroku reguł faktycznie nic nie
  nadpisuje, profil custom bez `linked_policy` nie pokazuje przełączników
  ale pokazuje własną regułę w kroku "Zasady", Anuluj nie kończy
  kreatora).
- `pytest tests/` → 82 passed, ten sam 1 pre-existing fail.
- Przy okazji: projekty tworzone z profilem custom (czy to przez ten
  kreator, czy przez "Nowy projekt") teraz od razu dostają poprawne
  domyślne polityki dla swoich reguł (`default_policies(custom)`) zamiast
  dopiero po pierwszym otwarciu "Konfiguracji" - bez tego reguły
  custom profilu były cicho DISABLED aż do pierwszego wejścia w
  Konfigurację (`ConstraintPolicy` nieustawione = DISABLED w
  `apply_registry`). To dotyczy też ścieżki przez `_open_new_project`
  (`ui/main_window.py`), nie tylko kreatora - nieopisane wcześniej w tym
  pliku, zauważone przy pisaniu kreatora.
- Obserwacja poboczna: plik `last_projec.json` (literówka, zgłoszony w
  sekcji "Drobne, nieblokujące" poniżej) zniknął z katalogu repo w
  trakcie tej sesji - trafił do Kosza Windows (potwierdzone), więc nie
  jest utracony, ale żadna komenda uruchomiona w tej sesji go nie
  dotyczyła. Nieprzywrócony - do wyjaśnienia z Tobą.

---

## Co zostało do zrobienia

### Świadomie odłożone (wymaga wiedzy o kliencie / realnej potrzeby)

- **Konkretny profil dla firmy ochroniarskiej.** Cała infrastruktura
  czeka — nie ma jeszcze wymagań (role, godziny, reguły) od klienta.
- **Generyczny "kreator sub-cech"** — żeby dowolny profil custom mógł w
  kreatorze definiować własne, przełączalne moduły ról/constraintów/UI
  (uogólnienie mechanizmu `linked_policy` poza mięso). Czeka na drugi
  realny przypadek użycia.

### Odłożone jako głęboka przebudowa (podobny kaliber ryzyka co lokalizacje)

- **Prawdziwy model zmian 24/7** — dziś zmiany liczone są w obrębie
  jednego dnia kalendarzowego (`datetime` bez śledzenia daty), zero
  miejsc dodaje dzień przy przekroczeniu północy. Rzeczywista zmiana
  nocna 22:00–06:00 nie jest wspierana; obejście: godziny placówki
  ustawione na prawie całą dobę (np. 00:00–23:45).
- **Dni handlowe per lokalizacja** — `LocationConfig.trade_sundays`/
  `public_holidays` istnieją w modelu (od pierwszej fazy lokalizacji),
  ale generator ich nie czyta. `trade_days` to dziś jedna, globalna lista
  współdzielona przez prawie każdy moduł constraintu w generatorze —
  zrobienie tego per lokalizacja to osobna, spora przeróbka.

### Drobne, nieblokujące

- **`last_projec.json`** (literówka w nazwie) w katalogu repo z realnymi
  danymi projektu, nieobjęty `.gitignore` — zgłoszone, nienaprawione.
- **`model/constraints.py`** — równoległa, zduplikowana logika
  meat/opener używana tylko do kolorowania grida (przez
  `logic/constraint_presenter.py`); może rozjechać się z prawdziwym
  generatorem. Dług techniczny z pierwszej fazy, nieadresowany.
- **Commit `ad45fd4`** ("Add scrollbars...") przez pomyłkę zawiera też
  całą funkcję edycji profili pod niepasującym opisem — historia gita
  jest w tym miejscu myląca (kod poprawny, tylko message nietrafiony).
  Nie naprawiane (wymagałoby rebase/amend, nie robię tego bez pytania).

### Incydent do zamknięcia

- Podczas testów w tej sesji przypadkowo skasowany plik
  `custom_profiles.json` (stary skrypt testowy czyścił go na starcie),
  co usunęło 3 Twoje realne profile custom (`custom_sdgsdgsg`,
  `custom_hdhdh`, `custom_dupa`). Bez kopii zapasowej, nieodzyskane.
  Nie potwierdzone, czy to była realna strata czy tylko klikanie testowe.

---

## Jak z tego korzystać

Ten plik to zrzut stanu na dziś (branch `feature/business-profiles`,
commit `26d0a59`) — aktualizuj go albo poproś o świeże podsumowanie, gdy
zrobimy kolejny krok, bo inaczej szybko się zdezaktualizuje.
