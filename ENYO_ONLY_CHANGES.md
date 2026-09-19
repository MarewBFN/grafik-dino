# Log zmian: branch `integration/enyo-only`

Ten branch wycina z aplikacji wszystko, co nie jest potrzebne klientowi
Enyo (ochrona) — profil "Dino"/retail, wybór/kreator profili biznesowych
i wszystko, co by mu je pokazywało. Punkt startowy: `integration/all-
branches-to-main` (PR #6), czyli `main` + cała praca ze scalonych branchy.

**Cel tego pliku:** każda rzecz, którą tu usuwamy lub ukrywamy, ląduje
tu jako wpis - żeby dało się to później świadomie odtworzyć/przywrócić do
`main`, gdyby okazało się, że jednak jest potrzebna (klientowi Enyo albo
w ogólnej wersji Dino). Bez tego logu "wycinanie" i "gubienie bezpowrotnie"
wyglądają identycznie w diffie.

**Zasada:** przed (albo w tym samym commicie co) usunięciem/ukryciem
czegokolwiek dla Enyo, dopisz wiersz do tabeli niżej. Jeśli coś zostaje
tylko *ukryte* (kod istnieje, ale nieosiągalny z UI/configu), zaznacz to
wprost w kolumnie Akcja - to inna sytuacja niż fizyczne usunięcie pliku.

## Zasady robocze dla pracy nad constraintami/generatorem (2026-09-19)

Ustalone z użytkownikiem, obowiązują dla dalszej pracy nad generatorem:

1. **Modyfikacja vs nowy plik:** jeśli potrzebna zmiana to tylko drobna
   korekta zachowania istniejącego constrainta - zmień go w miejscu.
   Nowy, osobny plik/funkcja tylko gdy potrzebne zachowanie jest
   *znacząco* inne od tego, co już istnieje. (Nie dotyczy Dino - tam
   nadal zero zmian zachowania, punkt niżej.)
2. **Dino vs Enyo:** nigdy nie zmieniaj zachowania constraintów pisanych
   pod Dino. Można zmieniać zachowanie constraintów Enyo. Wspólny/
   generyczny kod (`base_specs.py`, `hours_constraint.py` itd.) wolno
   zmieniać, jeśli zmiana jest prawdziwym bugiem (nie kwestią gustu) i
   jest przetestowana na pełnym zestawie danych Dino.
3. **Pokrycie > nadgodziny, ZAWSZE:** generator ma wolno przypisać
   dowolną ilość nadgodzin komukolwiek, byleby zapewnić pełne pokrycie
   obiektu przez cały miesiąc. Zweryfikowane 2026-09-19, że domyślna
   konfiguracja już to gwarantuje: `duty_rotation_coverage`/
   `duty_rotation_no24h` = MANDATORY (twarde, model/shop_config.py),
   `balance`/`monthly_hours`/`max_consecutive` = PREFERRED (miękkie) -
   więc w niedoborze obsady generator dokłada nadgodziny zamiast
   zostawiać dziurę w grafiku. Priorytet "Umowa" i preferencja 12h+12h
   (ten branch) są celowo zawsze miękkie z tego samego powodu - nigdy nie
   mogą zablokować pokrycia.
   **Świadomie NIE zabezpieczone:** dropdown w Konfiguracji nadal
   pozwala ręcznie ustawić `balance`/`monthly_hours` na MANDATORY dla
   dowolnego profilu (w tym Enyo) - użytkownik zdecydował zostawić to
   bez zmian, mimo że taka ręczna zmiana złamałaby tę zasadę.

## Jak czytać kolumny

- **Akcja** - `USUNIĘTY` (plik/kod skasowany), `UKRYTY` (kod zostaje,
  ale nieosiągalny z UI dla Enyo), `WYŁĄCZONY` (istnieje, ale zablokowany
  flagą/warunkiem), `UPROSZCZONY` (funkcjonalność okrojona, nie usunięta
  w całości).
- **Przywrócić do main?** - `TAK` / `NIE` / `DO USTALENIA`. To osąd w
  momencie usuwania, nie wyrok ostateczny - i tak wraca do decyzji przy
  ewentualnym porcie.

## Pliki i moduły

| Plik/moduł | Akcja | Co robił(a) dla Dino/ogółu | Commit | Przywrócić do main? | Notatka |
|---|---|---|---|---|---|
| _(na razie brak wpisów - usuwane/dodawane całe pliki jeszcze nie wystąpiły)_ | | | | | |

## Pojedyncze fragmenty kodu (nie całe pliki)

Gdy usuwamy/ukrywamy tylko kawałek pliku (np. gałąź `if is_dino_style(...)`
albo jedno pole formularza), a nie cały plik - wpis tutaj zamiast w tabeli
wyżej, żeby nie zaśmiecać jej ścieżkami plików, które w większości zostają.

| Plik | Co dokładnie (funkcja/blok/pole) | Akcja | Commit | Przywrócić do main? | Notatka |
|---|---|---|---|---|---|
| `model/business_profile.py` | Nowa funkcja `visible_profiles()` - filtruje `dino_retail` z listy do wyświetlenia, `BUSINESS_PROFILES`/`get_profile()` bez zmian | UKRYTY (dodatek, nic nie usunięte) | (ten wpis) | TAK (sama funkcja jest neutralna/nieużywana w main, nie szkodzi) | Czysto addytywne - można spokojnie zabrać do main, tylko main nie musi jej wywoływać |
| `ui/business_profile_picker.py::_reload` | `BUSINESS_PROFILES.values()` → `visible_profiles()`; domyślny wybór profilu też liczony z listy widocznej, nie ze wszystkich zarejestrowanych | UKRYTY | (ten wpis) | NIE (main ma dalej pokazywać Dino w tym pickerze) | Używany przez `NewProjectDialog` i `FirstRunWizardDialog` - jeden fix naprawia oba ekrany |
| `ui/config_dialog.py::_reload_business_type_selector` | `BUSINESS_PROFILES.values()` → `visible_profiles()` w dropdownie "Profil działalności:" | UKRYTY | (ten wpis) | NIE (main ma dalej pokazywać Dino) | |
| `ui/config_dialog.py::_build_limits_tab` | Sekcja "MINIMALNA OBSADA PRACOWNIKÓW" (`min_open`/`min_close`) - budowana tylko gdy `business_type == DEFAULT_BUSINESS_TYPE`; same widżety `QSpinBox` zawsze tworzone (żeby `_save()` nie wymagał zmian), tylko nie trafiają do layoutu gdy ukryte | UKRYTY | (ten wpis) | NIE (main ma dalej pokazywać tę sekcję zawsze) | Zweryfikowane w izolacji: dla `dino_retail` sekcja się buduje bez zmian, dla innego profilu - nie |
| `tests/test_first_run_wizard.py::test_wizard_dino_retail_feature_toggle_disables_meat_policy` | Test zakładał domyślny wybór "Dino" w kreatorze (teraz niedostępny w UI) | POMINIĘTY (`@pytest.mark.skip`, kod testu zostaje) | (ten wpis) | TAK (odkomentować/usunąć skip przy porcie do main) | Jedyny test, który padł po ukryciu Dino z pickera - 361/362 przeszło bez zmian |
| `ui/config_dialog.py` (profile_row) | Guziki "Nowy profil...", "Edytuj profil...", "Usuń profil..." - `setVisible(False)` zaraz po utworzeniu, cała logika kliknięć/`_sync_edit_profile_button()` zostaje | UKRYTY | (ten wpis) | NIE (main ma je pokazywać) | Decyzja użytkownika: klient ma dokładnie jeden, gotowy profil "Ochrona" i nie zarządza profilami przez UI w ogóle |
| `ui/business_profile_picker.py` | Guzik "+ Nowa branża..." oraz per-wierszowe "Edytuj..."/"Usuń..." dla każdego profilu custom na liście - `setVisible(False)`, logika zostaje | UKRYTY | (ten wpis) | NIE (main ma je pokazywać) | Ten sam powód co wyżej - inny punkt wejścia do tej samej funkcjonalności (używany przez "Nowy projekt" i kreator pierwszego uruchomienia) |
| `ui/main_window.py::_about` | Tekst `<b>Dingo!</b>` + dedykacja "Dla Mamy" | UPROSZCZONY (branding zamieniony na neutralny, nie usunięty cały dialog) | (ten wpis) | DO USTALENIA (zależy, czy main ma zostać przy brandingu "Dingo!" - to nie jest odtwarzalne 1:1, to decyzja marketingowa) | Wersja + link `madebykewin.pl` zostały |
| `ui/main_window.py::_build_tutorial_steps` | Tytuł pierwszego kroku "Witaj w Dingo!" | UPROSZCZONY | (ten wpis) | DO USTALENIA (jw.) | To jest ŻYWY samouczek (`TutorialOverlay`) - reszta kroków była już neutralna |
| `ui/main_window.py` (`_start_update_download`) | Tytuł dialogu "Aktualizacja DinGO" | UPROSZCZONY | (ten wpis) | DO USTALENIA (jw.) | |
| `ui/tutorial_dialog.py` (`TutorialDialog.steps`) | "Witaj w Grafik Dino v2!", "dla sklepów", przykład roli "otwarcie, mięso" | UPROSZCZONY | (ten wpis) | DO USTALENIA (jw., choć ta klasa i tak nigdzie się nie tworzy - patrz notatka wyżej) | Martwy kod odkryty przy okazji - nic w aplikacji nie tworzy `TutorialDialog` |

## Audyt (2026-09-18) - pełna lista kandydatów, jeszcze nietknięta

Pełny przegląd kodu pod kątem tego, co klient Enyo faktycznie widzi/może
kliknąć. Podzielony na 3 poziomy priorytetu. Profil klienta to custom
profil `ochrona_enyo` (patrz `demo/install_demo.py`) - `DINO_RETAIL_PROFILE`
("dino_retail") jest ZAWSZE zarejestrowany bezwarunkowo przy imporcie
`model/business_profile.py` (linia `register_profile(DINO_RETAIL_PROFILE)`
poza jakimkolwiek warunkiem), więc każdy mechanizm, który iteruje
`BUSINESS_PROFILES.values()`, pokazuje go klientowi razem z Ochroną.

### Poziom 1 - realne wycieki do klienta (widoczne w normalnym użytkowaniu)

- ✅ **ZROBIONE** `ui/config_dialog.py` - dropdown "Profil działalności:"
  filtruje teraz przez `visible_profiles()` (bez Dino). **Nadal otwarte:**
  przyciski "Nowy profil...", "Edytuj profil...", "Usuń profil..." zostają
  widoczne bez zmian - to osobna decyzja, patrz Poziom 3.
- ✅ **ZROBIONE** `ui/config_dialog.py` (zakładka "Limity") - sekcja
  "MINIMALNA OBSADA PRACOWNIKÓW" pokazuje się teraz tylko dla
  `business_type == dino_retail`, tak jak zakładka "Niedziele handlowe".
- ✅ **ZROBIONE** `ui/new_project_dialog.py` + `ui/business_profile_picker.py`
  - "Branża:" w "Nowym projekcie" i w kreatorze pierwszego uruchomienia
  (`ui/first_run_wizard.py`, krok `STEP_BRANCH`) też filtruje przez
  `visible_profiles()` - jeden fix w pickerze naprawił oba ekrany.
  **Nadal otwarte:** przycisk "+ Nowa branża..." zostaje widoczny.
- ✅ **ZROBIONE** `ui/main_window.py::_about` - "O programie" nie pisze już
  `<b>Dingo!</b>` ani osobistej dedykacji ("Z dedykacją dla Mamy ❤️..."),
  zostaje neutralny opis + wersja + `madebykewin.pl` (link do strony
  producenta, nie marka Dino - zostawiony).
- ✅ **ZROBIONE** samouczek (`_build_tutorial_steps` w `ui/main_window.py`,
  RZECZYWIŚCIE używany overlay, nie `ui/tutorial_dialog.py` - patrz niżej) -
  "Witaj w Dingo!" → "Witaj!". Reszta kroków była już neutralna. Zrzuty
  ekranu (`assets/tutorial/step1-6.png`) obejrzane - to generyczne kadry
  UI (przyciski, panel trybu szybkiego), bez brandingu/danych Dino - OK,
  zostają bez zmian.
- ✅ **ZROBIONE** (choć bez realnego efektu) `ui/tutorial_dialog.py` -
  "Witaj w Grafik Dino v2!"/"dla sklepów"/"otwarcie, mięso" zneutralizowane.
  Przy okazji ustalone: **ta klasa (`TutorialDialog`) jest martwym kodem -
  nigdzie w aplikacji nie jest tworzona** (żywy samouczek to
  `TutorialOverlay`/`_build_tutorial_steps`, wpis wyżej). Zero wpływu na
  klienta; wart osobnej decyzji "usunąć plik" przy kolejnym porządkowaniu.
- ✅ **ZROBIONE** `ui/main_window.py` (dialog aktualizacji) - tytuł
  `"Aktualizacja DinGO"` → `"Aktualizacja programu"`.
- **`release_channel.py`** - `RELEASE_CHANNEL = "dino"` zacommitowane jako
  wartość domyślna; build dla Enyo musi to nadpisywać przez
  `scripts/build_release.ps1 -Channel enyo` - do zweryfikowania, że
  faktyczny build klienta rzeczywiście tak działa, a nie zostaje na "dino".
- **Branding instalatora/appki** - `dla inno.iss` (`MyAppName = "Dingo! -
  narzędzie do grafików pracy"`, katalog `Programs\Dingo\Dingo!`),
  `Dingo! - narzędzie do grafików pracy.spec` (PyInstaller), `dingo_icon.ico`.

### Poziom 2 - martwy kod, już ukryty (zero efektu wizualnego dla Enyo, niski priorytet)

- Role Dino w `model/employee.py` (`is_opener`, `is_meat`, `is_meat_light`,
  `is_manager`, `no_night`, `no_afternoon`) - niewidoczne w
  `EmployeeDialog`, bo ten czyta `get_profile(business_type).roles`
  (profil `ochrona_enyo` ich nie ma). Zostają jako nieużywane pola danych.
- `ui/grid_view.py:418-421` - ikony `key.png`/`meat.png`/`keymeat.png`
  ładowane zawsze, ale renderowane jako badge tylko gdy
  `employee.is_opener`/`is_meat` - dla Enyo zawsze `False`, więc nigdy się
  nie pokazują.
- Przyciski trybu szybkiego "Rano"/"Popo" w `main_window.py` - już
  warunkowo ukryte przez `_update_quick_panel_profile_visibility`
  (`is_retail = business_type == DEFAULT_BUSINESS_TYPE`) - **działa
  poprawnie już dziś**, potwierdzone czytając kod.
- Cała gałąź generatora dla `dino_retail`: `logic/generator/
  dino_retail_profile.py`, `constraints_staff.py`, `meat_constraint.py`,
  `meat_light_budget.py`, `afternoon_constraint.py` - budowana tylko gdy
  `business_type == "dino_retail"` (patrz `custom_profile_wiring.py`/
  `constraint_registry.py`), nieużywana przez `ochrona_enyo`, ale
  importowana i obecna w binarce.
- `utils.py:16` - folder danych aplikacji to `%LOCALAPPDATA%\GrafikDino`
  (nazwa na sztywno) - niewidoczne dla klienta w normalnym użyciu, ale
  niespójne z brandingiem Enyo, gdyby ktoś zajrzał do AppData.

### Odłożone na później (świadomie NIE zrobione)

- **Branding instalatora/appki** - `release_channel.py` (domyślny kanał
  `"dino"`), `dla inno.iss`, `Dingo! - narzędzie do grafików pracy.spec`,
  `dingo_icon.ico`. Wymaga decyzji o nazwie/ikonie dla builda Enyo, nie
  prostej zamiany tekstu - wraca do tego później.

### Poziom 3 - decyzje architektoniczne (nie da się rozstrzygnąć samym gotowym audytem)

- ~~Czy dropdown profili ma przestać pokazywać Dino~~ - **ZROBIONE**
  (`visible_profiles()`).
- ~~Czy przyciski Nowy/Edytuj/Usuń profil i "+ Nowa branża..." mają
  zniknąć~~ - **ZROBIONE** (decyzja: tak, ukryte - klient ma dokładnie
  jeden, gotowy profil "Ochrona" i nie zarządza profilami przez UI).
  `ProfileWizardDialog` sam w sobie zostaje w repo nietknięty, tylko
  wszystkie 4 wejścia do niego są `setVisible(False)`.
- Czy `DINO_RETAIL_PROFILE`/`dino_retail` zostaje zarejestrowany w ogóle w
  tym buildzie, czy usuwamy rejestrację i cały generator dino_retail
  fizycznie z tego brancha (mniejsza binarka, zero ryzyka wycieku, ale
  utrudnia ewentualny powrót zmian do main przez rozjazd struktury)?

## Audyt generatora/constraintów (2026-09-18)

Przegląd `logic/generator/*.py` pod kątem: co jest Dino-only, co jest
generyczne i bezpieczne dla Enyo, i czy coś realnie koliduje z rotacją
24/7 (duty_rotation). Zasada dla całej tej sekcji: **zero zmian w
zachowaniu dla Dino** - każda poprawka jest albo nowym, równoległym
kodem, albo guardem, który dla lokalizacji bez `duty_rotation` (czyli
KAŻDEGO dzisiejszego projektu Dino) jest bezwarunkowym no-opem.

### Wynik: architektura już dobrze rozdzielona

`dino_retail_profile.py` (mięso, opener/closer, no_night/no_afternoon,
`constraints_staff.add_fixed_staff_shift_constraints`) jest **w pełni
izolowany** - `custom_profile_wiring.py` (którego używa profil Enyo,
`ochrona_enyo`) nigdy go nie importuje ani nie wywołuje. Sprawdzone i
potwierdzone bezpieczne/generyczne dla Enyo: `hours_constraint.py`
(monthly_hours/balance liczą minuty per duty-shift), `availability_
constraint.py` (jawny wyjątek dla zmian duty_rotation), `objective.py`
(kary OPEN/CLOSE zawsze wychodzą 0 dla pracowników rotacji, bo te
zmienne są tam zawsze wyzerowane - nieszkodliwe, tylko marnowane
terminy), `constraints_basic.py`, `constraints_logic.py::
add_work_dependency_constraint` (ma już jawny wyjątek dla `duty_shift_ids`),
cały `duty_rotation_*.py`.

### Znaleziony i naprawiony konflikt: ręczna blokada dnia

**Problem:** `logic/generator/manual_constraint.py::add_manual_shift_constraints`
(ALWAYS_ON, działa dla każdego generowania) nie znało pięciu zmian
duty_rotation ani `DaySchedule.is_full_day`. Ręczne zablokowanie dnia
pracownikowi rotacji 24/7 (dwuklik na komórce w gridzie **lub** "Cała
doba (24h)" w Ustawieniach trybu szybkiego - obie ścieżki dostępne bez
żadnej blokady profilowej) próbowało dopasować godziny do starego modelu
OPEN/CLOSE/START/END. Zweryfikowane empirycznie na żywym
`AutoScheduleGenerator`: **jeden ręcznie zablokowany dzień robił model
INFEASIBLE dla całego miesiąca**, bo zablokowana zmiana najczęściej
rozwiązywała się na `SHIFT_OPEN` (godziny startu duty_rotation pokrywają
się z godzinami otwarcia lokalizacji), co wprost sprzeczne z
`add_duty_rotation_gate_constraint` (zawsze zeruje `SHIFT_OPEN` dla
pracowników rotacji). Kontrolny przebieg bez ręcznej blokady na tych
samych danych: FEASIBLE.

**Naprawa** (nowa, równoległa funkcja - decyzja użytkownika):

| Plik | Akcja | Przywrócić do main? |
|---|---|---|
| `logic/generator/duty_rotation_manual_constraint.py` (nowy plik, `add_duty_rotation_manual_shift_constraint`) | Odpowiednik `add_manual_shift_constraints` dla pięciu zmian duty_rotation - dopasowuje zablokowane godziny (albo `is_full_day`+start) do właściwej zmiany tej lokalizacji, w przeciwnym razie zeruje wszystkie zmiany duty tego dnia | TAK - czysto addytywny, main może go po prostu nie wpinać |
| `logic/generator/manual_constraint.py` | Jedna linijka: `if shop.get_location(emp).get_duty_rotation(): continue` na początku pętli po pracownikach - pomija pracowników rotacji 24/7 (nowa funkcja ich przejmuje) | TAK do main jest bezpieczne (no-op tam, gdzie żadna lokalizacja nie ma duty_rotation), ale main nie MUSI tego mieć, skoro tam duty_rotation dla Dino i tak nie istnieje |
| `logic/generator/base_specs.py` | Nowy `ConstraintSpec("duty_rotation_manual_shift", ...)` w `_build_always_on_specs()`, ten sam wzorzec co `duty_rotation_gate` (`if ctx.duty_shifts is not None`) | TAK |
| `tests/test_duty_rotation_manual_constraint.py` (nowy plik, 8 testów) | Testy izolowane (ConstraintSpec wprost) + end-to-end przez `AutoScheduleGenerator` odtwarzające dokładnie ten scenariusz, który wcześniej dawał INFEASIBLE | TAK |

**Weryfikacja:** 369/369 testów przechodzi (361 sprzed tej zmiany + 8
nowych), 1 świadomie pominięty test bez zmian. Reprodukcja z audytu
(ręczna blokada `06:00-22:00` na dzień tygodnia) po naprawie: FEASIBLE,
zablokowane godziny zachowane w wyniku.

**Mniejsze, nierozwiązane znalezisko przy okazji:** `diagnostics.py`
tłumaczy niewykonalność językiem Dino ("brak pracownika otwarcia") nawet
dla profilu Enyo, gdzie to pojęcie nie istnieje - myląca diagnostyka.
Niezgłoszone do naprawy, czeka na decyzję.

## Generator "pod klucz" dla Enyo (2026-09-19)

Realizacja pełnej listy wymagań generatora dla Enyo (obłożenie, L4/urlop,
równy podział godzin, "nie chce 24h w weekendy", 24h przerwy między
zmianami 24h, preferencja 12h+12h, priorytet "Umowa"). Mapowanie wymagań
na kod - co już istniało (wykorzystane bez zmian) i co jest nowe:

| Wymaganie | Status |
|---|---|
| Obłożenie 24/7 | ✅ już istniało - `duty_rotation_coverage_constraint` |
| Obłożenie w konkretnych godzinach otwarcia (nie-24/7) | ✅ już istniało - generyczna reguła `min_staff_with_role` (scope `open`+`close`) z kreatora profilu, ten sam mechanizm co obsada otwarcia/zamknięcia u Dino |
| L4/urlop | ✅ już istniało (`add_leave_constraints`) + naprawiony błąd celu godzinowego (patrz niżej) |
| Dni ręcznie zablokowane | ✅ naprawione w poprzedniej turze (`duty_rotation_manual_constraint.py`) |
| Równy podział godzin "w miarę możliwości" | ✅ już istniało - `add_workload_balance_penalty` (generyczne, już wpięte dla Enyo) |
| "Nie chce 24h w weekendy" | ✅ już istniało - `add_duty_rotation_no24h_gate_constraint` |
| Min. 24h przerwy między zmianami 24h | ✅ już istniało, i to w wersji dokładniejszej niż proszona - `duty_rotation_rest_constraint.py` liczy (N-1)×24h wg liczby chętnych/zdolnych do rotacji, nigdy mniej niż 24h |
| Preferencja 12h+12h zamiast 24h | 🆕 NOWE - `logic/generator/duty_rotation_preference.py` |
| Priorytet "Umowa" w nominalnym czasie pracy | 🆕 NOWE - `logic/generator/priority_hours_constraint.py` |
| Bug L4/urlop w nominalnym czasie pracy (zgłoszony) | 🐛 ZNALEZIONY I NAPRAWIONY - `hours_constraint.py` + `monthly_hours_status.py` (dotyczy też Dino, autoryzowane) |

### Nowe pliki (czysto Enyo, addytywne)

| Plik | Co robi | Przywrócić do main? |
|---|---|---|
| `logic/generator/duty_rotation_preference.py` | Miękka kara za każde przypisanie `weekend_full` - zachęca solver do wyboru 12h+12h zamiast 24h, gdy oba warianty są osiągalne (nigdy nie blokuje 24h, gdy podział niemożliwy) | TAK |
| `logic/generator/priority_hours_constraint.py` | Bardzo mocno ważony (10000) term "niedobór poniżej nominału" TYLKO dla pracowników z rolą `umowa` - działa niezależnie od tego, czy balance/monthly_hours są w ogóle włączone dla profilu | TAK |
| `logic/generator/custom_profile_wiring.py` (`build_objective_terms`) | Podpięcie obu powyższych | NIE (main nie ma pojęcia "Umowa"/duty_rotation split - to specyficzne dla Enyo, ale bez szkody, gdyby zostało) |
| `tests/test_priority_hours_and_duty_preference.py` (nowy, 5 testów) | Izolowane + end-to-end przez `AutoScheduleGenerator` - zweryfikowane empirycznie: pracownik "Umowa" trafia dokładnie w nominał (176h) przy realnym niedoborze (8 pracowników / 31 dni rotacji), reszta dostaje co zostało; przy 2 dostępnych pracownikach na weekend solver w 100% wybiera 12h+12h zamiast 24h | TAK |

**Decyzje podjęte z użytkownikiem:** priorytet "Umowa" jako bardzo wysoka
waga miękka (nie twardy MANDATORY) - generator ma zawsze znaleźć
rozwiązanie, nawet gdy w danym miesiącu fizycznie zabraknie godzin dla
wszystkich Umowa (np. przez L4 innych).

### Naprawiony bug: cel godzinowy dla L4/urlopu (dotyczy Dino i Enyo)

**Problem** (znaleziony na żądanie użytkownika, potwierdzony liczbowo):
`add_monthly_hours_constraint`/`add_balance_constraint`
(`logic/generator/hours_constraint.py`) liczyły cel jako
`nominał - L4 - urlop`, bez dolnego ograniczenia na 0.

- Pracownik na L4/urlopie przez **cały miesiąc** → cel wychodził **ujemny**
  (np. -87.5h dla pełnego etatu, marzec, 8.5h/dzień).
- Generator poprawnie przydzielał mu 0 godzin, ale skoro cel był ujemny,
  `add_monthly_hours_constraint` liczyło to jako **87.5h fikcyjnej
  "nadwyżki"** w funkcji celu - kara dla kogoś, kto nic złego nie zrobił.
- Przy `monthly_hours` = MANDATORY to samo mogło zrobić model
  **niewykonalnym w ogóle** (górna granica pasma schodziła poniżej 0,
  sprzecznie z `total_minutes >= 0`).
- `add_balance_constraint` miała ten sam problem w gorszej wersji - **w
  ogóle nie odejmowała L4/urlopu** od celu przed tą poprawką.

**Naprawa** (za zgodą użytkownika, dotyczy też Dino):

| Plik | Zmiana | Testy Dino |
|---|---|---|
| `logic/generator/hours_constraint.py::add_monthly_hours_constraint` | `target_minutes` przycięty do min. 0 | ✅ |
| `logic/generator/hours_constraint.py::add_balance_constraint` | Dodane odejmowanie L4/urlopu (nowy parametr `schedule`) + przycięcie do 0 | ✅ |
| `logic/generator/base_specs.py::_build_balance` | Przekazanie `ctx.schedule` do zmienionej sygnatury | ✅ |
| `logic/monthly_hours_status.py` | Ten sam clamp - używane przez podświetlanie "Nadgodziny" w gridzie/eksportach (musi zostać w synchronizacji z generatorem) | ✅ |
| `tests/test_night_shift_constraint.py` | Zaktualizowane jedno wywołanie `add_balance_constraint` pod nową sygnaturę | ✅ |
| `tests/test_hours_leave_sick_target.py` (nowy, 5 testów) | Regresja: pełny miesiąc L4/urlop → cel=0, zero fikcyjnej kary, MANDATORY nie jest już niewykonalny; częściowy L4/urlop → liczby bez zmian względem sprzed poprawki | ✅ |

**Weryfikacja:** pełny zestaw testów (Dino + Enyo) - **379/380 przechodzi,
1 świadomie pominięty** (bez zmian względem stanu przed tą turą). Zero
regresji na danych Dino.

## Dane testowe z realnych grafików klienta (2026-09-19)

Wyłącznie przygotowanie danych testowych - **żaden plik produkcyjny nie
został zmieniony w tym kroku**. Źródło: użytkownik ręcznie przepisał ze
zdjęć papierowych kart grafiku prawdziwego klienta (firma
ochroniarska/serwisowa, 9 placówek), część odczytów jawnie oznaczona jako
niepewna/nieczytelna.

### Nowe pliki (czysto addytywne, dane testowe)

| Plik | Co robi | Przywrócić do main? |
|---|---|---|
| `demo/install_client_sample_data.py` | Rejestruje tymczasowy profil biznesowy `ochrona_dane_klienta_test` (role: `umowa`, `nie_chce_24h`) w `%LOCALAPPDATA%\GrafikDino\custom_profiles.json` i zapisuje `test_data/dane_klienta_ochrona.json` - analogicznie do `demo/install_demo.py`, ale z realnymi nazwiskami/wzorcem zmian zamiast syntetycznych danych | NIE - dane jednego konkretnego klienta testowego, nie mają sensu w main |
| `test_data/dane_klienta_ochrona.json` | Gotowy projekt (2 lokalizacje, 11 pracowników, październik 2026, pusty grafik) do otwarcia w programie po uruchomieniu skryptu wyżej | NIE (jw.) |

**Jak użyć:** uruchom `python demo/install_client_sample_data.py` **na
własnej maszynie Windows** (rejestracja profilu zapisuje się do
`%LOCALAPPDATA%`, które nie istnieje w środowisku, w którym te dane
zostały przygotowane) - dopiero potem otwórz
`test_data/dane_klienta_ochrona.json` przez "Plik -> Otwórz projekt..." w
programie. Bez tego kroku program nie rozpozna `business_type`
(`get_custom_profile()` zwróci `None`) i cofnie się do generatora Dino
zamiast Enyo.

### Placówki, które PASUJĄ do dzisiejszego modelu duty_rotation (2/9)

`normalize_duty_rotation()` (`model/location.py`) wymaga **kompletnego**
schematu rotacji - nie da się skonfigurować samej zmiany dziennej bez
nocnej (albo samego 24h bez wariantu podziału). Tylko te dwie placówki
miały w danych źródłowych wystarczające potwierdzenie obu wymaganych
elementów schematu:

1. **Ubojnia Drobiu GOSZ - waga/biuro** (7 pracowników) - potwierdzony
   wzorzec 8:00-20:00 (dzień) + 20:00-8:00 (noc), naprzemiennie, każdego
   dnia tygodnia. Wszyscy pracownicy dostali rolę `nie_chce_24h`, bo w
   realnych danych nigdy nie widać pojedynczej zmiany 24h w tej placówce.
2. **PGE Ustka, ul. Westerplatte 4** (4 z 6 wypisanych pracowników - 2
   nazwiska nieczytelne/skreślone, pominięte) - potwierdzony wzorzec "8/8"
   powtarzający się codziennie, czyli zmiana 24h. Żaden pracownik NIE
   dostał `nie_chce_24h` - świadomie, żeby zobaczyć, czy nowa preferencja
   12h+12h (patrz niżej) zacznie w praktyce sugerować podział, którego ta
   konkretna placówka historycznie nigdy nie stosowała.

### Placówki, które NIE pasują do dzisiejszego modelu (7/9) - do wyjaśnienia z klientem

Zgodnie z instrukcją: żadna z nich nie została "dociągnięta na siłę" do
modelu duty_rotation. Każda wymaga innej zmiany w produkcyjnym kodzie
(albo po prostu więcej danych od klienta), zanim da się ją sensownie
zamodelować:

| Placówka | Dlaczego nie pasuje |
|---|---|
| **GZUK** | W danych źródłowych widać pojedyncze liczby (godziny), nie pary start/koniec zmiany - nie da się odróżnić, czy to krótka wizyta, czy fragment dłuższej zmiany, bez zgadywania. Potwierdza własne podejrzenie użytkownika. |
| **Lakpol** | To samo co GZUK - pojedyncze liczby, nie pary zmian. |
| **Brico Marche Wejcherowo** | Widać tylko zmianę dzienną, brak jakiegokolwiek potwierdzonego wzorca nocnego/uzupełniającego w źródle - `normalize_duty_rotation()` wymaga kompletnego schematu (dzień+noc), nie da się skonfigurować samej połowy. |
| **Bricomarche Lębork** | Ten sam problem co Wejcherowo - brak potwierdzonego wzorca nocnego. |
| **Łeba Apartamenty** | Godziny w źródle nieczytelne - nie da się odczytać nawet w przybliżeniu, więc nie ma z czego zbudować wzorca bez zgadywania. |
| **Nadleśnictwo Cewice** (obie tabele) | Główna tabela: brak jakichkolwiek czytelnych godzin. Osobna tabela "Sprzątanie": to inna rola/inny wzorzec pracy niż ochrona (dzienna, bez zmiany nocnej) - potwierdza własną obserwację użytkownika, że to nie pasuje do rotacji 24/7. |
| **MZGK Krzywoustego** | W źródle jest tylko ogólne wrażenie zakresu godzin, bez konkretnych par X/Y - zbyt mało, żeby zbudować cokolwiek bez wymyślania danych. |

**Rekomendacja:** przed próbą zakodowania którejkolwiek z tych 7 placówek
- doprecyzować z klientem konkretne godziny start/koniec każdej zmiany
(najlepiej w formacie X/Y jak reszta danych), a dla Nadleśnictwa/GZUK/Lakpol
ustalić, czy to w ogóle model rotacji 24h, czy zupełnie inny typ grafiku
(pojedyncze wizyty, zmiana czysto dzienna) - może wymagać nowego,
osobnego mechanizmu w generatorze, nie tylko nowej konfiguracji istniejącego.

### Rzeczy niepewne/nieczytelne do potwierdzenia z Michałem

- Ubojnia Drobiu GOSZ: wpisy przy datach 7/15 i 7/16 w źródle nie zostały
  odzwierciedlone w wygenerowanym JSON (niejasne, czy to inny wzorzec czy
  błąd odczytu) - do sprawdzenia bezpośrednio na oryginalnym zdjęciu.
- Kto konkretnie z 7 pracowników Ubojni realizuje który z 4 typów zmian
  (dzień/noc) w danym dniu - w tej wersji danych to generator dobiera
  sam, ale realny, już ustalony grafik może mieć konkretne, stałe pary/
  kolejność, których nie było widać wprost w źródle.
- PGE Ustka: 2 z 6 wypisanych nazwisk nieczytelne/skreślone - pominięte
  w danych testowych (tylko 4 pracowników zamiast 6).
- Nikt w żadnej z 2 placówek nie ma ustawionej flagi "Umowa" - z samych
  zdjęć nie da się stwierdzić, kto ją ma. Profil definiuje tę rolę, więc
  da się ją zaznaczyć ręcznie w UI (Edytuj pracownika) po potwierdzeniu.
- Wszystkie pozostałe niepewne odczyty oznaczone wprost przez użytkownika
  przy pierwotnym przepisywaniu danych (patrz oryginalna wiadomość) -
  niniejszy plik nie duplikuje ich słowo w słowo, tylko te, które wpływają
  bezpośrednio na wygenerowany plik testowy powyżej.

### Wynik weryfikacji (uruchomienie generatora na tych danych)

`AutoScheduleGenerator.generate()` na `dane_klienta_ochrona.json` (październik
2026, limit solvera 60s) zwraca **OPTIMAL / success=True** - pełne pokrycie
obu placówek, żadnej infeasibility.

**Obserwacja warta uwagi klienta:** dla PGE Ustka - placówki, gdzie
historyczne dane ZAWSZE pokazują pojedynczą zmianę 24h i żaden pracownik
nie ma tu `nie_chce_24h` - solver mimo to na części dni (np. pracownik
Kaufman M., dni 4-5) wybrał podział 12h+12h zamiast zmiany 24h. To
bezpośredni efekt nowej miękkiej preferencji
`duty_rotation_preference.py` (dodanej na życzenie użytkownika jako ogólny
mechanizm Enyo) - pokrycie jest poprawne w obu wariantach, ale wynik nie
odzwierciedla stylu pracy, jaki ta konkretna placówka historycznie
stosowała. To nie błąd generatora (obie zmiany są dozwolone i pokrywają
dobę), ale różnica w praktyce warta przedyskutowania z klientem: czy
preferencja podziału powinna być per-lokalizacja wyłączalna (podobnie jak
`nie_chce_24h` per-pracownik), zamiast globalnej dla każdej placówki z
rotacją 24/7. Żadna zmiana kodu nie została zrobiona w tym kroku - to
tylko obserwacja z testu na realnych danych.
