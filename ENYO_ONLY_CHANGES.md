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
| _(na razie brak wpisów - branch dopiero startuje)_ | | | | | |

## Pojedyncze fragmenty kodu (nie całe pliki)

Gdy usuwamy/ukrywamy tylko kawałek pliku (np. gałąź `if is_dino_style(...)`
albo jedno pole formularza), a nie cały plik - wpis tutaj zamiast w tabeli
wyżej, żeby nie zaśmiecać jej ścieżkami plików, które w większości zostają.

| Plik | Co dokładnie (funkcja/blok/pole) | Akcja | Commit | Przywrócić do main? | Notatka |
|---|---|---|---|---|---|
| _(brak wpisów)_ | | | | | |

## Audyt (2026-09-18) - pełna lista kandydatów, jeszcze nietknięta

Pełny przegląd kodu pod kątem tego, co klient Enyo faktycznie widzi/może
kliknąć. Podzielony na 3 poziomy priorytetu. Profil klienta to custom
profil `ochrona_enyo` (patrz `demo/install_demo.py`) - `DINO_RETAIL_PROFILE`
("dino_retail") jest ZAWSZE zarejestrowany bezwarunkowo przy imporcie
`model/business_profile.py` (linia `register_profile(DINO_RETAIL_PROFILE)`
poza jakimkolwiek warunkiem), więc każdy mechanizm, który iteruje
`BUSINESS_PROFILES.values()`, pokazuje go klientowi razem z Ochroną.

### Poziom 1 - realne wycieki do klienta (widoczne w normalnym użytkowaniu)

- **`ui/config_dialog.py:82-108`** - okno "Konfiguracja" (otwierane
  regularnie) ma wiersz "Profil działalności:" z dropdownem listującym
  WSZYSTKIE zarejestrowane profile (`BUSINESS_PROFILES.values()`) - klient
  widzi tam "Sklep (Dino)" obok "Ochrona" i może realnie przełączyć swój
  projekt na Dino. Do tego przyciski "Nowy profil...", "Edytuj profil...",
  "Usuń profil..." - pełne CRUD profili wprost w głównym oknie configu.
  `business_type_selector.setEnabled(count() > 1)` (linia 149) - selektor
  jest aktywny zawsze, bo Dino zawsze jest zarejestrowany.
- **`ui/config_dialog.py:394-412`** (zakładka "Limity") - sekcja
  "MINIMALNA OBSADA PRACOWNIKÓW" (pola "Pracowników na otwarciu (rano)"/
  "...na zamknięciu (wieczór)") pokazuje się BEZWARUNKOWO, bez guardu jak
  ma zakładka "Niedziele handlowe" (`if self.profile.uses_trade_calendar`,
  linia 120-121). `model/constraints.py:223` już i tak ignoruje te wartości
  dla profili innych niż dino_retail - więc dla Enyo to pole, które nic nie
  robi, ale wygląda jak działające ustawienie.
- **`ui/new_project_dialog.py` + `ui/business_profile_picker.py`** - okno
  "Nowy projekt" zawsze pokazuje sekcję "Branża:" z pełną listą profili +
  przycisk "+ Nowa branża..." otwierający `ProfileWizardDialog`.
- **`ui/first_run_wizard.py`** (krok `STEP_BRANCH`) - ten sam wybór branży
  w kreatorze pierwszego uruchomienia.
- **`ui/main_window.py::_about` (~linia 1601)** - okno "O programie" pisze
  wprost `<b>Dingo!</b>` + osobistą dedykację ("Z dedykacją dla Mamy ❤️,
  Dzięki za wsparcie i motywację") + link `madebykewin.pl`. Zero z tego nie
  nadaje się na ekran, który zobaczy klient Enyo.
- **`ui/tutorial_dialog.py`** - samouczek zaczyna się od "Witaj w Grafik
  Dino v2!", opisuje program jako narzędzie "dla sklepów", a przykładowe
  role w kroku 1 to "otwarcie"/"mięso" (Dino-specyficzne, nie istnieją w
  profilu Ochrona). Zrzuty ekranu `assets/tutorial/step1-6.png` prawie na
  pewno pokazują UI/dane Dino (nieprzejrzane wizualnie - do sprawdzenia
  ręcznie, screenshoty się nie grepują).
- **`ui/main_window.py:2097`** - tytuł dialogu aktualizacji to
  `"Aktualizacja DinGO"`.
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

### Poziom 3 - decyzje architektoniczne (nie da się rozstrzygnąć samym gotowym audytem)

- Czy **cały mechanizm profili custom** (kreator `ProfileWizardDialog`,
  `+ Nowa branża...`, edycja/usuwanie profilu, `model/custom_profile*.py`)
  ma zniknąć z UI Enyo w całości (klient ma DOKŁADNIE jeden, gotowy profil
  "Ochrona" i nigdy nie tworzy nowego), czy tylko dropdown profili ma
  przestać pokazywać Dino (usunąć `DINO_RETAIL_PROFILE` z listy, zostawić
  kreator na wypadek gdyby Enyo dostał drugi obiekt/branżę)?
- Czy `DINO_RETAIL_PROFILE`/`dino_retail` zostaje zarejestrowany w ogóle w
  tym buildzie, czy usuwamy rejestrację i cały generator dino_retail
  fizycznie z tego brancha (mniejsza binarka, zero ryzyka wycieku, ale
  utrudnia ewentualny powrót zmian do main przez rozjazd struktury)?
