# Plan: refaktoryzacja warstwy constraintów pod przyszłą rozbudowę

Ten plik to wyłącznie przegląd i propozycja — **brak zmian w kodzie**.
Zakres: `model/constraints.py`, `model/constraint_policy.py`,
`logic/constraint_presenter.py`, `logic/generator/*` (constraint_registry,
base_specs, dino_retail_profile, custom_profile_wiring, generic_rules i
poszczególne pliki `*_constraint.py`).

Kontekst: `plan generalizacji branzowej.md` opisuje przejście Dingo w
stronę wielobranżowego SaaS. Ten plik ocenia, na ile dzisiejsza warstwa
constraintów jest na to gotowa i co warto poprawić, zanim dojdzie kolejna
branża/profil.

## 1. Stan obecny — trzy równoległe systemy

1. **Generator (CP-SAT)** — dobrze zrefaktoryzowany: `ConstraintContext` +
   `ConstraintSpec` + `apply_registry` (`constraint_registry.py`), z
   podziałem na branżowo-neutralne specy (`base_specs.py`, współdzielone)
   i specyficzne dla profilu (`dino_retail_profile.py` — role na sztywno;
   `custom_profile_wiring.py` + `generic_rules.py` — reguły z kreatora
   profili, sparametryzowane rolą/oknem/progiem).
2. **Walidacja UI / kolorowanie gridu** — `model/constraints.py::
   ConstraintEngine` + `logic/constraint_presenter.py::ConstraintPresenter`.
   Osobna, ręcznie pisana implementacja tych samych reguł biznesowych
   (bez CP-SAT — proste sprawdzanie gotowego grafiku), używana do
   kolorowania komórek/wierszy w `ui/grid_view.py`.
3. **Katalog reguł kreatora** (`generic_rules.py`) — karmi wyłącznie
   system (1). System (2) o nim nie wie.

Te trzy systemy nie są ze sobą spięte żadną wspólną definicją reguły —
każda reguła biznesowa, która ma być i wymuszana przez generator, i
pokazywana w gridzie, jest dziś pisana dwa razy, w dwóch różnych stylach
(CP-SAT vs zwykły Python).

## 2. Konkretne problemy

### 2.1 Duplikat logiki "okno czasowe" — no_night/no_afternoon vs role_time_restriction

`logic/generator/night_constraint.py::add_no_night_constraint` i
`logic/generator/generic_rules.py::build_role_time_restriction` liczą
dokładnie to samo (które warianty zmiany "dotykają" zadanego okna
godzinowego, uwzględniając SHIFT_NIGHT) — jedno na sztywno dla flagi
`no_night` (okno 22–6), drugie generycznie dla dowolnej roli/okna z
kreatora. `add_no_afternoon_constraint` to trzeci, jeszcze prostszy
wariant tego samego pomysłu.

To nie jest tylko teoretyczne ryzyko — już się zmaterializowało. Trzy
ostatnie commity na tym branchu to ten sam koncepcyjny bug naprawiany
osobno w obu miejscach:

- `3b162af` — "no_night nie blokował ręcznie ustawionej zmiany nocnej"
- `3c10759` — "build_role_time_restriction nie obejmował SHIFT_NIGHT"
- `0e20055` — "no_night blokował SHIFT_NIGHT nawet gdy okno nie było nocą"

Każda kolejna poprawka dotycząca zmiany nocnej i okien czasowych musi być
dziś pamiętana i wykonana w dwóch plikach. To rośnie z każdą kolejną
"blokadą godzinową" per rola, jaką dostanie kolejny profil.

**Wniosek:** `build_role_time_restriction` jest już ogólniejszą wersją
`add_no_night_constraint`/`add_no_afternoon_constraint` (rola zamiast
flagi `no_night`, dowolne okno zamiast 22–6). Dino mogłoby wywoływać ten
sam generyczny builder z rolą "pracownicy z `no_night=True`" — bez
dwóch kopii tej samej logiki do utrzymania.

### 2.2 Walidacja w gridzie nie rozumie reguł profili custom

`ConstraintPresenter.get_validation_cell_view(key, day)` rozpoznaje
tylko trzy zaszyte na sztywno klucze: `"open"`, `"close"`, `"meat"`
(`logic/constraint_presenter.py:39-46`). Wiersze podsumowania dla ról z
profilu custom (`ui/grid_view.py:925-926`, klucz `role_key` =
`"role:<id>"`) trafiają w `get_validation_cell_view` do gałęzi domyślnej
i zawsze dostają zwykłe tło (`ui/grid_view.py:936-939`) — pokazywana jest
sama liczba osób, **nigdy** czerwone/żółte ostrzeżenie, niezależnie od
tego, czy reguła `min_staff_with_role`/`role_time_restriction` jest
faktycznie naruszona w gotowym grafiku.

To bezpośrednio uderza w cel z `plan generalizacji branzowej.md` — klient
spoza Dino (np. firma ochroniarska) korzystający z kreatora profili nie
dostaje żadnej wizualnej informacji o naruszeniu własnych reguł, mimo że
dokładnie taka informacja dla Dino istnieje od dawna.

### 2.3 `Rest11hRule` w walidacji ignoruje tryb generatora

`ConstraintEngine`'s `Rest11hRule` liczy odpoczynek 11h zawsze "dokładnym"
sposobem, niezależnie od `shop.constraints["rest_11h_mode"]`
("standard" vs "simplified" — patrz `base_specs.py::_build_rest_11h`) i
nie wie nic o `SHIFT_NIGHT`/`night_shift_adjacency`. Odnotowane już
świadomie w `plan generalizacji branzowej.md` jako "potencjalna,
drugorzędna rozbieżność" i zostawione bez zmian — wymieniam tu tylko dla
kompletności obrazu, nie jako nowe odkrycie.

### 2.4 Trzy kopie "grupuj pracowników po progu per lokalizacja"

Ten sam wzorzec — pogrupuj pracowników wg progu odczytanego z
`shop.get_location(emp).constraints.get(rule_key, default)`, zbuduj
osobny constraint per grupa — jest przepisany osobno w:

- `model/constraints.py::MaxConsecutiveDaysRule.apply` (walidacja),
- `logic/generator/base_specs.py::_build_max_consecutive` (generator),
- `logic/generator/generic_rules.py::build_min_staff_with_role` (kreator).

Działa poprawnie wszędzie dziś, ale każdy kolejny constraint z
nadpisaniem per lokalizacja to czwarta kopia tego samego dziesięciu linijek.

### 2.5 Niespójne logowanie: `print()` kontra `trace.log_constraint()`

Część constraintów woła jedno, część drugie, część oba naraz (np.
`constraints_staff.py:16` drukuje `print(f"[CONSTRAINT] ...")` **obok**
wpisu do `trace`). `ConstraintTraceLogger` (`trace.py`) już istnieje i
służy właśnie do tego, plus zapisuje się do JSON-a
(`trace_output_path`), co `print()` nie daje. Nieszkodliwe dziś, ale
z każdym kolejnym profilem konsola generatora robi się głośniejsza bez
dodatkowej wartości diagnostycznej.

## 3. Co świadomie NIE proponuję

Zgodnie z `.ai/AGENTS.md` ("nie zmieniaj architektury projektu", "preferuj
prostsze rozwiązania") — dwie rzeczy, które mogłyby wyglądać jak
"oczywisty" refaktor, ale których koszt/ryzyko nie jest dziś uzasadnione:

- **Zejście z `ConstraintContext` do sygnatur pozycyjnych** — dziś każdy
  `_build_x(ctx, soft)` w `base_specs.py`/`dino_retail_profile.py` tylko
  rozpakowuje `ctx` do starych, wieloparametrowych funkcji
  (`add_rest_11h_constraint(model, x, employees, ...)`). Techniczne
  ładniejsze byłoby, gdyby te funkcje przyjmowały `ctx` bezpośrednio, ale
  to dotknęłoby ~15 plików bez żadnej zmiany zachowania — czysty koszt
  ryzyka regresji za estetykę.
- **Uelastycznienie reprezentacji zmian** (dziś `SHIFT_OPEN`/`SHIFT_CLOSE`/
  `SHIFT_WORK_START_15..90`/`SHIFT_NIGHT` jako zaszyte na sztywno stałe w
  `AutoScheduleGenerator.__init__`) — realne ograniczenie dla przyszłych
  branż z inną strukturą zmian, ale to przebudowa kalibru "lokalizacji"/
  "zmian nocnych" (własny, wieloetapowy plan), nie coś do ruszania przy
  okazji porządkowania constraintów.

## 4. Rekomendacje (do robienia pojedynczo, każda z własnym testem)

Kolejność wg realnej wartości / ryzyka, nie wg numeracji problemów wyżej.

**Priorytet 1 — ujednolicić no_night/no_afternoon z `build_role_time_restriction`.**
Najmniejsza zmiana, największa wartość: usuwa udowodnione już źródło
podwójnych bugów (sekcja 2.1). Dino's `no_night`/`no_afternoon` stają się
wywołaniem generycznego buildera z rolą "pracownicy z flagą
`no_night`/`no_afternoon`" zamiast osobnym kodem. Wymaga: dodania
"wirtualnej roli" opartej o atrybut zamiast `has_role()`, albo prostszego
wariantu — parametr `employee_predicate` w `build_role_time_restriction`.
Testy do zachowania zielone: `test_night_shift_role_restriction.py`,
`test_night_shift_constraint.py`, `test_overnight_shift.py`.

**Priorytet 2 — rozszerzyć walidację/kolorowanie gridu o reguły custom.**
Domyka realną lukę funkcjonalną (sekcja 2.2), nie tylko porządek w
kodzie: klient na profilu custom zacznie widzieć czerwone/żółte komórki
dla własnych reguł, tak jak Dino je widzi dziś dla `open`/`close`/`meat`.
Wymaga dodania do `ConstraintEngine`/`ConstraintPresenter` ścieżki, która
dla `business_type` z `get_custom_profile()` liczy naruszenia
`min_staff_with_role`/`role_time_restriction` względem gotowego grafiku
(odpowiednik `generic_rules.py`, ale bez CP-SAT — zwykłe liczenie po
`schedule.get_day`). Test: rozszerzenie
`tests/test_profile_features.py`.

**Priorytet 3 — wspólny helper "grupuj po progu per lokalizacja".**
Czysty porządek (sekcja 2.4), zero zmiany zachowania. Warto zrobić **po**
Priorytecie 2, bo ten dołoży czwarte miejsce z tym samym wzorcem i wtedy
uzasadnienie do wydzielenia będzie mocniejsze niż dziś (trzy kopie).

**Priorytet 4 (opcjonalny, niski priorytet) — ujednolicić logowanie
generatora na `trace`, plik po pliku**, przy okazji innych zmian w danym
pliku, a nie jako osobna, mechaniczna zmiana w kilkunastu plikach naraz.

## 5. Jak z tego korzystać

Zgodnie z `.ai/AGENTS.md` ("nie zmieniaj kilku constraintów jednocześnie")
proponuję realizować jeden priorytet na raz, z testem i podsumowaniem
wpływu na generator po każdym. Ten plik warto zaktualizować (albo
poprosić o świeże podsumowanie) po ukończeniu każdego priorytetu.

## 6. Priorytet 1 — zrobiony (ta sesja)

`add_no_night_constraint` (`night_constraint.py`) i `build_role_time_restriction`
(`generic_rules.py`) dzielą teraz jedną implementację liczenia "które
zmiany OPEN/CLOSE/START/END dotykają zadanego okna godzinowego"
(`generic_rules.py::forbidden_shifts_for_time_window`). `no_night` dalej
sprawdza własną flagę pracownika (nie rolę) i dalej liczy godziny
sklepowe globalnie (nie per lokalizacja jak `build_role_time_restriction`)
— to świadomie zachowane bez zmian, żeby nie dotykać zachowania Dino poza
zakresem tego priorytetu (patrz sekcja 4 wyżej — "wspólny helper", nie
"identyczna funkcja"). `no_afternoon` (`afternoon_constraint.py`) **nie**
został przepięty — jego zakaz to statyczny zbiór zmian (CLOSE + warianty
END), bez żadnej matematyki okna godzinowego ani świadomości SHIFT_NIGHT,
więc nie dzielił z resztą tej samej, dwukrotnie już naprawianej logiki;
wymuszanie go przez `build_role_time_restriction` byłoby na siłę, nie
usuwaniem realnego duplikatu.

Przy okazji przeglądu tej wspólnej logiki wyszły na jaw dwa realne bugi
(oba naprawione, oba z testem regresyjnym udowadniającym, że failują na
starym kodzie):

- **`generic_rules.py::_shift_touches_window` miał zamienione progi
  miejscami** — `end.hour >= window_end_hour or start.hour <= window_start_hour`
  zamiast `end.hour >= window_start_hour or start.hour <= window_end_hour`.
  Dla domyślnego okna 22–6 dawało to `end.hour >= 6 or start.hour <= 22`,
  czyli prawdę dla praktycznie każdej zmiany w ciągu dnia —
  `build_role_time_restriction` (jedyny użytkownik tej funkcji, czyli
  reguła `role_time_restriction` z kreatora profili custom) realnie
  zabraniał danej roli pracy w ogóle, a nie tylko w oknie 22–6. Żaden
  istniejący test tego nie łapał — `tests/test_night_shift_role_restriction.py`
  sprawdzał dotąd wyłącznie SHIFT_NIGHT, nigdy prawdziwej zmiany
  OPEN/CLOSE/START/END liczonej z godzin otwarcia. Test regresyjny:
  `TestShiftTouchesWindow`, `TestBuildRoleTimeRestrictionDaytime`.
- **`add_no_night_constraint` liczył próg zmiany CLOSE względem
  nieaktualnej zmiennej `start`** (pozostałość po sprawdzeniu OPEN wyżej)
  zamiast rzeczywistej godziny rozpoczęcia zmiany CLOSE — dla każdego
  sklepu otwieranego o/przed 6:00 blokowało to zmianę CLOSE każdemu
  pracownikowi z `no_night`, niezależnie od faktycznej godziny jej
  zakończenia. Test regresyjny: `NoNightConstraintCloseShiftBugTests`
  w `tests/test_night_shift_manual_editing.py`.

`pytest tests/` → 179 passed (172 sprzed tej zmiany + 7 nowych testów
regresyjnych), zero regresji.
