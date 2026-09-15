# Plan: poprawa czytelności i przyjemności użytkowania UI (bez przeprojektowania)

Branch: `claude/ui-readability-audit-bnjy3e`. To jest wyłącznie plan — audyt
oparty o pełne przeczytanie kodu (`ui/main_window.py`, `ui/grid_view.py`,
`ui/config_dialog.py`, `ui/employee_dialog.py`, `ui/new_project_dialog.py`,
`ui/profile_wizard_dialog.py`, `ui/day_edit_dialog.py`,
`ui/day_override_dialog.py`, `ui/business_profile_picker.py`,
`ui/theme.py`, `ui/first_run_wizard.py`, `ui/tutorial_overlay.py`,
`ui/tutorial_dialog.py`, `ui/demo_manager.py`, `ui/license_manager.py`,
`ui/loading_overlay.py`, `ui/tooltip.py`, `ui/time_input.py`,
`ui/emoji_palette.py`), **brak zmian w kodzie**.

Cel: appka ma zostać tą samą appką — tylko wygodniejszą i bardziej spójną
wizualnie — dla klientów codziennie z niej korzystających (dziś Dino,
docelowo inne branże). Nie zgadujemy potrzeb konkretnej branży (np.
ochrony) — to poprawki uniwersalne dla każdego użytkownika appki.

## 1. Przegląd głównych okien

**`main_window.py`** — panel boczny generalnie dobrze zorganizowany
(sekcje z nagłówkami, scroll na niskich ekranach). Problemy:
- Tryb szybki nadpisuje dane pojedynczym kliknięciem na siatce bez
  żadnego sygnału na komórkach, że tryb jest aktywny — łatwo o
  przypadkową zmianę.
- Przy okazji czytania kodu znalezione dwa drobne bugi, niezwiązane wprost
  z UX, ale warte odnotowania: zduplikowana metoda `_ctx_sick` (linie 922
  i 1412 — martwa duplikacja) oraz realne ryzyko `UnboundLocalError` w
  `_quick_update_duration` (linie 1447–1466) — gdy pole godziny jest puste
  (a `TimeInputWidget` czyści się przy kliknięciu, patrz niżej), funkcja
  odwołuje się do niezainicjowanych zmiennych `h`/`m`. To realna ścieżka
  do crasha przy zwykłym korzystaniu z trybu szybkiego.

**`grid_view.py`** (1334 linii, serce aplikacji) — najbardziej
przeciążone wizualnie okno:
- Na jednej komórce potencjalnie nakładają się: kolor tła (stan/błąd),
  wzór szrafury (używany do **dwóch różnych znaczeń** — zablokowany typ
  zmiany i zablokowany dzień wolny, linie 695-719, nie do odróżnienia bez
  tooltipa), 3 różne "technologie" ikon (ręcznie rysowane QPainter, pliki
  PNG, surowe emoji), obramowanie aktywnego wiersza, pasek nad nagłówkiem
  dnia przy nadpisanych godzinach.
- Menu kontekstowe (PPM, linie 1135-1195) i skróty klawiszowe
  (`1`/`2`/`W`/`Ctrl+C`/`Ctrl+V`, linie 995-1024) są całkowicie
  nieodkrywalne — zero wizualnego sygnału, że w ogóle istnieją.
- Wiersz walidacji "mięso" pokazuje emoji (✅❌⚠️, linie 909-924), sąsiednie
  wiersze — liczby. Niespójna reprezentacja w tej samej tabeli.
- `TimeInputWidget` (używany też w `day_edit_dialog.py`,
  `day_override_dialog.py`, panelu szybkim) czyści pole natychmiast po
  kliknięciu zamiast zaznaczać wartość (`time_input.py:48-51`) — sprawia
  wrażenie utraty danych.
- Puste komórki dla dni, gdy sklep jest nieczynny — tylko szare tło, bez
  tekstu i bez tooltipa na samej komórce (linie 735-738); wyjaśnienie jest
  wyłącznie w tooltipie nagłówka kolumny — łatwo przeoczyć.

**`config_dialog.py`** (892 linie) — najbardziej "dokładane funkcja po
funkcji" okno:
- 5 zakładek, 3 wymagają scrolla mimo okna 720×560 — jawny sygnał
  przeciążenia względem rozmiaru.
- Tekst w UI wprost zdradza stan wewnętrzny developmentu (linie 546-559:
  "Generator jeszcze go nie przydziela...") — komunikat dla testera, nie
  dla pracownika sklepu.
- Progressive disclosure ("Pokaż ustawienia zaawansowane", linie 648-664)
  zastosowane tylko w jednej z 5 zakładek — reszta miesza podstawowe i
  rzadkie pola bez rozróżnienia.
- Żargon solvera ("Polityka: Wymagane/Preferowane/Wyłączone", "Waga") bez
  tłumaczenia dla laika w większości miejsc (część ma dobre tooltipy, np.
  `solver_time_limit` linie 682-686, `rest_11h_mode` linie 727-733 — ale
  niekonsekwentnie).
- Ma resztki starego, hardkodowanego stylu (linie 374, 413, 670) mimo
  komentarza w kodzie (linie 173-175), że tego już nie ma.

**`employee_dialog.py`** — najbardziej "czysty" formularzowo, ale ma
realny bug funkcjonalny: pole **"miesięczny cel godzin" jest utworzone
(linie 88-91), ale nigdy nie dodane do żadnego layoutu** — niewidoczne dla
użytkownika, mimo że jest zapisywane i wczytywane w tle (linie 207, 250).
Osobno: zaznaczenie "Kierownik" po cichu zmienia wymiar etatu bez
wyjaśnienia w UI (linie 189-195).

**`new_project_dialog.py`** i **`business_profile_picker.py`** —
najlżejsze i najbardziej spójne okna, dobry wzorzec do naśladowania
gdzie indziej.

**`profile_wizard_dialog.py`** — nazwa i tytuł sugerują kreator krokowy,
w praktyce to jeden długi, przewijany formularz reguł generatora (linie
298-312) bez podziału na etapy — rozjazd między oczekiwaniem a
rzeczywistością. Pole "Waga" (`weight_spin`, linie 167-171) bez żadnego
tooltipa tłumaczącego co ta liczba znaczy.

**`day_edit_dialog.py`** vs **`day_override_dialog.py`** — spójne między
sobą (te same wzorce nagłówków `sectionLabel`, `QFormLayout`, kolejność
przycisków w `QDialogButtonBox`), ale oba dziedziczą niespójność
wizualną `TimeInputWidget` względem reszty aplikacji.

**Onboarding** (`first_run_wizard.py`, `tutorial_overlay.py`) — opisany
w sekcji 3.

**Martwy kod** (nie wpływa na UX bezpośrednio, ale myli w utrzymaniu i
warto posprzątać przy okazji): `ui/tutorial_dialog.py` (niedokończona,
zastąpiona wersja samouczka z placeholderami na obrazki, zero importów w
repo) i `ui/tooltip.py` (napisany w **Tkinterze** w projekcie PySide6 —
nigdy nie mógł zadziałać, zero importów).

## 2. Spójność wizualna — wzorce powtarzające się w wielu plikach

`theme.py` jako fundament trzyma większość aplikacji spójnie, ale kilka
konkretnych elementów regularnie go omija w powtarzających się wzorcach —
to sygnał, że dodawaliśmy funkcje w różnych sesjach bez wracania do
wspólnego źródła stylu:

**A. Trzy miejsca z "obcym" niebieskim `#0078d4`** (kolor Windows/Fluent)
zamiast marki `ACCENT = #1d4ed8`:
- `time_input.py:19-33` (focus pola godziny)
- `tutorial_overlay.py:182` (podświetlenie elementu w samouczku)
- `grid_view.py:958,965` (obramowanie aktywnego/najechanego wiersza)

To najbardziej rzucająca się w oczy rozbieżność, bo dotyczy głównego
akcentu kolorystycznego marki, w trzech niezależnych plikach.

**B. Proliferacja kolorów "ostrzegawczych/błędu"** bez wspólnego źródła:
`theme.ERR_RED` (#ffd0cf), `theme.WARN_YELLOW` (#fff0b3),
`OVERRIDE_BAR_COLOR` w grid_view (#f59e0b), tło "Chorobowe" w grid_view
(#FFA07A — trzeci, niezależny pomarańcz), czerwień ikony "zakaz"
(#d64545). Pięć różnych odcieni "coś jest nie tak/uwaga" w jednej
aplikacji.

**C. Dwa różne przyciemnienia tła nakładek modalnych**:
`loading_overlay.py` (`rgba(0,0,0,120)`) vs `tutorial_overlay.py`
(`rgba(15,18,24,190)`) — ta sama koncepcja, dwie różne wartości.

**D. Dwa odcienie szarości na "przygaszony tekst"**: `theme.TEXT_MUTED`
(#6b7280) vs `grid_view.py:286` (#8a8a8a) na etykiecie wymiaru etatu.

**E. `time_input.py` całkowicie omija theme.py** — inny promień
zaokrąglenia (4px zamiast 10px), inny border, inny focus. Ponieważ ten
widget jest używany w panelu szybkim, `day_edit_dialog` i
`day_override_dialog`, te miejsca wizualnie odstają od reszty pól
tekstowych w aplikacji.

**F. Ikonografia bez jednego systemu** — ręcznie rysowane ikony QPainter
(gwiazdka kierownika, przekreślony księżyc/słońce), pliki PNG z assets,
surowe emoji (🔒🌴🤒⚠️✅❌) — trzy różne "języki wizualne" na tej samej
siatce.

**G. Systemowe `QMessageBox`/`QInputDialog`** (demo/licencja, większość
komunikatów błędów w całej appce) kontrastują z resztą aplikacji, która
ma spersonalizowany, zaokrąglony, niebiesko-biały styl — systemowe
okienka z ikoną ostrzeżenia mogą się mylić z faktycznym błędem/awarią
programu.

Pozytyw: `first_run_wizard.py`, `new_project_dialog.py`,
`business_profile_picker.py`, `employee_dialog.py`,
`profile_wizard_dialog.py` konsekwentnie korzystają z `objectName`
zdefiniowanych w `theme.py` (`primaryButton`, `secondaryButton`,
`dangerButton`, `mutedHint`, `configCard` itd.) — dobrze działający
wzorzec, tylko niekonsekwentnie stosowany w starszych/bardziej złożonych
plikach (`config_dialog.py`, `grid_view.py`).

## 3. Onboarding nowego użytkownika

Przepływ: `_check_first_run()` (main_window.py:1501-1526) → jeśli świeży
instal: `FirstRunWizardDialog` (5 kroków: powitanie, dane podstawowe,
branża, cechy, zasady generatora) → **zawsze**, nawet po anulowaniu
kreatora, odpala się `TutorialOverlay` (8 kroków, live-podświetlanie
elementów UI, `main_window.py:1344-1392`).

Problemy:
- **Anulowanie kreatora nie ma potwierdzenia** (`first_run_wizard.py:102-105`,
  `self.reject()` bez pytania) — przypadkowy klik "Anuluj" zostawia
  użytkownika z domyślnym, nieopisanym profilem `dino_retail`, bez
  świadomości że nic nie skonfigurował.
- **Wizard nie pokazuje postępu** ("krok X z Y") — w przeciwieństwie do
  `TutorialOverlay`, który to robi (`tutorial_overlay.py:106`).
- Niespójna terminologia "Pomiń": krok "Zasady generatora" ma przycisk
  "Pomiń — użyj wartości domyślnych", który **kończy cały kreator**, a nie
  tylko bieżący krok — inne kroki nie mają odpowiednika.
- Po kreatorze od razu, bez przerwy, startuje przyciemniona nakładka
  samouczka — brak chwili, by zobaczyć wynikowy stan aplikacji.
- Jeśli element docelowy kroku samouczka (np. `btn_add_employee`) nie jest
  akurat widoczny, karta pojawia się na środku ekranu bez podświetlenia i
  bez wyjaśnienia dlaczego.
- **Brak trwałego "co dalej"** — jedyna wskazówka sekwencji działań to
  ulotny tekst w ostatnim kroku samouczka, który znika i nigdy nie zostaje
  utrwalony jako stały element UI (np. checklist w panelu bocznym).
- **Brak realnego empty state na siatce** — gdy nie ma pracowników,
  `grid_view.build()` po prostu zeruje tabelę (linie 549-552: pusta,
  biała, bezkolumnowa siatka). Jedyna podpowiedź to reaktywny komunikat
  dopiero **po kliknięciu "Generuj"** ("Dodaj pracowników przed
  generowaniem grafiku", `main_window.py:723-725`).
- Samouczek jest dostępny z menu Pomoc → Samouczek (`main_window.py:534`),
  ale nic w interfejsie aktywnie o tym nie przypomina, jeśli użytkownik go
  zamknie/pominie.

## 4. Szybkie wygrane — priorytetowa lista

Tanie, niskiego ryzyka, zauważalny wpływ na odbiór:

1. Ujednolicić "obcy" niebieski `#0078d4` → `theme.ACCENT` w trzech
   miejscach: `time_input.py`, `tutorial_overlay.py:182`,
   `grid_view.py:958,965`.
2. Zastąpić hardkodowany stylesheet `TimeInputWidget`
   (`time_input.py:19-33`) stylami zgodnymi z `theme.py` — naprawia
   spójność jednym miejscem w 3+ oknach naraz.
3. Naprawić `_quick_update_duration` w `main_window.py` (ryzyko crasha
   przy pustym polu godziny w trybie szybkim) i usunąć zduplikowaną
   `_ctx_sick`.
4. Odsłonić w UI pole "miesięczny cel godzin" w `employee_dialog.py`
   (obecnie martwe wizualnie mimo że działa w tle) — albo świadomie
   usunąć, jeśli faktycznie niepotrzebne.
5. Dodać potwierdzenie przy "Anuluj" w `first_run_wizard.py` (analogicznie
   do istniejącego `closeEvent` w main_window).
6. Dopisać krótką wzmiankę o PPM i skrótach klawiszowych
   (1/2/W/Ctrl+C/V) w tooltipie nagłówka kolumny lub w statusbarze.
7. Dodać do tooltipa zablokowanej komórki informację "kliknij prawym
   przyciskiem, aby odblokować".
8. Usunąć martwe pliki `ui/tutorial_dialog.py` i `ui/tooltip.py`
   (Tkinter) — zero ryzyka, porządkuje kod.
9. Zamienić trzy inline `setStyleSheet("color: #6b7280...")` w
   `config_dialog.py` (linie 374, 413, 670) na `objectName="mutedHint"`.
10. Złagodzić `QMessageBox.critical` → `.warning` przy zwykłych błędach
    walidacji formularzy (dzień, override).
11. Dodać placeholder z formatem godziny ("GG:MM") w `TimeInputWidget`.
12. Ujednolicić kolor tła "Chorobowe" (`#FFA07A`) z istniejącą paletą
    ostrzeżeń zamiast trzeciego niezależnego odcienia.
13. Usunąć/przeformułować tekst zdradzający stan developmentu w
    `config_dialog.py:546-559` pod użytkownika końcowego.

## 5. Rzeczy większe / ryzykowne — do świadomej decyzji

- **Legenda/klucz kolorów i ikon na siatce grafiku** — dziś na jednej
  komórce nakłada się zbyt wiele niezależnie dodawanych sygnałów
  wizualnych. Wymaga przemyślenia całego systemu wizualnego komórki, nie
  kosmetyki.
- **Rozszerzenie `theme.py` o pełną, nazwaną paletę "stanów komórki"**
  (sick/leave/error/warning/locked/blocked-shift/manager/no-night) i
  migracja `grid_view.py` do niej.
- **Realny empty state na siatce** (baner/CTA "Dodaj pierwszego
  pracownika") zamiast reaktywnego komunikatu po kliknięciu Generuj.
- **Spersonalizowane dialogi zamiast systemowych
  `QMessageBox`/`QInputDialog`** dla demo/licencji i części błędów.
- **Wizualne rozróżnienie dwóch znaczeń tej samej szrafury** (blokada
  typu zmiany vs blokada dnia wolnego).
- **Scalenie modelu samouczka** (żywy `TutorialOverlay` vs martwy
  `tutorial_dialog.py` ze statycznymi obrazkami) w jeden spójny system
  podpowiedzi, z sensownym fallbackiem gdy element docelowy nie jest
  widoczny.
- Mechanizm "zamrożonej kolumny nazwisk" w `grid_view.py`
  (`_create_frozen_name_column`, linie 437-492) jest złożony i kruchy —
  każda przyszła zmiana layoutu siatki niesie ryzyko rozjazdu i wymaga
  ostrożnego retestu.

## 6. Priorytetyzacja — efekt vs ryzyko

Najwyższy stosunek efekt/ryzyko, w kolejności:

1. Ujednolicenie "obcego" niebieskiego akcentu (3 pliki, 1 kolor) —
   natychmiast bardziej spójna marka, zero ryzyka funkcjonalnego.
2. Naprawa `TimeInputWidget` pod theme.py — jedna zmiana, poprawia 3+
   okna.
3. Naprawa bugów: crash w trybie szybkim, ukryte pole celu godzinowego
   pracownika.
4. Odkrywalność ukrytych interakcji (PPM, skróty, odblokowanie) przez
   same tooltipy/statusbar — czysto tekstowe zmiany, zero ryzyka layoutu.
5. Usunięcie martwego kodu (`tutorial_dialog.py`, `tooltip.py`) —
   porządek bez ryzyka.
6. Potwierdzenie przy Anuluj w kreatorze pierwszego uruchomienia.
7. Dopiero potem: większe rzeczy (legenda kolorów/ikon na siatce, empty
   state, migracja palety stanów) — bo wymagają decyzji projektowych i
   szerszego retestu.

## 7. Etapy wdrożenia (małe, testowalne kroki)

### Etap A — kolory bazowe (bez ryzyka funkcjonalnego)
Ujednolicić `#0078d4` → `ACCENT` w 3 plikach (`time_input.py`,
`tutorial_overlay.py`, `grid_view.py`); ujednolicić dwa odcienie
muted-text; scalić dwa przyciemnienia overlay.
Test: wizualne porównanie przed/po w każdym z dotkniętych okien.

### Etap B — `TimeInputWidget` pod theme.py
Usunąć lokalny stylesheet, polegać na globalnym stylu `QLineEdit`.
Test: pola godzin w panelu szybkim, `day_edit_dialog`,
`day_override_dialog` — sprawdzić wygląd i że focus/walidacja nadal
działają.

### Etap C — porządki i drobne bugi
Usunąć `tutorial_dialog.py`, `tooltip.py`; naprawić
`_quick_update_duration`; usunąć zduplikowaną `_ctx_sick`; odsłonić lub
świadomie usunąć pole `monthly_target_hours`.
Test: tryb szybki z pustym polem godziny nie crashuje; edycja
pracownika.

### Etap D — odkrywalność interakcji
Tooltipy z informacją o PPM/skrótach na siatce, tooltip "PPM →
Odblokuj" na zablokowanej komórce, placeholder w polu godziny.
Test: manualne najechanie na komórki, sprawdzić czytelność tooltipów.

### Etap E — onboarding
Potwierdzenie przy Anuluj w kreatorze; licznik kroków w
`first_run_wizard`; usunięcie tekstu deweloperskiego z
`config_dialog.py` (zmiana nocna).
Test: pełne przejście onboardingu od zera (świeży `first_run.flag`).

### Etap F — spójność komunikatów błędów
Złagodzić `critical` → `warning` tam, gdzie to zwykła walidacja
formularza; ujednolicić kolor "Chorobowe".
Test: wywołać typowe błędy walidacji w każdym z dialogów.

### Etap G — większe zmiany (do osobnej decyzji, po A–F)
Legenda/system wizualny komórki siatki, pełna paleta stanów w
theme.py, empty state na siatce, spersonalizowane dialogi
demo/licencja.

## 8. Kolejność i punkt startu

Start od Etapu A (kolory) i B (`TimeInputWidget`) — zero ryzyka
funkcjonalnego, natychmiast widoczna poprawa spójności w wielu oknach
naraz. Etapy C–F można robić w dowolnej kolejności między sobą, każdy
niezależnie testowalny. Etap G wymaga wcześniejszej świadomej decyzji
(patrz sekcja 5) i nie powinien ruszać przed ukończeniem A–F.
