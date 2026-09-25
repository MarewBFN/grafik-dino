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

## Sweep testów: L4/urlop i różne długości zmian (2026-09-19)

Na żądanie użytkownika: sweep testów sprawdzający, jak generator reaguje
"przed" i "po" wygenerowaniu na różne ILOŚCI L4/urlopu, oraz czy
gate/coverage/rest/kalkulacja minut duty_rotation generalizują się poza
jedyny dotąd testowany, zahardkodowany zestaw godzin (06:00/18:00/22:00).
**Wynik: żaden błąd produkcyjny nie został znaleziony - tylko nowe testy,
kod generatora bez zmian.**

### Nowe pliki testowe

| Plik | Co sprawdza | Przywrócić do main? |
|---|---|---|
| `tests/test_leave_sick_generation_sweep.py` (31 testów) | Sweep 0%/26%/48%/74%/100% miesiąca L4/urlopu (osobno i mieszane), "przed" (`monthly_hours_status`) i "po" (pełny `AutoScheduleGenerator.generate()`) - na ścieżce rotacji 24/7 (Enyo) I zwykłej (Dino open/close). Dodatkowo: pula 2 pracowników z długim L4 -> obsada 24/7 fizycznie niemożliwa - sprawdza, że generator zgłasza to jako `success=False` + niepustą diagnostykę, z pełnym rollbackiem grafiku, zamiast zwrócić błędny wynik. | TAK - ogólne, nie-Enyo-specyficzne testy generatora |
| `tests/test_duty_rotation_shift_length_variants.py` (27 testów) | To samo gate/coverage/rest/preferencja/kalkulacja minut co istniejące testy duty_rotation, ale przy 5 różnych "kształtach" zmian zamiast jedynego dotąd testowanego (06:00/18:00/22:00): "8/8" (24h @08, realny wzorzec PGE Ustka), "7/7" (24h @07), "8/16" i "9/17" (podział asymetryczny 8h+16h, dwa różne anchory), anchor na pół godziny (08:30). Plus 3 pełne uruchomienia generatora na kształtach 1:1 z realnymi danymi klienta (PGE Ustka, Ubojnia GOSZ) i na nowym kształcie (tydzień @09:00-17:00 + weekend @06:00, dwa niezależne anchory w jednym projekcie). | TAK - ogólne testy duty_rotation, nie Enyo-specyficzne |

### Co potwierdzono (wszystko już działało poprawnie, bez zmian w kodzie)

- **Obsada 24/7 zawsze pełna niezależnie od ilości L4/urlopu** - dopóki
  pozostali pracownicy fizycznie wystarczają, pokrycie (MANDATORY) trzyma
  się w 100% na każdym punkcie sweepu (0-100% miesiąca).
- **Brak fikcyjnego "dobijania" nadgodzin** - target/worked po
  wygenerowaniu zawsze spójne z klamrowaną formułą (poprawka z poprzedniej
  tury), także przy minutach 12h/24h zmian rotacji, nie tylko przy
  "zwykłych" zmianach o stałej długości.
- **Graceful infeasibility** - scenariusz fizycznie niemożliwy do pokrycia
  (2 pracowników, jeden na długim L4) daje kontrolowane `success=False` z
  diagnostyką, a stan grafiku wraca dokładnie do sprzed próby generowania
  (bez żadnych częściowych przypisań).
- **Gate/coverage/rest/preferencja duty_rotation są w pełni generyczne** -
  żaden z mechanizmów nie okazał się przypadkiem przywiązany do
  06:00/18:00/22:00 - te same reguły (11h odpoczynku dla połówek, (N-1)×24h
  dla pełnej doby, dokładnie 1 osoba na typ zmiany) trzymają się
  identycznie przy dowolnych, w tym niecałogodzinnych, godzinach startu.
- Jedyny "błąd" znaleziony podczas pisania tych testów był we własnych
  fixture'ach testowych (m.in. profil "zerowy" bez ról `is_opener`/`is_meat`
  dla Dino okazał się strukturalnie niewykonalny niezależnie od L4 -
  wymóg obsady działu mięsnego jest realną, wcześniej istniejącą regułą
  Dino, nie błędem), nie w kodzie generatora.

**Weryfikacja:** pełny zestaw testów - **437/438 przechodzi, 1 świadomie
pominięty** (bez zmian względem stanu przed tą turą; 58 nowych testów, 0
regresji).

### Projekt do wizualnej inspekcji kształtów rotacji w programie (2026-09-19)

Na żądanie użytkownika: `demo/install_test_shapes_project.py` (nowy plik,
wzorowany na `demo/install_client_sample_data.py`) zbiera WSZYSTKIE
placówki z powyższego sweepu testów (2 realne z danych klienta + 5
syntetycznych kształtów: 7/7, 8/16, 9/17, anchor 08:30, tydzień
09:00-17:00+weekend 06:00) w jeden projekt, zapisywany prosto do
`last_project.json` (auto-wczytywany przy starcie programu) - żeby dało
się je zobaczyć/wygenerować w realnym UI, nie tylko przez asercje pytest.
Rejestruje profil `test_duty_rotation_shapes` w prawdziwym
`%LOCALAPPDATA%` (na maszynie użytkownika, nie w sandboxie) - działa od
razu po `python demo/install_test_shapes_project.py` + `python main.py`.

Zweryfikowane przed przekazaniem: `AutoScheduleGenerator.generate()` na
całym projekcie (30 pracowników, 7 lokalizacji, październik 2026) ->
**OPTIMAL**, pełne pokrycie każdej placówki każdego dnia. Poprzedni,
niezwiązany `last_project.json` użytkownika (własne dane testowe,
"Test"-owe nazwiska) skasowany za jego zgodą przed nadpisaniem.

| Plik | Przywrócić do main? |
|---|---|
| `demo/install_test_shapes_project.py` | NIE - czysto lokalny/demonstracyjny, specyficzny dla tej sesji testowej |

### Naprawiony bug: ręczne "wolne" (OFF) nie blokowało zmian duty_rotation, gdy is_day_off nie było ustawione (2026-09-19)

**Zgłoszenie użytkownika:** generator zwracał OPTIMAL, ale zapisany grafik
miał niepokryty dzień, mimo że fizycznie 2 wolnych pracowników z 4-osobowej
załogi powinno wystarczyć. Zweryfikowane na realnym `last_project.json`
użytkownika (nie problem ze starym .exe - użytkownik testował przez
`python main.py` na aktualnym branchu).

**Root cause:** `ui/grid_view.py` ma DRUGĄ, niezależną od
`ScheduleController.set_day_free()` ścieżkę ustawiania "wolne" (akcja "OFF"
w dropdownie na komórce, ok. linia 1337) - czyści `start`/`end` i ustawia
`is_locked=True`, ale NIE ustawia `is_day_off=True`.
`duty_rotation_manual_constraint.py` (dodany w poprzedniej turze) zakładał,
że taki dzień jest "już obsłużony generycznie" przez `add_day_off_constraints`
(sprawdza `is_day_off`) i nic nie wymuszał dla `is_locked` + pusty `start`.
Skutek: solver miał wolną rękę przypisać temu pracownikowi zmianę duty,
spełniając sobie coverage WEWNĘTRZNIE (model raportował OPTIMAL) - ale
`solution_mapper` (patrz `[SKIP LOCKED]`) i tak nic nie zapisywał dla tej
komórki, bo `is_locked=True`. Efekt: pozornie kompletny grafik z
niepokrytym dniem, mimo statusu OPTIMAL. Stary model
(`manual_constraint.py`) nie ma tego problemu - traktuje `is_locked` + pusty
`start` jako wystarczający sygnał samodzielnie, nie zależy od `is_day_off`.

**Naprawa:** `duty_rotation_manual_constraint.py` teraz też traktuje
`is_locked` + pusty `start` jako wystarczający sygnał (jak stary model) -
wymusza `x[e,d,s]==0` na każdej z pięciu zmian duty tego
pracownika/dnia, niezależnie od tego, czy `is_day_off` jest ustawione.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `logic/generator/duty_rotation_manual_constraint.py` | `if not getattr(day_state, "start", None): continue` -> wymusza `x[e,d,s]==0` na wszystkich zmianach duty przed `continue` | TAK |
| `tests/test_duty_rotation_manual_constraint.py` (+2 testy) | Izolowany (dokładnie replikuje pola ustawiane przez `ui/grid_view.py`, nie `ScheduleController`) + end-to-end (4-osobowa placówka, 2 zablokowane "OFF", sprawdza że pozostali 2 faktycznie pokrywają dzień w zapisanym wyniku) | TAK |

**Weryfikacja:** 439/440 testów przechodzi (1 świadomie pominięty, bez
zmian), 2 nowe testy, zero regresji. Naprawa zweryfikowana bezpośrednio na
zgłoszonym przez użytkownika `last_project.json` - wszystkie 4 wcześniej
niepokryte dni (`test_9_17_split` dni 7/8, `test_8_16_split` dzień 12,
`test_anchor_0830` dzień 9) teraz poprawnie pokryte przez pozostałych
wolnych pracowników, status OPTIMAL. Plik przeliczony i zapisany ponownie
(lokalnie, `last_project.json` jest w `.gitignore`).

## Runda UI/UX + bug fixy na życzenie klienta (2026-09-20)

Duża, wieloczęściowa runda: kilka rzeczy ukrytych dla Enyo (tabela niżej) +
kilka realnych bugów naprawionych (dotyczą też Dino, gdzie nie zaznaczono
inaczej). Ustalone z użytkownikiem: "Progi obsady" per-lokalizacja i cała
sekcja "Nazwa i Profil placówki"/zakładka "Limity" w Konfiguracji - tylko
ukryte (`.hide()`), dane i mechanizm w generatorze zostają w pełni
działające, tym samym wzorcem co wcześniejsze `settlement_section.hide()`.

### Ukryte dla Enyo (dane/logika zostają)

| Co | Gdzie | Notatka |
|---|---|---|
| Sekcja "Progi obsady dla tej lokalizacji" (dni pod rząd + progi `min. N osób z rolą X`) | `ui/locations_dialog.py::_LocationRow` (`self.thresholds_container`) | Generator nadal je czyta (`base_specs.py`, `generic_rules.py`) - tylko niedostępne z UI |
| Sekcja "Nazwa i Profil placówki" (nazwa placówki + wybór profilu biznesowego) | `ui/config_dialog.py` (`self.facility_header`) | Klient ma jeden, gotowy profil "Ochrona" i jedną placówkę (kilka lokalizacji) |
| Zakładka "Limity" (limity dni pod rząd, wymiar zmiany, rotacja 24/7 "tylko 12/24h", flagi) | `ui/config_dialog.py` (`self.limits_tab`, budowany ale nie dodany do `self.tabs`) | Nieużywana przez klienta - wartości zostają na ostatnio zapisanych/domyślnych |
| Krok samouczka "Okres rozliczeniowy" | `ui/main_window.py::_build_tutorial_steps` | Celował w `btn_settlement_toggle`, który jest schowany (`settlement_section.hide()`) - usunięty, nie tylko ukryty, bo wskazywałby na niewidoczny przycisk |
| Krok samouczka "Limity" + indeksy zakładek na sztywno | `ui/config_dialog.py::_build_tutorial_steps` (osobny, wewnętrzny samouczek tego okna, uruchamiany przyciskiem "Pomoc"/przy pierwszym otwarciu) | Krok "Limity" usunięty (zakładka schowana); "Niedziele handlowe" pokazuje się tylko gdy realnie istnieje (`self._tab_index_sundays`); indeksy zakładek śledzone jawnie zamiast `setCurrentIndex(2)`/`(3)` na sztywno, bo teraz się przesuwają |

Numeracja kroków obu samouczków ("Krok X z Y", `ui/tutorial_overlay.py`) była
już policzona dynamicznie z `len(steps)` - usuwanie kroków nie tworzy "dziur".

### Naprawiony bug: godziny otwarcia nieużywane spójnie przez generator

**Problem:** projekt ma dwa niezależne miejsca na "godziny otwarcia" -
`ShopConfig.open_hours` (Konfiguracja -> "Godziny otwarcia", poziom
projektu) i `LocationConfig.open_hours` (Lokalizacje, poziom lokalizacji).
Zgodne tylko raz, przy tworzeniu lokalizacji - potem edycja jednego nie
aktualizuje drugiego. Ustalone z użytkownikiem: **lokalizacja jest źródłem
prawdy**. Kilka miejsc czytało jednak zawsze godziny projektu:

| Plik | Naprawione | Notatka |
|---|---|---|
| `logic/generator/objective.py::add_morning_afternoon_balance_penalty` | TAK | Przebudowane: godziny liczone teraz per pracownik/lokalizacja WEWNĄTRZ pętli po pracownikach (wcześniej raz na dzień, przed pętlą) |
| `logic/settlement_balancer.py::classify_editable_side` | TAK | Nowy parametr `emp` (opcjonalny, dla zgodności wstecznej) |
| `logic/generator/solution_mapper.py` (blok debug "VERIFY AFTER SAVE") | TAK | Kosmetyczne (tylko `print`), ale poprawione dla spójności |
| `logic/generator/trace.py::build_random_project` | TAK | Generator danych testowych/stress, nie produkcyjna logika |
| `logic/schedule_controller.py::set_shift` (gałąź WORK bez podanych start/end) | TAK | |
| `logic/generator/meat_constraint.py`, `meat_light_budget.py`, `logic/generator/diagnostics.py::build_infeasibility_summary` | NIE | Świadomie pominięte - koncepty specyficzne dla profilu `dino_retail` (mięso, `min_open_staff`/`min_close_staff`), który jest wykluczony z `visible_profiles()` w tym buildzie - nieosiągalne dla Enyo, a naprawa wymagałaby przebudowy z pojedynczej siatki "cały dzień" na siatkę per-lokalizacja bez żadnej korzyści dla klienta |

**Dodatkowo znaleziony, powiązany bug (ta sama przyczyna):**
`ui/main_window.py::_open_header_menu` (dwuklik na nagłówku dnia w
gridzie) zapisywał ręczne nadpisanie godzin/święta na
`shop_config.day_overrides`/`public_holidays` (poziom projektu) zamiast na
`day_overrides`/`public_holidays` AKTUALNIE przeglądanej lokalizacji -
generator (przez `shop.get_location(emp)`) w ogóle tego nie widział.
Naprawione: teraz pisze do `self.shop_config.locations[selected_location_key]`.
To też naprawia zgłoszony bug tooltipów w gridzie (nie odświeżały się po
zmianie godzin) - `ui/grid_view.py::_day_header_tooltip`/nagłówkowy znacznik
"zmienione ręcznie" czytały już poprawnie per-lokalizacyjne dane, tylko
zapis szedł w złe miejsce.

**"Godziny otwarcia" w Konfiguracji nie zniknęła** - po feedbacku klienta
(2026-09-20) edytuje teraz wprost godziny AKTUALNIE WYBRANEJ lokalizacji
(`ui/config_dialog.py::ConfigDialog.__init__(location_key=...)`, przekazywane
z `main_window.py::_open_config` jako `self.selected_location_key`) -
dokładnie te same dane co w oknie Lokalizacje dla tej lokalizacji, z
etykietą "Edytujesz godziny otwarcia w placówce X" nad edytorem. `ui/
locations_dialog.py` "Dodaj lokalizację" nadal zaciąga
`ShopConfig.open_hours` jako punkt startowy dla NOWEJ lokalizacji - to pole
zostaje w modelu jako "zamrożony" szablon początkowy, ale nie ma już
własnej zakładki do edycji.

### Inne naprawione bugi (ogólne, nie Enyo-specyficzne)

- **Kopiuj/wklej dnia w gridzie nie działało dla nocnych/24h/urlopu/L4/
  zablokowanego typu zmiany** - `ui/grid_view.py` (Ctrl+C/Ctrl+V i menu
  kontekstowe) wklejało wyłącznie start/end przez `set_day_hours`, gubiąc
  resztę stanu i po cichu odrzucając wklejenie, gdy `end<=start` (noc/24h).
  Nowe `ScheduleController.copy_day_snapshot()`/`paste_day_snapshot()`
  przenoszą pełny stan dnia, delegując do istniejących `set_day_*()` (więc
  ta sama walidacja co przy ręcznym wpisywaniu). Uwaga do świadomości: w
  `ui/main_window.py` jest DRUGI, martwy zestaw kopiuj/wklej (`_ctx_copy`/
  `_ctx_paste`/`_open_day_context_menu`, podpięty jako `on_context_menu`) -
  nigdy nieużywany, bo `ScheduleGrid.contextMenuEvent` buduje własne menu i
  nie wywołuje tego callbacku. Nietknięty w tej turze (poza zakresem
  zgłoszenia), ale klient/main powinien wiedzieć, że tamta, bogatsza wersja
  menu (Rano/Zamknięcie/Zablokuj rano/popołudnie) jest dziś nieosiągalna.
- **Dwa checkboxy "nie chce 24h" w oknie Edytuj pracownika** -
  `ui/employee_dialog.py` pokazywał generyczny checkbox z pętli ról profilu
  ORAZ dedykowany `self.no_24h_check` (gated na `_project_uses_duty_rotation()`)
  jednocześnie, gdy oba warunki były spełnione - `_save()` zawsze nadpisywał
  wynik dedykowanym, czyniąc generyczny martwym w tym scenariuszu. Ten klucz
  (`nie_chce_24h`) ma sens WYŁĄCZNIE w kontekście rotacji 24/7, więc usunięty
  z generycznej pętli ról całkowicie - dedykowany checkbox (poprawnie gated)
  zostaje jedynym.
- **Checkbox "Zmiana nocna (22:00-6:00)" w edycji dnia** -
  `ui/day_edit_dialog.py` - stara funkcjonalność sprzed automatycznego
  wykrywania nocy z godzin otwarcia. Usunięty; ręczne wpisanie configured
  night window (np. 22:00/06:00) bezpośrednio w pola Start/Koniec działa
  teraz wprost (walidacja `_save()` akceptuje `end<=start` tylko gdy to
  dokładnie skonfigurowane okno nocne, tak jak `schedule_controller.py`).

### Nowe funkcje na życzenie klienta

- **Limit 35 znaków na nazwę lokalizacji** (`ui/locations_dialog.py`) +
  nowy `ui/marquee_text.py` (`MarqueeButton`/`MarqueeLabel`) - długa nazwa
  nie wpływa już na `sizeHint`/szerokość paska bocznego w
  `ui/main_window.py`; gdy nazwa i tak się nie mieści, przewija się w
  kółko (marquee) zamiast rozjeżdżać layout.
- **Karty pracy pracowników** (`export/employee_card_exporter.py`) - kolumna
  "Dzienne / Nocne" (etykieta) rozdzielona na "Godziny dzienne"/"Godziny
  nocne" (liczba godzin per dzień, próg 22:00-06:00). Usunięta kolumna na
  podpis w każdym dniu - zostaje jedna komórka na podpis na dole strony
  (podpisana "Podpis pracownika:", w JPG/PDF i w Excelu).
- **Przycisk "+ Dodaj własne..." w trybie szybkim** (`ui/main_window.py`) -
  otwiera istniejące okno `QuickModeSettingsDialog` (wcześniej dostępne
  tylko przez Konfiguracja -> "Ustawienia trybu szybkiego").
- **Ikony przy nazwie pracownika** dla roli `umowa` (dokument) i
  `nie_chce_24h` (przekreślone "24h") - `ui/grid_view.py`
  (`_build_contract_icon`/`_build_no_24h_icon`, ta sama technika co
  istniejące `_build_no_night_icon`/`_build_no_afternoon_icon`).
- **Toggle "Nieczynne" per dzień tygodnia/dzień z nadpisaniem** -
  `ui/weekly_hours_editor.py` (współdzielony przez Konfiguracja ->
  "Godziny otwarcia" i Lokalizacje) oraz `ui/day_override_dialog.py`
  (dwuklik na nagłówku dnia w gridzie). Zamknięty dzień reprezentowany jako
  `(None, None)` - konwencja, którą `get_open_hours_for_day()` już
  rozumiał, tylko UI nie umiało jej wcześniej wyprodukować.

**Weryfikacja:** pełny zestaw testów zielony (patrz commit), plus nowe
testy: `tests/test_copy_paste_day.py`, `tests/test_closed_day_toggle.py`,
`tests/test_grid_view_day_header_tooltip.py`, rozszerzenia w
`tests/test_employee_card_exporter.py`, `tests/test_settlement_balancer.py`,
`tests/test_night_shift_manual_editing.py`.

### Doprecyzowanie po feedbacku klienta (2026-09-20, ta sama runda)

- **Nieczynny dzień wyszarza komórki w gridzie** (jak dawniej w Dino) -
  `ui/grid_view.py::_fill_day_cells` i `logic/schedule_presenter.py::
  get_cell_view` sprawdzały dotąd tylko `shop_config.is_trade_day(day)`
  (poziom projektu, tylko święta/niedziele handlowe) - teraz sprawdzają
  `shop.get_location(emp).get_open_hours_for_day(day) is None`, co pokrywa
  ORAZ nowy toggle "Nieczynne" (dowolny dzień tygodnia/nadpisanie), ORAZ
  jest poprawnie per-lokalizacyjne.
- **Konfiguracja -> "Godziny otwarcia" edytuje wybraną lokalizację
  wprost** - patrz wyżej (zastępuje poprzednie zachowanie "tylko szablon
  dla nowych lokalizacji" z tej samej rundy, na wyraźne życzenie klienta).
- **Zwijanie/rozwijanie godzin otwarcia w oknie Lokalizacje** -
  `ui/locations_dialog.py::_LocationRow` - przycisk "Rozwiń"/"Zwiń"
  wycentrowany w prawo w wierszu z checkboxem "Działalność całodobowa
  (24/7)" (wycentrowanym w lewo), pokazuje/chowa `WeeklyHoursEditor`.
  Domyślnie zwinięte (czytelność listy lokalizacji). Dla lokalizacji 24/7
  ani przycisk, ani edytor się nie pokazują (nie ma czego edytować - cały
  tydzień to zawsze 00:00-23:45).

**Weryfikacja:** pełny zestaw testów zielony, plus nowe testy w
`tests/test_location_presentation.py` (wyszarzanie zamkniętych dni) i
nowy `tests/test_location_hours_editing_ui.py` (edycja godzin lokalizacji
przez Konfigurację + zwijanie/rozwijanie w Lokalizacjach).

### Naprawiony bug: niedziela wyszarzona mimo braku niedzieli handlowej (2026-09-20, ta sama runda)

**Zgłoszenie użytkownika:** grafik wyszarzał niedzielę w gridzie, mimo że
nie została oznaczona jako "niepracująca" - i to niezależnie od tego, czy
w Dino niedziela zostałaby kiedyś zaznaczona jako pracująca (domyślnie nie).

**Root cause:** `ShopConfig.is_trade_day()` już dawno miał zabezpieczenie
"profile bez kalendarza handlowego (`BusinessProfile.uses_trade_calendar`)
traktują każdy dzień jako normalny, roboczy" - ale `LocationConfig.
is_trade_day()`/`get_open_hours_for_day()` (poziom lokalizacji) NIGDY tego
zabezpieczenia nie miały, bo LocationConfig nie zna `business_type`.
Dopóki cały kod czytał godziny z poziomu `ShopConfig` wprost, bug był
niewidoczny - ujawnił się dopiero, gdy w tej samej rundzie (feedback
"lokalizacja jest źródłem prawdy") przełączono `ui/grid_view.py`/`logic/
schedule_presenter.py` na `shop.get_location(emp)`. Efekt: dla profilu
Enyo (bez kalendarza handlowego) KAŻDA niedziela wychodziła "zamknięta"
(`trade_sundays` puste domyślnie), niezależnie od realnych godzin otwarcia
tej lokalizacji.

**Naprawa:** `LocationConfig.is_trade_day()`/`get_open_hours_for_day()`
dostały nowy parametr `uses_trade_calendar` (domyślnie `True` - zachowuje
stare zachowanie dla wywołań, które go nie podają). `_LocationView`
(`model/shop_config.py`, to co zwraca `shop.get_location(emp)`) liczy tę
flagę raz, z `get_profile(shop.business_type).uses_trade_calendar`, i
przekazuje ją dalej - naprawia to od razu CAŁY generator (wszystkie miejsca
idące przez `shop.get_location(emp)`), bez osobnych poprawek per plik.
Dwa pozostałe miejsca czytające `LocationConfig` wprost (bez konkretnego
pracownika - `ui/grid_view.py::_day_header_tooltip`, `ui/main_window.py::
_open_header_menu`) dostały tę samą flagę jawnie.

| Plik | Zmiana |
|---|---|
| `model/location.py` | Nowy param `uses_trade_calendar=True` w `is_trade_day`/`get_open_hours_for_day` |
| `model/shop_config.py` (`_LocationView`, `get_location`) | Liczy i przekazuje flagę z profilu projektu |
| `ui/grid_view.py::_day_header_tooltip` | Jawnie przekazuje flagę do bezpośredniego wywołania na `LocationConfig` |
| `ui/main_window.py::_open_header_menu` | j.w. |
| `tests/test_location.py` (+5 testów), `tests/test_location_presentation.py` (+1 test) | Niedziela zostaje otwarta dla profilu bez kalendarza handlowego; zachowanie Dino (`uses_trade_calendar=True`) bez zmian |

**Weryfikacja:** pełny zestaw testów zielony, zero regresji na danych Dino

## Pamięć poprzedniego miesiąca (2026-09-21)

Nowy mechanizm generatora (nie ukrywanie ani bug fix) - dotyczy zarówno
Enyo, jak i Dino jednakowo. Zmiana miesiąca w tym samym projekcie
("Zmień datę", `ui/main_window.py::_save_date_clicked`) tworzy zupełnie
nowy `MonthSchedule` - do tej pory generator/GUI całkiem traciły, o której
godzinie każdy pracownik faktycznie skończył ostatnią zmianę w poprzednim
miesiącu, więc dzień 1 nowego miesiąca nigdy nie był chroniony 11h rest
constraintem względem tamtego końca (pierwszy dzień modelu nie ma "dnia
0" do porównania - luka istniała od zawsze, nie tylko przy tej funkcji).

**Zakres (świadomie wąski, ustalony z użytkownikiem):** jeden punkt danych
na pracownika - koniec ostatniej zmiany poprzedniego miesiąca + czy ta
zmiana wchodziła już w dzień 1 (`crosses_midnight`). Nie zawiera: generator
"widzący" miesiąc +1 (do przodu) ani otwartej/nieskończonej rotacji
zmianowej - to osobne, odłożone propozycje klienta.

**CP-SAT - zbadane przed kodowaniem:** obsada rotacji 24/7
(`add_duty_rotation_coverage_constraint`) NIE wymagała żadnej zmiany.
Okna zmian są ustalonymi godzinami zegarowymi per lokalizacja i
interlockują dzień-w-dzień z założenia (koniec jednej zmiany = start
następnej) - "dziura" na starcie dnia 1 nigdy nie była osobną zmienną w
modelu, więc nie ma czego "zamykać". Jedyne realne ryzyko to przydzielenie
TEJ SAMEJ osoby zbyt wcześnie po jej faktycznym końcu z poprzedniego
miesiąca - a to już w całości załatwia rozszerzenie rest constraintu o
wirtualne zakotwiczenie "dzień -1/0" względem dnia 1, tym samym wzorcem co
istniejące porównania dzień-do-dnia w `duty_rotation_rest_constraint.py`.
Ponieważ zapamiętujemy tylko koniec + `crosses_midnight` (nie TYP tamtej
zmiany), granica z poprzednim miesiącem zawsze używa standardowego 11h,
nigdy podwyższonego "doba za dobę" (N-1)×24h po `weekend_full` - to
świadome uproszczenie, zgodne z wąskim zakresem zadania.

| Plik | Zmiana |
|---|---|
| `model/month_schedule.py` | Nowy `PreviousMonthShiftEnd(end, crosses_midnight)` + `MonthSchedule.previous_month_end_shifts` (Dict[Employee, ...], ten sam wzorzec co `settlement_targets`) - żyje na `MonthSchedule`, nie `ShopConfig`, bo zmienia tożsamość co miesiąc (opisuje "tuż przed TYM miesiącem", nie coś, co ma bezwarunkowo przetrwać `reset_for_new_month`); serializacja inline w `to_dict()`/`from_dict()` |
| `logic/utils/time_utils.py` | `is_next_calendar_month()` - przejęcie tylko gdy nowy miesiąc jest dokładnie kolejnym kalendarzowym po starym (skok o >1 miesiąc/wstecz = koniec sprzed dawna, nieprzydatny) |
| `ui/main_window.py::_save_date_clicked` | Przed nadpisaniem `self.schedule` czyta ostatni dzień STAREGO grafiku per pracownik (`ds.end`, `ds.crosses_midnight()`) i zapisuje na nowym `MonthSchedule` (`_carry_over_previous_month_end_shifts`) |
| `ui/previous_month_shift_dialog.py` (nowy) + menu Edycja | Ręczny fallback - lista pracowników, `TimeInputWidget` (koniec zmiany) + checkbox "Zmiana wchodzi w dzień 1"; jedyne miejsce, z którego można wpisać tę pamięć od zera (kolumna w gridzie pokazuje się dopiero, gdy dane już istnieją) |
| `logic/generator/rest_constraint.py` | `add_rest_11h_constraint`/`_simplified` dostały opcjonalny `schedule=` - nowa `_add_previous_month_rest_constraint()` zakotwicza koniec z poprzedniego miesiąca względem startu dnia 1 (ten sam wzorzec `_anchor()` co niżej); `_simplified` liczy tę granicę zawsze DOKŁADNYMI godzinami (mamy prawdziwy zapisany koniec), nie klasą zmiany - jedyny wyjątek od jej zwykłej, zgrubnej logiki |
| `logic/generator/duty_rotation_rest_constraint.py` | `add_duty_rotation_rest_constraint` dostało opcjonalny `schedule=` - `_add_previous_month_rest_constraint()` analogicznie, zawsze standardowe 11h (patrz wyżej) |
| `logic/generator/base_specs.py` | `_build_rest_11h` przekazuje `schedule=ctx.schedule` do wszystkich trzech wywołań |
| `ui/theme.py` | Nowe `BG_PREVIOUS_MONTH_HEADER`/`BG_PREVIOUS_MONTH_CELL` |
| `ui/grid_view.py` | Nowa, czysto informacyjna kolumna PRZED dniem 1 (numer ostatniego dnia poprzedniego miesiąca), widoczna tylko gdy choć jeden widoczny pracownik ma dane; `DayHeaderView` maluje ją pełnym innym tłem (zwykłe `QTableWidgetItem.setBackground()` nie działa w nagłówku - arkusz stylów ma pierwszeństwo); wszystkie miejsca liczące `dzień == kolumna` (kliknięcia/menu kontekstowe/skróty klawiszowe/kolumny podsumowania) przeliczone przez nowy `_prev_col_offset`/`_column_to_day()` |
| `tests/test_previous_month_memory.py` (nowy, 23 testy) | Przejęcie przy zmianie miesiąca (w tym guard `is_next_calendar_month`), rest constraint (zwykły/uproszczony/rotacja 24/7) na granicy z poprzednim miesiącem, pojawianie/znikanie kolumny w gridzie, round-trip zapisu/wczytania |

**Weryfikacja:** pełny zestaw testów zielony (505 passed, 1 skipped),
zero regresji na istniejących testach rest/duty_rotation/grid/night_shift.
(domyślny `uses_trade_calendar=True` zachowuje dokładnie stare zachowanie).

### Naprawiony bug: "infeasible" bez wyjaśnienia, gdy pamięć poprzedniego miesiąca blokuje otwarcie (2026-09-21)

**Zgłoszenie użytkownika:** włączenie tej funkcji wywalało `INFEASIBLE`
nawet na pustym (niczego jeszcze nie wygenerowanym) grafiku.

**Odtworzone:** domyślny profil (min_open_staff=3, `open` MANDATORY) +
kilku/wszystkich pracowników z tą samą godziną końca poprzedniego miesiąca
(np. `DEFAULT_END_TIME = "22:00"` z `ui/previous_month_shift_dialog.py`,
pozostawioną bez zmian po zaznaczeniu "Mam dane" dla wielu osób naraz) -
przerwa do domyślnego otwarcia (05:30) wynosi tylko 7.5h, mniej niż
wymagane 11h, więc `_add_previous_month_rest_constraint`
(`rest_constraint.py`) **poprawnie** blokuje WSZYSTKICH od otwarcia dnia
1 - to jest prawidłowe egzekwowanie realnego wymogu Kodeksu pracy, który
wcześniej (przed tą funkcją) był po prostu cicho ignorowany na granicy
miesięcy. Problem nie był w matematyce constraintu, tylko w tym, że
`build_infeasibility_summary` (`logic/generator/diagnostics.py`) nic nie
wiedziała o tej nowej przyczynie - użytkownik dostawał generyczny,
niezrozumiały komunikat zamiast wskazania konkretnej przyczyny.

**Naprawa:**
- `logic/generator/diagnostics.py` - nowa `_previous_month_rest_gap_hours()`
  (ta sama arytmetyka co `rest_constraint.py::_anchor`) + rozszerzenie
  pętli dnia 1 dla polityk `open`/`close`: pracownik, któremu przerwa do
  `target_time` wynosi <11h, trafia teraz do `blocked_by_previous_month`
  zamiast cicho do "niemożliwych" - gdy to WŁAŚNIE oni robią obsadę
  niewykonalną, komunikat wprost wskazuje "pamięć poprzedniego miesiąca"
  i podpowiada menu Edycja -> "Godziny zakończenia z poprzedniego
  miesiąca...".
- `ui/previous_month_shift_dialog.py` - dopisane ostrzeżenie w opisie
  okna: ta sama (albo zgadnięta) godzina dla wielu osób naraz może
  zablokować wszystkich jednocześnie na początku miesiąca.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `logic/generator/diagnostics.py` | `_previous_month_rest_gap_hours()` + rozszerzony `build_infeasibility_summary()` | TAK - dotyczy każdego projektu (Dino i Enyo), nie tylko Enyo |
| `ui/previous_month_shift_dialog.py` | Dopisane ostrzeżenie w tekście informacyjnym | TAK |
| `tests/test_previous_month_memory.py` (+4 testy) | Odtworzenie zgłoszonego scenariusza (izolowane `build_infeasibility_summary` + end-to-end `ScheduleController.generate_schedule`), sprawdzenie że wystarczająca przerwa / brak danych NIE są fałszywie zgłaszane | TAK |

**Weryfikacja:** zgłoszony scenariusz teraz zwraca precyzyjny komunikat
zamiast generycznego; pełny zestaw testów zielony, zero regresji.

### Mechanizm schowany na razie na życzenie użytkownika (2026-09-21)

Mimo naprawy diagnostyki wyżej, użytkownik zdecydował schować cały
mechanizm "pamięć poprzedniego miesiąca" do dalszej decyzji - zbyt łatwo
było wywołać nim mylące `INFEASIBLE`, a klient nie miał jeszcze okazji
przetestować poprawki. Ustalone: ukryć CAŁY mechanizm (nie tylko ręczne
okno), żeby nie zostawić auto-przejęcia działającego po cichu bez łatwego
sposobu podejrzenia/poprawienia danych.

**Jak:** nowa stała `model/month_schedule.py::PREVIOUS_MONTH_MEMORY_ENABLED
= False`, sprawdzana w trzech punktach wpięcia (kod całego mechanizmu -
model, dialog, constrainty, testy - zostaje w pełni działający, tylko
nieosiągalny):

| Plik | Co sprawdza flagę |
|---|---|
| `ui/main_window.py` | Nie dodaje pozycji menu Edycja "Godziny zakończenia z poprzedniego miesiąca..."; `_save_date_clicked` nie wywołuje `_carry_over_previous_month_end_shifts` |
| `logic/generator/base_specs.py::_build_rest_11h` | Przekazuje `schedule=None` zamiast `ctx.schedule` do wszystkich trzech wywołań rest constraintu - `_add_previous_month_rest_constraint` w obu plikach wychodzi natychmiast |
| `ui/grid_view.py::_previous_month_last_day_if_shown` | Zwraca `None` bezwarunkowo - kolumna nigdy się nie pojawia, nawet gdyby dane istniały (np. z zapisanego wcześniej projektu) |

**Uwaga dla testów:** `from X import Y` wiąże nazwę lokalnie w każdym z
tych trzech modułów osobno - włączenie flagi w testach wymaga patchowania
`ui.main_window.PREVIOUS_MONTH_MEMORY_ENABLED`/`ui.grid_view.
PREVIOUS_MONTH_MEMORY_ENABLED` (per moduł-konsument), nie samego
`model.month_schedule.PREVIOUS_MONTH_MEMORY_ENABLED` - trzy testy w
`tests/test_previous_month_memory.py`, które sprawdzają zachowanie
WŁĄCZONEGO mechanizmu, robią to teraz jawnie.

**Przywrócić do main?** DO USTALENIA razem z resztą tego mechanizmu -
patrz sekcja "Pamięć poprzedniego miesiąca" wyżej.

## Pierwszy build dla klienta: 1.0.0.enyo (2026-09-21)

Przygotowanie pierwszego instalatora dla klienta Enyo - wydzielony,
osobny od kanału "dino" (głównego) na każdym poziomie, żeby nigdy nie
dało się przypadkiem pomylić buildów/aktualizacji między klientami.

**Nowe, osobne pliki (nie modyfikują odpowiedników Dino):**

| Plik | Rola |
|---|---|
| `Enyo - Grafik Pracy.spec` | PyInstaller - buduje do `dist\Enyo - Grafik Pracy` (Dingo buduje do `dist\Dingo! - narzędzie do grafików pracy` - osobne foldery, zero ryzyka nadpisania) |
| `enyo.iss` | Inno Setup - `MyAppName "Enyo - Grafik Pracy"`, osobny `AppId` (`8C714D0B-17B2-4F06-8813-0CACEADBD73D`, inny niż Dingo - to INNY produkt z perspektywy rejestru Windows/deinstalacji, mimo wspólnego kodu), `DefaultDirName={localappdata}\Programs\Enyo\Grafik Pracy`, `OutputBaseFilename=EnyoSetup`, `OutputDir=Output`. Ikona: na razie dziedziczona z `dingo_icon.ico` - **brak osobnej ikony dla Enyo, do zrobienia później** |
| `version.py` | `APP_VERSION = "1.0.0.enyo"` - na tym branchu na stałe (branch jest dedykowany Enyo), w odróżnieniu od `release_channel.py`, który ZAWSZE zostaje "dino" w repo (patrz istniejący mechanizm `scripts/build_release.ps1 -Channel enyo`, tymczasowo podmienia i przywraca) |
| `releases/enyo.json` | `latest_version: "1.0.0.enyo"`, `download_url` wskazuje na tag `v1.0.0-enyo`, asset `EnyoSetup.exe` |
| `.gitignore` | Dodane `Output/` (katalog wyjściowy ISCC.exe) i `*.flag` (znaczniki "widziano samouczek" tworzone lokalnie w runtime, np. `locations_tutorial_seen.flag`) - oba wcześniej nie były ignorowane |

**Zbudowane i zweryfikowane lokalnie:** `scripts/build_release.ps1 -Channel enyo -SpecFile "Enyo - Grafik Pracy.spec"` (PyInstaller, `release_channel.py` poprawnie przywrócone do "dino" po buildzie) → `ISCC.exe enyo.iss` → `Output/EnyoSetup.exe` (~79 MB, nie commitowane, gitignored). Pełny zestaw testów zielony przed i po (534 passed, 1 skipped).

**Świadomie NIE zrobione teraz (poza zasięgiem tego, co dało się zautomatyzować z tego środowiska - brak `gh` CLI):**
- Rebranding tekstów WEWNĄTRZ aplikacji poza tym, co już wcześniej zneutralizowano (About, samouczek) - instalator/skrót/nazwa okna teraz mówią "Enyo", ale nie przeszukano całej apki pod kątem resztek "Dingo"/"Dino" w tekstach widocznych dla użytkownika.
- Utworzenie faktycznego GitHub Release z tagu `v1.0.0-enyo` z załącznikiem `EnyoSetup.exe` - wymaga `gh` CLI albo ręcznego kroku przez stronę GitHub, przekazane użytkownikowi osobno jako instrukcja krok po kroku.
- Wgranie `releases/enyo.json` na branch `main` - `update_checker.py` czyta ten plik ZAWSZE z `main` (URL na sztywno), nie z tego brancha - bez tego kroku sprawdzanie aktualizacji u klienta nigdy nic nie znajdzie, nawet po wydaniu nowszej wersji. Ustalone z użytkownikiem: wykonać to jako osobny, bezpośredni commit na `main` (dotyka tylko nowego pliku, nie kodu aplikacji).
- Osobna ikona dla Enyo (dziś reużywa `dingo_icon.ico`).

**Przywrócić do main?** NIE - te pliki (branding/wersja specyficzna dla
Enyo) nie mają sensu na `main`, poza samym mechanizmem kanałów
(`release_channel.py`/`update_checker.py`/`scripts/build_release.ps1`),
który już tam jest.

## Krytyczne braki znalezione przy pierwszym teście świeżego exe (2026-09-21)

Użytkownik przetestował faktycznie zainstalowany `EnyoSetup.exe` (nie
`python main.py` z ręcznie wczytanym `last_project.json`) i znalazł dwa
osobne, poważne braki - oba **blokujące realne użycie przez klienta**.
Poprawione w tej samej rundzie, ale **build `Output/EnyoSetup.exe` z
poprzedniej sekcji jest już NIEAKTUALNY** - trzeba go przebudować przed
przekazaniem klientowi.

### Brak 1: brak jakiejkolwiek konfiguracji "Ochrona" na świeżej maszynie

**Przyczyna:** `%LOCALAPPDATA%\GrafikDino\custom_profiles.json` (profile
biznesowe) to plik per-maszynowy - NIE jest częścią instalatora ani repo.
Dotąd jedynym sposobem, żeby cokolwiek się tam znalazło, było ręczne
uruchomienie `demo/install_*.py` (skrypt Pythona, wymaga źródeł repo) -
żaden taki krok nie jest częścią instalacji EXE. Do tego zarządzanie
profilami w UI jest dla Enyo świadomie schowane (klient nie może sam
stworzyć profilu przez kreator). Efekt: świeża instalacja u klienta
startowałaby z `visible_profiles()` zwracającym PUSTĄ listę (wyklucza
dino_retail) - kreator pierwszego uruchomienia nie miałby czego
zaproponować, klient utknąłby na starcie.

Na maszynie deweloperskiej (tej, na której testowano) profil
`custom_ochrona` akurat ISTNIAŁ, ale z porzuconej, wczesnej wersji sprzed
właściwego mechanizmu `LocationConfig.duty_rotation` - miał jedną rolę
`"Obłożenie"` (checkbox per pracownik), zamiast aktualnych `"Umowa"`/`"Nie
chce 24h"`. Stąd zgłoszenie: dodając pracownika przez świeże exe widać
tylko stary, porzucony toggle "Obłożenie".

**Naprawa:** `model/business_profile.py::_ensure_default_ochrona_profile()`
(wywoływane bezwarunkowo przy imporcie modułu, czyli przy każdym starcie
aplikacji) - synchronizuje `custom_ochrona` do jedynego, kanonicznego
kształtu (`build_default_ochrona_profile()`: role `umowa`/`nie_chce_24h`,
`rules=[]` - pokrycie 24/7 liczy się już w całości automatycznie z
`LocationConfig.duty_rotation`, nie przez regułę profilu). Naprawia
zarówno brak profilu (świeża maszyna), jak i już zarejestrowany, ale
przestarzały (ta maszyna deweloperska - potwierdzone, plik na dysku
faktycznie się poprawił po samym imporcie modułu).

**Świadomie unconditional na tym branchu** (nie za flagą typu
`RELEASE_CHANNEL`) - ten sam wzorzec co `visible_profiles()` wykluczające
dino_retail: cały branch jest dedykowany Enyo, więc nie ma potrzeby
warunkowania per-build, a `RELEASE_CHANNEL` w repo i tak zawsze zostaje
"dino" (patrz sekcja wyżej), więc warunkowanie na nim uczyniłoby to
nietestowalnym przy zwykłym `python main.py` z tego brancha.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `model/business_profile.py` | `DEFAULT_OCHRONA_PROFILE_KEY`, `build_default_ochrona_profile()`, `_ensure_default_ochrona_profile()`, wywołane przy imporcie modułu | NIE - Enyo-specyficzne, usunąć przy ewentualnym mergu do main |
| `ui/first_run_wizard.py` | Usunięty z hinta kroku "Branża" fragment wspominający "Sklep (Dino)" - myląca wzmianka o profilu wykluczonym z tego pickera | TAK (kosmetyka, neutralna też dla main) |
| `tests/test_default_ochrona_profile.py` (nowy) | Auto-provisioning: brakujący profil, przestarzały profil (dokładnie odtworzony przypadek "Obłożenie"), już poprawny profil NIE jest nadpisywany bez potrzeby, awaria zapisu na dysk nie wywraca importu | TAK |

### Brak 2: brak UI do konfiguracji "Rotacja służby 24/7" dla lokalizacji

Mechanizm generatora (`LocationConfig.duty_rotation`, pięć okien czasowych
+ `only_12_24h`) istniał w pełni od dawna (patrz sekcja "Generator pod
klucz dla Enyo"), ale **nie było ŻADNEGO okna w UI, które by go
ustawiało** - dane trafiały tam wyłącznie przez skrypty
`demo/install_*.py`. Efekt zgłoszony przez użytkownika: nowa lokalizacja
nie da się skonfigurować pod rotację 24/7, a wiersz podsumowania
"Obłożenie" (patrz `logic/duty_coverage_presenter.py`) nigdy się nie
pokazuje, bo pokazuje się tylko, gdy jakaś lokalizacja faktycznie ma
`duty_rotation` ustawione - co bez tego UI nigdy nie mogło się zdarzyć dla
nowo tworzonego projektu.

**Naprawa:** nowy współdzielony widget `ui/duty_rotation_editor.py::
DutyRotationEditor` (ten sam wzorzec co `WeeklyHoursEditor` - jedno źródło
prawdy dla dwóch okien), osadzony w:
- `ui/locations_dialog.py::_LocationRow` - pod sekcją "Progi obsady"
- `ui/config_dialog.py` (zakładka "Godziny otwarcia", tylko gdy okno wie,
  którą lokalizację edytuje - `self.location`, patrz wcześniejsza runda)

**Uproszczenie UI (decyzja z użytkownikiem, 2026-09-20 - patrz sekcja
"Pamięć poprzedniego miesiąca" wyżej, ta sama rozmowa):** zamiast
niezależnej kontroli nad wszystkimi 5 oknami czasowymi, użytkownik wpisuje
TYLKO start/koniec jednej zmiany na kontekst (tydzień, weekend) - drugą
połowę (i start zmiany 24h w weekend) program dolicza automatycznie jako
dopełnienie do 24h. We wszystkich dotychczasowych lokalizacjach klienta
(`last_project.json`, `demo/install_client_sample_data.py`) każda para
zmian faktycznie dopełnia się dokładnie w ten sposób, więc to nie jest
uproszczenie kosztem realnych przypadków - to jedyny kształt, jaki
kiedykolwiek widzieliśmy w danych klienta.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `ui/duty_rotation_editor.py` (nowy) | `DutyRotationEditor` - checkbox włączający, `only_12_24h`, 2 pola czasu (tydzień) + 2 pola (weekend), walidacja przez istniejące `normalize_duty_rotation()` | TAK - generyczne, nie Enyo-specyficzne (duty_rotation to mechanizm generatora dostępny dla każdego profilu) |
| `ui/locations_dialog.py` | Nowa sekcja w `_LocationRow`, `_save()` czyta `row.duty_rotation_editor.get_duty_rotation()` (było: `loc.duty_rotation = old.duty_rotation`, czyli zawsze zachowanie starej wartości - teraz faktycznie edytowalne), nowy krok samouczka | TAK |
| `ui/config_dialog.py` | Analogiczna sekcja w zakładce "Godziny otwarcia" (tylko z `self.location`), `_save()` zapisuje | TAK |
| `tests/test_duty_rotation_editor.py` (nowy) | Round-trip, automatyczne dopełnianie do 24h, `only_12_24h` chowa pola tygodnia, walidacja błędów | TAK |

**Weryfikacja:** end-to-end - zapisanie lokalizacji przez `LocationsDialog`
z włączoną rotacją 24/7 poprawnie ustawia `LocationConfig.duty_rotation`,
i `project_uses_duty_rotation()` (warunek pokazania wiersza "Obłożenie")
poprawnie zwraca `True` dla pracownika przypisanego do tej lokalizacji.

**Do zrobienia po tej naprawie:** `Output/EnyoSetup.exe` zbudowany w
poprzedniej sekcji trzeba PRZEBUDOWAĆ (zawiera kod sprzed tych poprawek) -
jeśli w GitHub Release z tagu `v1.0.0-enyo` już wgrano stary plik, trzeba
go zastąpić nowym.

## Scalenie przełącznika rotacji 24/7 z "Działalność całodobowa" (2026-09-21)

Poprawka UX na wyraźne życzenie użytkownika, zaraz po poprzedniej sekcji
("Brak 2"): `DutyRotationEditor` dostał WŁASNY, osobny checkbox "Rotacja
służby 24/7" obok już istniejącego "Działalność całodobowa (24/7)"
(`is_24_7_check`) w `ui/locations_dialog.py` - dwa niezależne przełączniki
robiące de facto to samo, mylące. Ustalone: **żadnego nowego checkboxa** -
widget rotacji ma być wprost podpięty pod istniejący `is_24_7_check`.

**Zmiana:**
- `ui/duty_rotation_editor.py` - usunięty `enabled_check` (i cała logika
  go dotycząca) z widgetu całkowicie. Widget nie ma już własnego pojęcia
  "włączony/wyłączony" - zawsze pokazuje `only_12_24h_check` +
  `weekend_container` (`weekday_container` chowany tylko przez
  `only_12_24h`). Decyzję "czy w ogóle pokazać/zapisać ten widget"
  podejmuje wyłącznie okno, które go osadza.
- `ui/locations_dialog.py::_LocationRow` - `duty_rotation_editor`
  osadzony pod sekcją godzin (przed "Progi obsady"),
  `_update_hours_visibility()` pokazuje go dokładnie wtedy, gdy
  `is_24_7_check.isChecked()`; `_save()` czyta
  `row.duty_rotation_editor.get_duty_rotation()` TYLKO gdy checkbox jest
  zaznaczony (inaczej `duty_rotation=None`), błąd walidacji owinięty w
  komunikat wskazujący nazwę lokalizacji. Krok samouczka "Rotacja służby
  24/7" (osobny) usunięty - tekst kroku "Działalność całodobowa (24/7)"
  rozszerzony o wyjaśnienie efektu na rotację.
- `ui/config_dialog.py` - CAŁA sekcja rotacji 24/7 (import, budowa
  widgetu w `_build_hours_tab()`, zapis w `_save()`) USUNIĘTA. To okno
  edytuje godziny jednej, już wybranej lokalizacji i nie ma własnego
  `is_24_7_check` do podpięcia - edycja rotacji zostaje wyłącznie w
  `ui/locations_dialog.py`.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `ui/duty_rotation_editor.py` | Usunięty `enabled_check`, widget zawsze "aktywny" (`get_duty_rotation()` zawsze liczy i zwraca) | TAK |
| `ui/locations_dialog.py` | Widoczność/zapis podpięte pod `is_24_7_check`; krok samouczka scalony | TAK |
| `ui/config_dialog.py` | Sekcja rotacji 24/7 usunięta (brak `is_24_7_check` w tym oknie) | N/D (cofnięcie wcześniejszego dodatku z tej samej rundy) |
| `tests/test_duty_rotation_editor.py` | Przepisany pod API bez `enabled_check` | TAK |
| `tests/test_locations_dialog_tutorial.py` | `_known_widgets()` bez `duty_rotation_editor.enabled_check`; "Rotacja służby 24/7" zdjęta z `FORBIDDEN_PHRASES` (funkcja już nie ukryta) | TAK |
| `tests/test_employee_dialog_tutorial.py`, `tests/test_quick_mode_settings_dialog_tutorial.py`, `tests/test_main_window_tutorial_content.py` | Ta sama korekta `FORBIDDEN_PHRASES` dla spójności | TAK |

**Weryfikacja:** pełny zestaw testów zielony (551 passed, 1 skipped).

## Czyszczenie plików `*.flag` przy deinstalacji (2026-09-21)

**Zgłoszenie użytkownika:** odinstalowanie Dingo albo Enyo powinno kasować
wszystkie znaczniki "widziano samouczek" (`*.flag`) tworzone przez
aplikację w runtime - domyślny deinstalator Inno Setup kasuje tylko pliki
wpisane jawnie w `[Files]` (czyli to, co zainstalował), więc pliki
tworzone PO instalacji, przy pierwszym uruchomieniu, zostawałyby
osierocone. Przy ponownej instalacji (reinstall/upgrade) samouczki
"pamiętałyby" błędnie, że użytkownik już je widział.

Zweryfikowane przez grep: wszystkie 5 istniejących znaczników
(`CONFIG_TUTORIAL_FLAG` w `ui/config_dialog.py`, `EMPLOYEE_TUTORIAL_FLAG`,
`LOCATIONS_TUTORIAL_FLAG`, `QUICK_MODE_TUTORIAL_FLAG`, oraz
`first_run.flag` w `ui/main_window.py`) trzymają się jednego wzorca
(`*.flag`) i są tworzone w katalogu roboczym aplikacji (`{app}`, bo skróty
w `[Icons]` nie ustawiają `WorkingDir` - ten sam katalog co
`last_project.json`).

**Naprawa:** nowa sekcja `[UninstallDelete]` w obu instalatorach
(identyczna treść, osobne pliki):

```
[UninstallDelete]
Type: files; Name: "{app}\*.flag"
```

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `enyo.iss` | Nowa sekcja `[UninstallDelete]` | N/D (plik sam w sobie Enyo-specyficzny) |
| `dla inno.iss` | Ta sama sekcja `[UninstallDelete]` (kanał Dingo/główny) | TAK - to jest instalator main |

**Weryfikacja:** `ISCC.exe enyo.iss` kompiluje się bez błędów po dodaniu
sekcji, `Output/EnyoSetup.exe` przebudowany. Nie testowane empirycznie
(faktyczna instalacja+deinstalacja na czystej maszynie) - tylko składnia
`.iss` i zgodność wzorca z realnymi nazwami plików flag w kodzie.

**Do zrobienia po tej naprawie:** `Output/EnyoSetup.exe` przebudowany
razem z powyższym scaleniem checkboxa 24/7 (ta sama runda) - jeśli w
GitHub Release z tagu `v1.0.0-enyo` już wgrano stary plik, trzeba go
zastąpić nowym (trzeci raz).

## Święta ustawowe: `pip holidays`, nominalny czas pracy, automatyczne zamknięcie (2026-09-25)

Na życzenie użytkownika: program przestał polegać wyłącznie na ręcznym
zaznaczaniu świąt (`ShopConfig.public_holidays`/`LocationConfig.
public_holidays` - dwuklik na nagłówku dnia) i "prostym" przeliczaniu
nominalnego czasu pracy. Nowa zależność: pakiet PyPI `holidays`
(`pip install holidays`) - **brak `requirements.txt` w repo, zależność
tylko w środowisku, w którym uruchamiane/budowane jest repo**.

### Nowy moduł

| Plik | Co robi | Przywrócić do main? |
|---|---|---|
| `logic/utils/holidays_pl.py` (nowy) | `polish_public_holiday_days(year, month)` - cienka nakładka na `holidays.country_holidays("PL", years=year)`, cache'owana per rok (`lru_cache`) | TAK - generyczne, nie Enyo-specyficzne |

### Naprawiony: nominalny czas pracy liczony "na prosto"

`ShopConfig.get_full_time_nominal_hours()` (używane przez `monthly_hours`/
`balance`/priorytet "Umowa"/diagnostykę - patrz wcześniejsza sekcja
"Generator pod klucz dla Enyo") liczyła nominał jako (dni robocze pon-pt w
miesiącu) × **stałe 8h**, pomniejszone WYŁĄCZNIE o ręcznie zaznaczone
`public_holidays` - użytkownik musiałby co roku pamiętać o ręcznym
zaznaczeniu każdego święta w każdym projekcie. Teraz: unia automatycznie
wykrytych świąt (`holidays_pl.py`) i ręcznie zaznaczonych (ręczne zostają
jako możliwość dodania dnia spoza kalendarza krajowego - lokalnego/
firmowego), pomnożone przez `self.standard_daily_hours` (użytkownikowe pole
"Standardowy wymiar zmiany", wcześniej ignorowane na rzecz sztywnego 8).

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `model/shop_config.py::get_full_time_nominal_hours` | Unia auto+ręcznych świąt, `* self.standard_daily_hours` zamiast `* 8` | TAK |
| `tests/test_location.py` (+8 testów) | Automatyczne wykrycie (styczeń 2026 = 160h), unia z ręcznymi, `standard_daily_hours` respektowane, miesiąc bez świąt bez zmian | TAK |
| `tests/test_monthly_hours_status.py` | 2 testy poprawione pod zwracany teraz `float` (`nominal_hours // 8` → `int(nominal_hours // 8)`) | TAK |

**Weryfikacja:** żaden z miesięcy używanych w istniejących testach (2026,
wszystkie z wyjątkiem stycznia/kwietnia/maja/czerwca) nie ma świąt
przypadających w dzień roboczy, więc zero regresji bez zmian w testach -
potwierdzone jawnie sprawdzeniem kalendarza 2026 przed wdrożeniem.

### Nowa funkcja: automatyczne zamknięcie lokalizacji w święta (grid + generator), per lokalizacja

Rozszerzenie tej samej rozmowy: użytkownik poprosił, żeby auto-wykryte
święta od razu traktowały dzień jako nieczynny (nie tylko w nominalnym
czasie pracy), z przełącznikiem PER LOKALIZACJA (część placówek nie
wymaga ochrony w święta, część zostaje 24/7 mimo to) - **domyślnie
włączone**.

**Nowe pole:** `LocationConfig.closed_on_public_holidays: bool = True` +
`is_closed_for_public_holiday(year, month, day)` (uwzględnia jawne
`day_overrides` - zawsze wygrywają nad automatycznym zamknięciem).

| Warstwa | Zmiana |
|---|---|
| Grid (zwykłe godziny otwarcia) | `LocationConfig.get_open_hours_for_day()` sprawdza `is_closed_for_public_holiday()` (po `day_overrides`, przed zwykłym fallbackiem tygodniowym) - grid szarzeje dokładnie tak samo jak "Nieczynne"/niedziela niehandlowa, bez żadnej zmiany w `ui/grid_view.py`/`logic/schedule_presenter.py` (już czytają `get_open_hours_for_day()`) |
| Generator: rotacja 24/7 (duty_rotation) | Lokalizacje z `duty_rotation` w ogóle NIE korzystają z `open_hours` (ustalone wcześniej, patrz sekcja "Napraw rozjazd..." wyżej) - nowy `logic/generator/duty_rotation_public_holiday_constraint.py::add_duty_rotation_public_holiday_constraint` zeruje wszystkie 5 typów zmian danego dnia (ręczne, jawne przypisanie zmiany wygrywa - ten sam priorytet co `day_overrides`); `add_duty_rotation_coverage_constraint` (`duty_rotation_constraint.py`) osobno pomija wymóg pokrycia tych samych dni, żeby oba constrainty nie były sprzeczne (twarde `count==0` obok twardego `count==1`) |
| Wiersz "Obłożenie" (podsumowanie w grid) | `logic/duty_coverage_presenter.py::is_day_fully_covered()` pomija zamkniętą lokalizację tego dnia zamiast liczyć brak obsady jako błąd (❌) |
| UI | Nowy checkbox "Zamknięte w polskie święta ustawowe" w `ui/locations_dialog.py::_LocationRow` (zawsze widoczny, niezależny od 24/7) i analogicznie w `ui/config_dialog.py` (zakładka "Godziny otwarcia", ten sam wzorzec co reszta tej zakładki) |

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `model/location.py` | `closed_on_public_holidays` (pole + `to_dict`/`from_dict`, domyślnie `True` też dla starych plików bez tego klucza), `is_closed_for_public_holiday()`, wpięte w `get_open_hours_for_day()` | TAK |
| `model/shop_config.py` | `_LocationView.is_closed_for_public_holiday(day)` (deleguje, bound rok/miesiąc) + fallback `ShopConfig.is_closed_for_public_holiday()` (zawsze `False`, ten sam wzorzec co `get_round_clock_start_hour`) | TAK |
| `logic/generator/duty_rotation_public_holiday_constraint.py` (nowy) | Zeruje 5 typów zmian duty w zamknięty dzień, respektuje ręczne przypisanie | TAK |
| `logic/generator/duty_rotation_constraint.py::add_duty_rotation_coverage_constraint` | Pomija wymóg pokrycia dla zamkniętych dni | TAK |
| `logic/generator/base_specs.py` | Nowy `ConstraintSpec("duty_rotation_public_holiday", ...)`, ALWAYS_ON, ten sam wzorzec co `duty_rotation_manual_shift` | TAK |
| `logic/duty_coverage_presenter.py::is_day_fully_covered` | Pomija zamkniętą lokalizację tego dnia | TAK |
| `ui/locations_dialog.py`, `ui/config_dialog.py` | Nowy checkbox + zapis/odczyt | TAK |
| `tests/test_duty_rotation_public_holiday_constraint.py` (nowy, 9 testów) | Izolowane (zero-out, toggle off, ręczne przypisanie wygrywa, "OFF" nadal zeruje, coverage pomija/nie pomija) + end-to-end pełny miesiąc (`AutoScheduleGenerator`, styczeń 2026: dni 1 i 6 puste, reszta w pełni obsadzona) | TAK |
| `tests/test_duty_coverage_presenter.py` (+3 testy) | Zamknięty dzień liczy się jako pokryty, zwykły dzień nadal wymaga pełnej obsady, toggle off nadal wymaga | TAK |
| `tests/test_location.py` (+7 testów) | `is_closed_for_public_holiday`, `day_overrides` wygrywa, `get_open_hours_for_day`, round-trip domyślne `True` dla starych plików | TAK |
| `tests/test_location_hours_editing_ui.py` (+4 testy) | Domyślnie zaznaczone dla nowej lokalizacji, zapis/odczyt w obu oknach | TAK |
| `tests/test_duty_rotation_scenario.py`, `tests/test_duty_rotation_shift_length_variants.py` (×2), `tests/test_leave_sick_generation_sweep.py` | Współdzielone fixture'y lokalizacji testowych dostały jawne `closed_on_public_holidays = False` - te testy sprawdzają pokrycie KAŻDEGO dnia niezależnie od kalendarza, więc realne polskie święto w danym miesiącu/roku fałszowałoby oczekiwany wynik | TAK (kosmetyka testowa) |

**Pakowanie EXE:** `holidays` dodane do `datas`/`hiddenimports` w obu
plikach `.spec` (`collect_data_files('holidays')` - pakiet niesie pliki
lokalizacji `.mo` na nazwy świąt w różnych językach; nasz kod czyta
wyłącznie same DATY, nigdy nazw, więc funkcjonalnie niepotrzebne, ale
dodane defensywnie, żeby przyszła zmiana nie wywaliła się dopiero w
gotowym exe). **Nieprzetestowane realnym buildem** w tej turze - do
zweryfikowania przy następnym `scripts/build_release.ps1`.

**Weryfikacja:** pełny zestaw testów zielony (746 passed, 1 skipped, 26
nowych testów, zero regresji). Zweryfikowane bezpośrednio: import
`holidays`, obliczenie `polish_public_holiday_days(2026, 1) == {1, 6}`,
pełne wygenerowanie stycznia 2026 (OPTIMAL, dni 1/6 puste, reszta w pełni
obsadzona).

## Pamięć wielu miesięcy + odblokowanie pamięci poprzedniego miesiąca (2026-09-21)

Dotychczas "projekt" (`.myp`) to był dokładnie JEDEN miesiąc - zmiana
miesiąca (`ui/main_window.py::_save_date_clicked`) zawsze bezpowrotnie
kasowała grafik i pytała o to ostrzegawczym popupem, zachowując tylko
listę pracowników i `ShopConfig` (lokalizacje/profil/reguły generatora -
te już wcześniej przeżywały zmianę miesiąca przez `ShopConfig.
reset_for_new_month`, tylko sam `MonthSchedule` ginął, razem z
`day_overrides`/`trade_sundays` konkretnego miesiąca, bo `reset_for_new_month`
zerowało je w miejscu na współdzielonym obiekcie). Użytkownik poprosił o
możliwość swobodnego poruszania się między miesiącami tego samego projektu
(np. żeby sprawdzić coś we wcześniejszym miesiącu) bez utraty żadnych
danych - i o wpięcie do tego mechanizmu pamięci poprzedniego miesiąca
opisanej wyżej (przywrócone z `PREVIOUS_MONTH_MEMORY_ENABLED = False` do
`True` w tej samej rundzie - diagnostyka INFEASIBLE, na którą to chowanie
czekało, była już gotowa).

**Model:** nowy `model/monthly_project.py::MonthlyProject` - kontener
`Dict[(year, month), (MonthSchedule, ShopConfig)]`, jeden wpis na KAŻDY
miesiąc kiedykolwiek odwiedzony w tej sesji, nie tylko aktualnie otwarty.
Każdy miesiąc ma WŁASNY, niezależny `ShopConfig` (kopiowany przez
`deepcopy` - ten sam, już istniejący wzorzec co undo/redo w
`logic/schedule_controller.py`) zamiast jednego współdzielonego i zerowanego
w miejscu - dzięki temu powrót do starego miesiąca pokazuje dokładnie te
niedziele handlowe/nadpisania dni/święta, jakie tam faktycznie ustawiono.

**`ui/main_window.py::_switch_to_month`** (zastępuje `_save_date_clicked`
jako jedyną drogę zmiany miesiąca, wołane teraz z nowego okna wyboru -
patrz niżej): miesiąc już obecny w `self.project` wraca dokładnie taki,
jaki został zostawiony; naprawdę nowy miesiąc startuje pusty (te same
pracownicy/lokalizacje/reguły generatora co dziś), z pamięcią końca
poprzedniego miesiąca doliczoną automatycznie, JEŚLI miesiąc bezpośrednio
kalendarzowo go poprzedzający już istnieje w projekcie - sprawdzane przez
`logic/utils/time_utils.py::previous_calendar_month`, NIEZALEŻNIE od tego,
który miesiąc był aktualnie otwarty przed przełączeniem (swobodna
nawigacja to umożliwia: użytkownik mógł być na marcu i stamtąd wprost
utworzyć czerwiec - źródłem pamięci ma być maj, jeśli maj istnieje w
projekcie, nie marzec). To zastępuje dawne użycie
`is_next_calendar_month(stary_miesiąc, nowy_miesiąc)` w tym samym miejscu,
które porównywało do czegokolwiek aktualnie otwartego - `is_next_calendar_month`
zostaje (własne testy, koncept wciąż poprawny), tylko przestaje być tym,
co bramkuje to konkretne wywołanie.

**Nowe okno wyboru miesiąca** (`ui/month_picker_dialog.py::MonthPickerDialog`,
wpięte pod ISTNIEJĄCY przycisk "🗓 Zmień datę" zamiast dawnego inline
spinboxa) - kalendarz roczny: siatka 4x3 kafelków (jeden na miesiąc),
strzałki `‹ rok ›` do przełączania roku, przycisk "Dziś". Każdy kafelek
pokazuje krótki, LICZONY NA ŻYWO (nie osobno logowany - zero ryzyka
rozjazdu po cofnięciu/edycji) opis stanu z `model/monthly_project.py::
describe_month_state` - np. "10 lokacji, 8 pracowników, grafik gotowy" /
"Pusty grafik" - plus kolorowy pasek po lewej (szary/żółty/zielony -
`month_state_class`). Klik zaznacza, dwuklik od razu przełącza. Przycisk
"Zmień datę" pokazywał wcześniej inline spinboxy (`year_spin`/`month_spin`/
`btn_save_date`) - usunięte razem z `_enter_edit_date_mode`/dawnym
`_save_date_clicked`, bo stały się martwym UI (nieosiągalnym po podpięciu
przycisku pod nowe okno).

**Zapis/wczytanie** (`persistence/project_io.py`) - nowe
`save_project_bundle`/`load_project_bundle` zapisują/wczytują CAŁY
`MonthlyProject` (wszystkie miesiące, plus który jest aktywny) zamiast
tylko jednego miesiąca; rozumieją też stary, jednomiesięczny format (pliki
sprzed tej zmiany, i te wciąż zapisywane starym `save_project()` przez
`demo/*.py`/`logic/generator/trace.py`, które celowo zostały bez zmian -
tam chodzi o pojedynczy migawkowy plik, nie o cały projekt) - taki plik
wczytuje się jako jedyny miesiąc świeżego `MonthlyProject`. Wszystkie
miejsca w `ui/main_window.py` wołające dawne `save_project`/`load_project`
(zapis `.myp`, autozapis `last_project.json`, wczytanie przy starcie,
otwarcie z linii poleceń) przełączone na wersje `_bundle`.

Już nie usuwa się NIC nieodwracalnie przy zmianie miesiąca - dawny
ostrzegawczy popup "Zmiana miesiąca spowoduje usunięcie wszystkich zmian"
zniknął całkowicie, bo przestał być prawdą.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `model/monthly_project.py` (nowy) | `MonthlyProject` (kontener) + `describe_month_state`/`month_state_class` (opis/kolor kafelka) | TAK - generyczne, nie Enyo-specyficzne |
| `persistence/project_io.py` | `save_project_bundle`/`load_project_bundle`, wstecznie kompatybilne ze starym, jednomiesięcznym formatem | TAK |
| `ui/main_window.py` | `_switch_to_month` (zastępuje `_save_date_clicked`), `_open_month_picker`, `self.project`; usunięte martwe UI inline edycji daty | TAK |
| `ui/month_picker_dialog.py` (nowy) | `MonthPickerDialog` - kalendarz roczny z kafelkami stanu | TAK |
| `logic/utils/time_utils.py` | `previous_calendar_month()` - miesiąc bezpośrednio poprzedzający | TAK |
| `model/month_schedule.py` | `PREVIOUS_MONTH_MEMORY_ENABLED` z powrotem `True` (patrz sekcja "Pamięć poprzedniego miesiąca" wyżej) | TAK |
| `tests/test_monthly_project.py` (nowy, 25 testów) | Kontener, opis stanu, round-trip zapisu (nowy i stary format), `_switch_to_month` (w tym predecessor niezależny od aktualnie otwartego miesiąca), `MonthPickerDialog` | TAK |
| `tests/test_previous_month_memory.py` | Klasa `PreviousMonthMemoryHiddenTests` -> `PreviousMonthMemoryEnabledByDefaultTests` (odwrócone asercje - mechanizm jest teraz domyślnie WŁĄCZONY); 3 testy przepięte z `_save_date_clicked`+spinboxy na `_switch_to_month` bezpośrednio | TAK |

**Weryfikacja:** pełny zestaw testów zielony, zero regresji; ręczne
sprawdzenie na żywym `MainWindow()` (nie mocki) - przełączanie
tam-i-z-powrotem między miesiącami zachowuje dane, pamięć poprzedniego
miesiąca liczy się poprawnie niezależnie od kolejności odwiedzin, round-trip
zapisu/wczytania (`.myp` nowego formatu + wsteczna kompatybilność ze
starym) zachowuje wszystkie miesiące.

### Doprecyzowanie zasięgu edycji: tylko ten miesiąc + nowe kolejne (2026-09-21)

Użytkownik zapytał, czy edycja konfiguracji/dodanie lokalizacji/pracownika
"wycieka" do innych miesięcy, i poprosił o sprawdzenie konkretnego
scenariusza: dodajemy nową lokalizację, mając ją otwartą wczytujemy
poprzedni miesiąc - czy program się nie wywali/nie pokaże niczego.

**Sprawdzone na żywym `MainWindow()`:** ten scenariusz już działał
poprawnie dzięki `_update_location_switcher()` (istniejący mechanizm
samonaprawy - `self.selected_location_key not in locations` -> fallback na
`next(iter(locations))`, czyli pierwszą lokalizację TEGO miesiąca) -
zero zmian kodu potrzebnych tutaj.

**Druga, subtelniejsza rzecz sprawdzona tym samym eksperymentem:** edycja
configu (np. `min_open_staff`) na miesiącu N NIE propaguje się do już
istniejących, PÓŹNIEJSZYCH miesięcy (N+1, N+2...) - tylko do nowo
tworzonych od tego momentu. Użytkownik: to jest pożądane zachowanie
(bezpieczne - nic nie zmienia się po cichu w miesiącu, który mógł już
zostać wygenerowany/sprawdzony), więc bez zmian w logice - tylko dopisana
jawna notka w GUI, żeby klient wiedział, czego się spodziewać, zamiast
się tego domyślać.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `logic/utils/time_utils.py` | `MONTH_NAMES_PL`, `format_month_label()`, `month_scope_note()` - wspólny tekst dla trzech okien niżej | TAK |
| `ui/month_picker_dialog.py` | Nazwy miesięcy przeniesione na współdzielone `MONTH_NAMES_PL` (usunięta duplikacja) | TAK |
| `ui/config_dialog.py`, `ui/locations_dialog.py`, `ui/employee_dialog.py` | Nowa notka (`quickInfoHint`) na górze okna: "Zmiany w tym oknie dotyczą tylko miesiąca X i miesięcy utworzonych od teraz..." | TAK |
| `tests/test_monthly_project.py` (+11 testów) | `MonthScopeIsolationTests` (samonaprawa lokalizacji, izolacja configu/pracowników wstecz i do już istniejących późniejszych miesięcy, dziedziczenie przez nowo tworzone), `MonthScopeNoteTests` (obecność i treść notki w trzech oknach) | TAK |

**Weryfikacja:** pełny zestaw testów zielony (587 passed, 1 skipped),
zero regresji.

## Rotacja całodobowa "ogólna" - godzina rozpoczęcia dla lokalizacji 24/7 (2026-09-21)

Zgłoszenie klienta: dla lokalizacji z zaznaczonym "Działalność całodobowa
(24/7)" (`LocationConfig.is_24_7`) generator nie potrafił obsadzić środka
doby. Zweryfikowane empirycznie PRZED napisaniem kodu (uruchomienie
prawdziwego `AutoScheduleGenerator` na lokalizacji 24/7): mechanizm
OPEN/CLOSE (`logic/auto_generator.py::START_SHIFT_MAP`/`END_SHIFT_MAP`)
zakotwicza zmiany tylko na godzinie otwarcia/zamknięcia, z przesunięciami
do maks. 90/75 minut - to wystarcza na typowy dzień sklepu (~17h), ale przy
24h otwarcia zawsze zostaje ok. 5-6-godzinna dziura bez nikogo w pracy
(solver zgłaszał "rozwiązanie", ale środek doby zostawał pusty).

**Rozwiązanie (ustalone z użytkownikiem - dwa pytania przed kodowaniem):**
nowe pole `LocationConfig.round_clock_start_hour` (tylko dla `is_24_7=True`)
- generator dzieli dobę na N "kafelków" (zmian) o długości
`ShopConfig.standard_daily_hours` każda, zaczynających się od podanej
godziny i rozstawionych równo co `24h/N`, aż wypełnią całą dobę - N liczone
automatycznie jako `ceil(24h / standard_daily_hours)` (domyślnie 8h → 3
kafelki), z granicami [2, 6]. Obsada każdego kafelka: DOKŁADNIE ta sama
reguła co dzisiejsze otwarcie/zamknięcie (`min_open_staff` + wymóg co
najmniej 1 osoby z rolą "otwiera" i 1 z rolą "mięso") - świadomie
WYŁĄCZNIE dla profilu Dino (te role nie mają sensu dla innych profili, np.
Ochrona ma już własny, dedykowany `duty_rotation`).

**Architektura (ten sam wzorzec co `duty_rotation_constraint.py` - Etap B
"plan profil ochrona"):** nowa rodzina 6 stałych ID zmian
(`SHIFT_ROUND_1..6`, zawsze w `ALL_SHIFTS`, jak `SHIFT_DUTY_*`) - gate
(`add_round_clock_gate_constraint`) blokuje je twardo dla każdego
pracownika bez skonfigurowanej lokalizacji round-clock (i blokuje kafelki
`>= N` dla wszystkich), rest (`add_round_clock_rest_constraint`, standardowe
11h - w odróżnieniu od `duty_rotation`'s "doba za dobę" po zmianie 24h,
żaden kafelek round-clock nie jest tak długi jak doba, więc wystarczy
sprawdzić dzień d wobec d+1), manual (`add_round_clock_manual_shift_constraint`,
dopasowanie po samej godzinie startu). Zero zmiany zachowania dla każdego
istniejącego projektu (żadna lokalizacja nie ma `round_clock_start_hour`
domyślnie).

**Naprawiony bug znaleziony PODCZAS budowy tej funkcji (nie osobne
zgłoszenie):** profil Dino wymaga obsady OPEN/CLOSE bezwarunkowo
(MANDATORY domyślnie) - gdy WSZYSCY pracownicy projektu są na lokalizacji
round-clock (więc mają `x[e,d,SHIFT_OPEN/CLOSE]` zablokowane przez bramę
round-clock), `min_open_staff`/`min_close_staff` było strukturalnie
niespełnialne, robiąc CAŁY miesiąc `INFEASIBLE` (odtworzone empirycznie -
12 pracowników z rolami otwiera+mięso, generator i tak zgłaszał brak
rozwiązania). Naprawa: `add_fixed_staff_shift_constraints`
(`constraints_staff.py`) dostało opcjonalny `employee_indices` (ten sam
wzorzec co `add_max_consecutive_constraint`) + early-return `[]`, gdy lista
jest pusta (zamiast wymuszać niespełnialne `total_staff == min_staff` na
zerze pracowników); `dino_retail_profile.py::_build_open`/`_build_close`
filtrują teraz pracowników rotacji całodobowej (i, dla spójności, służby
24/7) z tego wymogu - projekt mieszany (część lokalizacji zwykła, część
round-clock) nadal poprawnie wymaga obsady open/close od "zwykłych"
pracowników.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `model/location.py` | `LocationConfig.round_clock_start_hour`, `set_24_7(False)` czyści je | TAK |
| `model/shop_config.py` | `_LocationView.get_round_clock_start_hour()`, `ShopConfig.get_round_clock_start_hour()` (zawsze `None` - fallback dla pracownika bez lokalizacji), domyślna polityka `round_clock_coverage: MANDATORY` | TAK |
| `logic/generator/round_clock_constraint.py` (nowy) | `round_clock_tile_count`/`round_clock_tile_start_hour`, `add_round_clock_gate_constraint`, `add_round_clock_coverage_constraint` | TAK |
| `logic/generator/round_clock_rest_constraint.py` (nowy) | `add_round_clock_rest_constraint` (11h + pamięć poprzedniego miesiąca) | TAK |
| `logic/generator/round_clock_manual_constraint.py` (nowy) | `add_round_clock_manual_shift_constraint` | TAK |
| `logic/generator/constraints_staff.py` | `add_fixed_staff_shift_constraints` - nowy opcjonalny `employee_indices` | TAK |
| `logic/generator/dino_retail_profile.py` | `_build_round_clock_coverage` (nowy spec), `_open_close_eligible_indices()` (naprawa opisana wyżej) | TAK |
| `logic/generator/constraints_logic.py`, `availability_constraint.py`, `manual_constraint.py` | Wykluczenie kafelków round-clock z `work_dependency`/`availability`/starego `manual_shift`, ten sam wzorzec co dla `duty_shifts` | TAK |
| `logic/generator/base_specs.py` | Rejestracja gate/manual (always-on) + rest (w `_build_rest_11h`) | TAK |
| `logic/generator/solution_mapper.py`, `logic/auto_generator.py`, `logic/generator/constraint_registry.py` | Nowe ID zmian, zapis przydziału do `DaySchedule`, `ConstraintContext.round_clock_shifts` | TAK |
| `ui/locations_dialog.py` | Pole "Rotacja całodobowa - godzina rozpoczęcia" (tylko dla 24/7) + opis działania w GUI | TAK |
| `tests/test_round_clock.py` (nowy, 29 testów) | Matematyka kafelków, brama, obsada (end-to-end przez prawdziwy generator - potwierdzona pełna obsada doby bez luki), odpoczynek 11h, ręczna blokada, regresja na buga open/close, GUI | TAK |

**Świadome ograniczenia zakresu (v1):** budżet "mięsa tymczasowego"
(`is_meat_light`) nie liczy się do obsady kafelków round-clock (budowany
tylko dla OPEN/CLOSE/START/END); `logic/generator/fix.py` (tryb
częściowej regeneracji "Napraw") nie wie o kafelkach round-clock -
zaakceptowane uproszczenia, nieblokujące podstawowej funkcjonalności.

**Weryfikacja:** empirycznie na żywym `AutoScheduleGenerator` (12
pracowników, lokalizacja 24/7, `round_clock_start_hour="08:00"`) - status
`OPTIMAL`, sprawdzone dzień po dniu: pełna obsada doby (00:00-08:30,
08:00-16:30, 16:00-00:30 - zachodzące kafelki, zero luki) tam, gdzie
wcześniej środek doby zostawał pusty. Pełny zestaw testów zielony (patrz
liczba w kolejnym wpisie), zero regresji na testach duty_rotation/night_shift/
open/close/rest_11h.

## Schowanie ręcznego edytora "Godziny zakończenia z poprzedniego miesiąca..." (2026-09-22)

Zgłoszenie użytkownika: pozycja menu Edycja - "Godziny zakończenia z
poprzedniego miesiąca..." (`PreviousMonthShiftDialog`) to był tylko
testowy dostęp do pamięci poprzedniego miesiąca, nie miała trafić do
klienta w tej formie - zwłaszcza że jej domyślna wartość ("22:00") była
już raz źródłem realnego buga (patrz `PreviousMonthBlocksDay1DiagnosticsTests`
w `tests/test_previous_month_memory.py`: jednolita, zgadnięta godzina dla
wszystkich pracowników potrafiła zrobić cały grafik `INFEASIBLE` bez
wyjaśnienia, zanim naprawiono to w `logic/generator/diagnostics.py`).

**Zmiana:**
- `ui/main_window.py::_build_menu` - usunięte wywołanie
  `edit_menu.addAction("Godziny zakończenia z poprzedniego miesiąca...", ...)`
  (zastąpione komentarzem wyjaśniającym decyzję). Metoda
  `_open_previous_month_shift_dialog` i cały `ui/previous_month_shift_dialog.py`
  zostają nietknięte - to jest UKRYCIE (kod nieosiągalny z UI), nie
  usunięcie, więc łatwo odwracalne. Sam mechanizm pamięci (auto-przejęcie
  przy zmianie miesiąca, wpływ na generator) zostaje w pełni aktywny -
  jedyna zmiana to brak ręcznej furtki do wpisania danych od zera.
- `ui/main_window.py::_previous_month_memory_note`/`_on_generation_finished` -
  nowe: po udanej generacji, jeśli pamięć poprzedniego miesiąca jest
  włączona, ale ŻADEN pracownik nie ma zapisanych danych (typowo:
  pierwszy miesiąc projektu, albo skok przez miesiąc bezpośrednio
  poprzedzający) - generator już wcześniej po cichu pomijał wtedy
  sprawdzenie przerwy 11h względem poprzedniego miesiąca (`if carry is
  None: continue` w `_add_previous_month_rest_constraint`, we wszystkich
  trzech wariantach: zwykłym, rotacji służby, round-clock) - teraz
  dodatkowo informuje o tym w oknie "Sukces"/"Wersja demo" zamiast
  zostawiać to niezauważone. `ui/demo_manager.py::show_after_generate`
  dostało analogiczny opcjonalny `extra_note`, żeby wersja demo też to
  pokazywała.

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `ui/main_window.py` | Usunięta rejestracja akcji menu (kod dialogu zostaje, tylko nieosiągalny); nowe `_previous_month_memory_note` | N/D (decyzja UX tej rundy, nie Enyo-specyficzna - dotyczy obu kanałów) |
| `ui/demo_manager.py` | `show_after_generate(parent, extra_note=None)` | TAK |
| `tests/test_previous_month_memory.py` | Test obecności akcji w menu zamieniony na test jej NIEobecności (przez źródło `_build_menu`, nie przez żywe `menuBar()` - PySide6 kasuje Python-owy wrapper podmenu z `addMenu(str)` bez trzymanej referencji); nowa klasa `PreviousMonthMemoryNoteTests` | TAK |
| `tests/test_demo_manager.py` (nowy) | `show_after_generate` z/bez `extra_note` | TAK |

**Weryfikacja:** pełny zestaw testów zielony (640 passed, 1 skipped),
zero regresji.

## Rozszerzenie danych klienta o kolejne placówki (2026-09-22)

Kontynuacja sekcji "Dane testowe z realnych grafików klienta (2026-09-19)"
wyżej - użytkownik doprecyzował konkretne godziny start/koniec zmian dla
większości z 7 placówek, które wtedy nie dały się odczytać ze zdjęć, i
podał komplet 10 placówek na nowo (z jedną dodatkową, "Sprzątanie",
wcześniej wspominaną tylko jako osobna tabela przy Nadleśnictwie).
`demo/install_client_sample_data.py` i `test_data/dane_klienta_ochrona.json`
rozszerzone o 4 nowe placówki (2 już istniały: Ubojnia GOSZ, PGE Ustka -
PGE dostało dodatkowego, wcześniej pominiętego pracownika "Sowiecki").

### Placówki dodane, zweryfikowane realnym generatorem (4/6 nowych)

3. **GZUK Łęczyce** (5 pracowników) - klient podał DWA dopuszczalne
   warianty tej samej doby: "7/7 24h" LUB "15/7 16h" (16h wieczór/noc +
   uzupełniające 8h za dnia). To dokładnie ten sam mechanizm co "24h
   kontra 12h+12h" w Ubojni/PGE (`normalize_duty_rotation()` nie wymaga,
   żeby podział był po połowie ani żeby `weekend_full` zaczynał się o tej
   samej godzinie co `weekend_half_a`) - solver wybiera wariant sam,
   codziennie.
4. **Łeba, Apartamenty Nadmorska 33** (3 pracowników) - "jedna zmiana 8/8"
   (wyłącznie 24h). Pola `weekend_half_a`/`b` mimo to wymagane przez
   `normalize_duty_rotation()` (nie da się skonfigurować samej zmiany 24h
   bez "wentyla bezpieczeństwa" podziału) - placeholder 08:00/20:00, bez
   żadnej roli blokującej podział.
5. **LakPol Słupsk** (3 pracowników) - "jedna zmiana 7/7 24h", ten sam
   przypadek co Łeba Apartamenty.
6. **P.P. Nadleśnictwo Cewice** (2 pracowników) - klient wprost potwierdził
   BRAK danych o wzorcu zmian ("stwórz po prostu puste"). **Znaleziony po
   drodze realny bug w tym podejściu:** zostawienie domyślnego
   `LocationConfig.open_hours` (DEFAULT_OPEN_HOURS, prawie całodobowy
   wzorzec sklepowy 05:30-23:00ish) NIE oznacza "brak wzorca" -
   `LocationConfig.get_night_shift_hours()` automatycznie wykrywa z tych
   godzin zmianę nocną (nachodzą na stałe okno 22:00-06:00) i generator
   faktycznie zaczął tam coś przydzielać (zweryfikowane empirycznie: 2
   pracowników dostało zmiany 22:00-06:00 na części dni miesiąca, mimo
   zerowej konfiguracji). Naprawa: lokalizacja dostaje jawnie zamknięte
   wszystkie dni tygodnia (`open_hours = {wd: (None, None) for wd in
   range(7)}`) - dopiero to daje faktycznie zero przydziałów (zweryfikowane
   ponownie: 0 obsadzonych dni-zmian w całym miesiącu).

### Placówki NIE dodane - potwierdzone z użytkownikiem, że pomijamy (4/10)

Użytkownik wybrał "Pomiń na razie" dla obu pytań (nie próbować prowizorki,
nie wpisywać ręcznie zablokowanych zmian):

| Placówka | Dlaczego nie pasuje |
|---|---|
| **MZGK Krzywoustego** | Różna długość zmiany w różne dni tygodnia (8h/7h w tygodniu, 6h sobota, 4h niedziela) - `logic/utils/time_utils.py::get_effective_daily_hours()` liczy JEDNĄ, stałą długość zmiany na pracownika (`standard_daily_hours * employment_fraction`), niezależną od dnia tygodnia. Nie istnieje mechanizm zmiennej długości zmiany per-dzień - wymagałoby nowej funkcji generatora. |
| **Brico Marche Wejcherowo**, **Brico Marche Lębork**, **Sprzątanie** | Pojedyncza, ciągła zmiana na cały okres otwarcia (np. 8:00-20:00, 12h; 14:00-21:00, 7h). Profil "Ochrona" (`rules=[]`) nie wymusza w ogóle obsady zwykłych zmian OPEN/CLOSE dla żadnej lokalizacji (świadoma decyzja profilu - brak `min_staff_with_role`), a długość zmiany OPEN/CLOSE jest zakotwiczona na jednej, wspólnej dla CAŁEGO `ShopConfig` wartości `standard_daily_hours` - dopasowanie jej naraz do 12h i 7h w jednym pliku wymagałoby kruchych sztuczek (globalne ustawienie + dostrajanie ułamków etatu na granicy zaokrągleń 15-minutowych), które łatwo dają wynik NIEZGODNY z zadanymi godzinami zamiast go odtwarzać. |

### Obserwacja warta uwagi klienta (potwierdza wcześniejszą z sekcji PGE wyżej)

Uruchomienie `AutoScheduleGenerator.generate()` na pełnych 6 placówkach
(25 pracowników, październik 2026, limit solvera 60s) zwraca **OPTIMAL /
success=True**. Dla WSZYSTKICH czterech placówek z dopuszczonym wariantem
24h (GZUK, Łeba Apartamenty, PGE Ustka, LakPol) solver w tym konkretnym
rozwiązaniu wybrał podział (12h+12h albo 16h+8h, zależnie od placówki) na
**KAŻDY** dzień miesiąca - ani razu nie zaproponował czystej zmiany 24h,
mimo że dla trzech z tych czterech placówek (Łeba, PGE, LakPol) klient
opisał wyłącznie zmianę 24h jako historycznie stosowaną. To bezpośredni,
teraz jeszcze wyraźniej potwierdzony efekt miękkiej preferencji
`logic/generator/duty_rotation_preference.py` (`PREFER_SPLIT_WEIGHT=5`) -
pokrycie jest poprawne w obu wariantach, ale wynik nie odzwierciedla stylu
pracy, jaki te placówki historycznie stosowały. Nie ma dziś mechanizmu
"wymuś zawsze 24h" (jest tylko odwrotność, `nie_chce_24h`, blokująca 24h) -
do rozważenia jako osobna zmiana w produkcyjnym kodzie, jeśli klient
potwierdzi, że to realny problem (a nie tylko kwestia tych konkretnych
danych testowych).

| Plik | Zmiana | Przywrócić do main? |
|---|---|---|
| `demo/install_client_sample_data.py` | 4 nowe funkcje budujące lokalizacje (`_gzuk_leczyce_location`, `_apartamenty_leba_location`, `_lakpol_slupsk_location`, `_nadlesnictwo_cewice_location`), 4 nowe listy pracowników, PGE dostało dodatkowego pracownika "Sowiecki" | NIE - dane jednego konkretnego klienta testowego |
| `test_data/dane_klienta_ochrona.json` | 6 placówek (było 2), 25 pracowników (było 11) | NIE (jw.) |

**Weryfikacja:** `python demo/install_client_sample_data.py` bez błędów,
`load_project()` + `ScheduleController.generate_schedule(force=True)` na
pełnym pliku zwraca OPTIMAL/success=True, ręczna inspekcja przydziałów
dzień-po-dniu potwierdza pełną obsadę wszystkich 5 placówek z
`duty_rotation` i zero przydziałów dla Nadleśnictwa. Pełny zestaw testów
programu zielony (649 passed, 1 skipped) - żaden istniejący test nie
odczytuje tego pliku bezpośrednio (testy duty_rotation używają własnych,
syntetycznych replik tych samych wzorców godzinowych), więc rozszerzenie
nie mogło nic zepsuć.
