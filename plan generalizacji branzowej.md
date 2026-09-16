# Plan: generalizacja Dingo pod różne branże

Branch: `feature/business-profiles`, wypchnięty na `origin` 2026-09-14
(wcześniej był wyłącznie lokalny). Working tree czyste. Historia od
`ad45fd4` w górę została raz przepisana W TEJ SESJI, **przed** tym
pushem (poprawka message'a jednego commita, patrz sekcja "Drobne"
niżej) — więc to przepisanie już nie jest bezpieczne do powtórzenia
(branch jest teraz publiczny/współdzielony na `origin`, kolejny rebase
wymagałby force-push i koordynacji z każdym, kto go już pobrał). Stan na
2026-09-15 (po ściągnięciu commitów `3cb675b..4ddae25` zrobionych na
innym urządzeniu, patrz sekcja 9 niżej): `pytest tests/` → 172 passed,
0 fail. Stary pre-existing fail
(`test_default_shop_config_uses_soft_staff_and_availability_policies`)
usunięty w Etapie B sekcji 9 — sprawdzał domyślne polityki open/close
jako PREFERRED, a te świadomie stały się MANDATORY jeszcze przed tą
sesją, bez aktualizacji testu; commit usuwający go opisuje to wprost.

Powód całej tej pracy: klient z firmy ochroniarskiej chce kupić lokalną
wersję Dingo, skonfigurowaną pod swoją działalność. Docelowo appka ma iść
w stronę wielobranżowego SaaS (`Dingo Online V2`) — ta generalizacja ma być
fundamentem pod to przejście, nie tylko łatką pod jednego klienta.

## Statystyki (2026-09-14)

Kod faktycznego programu (`main.py`, `model/`, `logic/`, `ui/`,
`persistence/`, `export/`, `utils.py`, `update_checker.py`,
`version.py`) — bez `tests/`, bez danych/configów (JSON, obrazy, ikony,
flagi, pliki builda `.spec`/`.iss`) i bez dwóch plików spoza normalnego
działania appki: `tmp_debug.py` (skrypt zwiadowczy, nigdzie nieimportowany)
i `key_generator.py` (osobne narzędzie deweloperskie do generowania
kluczy licencji, appka go nie importuje):

- **68 plików** `.py`
- **12 856 linii** łącznie (z pustymi i komentarzami) / **~9 833 linii**
  bez pustych i linii będących wyłącznie komentarzem

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

### 2. Kreator własnych profili (commity `61e1c71`, `d2ac7ed`, `0bca725`, `df50b07`)

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

### 4. Lokalizacje / multi-placówka (commity `339fc79`, `6920577`, `e7c50f3`, `4da03c3`)

- `model/location.py` — `LocationConfig` (godziny, obsada, kalendarz).
- `ShopConfig.get_location(employee)` — resolver godzin per pracownik
  (fallback na `self`, gdy brak lokalizacji — zero zmiany dla Dino).
- Wpięte do generatora: godziny zmian, `max_consecutive_days`.
- UI: zakładka "Lokalizacje" w Konfiguracji, wybór lokalizacji w
  formularzu pracownika.

### 5. Odpięcie rzeczy "sklepowych" (commit `8a35eb3`)

- `BusinessProfile.uses_trade_calendar` — niedziele handlowe/święta
  domyślnie **wyłączone** dla każdego profilu poza `dino_retail`
  (wcześniej każdy świeży projekt miał domyślnie zamknięte niedziele,
  co nie miało sensu dla całodobowej ochrony).
- `RoleDef.linked_policy` — polityka constraintu steruje widocznością w
  UI (przykład: wyłączenie polityki "mięso" chowa checkboxy
  `is_meat`/`is_meat_light` i powiązany wiersz/odznakę w gridzie).
- (sesja 2026-09-14, cd.) `ui/grid_view.py::_summary_rows()` — to samo
  ukrywanie wiersza podsumowania rozszerzone z samego "mięsa" na "open"/
  "close" (niezależnie od siebie) - kod miał wprost zapisany komentarz,
  że te dwa "nie są dotknięte stanem własnej polityki"; teraz są.
  `constraint_policies["open"]`/`["close"]` dało się wyłączyć od dawna
  (`apply_registry` już wcześniej poprawnie pomijał wyłączony constraint
  w całości) - brakowało tylko kaskady w UI. Checkbox `is_opener` w
  formularzu pracownika i jego odznaka w gridzie **świadomie
  pozostawione bez zmian**: `constraints_staff.add_fixed_staff_shift_constraints`
  wymaga `opener_staff >= 1` przy WSPÓLNEJ funkcji obsługującej i "open",
  i "close", więc ukrycie roli tylko pod jedną z tych dwóch polityk
  mogłoby uczynić drugą (wciąż aktywną) niespełnialną. Test:
  `tests/test_profile_features.py::test_grid_view_hides_open_and_close_summary_rows_independently_when_disabled`.

### 6. Higiena/UX (commit `4e168f1` i drobne po drodze)

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

### 9. Zmiana nocna / 24-7 (commity `67f6452`…`0e20055`, zrobione na innym urządzeniu 2026-09-14/15, wciągnięte do lokalnego brancha przez `git merge --ff-only` 2026-09-15)

Zrealizowane wg osobnego planu `plan zmiany nocne (24-7).md` (commit
`9c6fa1e`), etapy A→G, każdy osobnym commitem/PR-em na branchu
`claude/night-shift-generator-support-ex6pqc`, scalonym do
`feature/business-profiles` przez PR #1–#4 na GitHubie:

- **Etap A** (`67f6452`) — `model/day_schedule.py`: `end <= start`
  rozumiane jako "koniec następnego dnia" zamiast rzucania wyjątku
  (`set_hours`/`total_duration`/`total_minutes`). Zero zmiany dla
  istniejących zmian Dino (`end > start` zawsze).
- **Etap B** (`054c26f`) — `night_shift: {"start", "end"} | None` na
  `LocationConfig` i `ShopConfig` (`model/location.py::normalize_night_shift`,
  wspólna walidacja), UI w zakładce "Lokalizacje". Samo
  przechowywanie/edycja, generator jeszcze go nie czyta. Przy okazji
  usunięty jedyny pre-existing fail (patrz wyżej) — sprawdzał nieaktualną
  domyślną politykę open/close.
- **Etap C** (`955bb07`) — `logic/generator/night_shift_constraint.py`:
  nowy `SHIFT_NIGHT` jako prawdziwa zmienna CP-SAT, wpięty w okna
  odpoczynku 11h (nie tylko `no_night`, który dalej tylko *zakazuje*
  dotykania nocy, nie tworzy zmiany) i w brak nakładania się z dniem D+1.
- **Etap D** (`e28fee4`) — ręczna edycja/blokowanie zmiany nocnej w
  `ui/day_edit_dialog.py`, poprawne rozpoznawanie przy `is_fix=True`
  w `logic/generator/manual_constraint.py`/`fix.py`.
- **Etap E** (`56f4c5a`) — `export/excel_exporter.py`/`image_exporter.py`
  renderują `22:00 → 06:00` czytelnie; `logic/settlement_balancer.py`
  liczy zmianę nocną raz, do dnia D (zgodnie z art. 128 §3 pkt 1 KP —
  cała doba pracownicza należy do dnia rozpoczęcia).
- **Etap F** (`6150cf7`) — zamiast sztywnego nowego profilu "ochrona":
  nowy typ reguły w kreatorze custom profili,
  `logic/generator/generic_rules.py` + `model/custom_profile.py` +
  `ui/profile_wizard_dialog.py`, liczący obsadę `SHIFT_NIGHT` — więc
  **dowolny** przyszły profil custom (nie tylko ochrona) może z tego
  skorzystać bez nowego, zahardkodowanego pliku profilu.
- **Etap G** (`3fbe186`) — scenariusze/stress w `tests/run_scenarios.py`,
  `tests/stress_test_generator.py`, nowy plik testowy per etap
  (`test_overnight_shift.py`, `test_night_shift_constraint.py`,
  `test_night_shift_manual_editing.py`,
  `test_night_shift_export_and_diagnostics.py`,
  `test_night_shift_coverage_rule.py`, `test_night_shift_stress.py`).
- Trzy poprawki po fakcie (PR #2/#3, `3b162af`/`3c10759`/`0e20055`):
  `no_night` blokował ręcznie ustawiony `SHIFT_NIGHT` bezwarunkowo (nawet
  gdy okno realnie nie dotykało nocy) i `build_role_time_restriction` nie
  obejmował w ogóle `SHIFT_NIGHT` — oba naprawione.
- Constrainty specyficzne dla Dino (`meat`, `no_night`, `no_afternoon`,
  `open`/`close`) nietknięte — `SHIFT_NIGHT` istnieje tylko tam, gdzie
  lokalizacja/projekt go skonfiguruje, więc `dino_retail` zachowuje się
  identycznie.
- **Nadal odłożone** (patrz sekcja niżej): sam profil "ochrona" jako
  gotowy, wbudowany `BusinessProfile` — infrastruktura (Etapy A–G) jest
  gotowa, ale konkretne role/godziny/reguły klienta wciąż nieznane.
- `pytest tests/` → 172 passed, 0 fail.

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

- **Dni handlowe per lokalizacja** — `LocationConfig.trade_sundays`/
  `public_holidays` istnieją w modelu (od pierwszej fazy lokalizacji),
  ale generator ich nie czyta. `trade_days` to dziś jedna, globalna lista
  współdzielona przez prawie każdy moduł constraintu w generatorze —
  zrobienie tego per lokalizacja to osobna, spora przeróbka.

### Drobne — zamknięte (sesja 2026-09-14, cd.)

- **`last_projec.json`** — plik zniknął z katalogu repo w trakcie tej
  sesji (trafił do Kosza Windows, niedotknięty żadną moją komendą - patrz
  sekcja 8 wyżej). Poprawna nazwa (`last_project.json`) już od dawna jest
  w `.gitignore`; skoro pliku nie ma i nic go już nie tworzy, nie ma czego
  dalej naprawiać.
- **`model/constraints.py`** — `ConstraintEngine.evaluate()` uruchamiał
  `MinStaffRule`(open/close)/`MeatCoverageRule` **bezwarunkowo**, nawet
  dla projektów na profilu custom (bo `shop.constraints` zawsze ma
  domyślne `min_open_staff`/`min_close_staff` = 3/3, niezależnie od
  `business_type`) - realny, żywy bug: kolorowanie wierszy
  "Otwarcie"/"Zamknięcie" w gridzie dla DOWOLNEGO profilu custom (np.
  ochrony) walidowało się względem liczb z Dino, kompletnie
  niepowiązanych z faktycznie skonfigurowanymi regułami tego profilu.
  Naprawione: te trzy reguły uruchamiają się teraz tylko dla
  `business_type == "dino_retail"`. Przy okazji `MaxConsecutiveDaysRule`
  (który zostaje generyczny, dla każdego profilu) zaczął też respektować
  per-lokalizacyjne nadpisanie `max_consecutive_days` (Etap 3d / sekcja 7
  wyżej) - wcześniej kolorowanie grida ignorowało lokalizacje nawet dla
  Dino. `Rest11hRule` **świadomie zostawiony bez zmian** - nie
  odzwierciedla `rest_11h_mode` ("standard" vs "simplified") generatora,
  ale to porównanie rzeczywistych godzin z gotowego grafiku względem
  jednej, uniwersalnej zasady 11h, nie duplikat konkretnego trybu solvera;
  nie jest to udowodniony bug, tylko potencjalna, drugorzędna
  rozbieżność - zostawione, żeby nie ciągnąć tego dalej bez konkretnego
  przypadku, który by to uzasadniał.
  Testy: `tests/test_profile_features.py::test_constraint_engine_skips_dino_only_rules_for_custom_profiles`,
  `::test_constraint_engine_max_consecutive_respects_employee_location_override`.
- **Commit `ad45fd4`** — message poprawiony (teraz opisuje też dodanie
  "Edytuj profil..." do Konfiguracji, nie tylko scrollbary). Zrobione
  przez ręczne przepisanie łańcucha commitów od `ad45fd4` w górę
  (`git commit-tree` per commit, bez `-i`) — każde drzewo zweryfikowane
  jako identyczne z oryginałem przed przesunięciem wskaźnika brancha, więc
  kod się nie zmienił, tylko hashe od `ad45fd4` w górę (branch lokalny,
  nigdy niewypchnięty na `origin`, więc nikogo to nie dotyka poza Tobą).
  Nowy hash tego commita: `4e168f1`.

### Incydent zamknięty

- `custom_profiles.json` skasowany w poprzedniej sesji — potwierdzone,
  że to było klikanie testowe (nazwy `custom_sdgsdgsg`/`custom_hdhdh`/
  `custom_dupa`), nie realna strata. Wątek zamknięty.

---

## Jak z tego korzystać

Ten plik to zrzut stanu na dziś (branch `feature/business-profiles`,
commit `4ddae25`) — aktualizuj go albo poproś o świeże podsumowanie, gdy
zrobimy kolejny krok, bo inaczej szybko się zdezaktualizuje.
