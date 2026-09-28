# Audyt generatora przed wydaniem (2026-09-28)

Pytanie audytu: **czy dla różnych konfiguracji użytkownika generator faktycznie
tworzy grafik odpowiadający tej konfiguracji, czy tylko pozornie ją respektuje?**

Odpowiedź w skrócie: dla rotacji służby 24/7 (Ochrona) — tak, we wszystkich
przetestowanych konfiguracjach wynik odpowiadał ustawieniom (poza jednym
błędem zakresu zmiennej, naprawionym). Dla placówek Ochrony z godzinami
otwarcia (bez 24/7) i dla profilu Dino — **nie zawsze**: znaleziono ustawienia,
które generator gubi, nadpisuje albo realizuje inaczej niż pokazuje GUI.
Dla Ochrony naprawione; dla Dino zgodnie z decyzją — tylko raport z
reproducerami.

Zakres: pierwsza kampania objęła oba profile (Dino i Ochrona). Na prośbę
użytkownika końcowy, niezależny przebieg (nowe seedy, aktualny kod) objął
**wyłącznie profil Enyo (Ochrona)** — ustalenia Dino poniżej pochodzą z
pierwszej kampanii i celowanych eksperymentów.

## Metoda

```
KONFIGURACJA (jak w GUI) -> GENERATOR (ScheduleController.generate_schedule,
ta sama ścieżka co "Generuj grafik") -> GRAFIK -> WALIDATOR -> PASS / NARUSZENIA
```

- `tests/schedule_validator.py` — niezależny walidator. Nie importuje nic z
  `logic/generator/`; liczy oczekiwania od zera z surowej konfiguracji
  (godziny lokalizacji, nadpisania dni, święta PL z biblioteki `holidays`,
  niedziele handlowe, polityki) i z rzeczywistych godzin w komórkach
  grafiku, na jednej osi czasu miesiąca (minuty). Sprawdza: zachowanie
  ręcznych wpisów/urlopów/L4, zmiany w dni zamknięte, zmiany poza godzinami
  otwarcia, odpoczynek (11 h, po 24 h rotacji (N-1)x24 h, pamięć
  poprzedniego miesiąca), dni pod rząd, godziny miesięczne, obsadę
  otwarcia/zamknięcia per lokalizacja, opener/mięso, mięso kwadrans po
  kwadransie, no_night/no_afternoon, obłożenie rotacji 24/7 kwadrans po
  kwadransie (luki i podwójna obsada), zakaz 24 h, kształty zmian rotacji,
  obłożenie godzin otwarcia, reguły profili custom. Każde naruszenie jest
  oceniane względem trybu polityki (Wymagane = błąd krytyczny, Preferowane =
  raportowane, Wyłączone = ignorowane) i rozróżnia sprzeczności samych
  danych wejściowych (np. dwa nakładające się ręczne wpisy).
- `tests/generator_audit_harness.py` — harness: buduje projekt z opisu
  (dokładnie te pola, które ustawia GUI), generuje, waliduje, zapisuje
  wynik (JSONL) i reproducery (projekt wejściowy + wynik). Rodziny
  konfiguracji: polityki x tryby, obsada 0–5, godziny, wiele lokalizacji,
  ręczne wpisy, rotacja 24/7 (9 kształtów doby, w tym 15:00→07:00,
  22:00→06:00, 00:00→12:00), losowe kombinacje, stary schemat rotacji,
  placówki Ochrony z godzinami, tryby odpoczynku.
- **Audyt „brak rozwiązania”**: dla każdego niepowodzenia generator jest
  uruchamiany ponownie z każdą zasadą Wymaganą poluzowaną do Preferowanej, a
  wynik oceniany wg ORYGINALNYCH zasad. Brak naruszeń = fałszywy „brak
  rozwiązania”.
- Warstwa GUI: okna Konfiguracja/Lokalizacje uruchamiane w Qt offscreen,
  zmiana widżetów, zapis, porównanie z tym, co trafia do generatora.
- Zapis/odczyt projektu: round-trip wszystkich konfiguracji kampanii (0 strat).

## Wyniki

### Końcowy, niezależny przebieg — tylko Enyo (Ochrona), aktualny kod, nowe seedy

| Rodzina | Przypadki | Grafik powstał | Brak rozwiązania (prawdziwy / fałszywy) | Naruszenie twarde w gotowym grafiku |
|---|---|---|---|---|
| Dane klienta (6 placówek, 25 osób, X.2026–II.2027, urlopy/L4, bilans) | 15 | 15 | 0 | 0 |
| Rotacja 24/7, losowe kombinacje | 98 | 78 | 20 (20 / 0) | 1* |
| Placówki z godzinami otwarcia, losowe | 79 | 69 | 10 (10 / 0) | 0 |
| Zasady × Wymagane/Preferowane/Wyłączone | 30 | 27 | 3 (3 / 0) | 0 |
| Tryby odpoczynku (dokładny / uproszczony) | 4 | 4 | 0 | 0 |
| Kilka placówek (rotacja + godziny) | 2 | 2 | 0 | 0 |
| Stary schemat rotacji | 4 | 4 | 0 | 2** |
| **Razem** | **232** | **199** | **33 (33 / 0)** | **3** |

- Wszystkie 33 „brak rozwiązania” mają status INFEASIBLE udowodniony przez
  solver (zero przekroczeń limitu czasu); audyt z poluzowaniem zasad nie
  znalazł żadnego fałszywego. 21/33 mają konkretny komunikat (ręczna zmiana
  24 h u osoby „Nie chce 24h” — 7, za mało osób na godziny otwarcia — 7,
  została 1 osoba z „Nie chce 24h” — 5, zablokowana przerwa < 11 h — 1, dzień
  za długi dla zmian — 1); **12/33 nadal ogólne** „Wymagane zasady są ze sobą
  sprzeczne” (głównie pokrycie rotacji przy małych zespołach, urlopach i
  odpoczynku po 24 h).
- \* `ochF_rand_16` — fałszywy alarm walidatora (kawałek doby 5.01 po
  północy trafia do komórki świątecznej 6.01, a należy do doby dnia 5);
  walidator poprawiony, ponowne wykonanie: 0 naruszeń, obłożenie ciągłe.
- \*\* Stary schemat rotacji — patrz „Obserwacje”.
- We wszystkich 199 gotowych grafikach: obłożenie kwadrans po kwadransie
  bez luk i bez podwójnej obsady (każda placówka 24/7 i z godzinami),
  0 naruszeń Wymaganego odpoczynku, dni pod rząd, zakazu 24 h, dni
  zamkniętych, godzin otwarcia i ręcznych wpisów.

### Testy różnicowe A–E (zmiana jednego ustawienia → ponowne generowanie)

| Test | Wynik |
|---|---|
| A/B: min. obsada otwarcia/zamknięcia 2 → 3 (Dino) | każdego dnia dokładnie 2, potem dokładnie 3 |
| C/D: „Dni pod rząd” Wymagane → Wyłączone → Wymagane (Ochrona, 3 osoby) | maks. 4 → 9 → 4 dni pod rząd |
| C/D: „Obłożenie godzin otwarcia” Wymagane → Wyłączone | 0 luk → luki (zasada przestaje działać) |
| C: odpoczynek 11 h Wymagane → Wyłączone (2 osoby, połówki) | 0 naruszeń w obu (Wyłączone nie wymusza łamania) |
| E: godziny 06:00–22:00 → rotacja 07:00/15:00 (15:00→07:00) → 06:00/22:00 (22:00→06:00) | kształty zmian dokładnie wg konfiguracji, obłożenie pełne |
| „Preferuj zmiany 24h” wyłączone → włączone | 0 → 30 zmian 24 h w miesiącu |

### Pierwsza kampania (Dino + Ochrona, kod przed poprawkami)

243 konfiguracje: 189 grafików, 54 „brak rozwiązania”, 32 grafiki z
naruszeniem twardym (Dino: nocka po zamknięciu, zmiany poza godzinami,
obsada liczona łącznie dla kilku sklepów; Ochrona: zmiany poza godzinami
placówki z godzinami). Niepowodzenia zbadane ręcznie: 16 z 34 w Ochronie
wynikało z błędu zakresu bilansu (naprawiony), 1 w Dino z limitu czasu
przy obciążonym CPU (fałszywy komunikat — naprawiony), reszta prawdziwa.
Po poprawce bilansu (114 konfiguracji Ochrony): 18 „brak rozwiązania”, 0
fałszywych.

### Warstwa GUI

- Okna Konfiguracja, Lokalizacje, Pracownik uruchamiane w Qt offscreen:
  godziny (w tym „Nieczynne”), święta, 24/7, rotacja (początek/podział/
  „Preferuj 24h”), zasady, „Umowa”, „Nie chce 24h”, lokalizacja pracownika —
  trafiają do konfiguracji generatora poprawnie (Ochrona).
- Projekt zbudowany oknami (grudzień 2026 ze świętami, zamknięta niedziela,
  urlop, ręczne wpisy, ręczna zmiana 24 h) → OPTIMAL, 0 naruszeń.
- Zapis/odczyt projektu: 243/243 konfiguracji bez strat.
- Godziny przez północ (np. 15:00–07:00) w oknach godzin otwarcia są
  odrzucane komunikatem — takie układy konfiguruje się rotacją 24/7
  (początek/podział), co testy potwierdzają.

### Zestaw testów

Przed audytem: 829 passed, 1 skipped. Po audycie: **843 passed, 1 skipped,
8 xfailed** (8 = reproducery błędów Dino, tylko raport).

## Naprawione (Ochrona + kod wspólny)

1. **Fałszywy „brak rozwiązania” w małych placówkach 24/7.**
   `add_balance_constraint` miał sztywny zakres sumy minut 0–20000 (333 h).
   2 osoby na placówce 24/7 = ok. 372 h każda, więc sam zakres zmiennej
   czynił model niewykonalnym, mimo że „Bilans godzin” jest tylko
   Preferowany (domyślny dla nowych projektów Ochrony). Klient widział
   „Wymagane zasady są ze sobą sprzeczne”. W kampanii: 16 z 34 przypadków
   „brak rozwiązania” Ochrony miało tę przyczynę.
2. **Placówki Ochrony bez rotacji 24/7 — pakiet pełnego obłożenia**
   (decyzja użytkownika), `logic/generator/opening_hours_coverage.py`:
   - brak sztywnej nocki 22:00–06:00 (wcześniej dla placówki do 22:45 ludzie
     pracowali do 06:00, ok. 7 h po zamknięciu),
   - zmiany przesunięte od otwarcia/zamknięcia muszą mieścić się w
     godzinach (wcześniej np. 10:45–19:15 przy 10:00–18:00),
   - doba 00:00–23:45 dzielona na kolejne zmiany od 00:00 (np. 00–08,
     08–16, 16–24) — wcześniej środek doby był nie do pokrycia,
   - nowa zasada „Obłożenie godzin otwarcia” (domyślnie Wymagana, także gdy
     projekt nie ma jeszcze jej wpisu): w każdym kwadransie godzin otwarcia
     min. 1 osoba z placówki,
   - ręczny wpis niepasujący dokładnie do żadnego kształtu zmiany jest
     stałym przedziałem: liczy się do obłożenia, godzin, odpoczynku i dni pod
     rząd (wcześniej był dla generatora niewidoczny — w wyniku łamany był
     Wymagany odpoczynek 11 h).
3. **Nowe projekty Ochrony: zmiana 8 h** zamiast Dino-owego „8h 30 min”
   (ukryta opcja była domyślnie włączona; urlop/L4 obniżał cel o 8,5 h).
   Istniejące projekty bez zmian.
4. **Limit czasu solvera zgłaszany jako „sprzeczne zasady”.** Status
   UNKNOWN (limit minął bez rozwiązania) dawał komunikat „Wymagane zasady są
   ze sobą sprzeczne” — teraz komunikat o limicie czasu z podpowiedzią.
   Znalezione przypadkiem: przy obciążonym CPU konfiguracja z WYŁĄCZONĄ
   „Obsadą zamknięcia” dała „brak grafiku — sprzeczne zasady”, a była
   wykonalna (na wolnym CPU: FEASIBLE).
5. **Tryb „Uproszczony” odpoczynku 11 h łamał Wymagany odpoczynek**
   (znalezione w drugim, niezależnym przebiegu). Tryb zakazuje tylko
   przejścia popołudnie → rano; przy różnych godzinach w kolejne dni (np.
   zamknięcie 22:00, następnego dnia zmiana od 06:00) w wyniku było 8 h
   odpoczynku. Dla Ochrony pary zmian sąsiednich dni są teraz dodatkowo
   liczone dokładnie; dla Dino — raport (D13).
6. **Czytelne komunikaty dla nowej zasady obłożenia**: nikt z placówki nie
   jest dostępny w danym dniu; za mało osób (suma możliwych godzin < długość
   dnia otwarcia); dzień zbyt długi dla kształtów zmian (np. 04:00–23:00 przy
   zmianach 8 h ma lukę w środku — podpowiedź: doba 00:00–23:45).

## Tylko raport — profil Dino (decyzja użytkownika)

Reproducery: `tests/test_generator_audit_regressions.py`, testy
`test_dino_*` oznaczone `xfail(strict=True)` — zaczną przechodzić, gdy błąd
zostanie naprawiony.

| # | Ustawienie w GUI | Co robi generator | Dowód |
|---|---|---|---|
| D1 | „Pracowników na otwarciu/zamknięciu” przy kilku lokalizacjach | liczy obsadę **łącznie dla wszystkich sklepów**; np. dzień 9: sklep A 0 osób na otwarciu, sklep B 3 | `test_dino_min_open_close_is_enforced_per_location`, kampania `dino_multiloc` (5/6 przypadków) |
| D2 | Niedziela handlowa zaznaczona w Konfiguracji | zapis tylko do `ShopConfig.trade_sundays`, generator czyta `LocationConfig.trade_sundays` → **0 osób** w tę niedzielę; odwrotnie: niedziela handlowa tylko na lokalizacji też 0 osób | `test_dino_trade_sunday_selected_in_config_gets_staff`, `dino_overrides` |
| D3 | Godziny otwarcia do 22:45/23:00 | automatyczna nocka 22:00–06:00 dla zwykłych pracowników (7 h po zamknięciu) | `test_dino_store_closing_2245_gets_no_shift_after_closing`, 6 przypadków `dino_hours` |
| D4 | Krótkie godziny (np. 10:00–18:00, 08:00–16:00, 12:00–20:00) | zmiany przed otwarciem / po zamknięciu (np. 10:45–19:15, 09:00–17:30) | `test_dino_short_day_offset_shifts_stay_inside_opening_hours`, 13 przypadków `dino_hours` |
| D5 | Ręczna zmiana niepasująca do wzorca (np. 13:00–21:00) | niewidoczna dla odpoczynku, dni pod rząd i godzin → w wyniku Wymagany odpoczynek 11 h złamany (9 h), 6 dni pod rząd przy limicie 4 | `test_dino_unmatched_manual_shift_is_respected_by_rest_11h`, `dino_manual_8` |
| D6 | Godziny otwarcia lokalizacji + „Mięso przez cały dzień” | mięso liczone wg **ukrytych godzin projektu** (05:30–22:45), nie lokalizacji → przy 06:00–22:00 „brak rozwiązania”, po zsynchronizowaniu godzin projektu grafik powstaje | `test_dino_meat_coverage_uses_the_locations_opening_hours` |
| D7 | „Maksymalna liczba dni pod rząd” (Konfiguracja → Limity) | zapis do `ShopConfig.constraints`, generator czyta wartość lokalizacji (ukryte pole, zawsze 4) → ustawienie bez wpływu | `test_dino_max_consecutive_from_config_reaches_the_generator`, test GUI (ustawione 6, efektywne 4) |
| D8 | „Mięso na zmianach”: Preferowane vs Wymagane | tryby sprawdzają **różne rzeczy**: Preferowane = mięso na otwarciu i zamknięciu; Wymagane = mięso na zmianach środkowych. Zmiana trybu zmienia regułę, nie tylko jej siłę | analiza `meat_constraint.py` |
| D9 | Obsada otwarcia = 0 (tylko z pliku; GUI ma zakres 1–10) | zawsze brak rozwiązania (wymóg „dokładnie 0” + „min. 1 opener i 1 mięso”) | `dino_min_0_*` |
| D10 | Obsada = 1 | jedyna osoba na otwarciu musi mieć jednocześnie „otwarcie” i „mięso” — inaczej brak rozwiązania z ogólnym komunikatem | `dino_min_1_*`, `dino_min_asym_1_3` |
| D11 | Preferowane „Obsada otwarcia/zamknięcia” | przegrywa z wyrównaniem godzin (waga 200 za osobę vs 250 za minutę odchyłki godzin): solver zostawia niedobór na otwarciu, choć pełna obsada jest możliwa (tryb Wymagane znajduje ją) | `dino_pol_tight_open_PREFERRED` vs `_MANDATORY` |
| D12 | Duży projekt wielosklepowy | kara „rano vs popołudnie” ma zmienną o zakresie ±50 osób na dzień — >50 zmian rannych w jednym dniu zrobi model niewykonalnym | analiza `objective.py` |
| D13 | Tryb odpoczynku „Uproszczony” + różne godziny w kolejne dni | Wymagany odpoczynek 11 h złamany w wyniku (pt 22:00 → sob 06:30 = 8,5 h) | `test_dino_simplified_rest_mode_still_guarantees_11h_when_hours_differ`, `dino_rest_simplified_mixed_week` |
| D14 | Obsada zamknięcia (Wymagane) | wymaga też osoby z „otwarciem” na zamknięciu (etykieta „Pracownik otwarcia”); gdy jedyny dostępny opener nie może być naraz na otwarciu i zamknięciu (np. pamięć poprzedniego miesiąca blokuje dwóch) — brak rozwiązania z ogólnym komunikatem | `dino_rest_*_0800-1600` (audyt: prawdziwa niewykonalność) |

Decyzja „obsada otwarcia/zamknięcia = dokładnie N” (tryb Wymagane)
została potwierdzona przez użytkownika — to nie jest błąd; w trybie
Preferowane jest „co najmniej N”.

## Obserwacje bez zmian w kodzie

- **Wersja Enyo: zapis okna Konfiguracja przełącza profil projektu na
  „Ochrona”.** Selektor profilu jest ukryty i zawiera tylko Ochronę, a
  `_save()` zawsze zapisuje jego wartość — projekt Dino otwarty w tej
  wersji po pierwszym „Zapisz” w Konfiguracji staje się projektem Ochrony
  (bez przeliczenia zasad). Zgodne z celem gałęzi (tylko Ochrona), ale
  cicha zmiana — warto wiedzieć przy otwieraniu starych plików.
- **Nieznany profil projektu = cicho profil Dino.** Plik z
  `business_type`, którego nie ma na danym komputerze (np.
  `test_data/dane_klienta_ochrona.json` → `ochrona_dane_klienta_test`),
  jest generowany regułami Dino (obsada otwarcia/zamknięcia Wymagana itd.).
- **Stary schemat rotacji (osobny tydzień i weekend)**, np. 07–23/23–07 w
  tygodniu i 08–20/20–08 w weekend: wynik ma lukę 07:00–08:00 w sobotę i
  podwójną obsadę 07:00–08:00 w poniedziałek (walidator: 20 kwadransów luki,
  16 podwójnych) przy statusie OPTIMAL. Edytor już takiego schematu nie
  tworzy; dotyczy tylko starych projektów — generator ich nie ostrzega.
- **Okno Pracownik gubi `availability`** przy edycji (nowy obiekt
  `Employee` bez tego pola). Dostępność nie ma dziś edytora w GUI, więc
  dotyczy tylko projektów, które ją mają z pliku.
- **Nagłówek dnia (Dino): pole „Dzień wolny ustawowo”** pokazuje stan z
  poziomu projektu, a zapisuje do lokalizacji — ponowny zapis może cofnąć
  zaznaczenie.
- **Diagnostyka „brak rozwiązania”** nie ma osobnego etapu dla pokrycia
  rotacji 24/7 i zakazu 24 h (są w grupie „core”) — przy niewykonalnym
  pokryciu komunikat bywa ogólny.
- **Istniejące projekty Ochrony z „8h 30 min”**: dzień urlopu/L4 obniża cel
  godzin o 8,5 h, a norma liczona jest po 8 h (nowe projekty już 8 h).
- **Odpoczynek po zmianie 24 h = (N−1)×24 h**, gdzie N liczy wszystkie osoby
  placówki bez „Nie chce 24h” — także te na urlopie cały miesiąc.

## Przegląd istniejących testów

Zestaw przed audytem: 829 passed, 1 skipped. Testy, które „mówią, że
działa”, ale nie tworzą sytuacji, w której błąd mógłby się ujawnić:

- **Obsada otwarcia/zamknięcia Dino przy kilku lokalizacjach** — żaden test
  end-to-end nie sprawdza liczby osób na otwarciu osobno per lokalizacja
  (D1 niewykryte).
- **Niedziele handlowe** — testy ustawiają `LocationConfig.trade_sundays`
  albo `ShopConfig.trade_sundays` bezpośrednio (np.
  `test_previous_month_memory.py`, `loc.trade_sundays.add(1)`), nigdy przez
  okno Konfiguracji → D2 niewykryte.
- **`test_multi_location_generator_resolves_each_employees_own_location_hours`**
  celowo dobiera okna „>= zmiana + 90 min z każdej strony, żeby każdy wariant
  się mieścił” — więc nigdy nie sprawdza zmian wychodzących poza godziny (D4).
- **`test_location_config_detects_night_shift_from_default_open_hours`**
  utrwala zachowanie z D3 (oczekuje nocki 22–06 dla sklepu do 22:45).
- **Testy „brak rozwiązania”** akceptują status UNKNOWN (limit czasu) albo
  samo `success is False` (np. `test_leave_sick_generation_sweep.py:214`,
  `test_round_clock.py:253`) — przeszłyby także wtedy, gdy grafik istnieje,
  a solver tylko nie zdążył.
- **Bilans przy małej placówce 24/7** — brak testu z 2 osobami i domyślnymi
  zasadami Ochrony (błąd zakresu 333 h niewykryty). Test
  `TestDutyRotationScarcePoolGracefulInfeasibility` (2 osoby) oczekiwał
  braku rozwiązania i przechodził — częściowo z tego samego fałszywego
  powodu (dziś nadal poprawnie: przyczyna jest prawdziwa).
- **Ręczne wpisy niepasujące do wzorców** — testy ręcznych blokad sprawdzają,
  że wpis przetrwał generowanie, ale nie sprawdzają odpoczynku/dni pod rząd
  WOKÓŁ niego (D5).
- Brak testów porównujących wynik trybów Wymagane/Preferowane/Wyłączone dla
  tej samej konfiguracji (poza „Wyrównaniem godzin”) — dodane w harnessie
  (testy różnicowe) i w `test_generator_audit_regressions.py`.

Dobre praktyki, które już były: niezależny audyt odpoczynku w
`test_night_shift_stress.py`, sprawdzanie godzin kwadrans po kwadransie w
`test_round_clock.py`, przywracanie grafiku po braku rozwiązania w
`test_leave_sick_generation_sweep.py`.

## Co przetestowano

Ponad 700 uruchomień prawdziwego generatora (3 kampanie + audyty „brak
rozwiązania” + eksperymenty celowane + testy różnicowe), m.in.:

- **Rotacja 24/7 (Ochrona)** — 9 kształtów doby: 07:00/15:00 (15:00→07:00),
  06:00/22:00 (22:00→06:00), 08:00/20:00, 07:00/19:00, 00:00/12:00,
  05:30/22:45, 12:00/23:45, 00:00/08:00, 22:00/23:00; „Preferuj 24h” wł./wył.;
  2–7 osób; „Nie chce 24h”, „Umowa”; urlop, L4, wolne (dwie ścieżki GUI),
  ręczne wpisy pasujące do rotacji, zmiana 24 h, dowolne wpisy (także przez
  północ); „Nieczynne tego dnia”; święta z „Zamknięte w święta” wł./wył.;
  pamięć poprzedniego miesiąca (koniec przed/po północy); miesiące 28/29/30/31
  dni (II.2027, II.2028, IV, IX, X, XI, XII, I); stary schemat tydzień/weekend.
- **Placówki z godzinami (Ochrona)** — 05:30–22:45, 06:00–22:00, 08:00–16:00,
  10:00–18:00, 06:00–23:00, 07:00–15:00, 00:00–23:45 (doba), weekend dobą,
  tydzień mieszany (doby, zwykłe dni, zamknięty dzień); ½ i ¾ etatu; typ zmiany
  rano/popołudnie; ręczne 22:00–06:00; nadpisania dni (zamknięte, 09:00–13:00);
  „8h 30 min” wł./wył. (stare/nowe projekty).
- **Zasady × tryby** — odpoczynek 11 h, dni pod rząd, godziny miesięczne,
  bilans, wyrównanie godzin, pokrycie rotacji, zakaz 24 h, obłożenie godzin
  otwarcia × Wymagane/Preferowane/Wyłączone; tryb odpoczynku dokładny/
  uproszczony.
- **Dino (pierwsza kampania)** — każda polityka × 3 tryby przy ciasnej i
  normalnej obsadzie; obsada 0–5 przy 2N−1…2N+5 osobach i asymetryczna;
  8 zestawów godzin × 3 miesiące; nadpisania dni, niedziele handlowe (projekt
  i lokalizacja), święta; 2 sklepy o tych samych/różnych godzinach;
  losowe ręczne wpisy (pasujące i nie), urlopy, L4, wolne, typ zmiany;
  kierowniczka przy różnych godzinach.
- **Dane klienta** — `test_data/dane_klienta_ochrona.json` (6 placówek, 25
  osób) jako projekt Ochrony, 5 miesięcy × 3 warianty.

Reprodukcja: `python tests/generator_audit_harness.py <rodziny> --only-profile
ochrona --audit-infeasible --out <katalog>`; testy różnicowe:
`python tests/generator_audit_harness.py --differential`.
