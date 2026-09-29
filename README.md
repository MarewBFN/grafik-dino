# Grafik pracy (DinGo! / Enyo)

Aplikacja desktopowa (Windows, Python + PySide6) do układania miesięcznych
grafików pracy. Sercem programu jest generator oparty o solver
**Google OR-Tools CP-SAT**, który układa zmiany tak, żeby spełnić zasady
ustawione przez użytkownika (odpoczynek, obsada placówki, godziny etatu,
ręczne wpisy, urlopy itd.), a gdy się nie da — mówi dlaczego.

Z tego samego kodu budowane są dwie wersje:

| Wersja | Dla kogo | Profil działalności |
|---|---|---|
| **DinGo!** (kanał `dino`) | sklepy Dino | „Sklep (Dino)” — zmiany otwarcia/zamknięcia, mięso, niedziele handlowe |
| **Enyo – Grafik Pracy** (kanał `enyo`) | firma ochroniarska | „Ochrona” — rotacja 24/7 i placówki z godzinami otwarcia (także przez północ) |

Gałąź `integration/enyo-only` to wersja Enyo: wybór profilu pokazuje tylko
profile inne niż Dino, a część elementów interfejsu Dino jest schowana (kod
zostaje — szczegóły w `ENYO_ONLY_CHANGES.md`). Profil Dino dalej działa i
jest objęty testami.

---

## Spis treści

1. [Uruchomienie](#uruchomienie)
2. [Okno programu](#okno-programu)
3. [Projekt, miesiące i placówki](#projekt-miesiące-i-placówki)
4. [Pracownicy](#pracownicy)
5. [Ręczne wpisy i tryb szybki](#ręczne-wpisy-i-tryb-szybki)
6. [Generator — jak działa](#generator--jak-działa)
7. [Profil Ochrona (Enyo)](#profil-ochrona-enyo)
8. [Profil Sklep (Dino)](#profil-sklep-dino)
9. [Gdy grafiku nie da się ułożyć](#gdy-grafiku-nie-da-się-ułożyć)
10. [Eksport i wydruk](#eksport-i-wydruk)
11. [Licencja, wersja demo, aktualizacje](#licencja-wersja-demo-aktualizacje)
12. [Pliki danych](#pliki-danych)
13. [Struktura kodu](#struktura-kodu)
14. [Testy i audyt generatora](#testy-i-audyt-generatora)
15. [Budowanie wydania](#budowanie-wydania)

---

## Uruchomienie

Wymagania: Python 3.11+ oraz biblioteki:

```bash
pip install PySide6 ortools holidays openpyxl Pillow requests
```

Start:

```bash
python main.py              # otwiera ostatni projekt (last_project.json)
python main.py plik.myp     # otwiera wskazany projekt (tak robi też dwuklik na .myp)
```

Przykładowe dane (opcjonalnie, przed startem):

```bash
python demo/install_demo.py                # profil „Ochrona” (Enyo) + przykładowy projekt
python demo/install_client_sample_data.py  # dane testowe klienta (kilka placówek, 24/7)
```

Pierwsze uruchomienie pokazuje kreator „Szybka konfiguracja” (nazwa, miesiąc,
branża, zasady generatora), a potem samouczek po oknie (Pomoc → Samouczek).

---

## Okno programu

**Panel boczny**

- **Grafik na: MM.RRRR** i **Zmień datę** — kalendarz miesięcy projektu ze
  stanem każdego („Grafik gotowy”, „W trakcie edycji”, „Pusty grafik”).
- **Przełącznik placówek** (◀ nazwa ▶) — siatka zawsze pokazuje jedną placówkę.
- **Nominalny etat** — liczba godzin pełnego etatu w tym miesiącu.
- **Generuj grafik** — układa grafik **tylko dla wybranej placówki**; ręczne
  wpisy zostają nietknięte.
- **Rozszerz widok** (kompaktowy ↔ rozszerzony), **Tryb szybki**,
  **Dodaj pracownika**, **Cofnij / Ponów**.

**Siatka grafiku**

- Wiersze: pracownicy placówki (z ikonami: „Umowa”, „Nie chce 24h”, „Nie
  pracuje w nocy/na popołudniu”, wymiar etatu). Kolumny: dni miesiąca,
  poprzedzone ostatnim dniem poprzedniego miesiąca (podgląd, skąd bierze się
  odpoczynek na początku miesiąca).
- Na końcu wiersza: godziny pracy, urlop, L4, razem i **nadgodziny** —
  przekroczenie miesięcznego limitu pełnego etatu jest podświetlone na
  czerwono (także w eksportach).
- Wiersze podsumowania pod pracownikami: dla Ochrony **„Obłożenie”** (✅/❌
  na każdy dzień — rotacja 24/7: dokładnie jedna osoba przez całą dobę;
  placówka z godzinami: całe okno obsadzone i nie więcej osób niż „Maks.
  obsada naraz”), dla Dino Otwarcie, Zamknięcie, Rano, Popo, Mięso.
- Obsługa:
  - dwuklik na nazwisku — edycja pracownika,
  - dwuklik na komórce — edycja dnia,
  - dwuklik na nagłówku dnia — godziny placówki tego dnia („Nieczynne tego
    dnia” albo inne godziny),
  - prawy przycisk myszy — kopiuj/wklej dzień i tryby z trybu szybkiego,
  - klawisze: `1`/`2` — typ zmiany rano/popołudnie, `W` — wolne,
    `Ctrl+C`/`Ctrl+V` — kopiuj/wklej dzień.

**Menu**

| Menu | Pozycje |
|---|---|
| Plik | Nowy projekt…, Usuń konfigurację, Zapisz, Wczytaj, Eksport (Excel / JPG / PDF), Karty pracy (Excel / JPG / PDF), Drukuj…, Zamknij |
| Edycja | Cofnij, Ponów, Wyczyść grafik (wszystko), Wyczyść auto (tylko zmiany z generatora) |
| Konfiguracja | Generator, Lokalizacje, Ustawienia trybu szybkiego |
| Wygląd | Wygląd komórek kompaktowych (standardowy / ułamki), Legenda kolorów |
| Pomoc | Samouczek, Klucz produktu, Sprawdź aktualizacje, O programie |

---

## Projekt, miesiące i placówki

**Projekt** to jeden plik `.myp` (JSON) zawierający **wszystkie miesiące**, które
w nim otwarto — przełączenie miesiąca niczego nie kasuje. Nowy miesiąc startuje
pusty, ale z tymi samymi pracownikami, placówkami i zasadami. Starsze pliki
`.json` (jeden miesiąc) nadal się wczytują.

- Program na bieżąco zapisuje stan roboczy do `last_project.json` (każda zmiana
  Konfiguracji, Lokalizacji, trybu szybkiego i godzin dnia) i otwiera go przy
  starcie. **Zapisz** tworzy właściwy plik projektu.
- **Pamięć poprzedniego miesiąca**: przy przejściu do nowego miesiąca program
  zapamiętuje koniec ostatniej zmiany każdego pracownika z ostatniego dnia
  poprzedniego miesiąca i uwzględnia go w odpoczynku na początku nowego.
- **Nominalny etat** liczony jest wg Kodeksu pracy: dni robocze pn–pt minus
  święta w dni powszednie, minus dzień za święto przypadające w sobotę
  (święta z biblioteki `holidays`), razy standardowa zmiana (8 h). Pracownik
  ma normę = nominał × wymiar etatu, pomniejszoną o urlop/L4.

**Placówki** (Konfiguracja → Lokalizacje; godziny bieżącej placówki także w
Konfiguracja → Generator → „Godziny otwarcia”). Każda placówka ma:

- **Zamknięte w polskie święta ustawowe** (domyślnie włączone),
- **Maks. dni pracy pod rząd** (domyślnie 4) — 1 oznacza, że nikt nie pracuje
  dwa dni z rzędu, czyli w placówce z 2 osobami zmiany na przemian,
- **własne zasady generatora** — tryby zasad i ustawienia z „Zasad
  generatora” (ustawienia zaawansowane) — patrz niżej,
- **Działalność całodobowa (24/7)** + edytor **rotacji służby** (godzina
  rozpoczęcia doby, godzina podziału, „Preferuj zmiany 24h”) — patrz niżej,
- albo **godziny tygodnia**: osobno na każdy dzień, z opcjami „Nieczynne” i
  „24h” (00:00–23:45); koniec wcześniejszy niż początek oznacza godziny
  **przez północ** (np. 15:00–07:00).

Pojedynczy dzień można nadpisać dwuklikiem na nagłówku (inne godziny albo
„Nieczynne tego dnia”) — to wygrywa z godzinami tygodnia i ze świętem.

---

## Pracownicy

Okno pracownika: nazwisko, imię, **wymiar etatu** (1/1 … 1/4), **lokalizacja**
oraz role i ograniczenia:

- **Ochrona**: „Umowa” (priorytet w dobijaniu godzin do normy), „Nie chce
  pracować zmian 24h” (w sobotę/niedzielę dostaje zmiany 12 h zamiast 24 h),
  „Nie pracuje w godzinach nocnych (22:00–6:00)”, „Nie pracuje na popołudniu”.
- **Dino**: pracownik otwarcia, obsługa stoiska mięsnego (i „lekkie” mięso),
  kierowniczka (sztywny wzorzec: pon. wolne, wt–pt 7–15, sob 6–14), wymiar
  „1/1 max 8:00”, „nie pracuje w nocy / na popołudniu”.

Ograniczenia pracownika dotyczą zmian przydzielanych przez generator —
ręczny wpis zawsze wygrywa.

---

## Ręczne wpisy i tryb szybki

**Edycja dnia** (dwuklik na komórce): godziny od–do, „Cała doba (24h)”,
Wolne, Urlop, Chorobowe. W placówkach 24/7 i w placówkach Ochrony z
godzinami otwarcia wolno wpisać zmianę przez północ (np. 15:00–07:00) i
24 h; w pozostałych — zmianę w obrębie doby albo nockę 22:00–06:00.

**Tryb szybki** (przycisk w panelu): wybierasz tryb i klikasz komórki.

| Tryb | Znaczenie dla generatora |
|---|---|
| Może pracować (`W`, Ochrona) | ta osoba **musi** dostać zmianę tego dnia — generator dobiera jaką |
| Rano / Popo (`1`/`2`, Dino) | zablokowany typ zmiany — godzinę dobiera generator |
| Wolne | dzień zablokowany jako wolny |
| Urlop / L4 | nieobecność (obniża normę godzin) |
| Usuń | komórka wraca do stanu „nietkniętego” |
| Własne przedziały | przyciski z „Ustawień trybu szybkiego” (nazwa, start, koniec, 24h, widoczność) |

Każdy ręczny wpis godzin jest **blokadą**: generator go nie zmienia, liczy do
obsady, godzin, odpoczynku i dni pod rząd, a resztę dopasowuje wokół niego.
„Wyczyść auto” usuwa tylko zmiany z generatora; „Wyczyść grafik” — wszystko.

---

## Generator — jak działa

```
KONFIGURACJA → model CP-SAT → rozwiązanie → zapis do grafiku
                                  └─ brak rozwiązania → grafik bez zmian + lista przyczyn
```

1. Dla wybranej placówki czyszczone są dni niezablokowane.
2. Dla każdego pracownika, dnia i typu zmiany powstaje zmienna 0/1.
3. Zasady dokładane są wg trybu ustawionego w Konfiguracja → Generator →
   „Zasady generatora” (ustawienia zaawansowane):
   - **Wymagane** — twardy warunek (grafik musi go spełnić),
   - **Preferowane** — może być złamane za karę (waga w funkcji celu),
   - **Wyłączone** — pomijane.

   Tryby zasad i ustawienia z tej sekcji (maks. osób naraz, maks. dni pod
   rząd, tryb liczenia odpoczynku) są **per placówka**: okno pokazuje i
   zapisuje ustawienia placówki wybranej w programie, a generator bierze je
   przy generowaniu jej grafiku. Placówka bez własnych ustawień ma tryby
   projektu (domyślne). Gdy generuje się cały projekt naraz, placówki o
   różnych ustawieniach generują się po kolei, każda ze swoimi.
4. Solver szuka najlepszego grafiku w **limicie czasu** (domyślnie 60 s,
   do zmiany w tych samych ustawieniach — jeden dla całego projektu), na
   maks. 8 wątkach.
5. Wynik trafia do komórek; zmiana należy do dnia, w którym się zaczyna.

Zawsze obowiązują (poza systemem trybów): urlop/L4/wolne, ręczne wpisy,
najwyżej jedna zmiana na dzień, brak zmian w dni zamknięte.

**Zasady wspólne** (lista w „Zasadach generatora” zależy od profilu):

| Zasada | Co robi |
|---|---|
| Odpoczynek 11 h | min. 11 h między zmianami (po 24 h — patrz Ochrona); tryb liczenia: standardowy (dokładny) albo uproszczony |
| Dni pod rząd | limit kolejnych dni pracy placówki (domyślnie 4); liczy też ostatni dzień poprzedniego miesiąca. Np. 1 dzień + Wymagane = zmiany na przemian; przy Wymaganym urlop jednej z dwóch osób dłuższy niż 1 dzień daje brak rozwiązania |
| Godziny miesięczne | suma godzin = norma (z tolerancją jednej zmiany) |
| Bilans godzin | jak najbliżej normy (tylko miękko) |
| Zakaz pracy nocnej / popołudniami | flagi pracownika |
| „Umowa” | zawsze aktywny priorytet: osoby z „Umową” dobijane do normy w pierwszej kolejności |
| Nominalny czas pracowników bez umowy | dobijanie do normy pozostałych (Preferowane / Wyłączone) |
| Wyrównanie godzin umowa/bez | równomierny podział godzin (domyślnie wyłączone) |

---

## Profil Ochrona (Enyo)

Placówka Ochrony działa w jednym z dwóch trybów.

### 1. Rotacja służby 24/7

Włączana w Lokalizacjach („Działalność całodobowa (24/7)”). Użytkownik podaje
godzinę rozpoczęcia doby S i godzinę podziału P. **Każdego dnia**: albo jedna
zmiana 24 h od S, albo dwie zmiany S→P i P→S — zawsze **dokładnie jedna
osoba** w pracy.

- „Preferuj zmiany 24h” odwraca domyślną lekką preferencję (domyślnie
  generator woli dwie połówki).
- „Nie chce pracować zmian 24h”: w sobotę/niedzielę tylko połówki.
- Odpoczynek po zmianie 24 h: **(N−1)×24 h, nie mniej niż 24 h** (N = osoby
  placówki bez „Nie chce 24h”); po pozostałych zmianach 11 h.
- Ręczny wpis dowolnych godzin liczy się jako pokrycie — generator dokłada
  zmiany resztkowe, żeby doba była pełna.
- Święto (przy „Zamknięte w święta”) i „Nieczynne tego dnia” zamykają dobę.
- Obsada rotacji jest zawsze wymagana.

### 2. Placówka z godzinami otwarcia (np. GZUK: pn–pt 15:00–07:00, sob–nd 24h)

Dotyczy każdego profilu Ochrony (profil „custom_ochrona” albo każdy profil z
rolą „Nie chce 24h”). Moduł: `logic/generator/opening_hours_coverage.py`.

- **Okno dnia** = godziny otwarcia tego dnia; koniec wcześniejszy niż
  początek = przez północ; okno co najmniej 23:45 (przycisk „24h”) = **doba**.
- **Jedna osoba na całe okno**: 15:00–07:00 to jedna zmiana 16 h. Doba to
  jedna zmiana 24 h albo dwie po 12 h (lekka preferencja całej doby).
- **Doba zaczyna się tam, gdzie kończy się okno dnia poprzedniego**: pt
  15:00–07:00 + sob/nd 24h daje ciągłą obsadę od pt 15:00 do pn 07:00 (sobota
  i niedziela 07:00–07:00). Okna dni nigdy na siebie nie nachodzą; dla dnia 1
  program sprawdza godziny końca poprzedniego miesiąca.
- **Zmiana resztkowa**: gdy ręczny wpis przykrywa część okna (np. 15:00–23:00),
  resztę (23:00–07:00) dostaje inna osoba — bez dwóch osób naraz.
- Odpoczynek liczony dokładnie na osi czasu: 11 h, po zmianie 24 h
  (N−1)×24 h (min. 24 h), także względem ręcznych wpisów i końca poprzedniego
  miesiąca.
- Godziny pracy liczone z rzeczywistej długości zmiany (16 / 24 / 12 h).
- „Może pracować” = musi dostać zmianę; „1”/„2” = zmiana zaczynająca się
  przed / od 12:00. „Nie pracuje w nocy” wyklucza zmiany nachodzące na
  22:00–06:00, „Nie pracuje na popołudniu” — zmiany od 12:00.

Zasady tego trybu:

| Zasada | Domyślnie | Co robi |
|---|---|---|
| Obłożenie godzin otwarcia | Wymagane | w każdym kwadransie okna co najmniej 1 osoba z placówki |
| Maks. obsada naraz | Preferowane | najwyżej N osób naraz (N domyślnie 1; pole „Maks. osób naraz w placówce” w ustawieniach zaawansowanych „Zasad generatora”). Waga wyższa niż „Umowa”, więc druga osoba nie jest dokładana tylko po to, żeby dobić godziny. Ręczne wpisy zajmują miejsca w limicie, ale same go nie łamią |

Uwaga: przy „Maks. obsadzie” równej 1 osoby dostają tylko tyle godzin, ile
wymaga obsada placówki — jeśli placówka potrzebuje mniej godzin niż suma
etatów, część osób nie dobije normy. Żeby dokładać drugą osobę, zwiększ limit
albo wyłącz zasadę.

### Domyślne zasady nowego projektu Ochrony

Odpoczynek 11 h — Wymagane; Zakaz pracy nocnej / popołudniami — Wymagane;
Obłożenie godzin otwarcia — Wymagane; Dni pod rząd, Godziny miesięczne,
Bilans, Nominalny czas bez umowy, Maks. obsada naraz — Preferowane;
Wyrównanie godzin umowa/bez — Wyłączone. Zmiana standardowa 8 h.

---

## Profil Sklep (Dino)

- Zmiany zakotwiczone przy **otwarciu** (OPEN) i **zamknięciu** (CLOSE) plus
  warianty przesunięte o 15–90 min; nocka 22:00–06:00, gdy godziny sklepu
  nachodzą na noc.
- **Obsada otwarcia/zamknięcia**: dokładnie N osób (domyślnie 3),
  pracownicy otwarcia, **mięso** na zmianach i przez cały dzień.
- **Kalendarz handlowy**: niedziele zamknięte poza zaznaczonymi niedzielami
  handlowymi, święta zamknięte.
- Kierowniczka ze sztywnym wzorcem, wymiar „1/1 max 8:00”, domyślnie zmiana
  „8h 30 min” dla pełnego etatu.
- Znane błędy profilu Dino są tylko opisane (bez zmian zachowania) w
  `GENERATOR_AUDIT.md` i oznaczone w testach jako `xfail`.

---

## Gdy grafiku nie da się ułożyć

Grafik zostaje **bez zmian**, a okno pokazuje przyczyny, które da się
udowodnić z danych, np.:

- w danym dniu nikt z placówki nie jest dostępny (urlop/L4/wolne),
- jedyna dostępna osoba na dobę ma „Nie chce 24h”,
- kolejne okna dzieli mniej niż 11 h, a jest tylko jedna osoba,
- typ zmiany „W”/„1”/„2” w dniu, w którym każda zmiana łamie Wymaganą zasadę
  tej osoby (np. „Nie pracuje w nocy”, odpoczynek od jej ręcznego wpisu,
  limit obsady zajęty ręcznymi wpisami),
- zablokowany odpoczynek krótszy niż 11 h między ręcznymi wpisami.

Jeśli solver nie zdążył w limicie czasu, komunikat mówi o limicie (a nie o
sprzecznych zasadach) i podpowiada jego zwiększenie.

---

## Eksport i wydruk

- **Eksport** (Excel / JPG / PDF) — grafik aktualnie wybranej placówki, z
  podglądem przed zapisem. Dino i Ochrona mają osobne układy
  (`export/image_exporter.py`, `export/security_*_exporter.py`).
- **Karty pracy** — „Lista obecności miesięczna pracownika”: jedna strona na
  osobę, dni w wierszach, godziny dzienne i nocne (22–06), norma, nadgodziny,
  miejsce na podpis; dla całej placówki albo jednej osoby.
- **Drukuj…** — wydruk grafiku z podglądem.

W wersji demo eksport i zapis są zablokowane.

---

## Licencja, wersja demo, aktualizacje

- **ID użytkownika** (prawy dolny róg okna) jest wyliczane z maszyny. Klucz
  produktu (Pomoc → Klucz produktu) jest powiązany z tym ID; bez klucza
  działa wersja demo: 5 generowań, bez zapisu i eksportu.
- **Aktualizacje**: przy starcie (i z menu Pomoc) program pobiera manifest
  `releases/<kanał>.json` z repozytorium, porównuje wersję z `version.py` i
  proponuje pobranie instalatora. Kanał (`dino` / `enyo`) ustala
  `release_channel.py` w czasie budowania.

---

## Pliki danych

W katalogu programu: `last_project.json` (roboczy projekt), `license.json`,
`machine_id.json`, `demo.json` (licznik demo), `first_run.flag` i
`*_tutorial_seen.flag` (samouczki). W `%LOCALAPPDATA%\GrafikDino\`:
`custom_profiles.json` (profile działalności; profil „Ochrona” jest tam
zapisywany automatycznie przy starcie).

---

## Struktura kodu

Warstwy: **UI → kontroler → generator → modele → zapis**. UI nie zawiera logiki
biznesowej, generator nie zależy od UI.

```
main.py                     start aplikacji (opcjonalnie ścieżka .myp)
ui/                         PySide6: okno główne, siatka, okna dialogowe, kreatory, motyw
logic/
  schedule_controller.py    operacje na grafiku (wpisy, cofnij/ponów, generowanie)
  auto_generator.py         budowa i rozwiązanie modelu CP-SAT, zapis wyniku, diagnostyka
  generator/
    constraint_registry.py  ConstraintSpec + tryby Wymagane/Preferowane/Wyłączone
    base_specs.py           zasady wspólne dla wszystkich profili
    dino_retail_profile.py  zasady profilu Dino
    custom_profile_wiring.py zasady profili custom (Ochrona)
    opening_hours_coverage.py placówki Ochrony z godzinami otwarcia
    duty_rotation_*.py      rotacja służby 24/7
    rest_constraint.py, hours_constraint.py, priority_hours_constraint.py, ...
    diagnostics.py          przyczyny braku rozwiązania
    solution_mapper.py      zapis rozwiązania do komórek
  duty_coverage_presenter.py wiersz „Obłożenie” w siatce
  monthly_hours_status.py   nadgodziny / przekroczenie limitu
  utils/                    czas, polskie święta
model/                      ShopConfig, LocationConfig, Employee, MonthSchedule, DaySchedule,
                            MonthlyProject, profile działalności
persistence/project_io.py   zapis/odczyt projektu (.myp / .json)
export/                     Excel, JPG/PDF, karty pracy
demo/                       skrypty instalujące przykładowe dane
tests/                      testy pytest + walidator i harness audytu
```

Dokumenty w repozytorium: `GENERATOR_AUDIT.md` (audyt generatora),
`ENYO_ONLY_CHANGES.md` (dziennik zmian gałęzi Enyo), `DINO_REGRESSION_AUDIT.md`,
pliki `plan *.md` (plany i decyzje), `.ai/` (zasady pracy nad projektem).

---

## Testy i audyt generatora

```bash
python -m pytest tests/                       # ok. 940 testów, kilka–kilkanaście minut
python -m pytest tests/test_generator_audit_regressions.py   # testy z audytu generatora
```

- `tests/schedule_validator.py` — **niezależny walidator** gotowego grafiku (nie
  importuje nic z generatora): zachowanie ręcznych wpisów, dni zamknięte,
  godziny otwarcia i kształty zmian, odpoczynek, dni pod rząd, godziny,
  obsada kwadrans po kwadransie (rotacja 24/7 i placówki z godzinami),
  maks. obsada naraz, reguły profili. Każde naruszenie oceniane wg trybu
  zasady.
- `tests/generator_audit_harness.py` — kampanie: buduje projekt jak GUI,
  generuje, waliduje, zapisuje wyniki i projekty-reproducery:

  ```bash
  python -m tests.generator_audit_harness weird_hours --out Output/audit --audit-infeasible
  python -m tests.generator_audit_harness --differential
  ```

  `--audit-infeasible` sprawdza, czy „brak rozwiązania” jest prawdziwy
  (ponowne uruchomienie z poluzowanymi zasadami).
- `tests/run_generator_diagnostics.py --seed 17 --employees 10` — raport
  etapowy dla losowego projektu (w `Output/diagnostics/`).

---

## Budowanie wydania

- PyInstaller: `Dingo! - narzędzie do grafików pracy.spec`,
  `Enyo - Grafik Pracy.spec`.
- Instalatory Inno Setup: `dla inno.iss` (DinGo!), `enyo.iss` (Enyo);
  rejestrują rozszerzenie `.myp`.
- `scripts\build_release.ps1 -Channel enyo` — buduje exe dla kanału,
  tymczasowo podmieniając `release_channel.py` (w repo zawsze `dino`).

Gałęzie: `main` (DinGo!) i `integration/enyo-only` (Enyo) — jedyne robocze.
