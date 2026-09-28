# DinGo! — grafik pracy dla sklepów

Aplikacja desktopowa (Windows, Python + PySide6) do układania miesięcznego
grafiku pracy sklepu Dino. Sercem programu jest generator oparty o solver
**Google OR-Tools CP-SAT**, który układa zmiany otwarcia i zamknięcia oraz
zmiany pośrednie tak, żeby spełnić zasady ustawione przez użytkownika
(obsada, mięso, odpoczynek 11 h, godziny etatu, ręczne wpisy, urlopy), a gdy
się nie da — wskazuje przyczynę.

Ta gałąź (`main`) to wersja **DinGo!** (v1.2.0). Rozwijana równolegle wersja
dla firmy ochroniarskiej (Enyo: kilka placówek, profile działalności, rotacja
24/7) jest na gałęzi `integration/enyo-only` i ma tam własny opis.

---

## Spis treści

1. [Uruchomienie](#uruchomienie)
2. [Okno programu](#okno-programu)
3. [Konfiguracja sklepu](#konfiguracja-sklepu)
4. [Pracownicy](#pracownicy)
5. [Ręczne wpisy i tryb szybki](#ręczne-wpisy-i-tryb-szybki)
6. [Generator — jak działa](#generator--jak-działa)
7. [Gdy grafiku nie da się ułożyć](#gdy-grafiku-nie-da-się-ułożyć)
8. [Okres rozliczeniowy](#okres-rozliczeniowy)
9. [Zapis, eksport i wydruk](#zapis-eksport-i-wydruk)
10. [Licencja, wersja demo, aktualizacje](#licencja-wersja-demo-aktualizacje)
11. [Pliki danych](#pliki-danych)
12. [Struktura kodu](#struktura-kodu)
13. [Testy i diagnostyka](#testy-i-diagnostyka)
14. [Budowanie wydania](#budowanie-wydania)

---

## Uruchomienie

Wymagania: Python 3.11+ oraz biblioteki:

```bash
pip install PySide6 ortools openpyxl Pillow requests
```

Start:

```bash
python main.py              # otwiera ostatni stan pracy (last_project.json)
python main.py plik.myp     # otwiera wskazany projekt (tak robi też dwuklik na .myp)
```

Przy pierwszym uruchomieniu program pokazuje samouczek po oknie (później:
Pomoc → Samouczek).

---

## Okno programu

**Panel boczny**

- **Grafik na: MM.RRRR** i **Zmień datę** (miesiąc, rok, Zapisz). Zmiana
  miesiąca tworzy nowy, pusty grafik — pracownicy zostają, a grafik i
  ustawienia Konfiguracji wracają do wartości domyślnych (program pyta o
  potwierdzenie).
- **Nominalny etat** — liczba godzin pełnego etatu w tym miesiącu.
- **Generuj grafik** — układa cały miesiąc; ręczne wpisy zostają nietknięte.
- **Rozszerz widok** (kompaktowy ↔ rozszerzony), **Tryb szybki**,
  **Dodaj pracownika**, **Cofnij / Ponów**.
- **Okres rozliczeniowy** (patrz niżej).
- W wersji demo: licznik pozostałych generowań i przycisk zakupu; na dole
  **ID użytkownika** i numer wersji.

**Siatka grafiku**

- Wiersze: pracownicy. Kolumny: dni miesiąca, a na końcu godziny: Praca,
  Urlop, L4, Razem (oraz Cel w okresie rozliczeniowym).
- Wiersze podsumowania pod pracownikami (dzień po dniu): **Otwarcie,
  Zamknięcie, Rano, Popo, Mięso** — czy obsada spełnia zasady.
- Obsługa:
  - dwuklik na nazwisku — edycja pracownika,
  - dwuklik na komórce — edycja dnia (godziny, wolne, urlop, chorobowe),
  - dwuklik na nagłówku dnia — inne godziny otwarcia tego dnia albo „Dzień
    wolny ustawowo”,
  - prawy przycisk myszy — Kopiuj dzień, Wklej dzień, Odblokuj, Wyczyść
    komórkę,
  - klawisze: `1` / `2` — zablokuj typ zmiany rano / popołudnie (godzinę
    dobierze generator), `W` — wolne, `Ctrl+C` / `Ctrl+V` — kopiuj / wklej
    dzień, `Ctrl+Z` / `Ctrl+Y` — cofnij / ponów.

**Menu**

| Menu | Pozycje |
|---|---|
| Plik | Zapisz, Wczytaj, Eksport (Excel / JPG), Drukuj…, Zamknij |
| Edycja | Cofnij, Ponów, Wyczyść grafik (wszystko), Wyczyść auto (tylko zmiany z generatora) |
| Konfiguracja | Generator |
| Pomoc | Samouczek, Klucz produktu, Sprawdź aktualizacje, O programie |

---

## Konfiguracja sklepu

Konfiguracja → Generator, cztery zakładki:

| Zakładka | Co ustawia |
|---|---|
| Godziny otwarcia | godziny sklepu na każdy dzień tygodnia (domyślnie 05:30–22:45, pon. do 23:00) |
| Niedziele handlowe | które niedziele tego miesiąca są handlowe (pozostałe są zamknięte) |
| Limity | maks. liczba dni pracy pod rząd (domyślnie 4), „Wymuś 8h 30 min dla pracowników pełnoetatowych” (domyślnie włączone), podświetlanie przekroczenia dni pod rząd, minimalna obsada otwarcia i zamknięcia (domyślnie po 3 osoby) |
| Zasady generatora | limit czasu generatora (domyślnie 60 s), tryb każdej zasady (Wymagane / Preferowane / Wyłączone) i tryb liczenia odpoczynku 11 h |

Godziny pojedynczego dnia zmienia się dwuklikiem na nagłówku dnia w siatce.
Dzień oznaczony jako „Dzień wolny ustawowo” jest zamknięty i obniża
nominalny etat.

**Nominalny etat** = liczba dni pon–pt w miesiącu minus dni oznaczone jako
święta, razy 8 h. Norma pracownika = nominał × wymiar etatu, pomniejszona o
urlop i L4.

---

## Pracownicy

Okno pracownika: nazwisko, imię, **wymiar etatu** (1/1, „1/1 max 8:00”, 7/8,
3/4, 5/8, 1/2, 3/8, 1/4) oraz:

- **Pracownik otwarcia** — na każdym otwarciu i zamknięciu musi być co
  najmniej jedna taka osoba,
- **Obsługa stoiska mięsnego** i „może stanąć na chwilę na mięsie”
  (zastępstwo; te dwie opcje się wykluczają),
- **Kierowniczka** — sztywny grafik co tydzień: poniedziałek wolne, wt–pt
  7:00–15:00, sobota 6:00–14:00 (dni wpisywane automatycznie jako
  zablokowane; wymiar ustawiany na „1/1 max 8:00”),
- **Nie pracuje w godzinach nocnych** (przed 6:00 i po 22:00),
- **Nie pracuje na popołudniu** (tylko zmiany poranne).

Długość zmiany: 8 h × wymiar etatu; pełny etat — 8 h 30 min, gdy włączone
„Wymuś 8h 30 min”; „1/1 max 8:00” — zawsze 8 h.

---

## Ręczne wpisy i tryb szybki

**Edycja dnia** (dwuklik na komórce): godziny od–do, Wolne, Urlop,
Chorobowe. Koniec musi być później niż start (w obrębie jednej doby).

**Tryb szybki** (przycisk w panelu): wybierasz tryb i klikasz komórki.

| Tryb | Znaczenie |
|---|---|
| Praca | wpisuje godziny Od–Do z panelu (z podpowiedzią czasu pracy) |
| Rano / Popo | blokuje typ zmiany — dokładną godzinę dobierze generator spośród porannych / popołudniowych wariantów |
| Wolne | dzień zablokowany jako wolny |
| Urlop / L4 | nieobecność (obniża normę godzin) |

Każdy ręczny wpis godzin jest **blokadą**: generator go nie zmienia i
uwzględnia go w obsadzie, godzinach i odpoczynku. „Odblokuj” (prawy
przycisk) oddaje komórkę generatorowi. „Wyczyść auto” usuwa tylko zmiany z
generatora; „Wyczyść grafik” — wszystko.

---

## Generator — jak działa

```
KONFIGURACJA → model CP-SAT → rozwiązanie → zapis do grafiku
                                  └─ brak rozwiązania → grafik bez zmian + lista przyczyn
```

1. Czyszczone są dni niezablokowane, wpisywany jest wzorzec kierowniczek.
2. Dla każdego pracownika i dnia są możliwe zmiany: **otwarcie** (od
   godziny otwarcia), **zamknięcie** (do godziny zamknięcia) oraz warianty
   pośrednie przesunięte o 15–90 minut od otwarcia lub zamknięcia.
3. Zasady dokładane są wg trybu z zakładki „Zasady generatora”:
   **Wymagane** — twardy warunek, **Preferowane** — może być złamane za
   karę, **Wyłączone** — pomijane.
4. Solver szuka najlepszego grafiku w limicie czasu, na maks. 8 wątkach.

Zawsze obowiązują: urlop / L4 / wolne, ręczne wpisy, najwyżej jedna zmiana
dziennie, brak zmian w dni niehandlowe (niedziele niehandlowe, święta), zmiany
pośrednie tylko w dni z obsadą otwarcia/zamknięcia.

| Zasada | Domyślnie | Co robi |
|---|---|---|
| Odpoczynek 11 h | Wymagane | min. 11 h między zmianami; tryb standardowy (dokładny) albo uproszczony (po popołudniu nie ma rana) |
| Obsada otwarcia | Wymagane | dokładnie N osób na otwarciu, w tym ≥1 pracownik otwarcia i ≥1 osoba od mięsa |
| Obsada zamknięcia | Wymagane | to samo dla zamknięcia |
| Mięso na zmianach | Preferowane | osoba od mięsa na zmianach |
| Mięso przez cały dzień | Preferowane | stoisko mięsne obsadzone przez cały dzień |
| Dostępność pracownika | Preferowane | godziny, w których pracownik może pracować (jeśli zapisane w projekcie — w oknie pracownika nie ma na to pola) |
| Zakaz pracy nocnej / popołudniami | Preferowane | flagi pracownika |
| Godziny miesięczne | Preferowane | suma godzin = norma (tolerancja jednej zmiany) |
| Bilans godzin | zawsze Preferowane | jak najbliżej normy |
| Dni pod rząd | Preferowane | limit kolejnych dni pracy |

---

## Gdy grafiku nie da się ułożyć

Grafik zostaje **bez zmian**, a okno pokazuje przyczyny, które da się
udowodnić z danych, np.:

- w danym dniu zablokowano więcej osób na otwarciu/zamknięciu, niż wymaga
  obsada,
- za mało osób możliwych do pracy na otwarciu/zamknięciu,
- brak pracownika otwarcia albo osoby od mięsa możliwej do pracy,
- zablokowana przerwa między ręcznymi wpisami krótsza niż 11 h.

---

## Okres rozliczeniowy

Po wygenerowaniu grafiku: **Włącz okres rozliczeniowy** → w kolumnie „Cel”
(dwuklik) wpisujesz docelową liczbę godzin pracownika w miesiącu →
**Wyrównaj godziny**. Program dostraja długości już przydzielonych zmian
(przesuwa krawędź zmiany, która nie jest godziną otwarcia ani zamknięcia, o
15 min — najwyżej −60 / +15 min dziennie), a przy dużej nadwyżce zwalnia
całe dni. Nie układa grafiku od nowa; w tym trybie generowanie jest
wyłączone.

---

## Zapis, eksport i wydruk

- **Zapisz / Wczytaj** — projekt jednego miesiąca w pliku `.myp` (JSON;
  starsze `.json` też się wczytują). Program zapisuje też stan roboczy do
  `last_project.json` (po Konfiguracji, przy zapisie i przy zamykaniu) i
  otwiera go przy starcie.
- **Eksport**: Excel (`.xlsx`) i JPG. **Drukuj…** — wydruk grafiku z
  podglądem.

W wersji demo zapis, eksport i wydruk są zablokowane.

---

## Licencja, wersja demo, aktualizacje

- **ID użytkownika** jest wyliczane z maszyny; klucz produktu (Pomoc → Klucz
  produktu) jest powiązany z tym ID. Bez klucza działa wersja demo: 5
  generowań, bez zapisu i eksportu.
- **Aktualizacje**: przy starcie (i z menu Pomoc) program sprawdza
  najnowsze wydanie na GitHub Releases, porównuje wersję z `version.py` i
  proponuje pobranie instalatora `DingoSetup.exe`.

---

## Pliki danych

W katalogu programu: `last_project.json` (stan roboczy), `license.json`,
`machine_id.json`, `demo.json` (licznik demo), `first_run.flag`,
`config_tutorial_seen.flag` (samouczki).

---

## Struktura kodu

Warstwy: **UI → kontroler → generator → modele → zapis**.

```
main.py                     start aplikacji (opcjonalnie ścieżka .myp)
ui/                         PySide6: okno główne, siatka, okna dialogowe, samouczek, motyw
logic/
  schedule_controller.py    operacje na grafiku (wpisy, cofnij/ponów, generowanie)
  auto_generator.py         budowa i rozwiązanie modelu CP-SAT, zapis wyniku
  generator/                zasady (odpoczynek, obsada, mięso, godziny, ręczne wpisy, ...),
                            funkcja celu, solver, diagnostyka, zapis rozwiązania
  manager_schedule.py       sztywny grafik kierowniczek
  settlement_balancer.py    okres rozliczeniowy („Wyrównaj godziny”)
model/                      ShopConfig, Employee, MonthSchedule, DaySchedule, tryby zasad
persistence/project_io.py   zapis/odczyt projektu
export/                     Excel i JPG
tests/                      testy pytest i skrypty diagnostyczne
```

---

## Testy i diagnostyka

```bash
python -m pytest tests/
```

Odtwarzalna diagnostyka solvera na losowym projekcie:

```bash
python tests/run_generator_diagnostics.py --seed 17 --employees 10
```

W `Output/diagnostics/` powstają: projekt wejściowy (do otwarcia w
aplikacji), raport po każdym kolejnym etapie zasad, wygenerowany grafik i
surowy ślad przypisań solvera. Gdy model nie ma rozwiązania, raport wskazuje
pierwszy etap i najmniejszy zestaw zasad Wymaganych, który się wyklucza.

---

## Budowanie wydania

- PyInstaller: `Dingo! - narzędzie do grafików pracy.spec`.
- Instalator Inno Setup: `dla inno.iss` (rejestruje rozszerzenie `.myp`).
- `releases/enyo.json` — manifest aktualizacji dla wydań Enyo (budowanych z
  gałęzi `integration/enyo-only`).
