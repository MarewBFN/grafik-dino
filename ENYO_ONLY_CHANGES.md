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
