# Plan: obsługa zmian nocnych (przekraczających północ) przez generator

Branch: `claude/night-shift-generator-support-ex6pqc`, oparty na
`feature/business-profiles` (commit `3cb675b`). To jest wyłącznie plan —
brak zmian w kodzie. Dotyczy punktu wymienionego w
`plan generalizacji branzowej.md` w sekcji "Odłożone jako głęboka
przebudowa": *"Prawdziwy model zmian 24/7 [...] Rzeczywista zmiana nocna
22:00–06:00 nie jest wspierana"*.

## 1. Dlaczego to nie jest drobna poprawka

Cały model czasu w aplikacji operuje na `datetime.strptime("HH:MM")` bez
daty i zakłada, że zmiana zaczyna się i kończy w obrębie jednego dnia
kalendarzowego:

- `model/day_schedule.py::DaySchedule.set_hours()` **twardo odrzuca**
  `end <= start` (`ValueError: Godzina zakończenia musi być późniejsza
  niż rozpoczęcia`). Zmiana 22:00→06:00 nie da się dziś zapisać.
- `model/day_schedule.py::calc_end/calc_start` liczą `start + timedelta`
  i biorą tylko `strftime("%H:%M")` z wyniku — jeśli suma "przewinie się"
  przez północ, zwracają poprawny zegarowy czas, ale **tracą informację
  że to już następna doba**. Dziś nie ma to efektu, bo nic nie generuje
  aż tak długich zmian; przy prawdziwej zmianie nocnej stanie się to
  źródłem cichych błędów.
- `model/month_schedule.py` trzyma dokładnie jeden `DaySchedule` na parę
  (pracownik, dzień) — nie ma miejsca na "zmianę, która należy do dnia D,
  ale kończy się w D+1".
- Rozproszone po całym generatorze porównania godzin zakładają "dziś":
  `rest_constraint.py` (już ma świadomy fallback `+= timedelta(days=1)`
  przy ujemnym odstępie — to jedyne miejsce, które już częściowo
  "wie" o przekraczaniu północy), `meat_light_budget.py`,
  `availability_constraint.py`, `manual_constraint.py`, `objective.py`,
  `solution_mapper.py`, `night_constraint.py`, `generic_rules.py`.
- `logic/generator/generic_rules.py::_shift_touches_window()` ma wprost
  zapisany w komentarzu ten sam wniosek: *"a shift genuinely spanning
  midnight is outside what this app's shift model represents today, for
  any profile"*.

Łącznie **20 plików** w `logic/`/`model/` parsuje albo porównuje godziny
zmian (`grep -rl "strptime\|calc_end\|calc_start\|total_duration\|get_open_hours_for_day"`).
To realnie kalibru "lokalizacji" (Etap 3a–3d) — do zrobienia etapami, nie
jedną łatką.

## 2. Kontekst biznesowy (dlaczego to w ogóle wypłynęło)

Zgodnie z `plan generalizacji branzowej.md`: klient z firmy ochroniarskiej
chce lokalną wersję Dingo pod swoją działalność. Ochrona pracuje w trybie
ciągłym (obiekt "otwarty" 24/7), z realnymi zmianami przechodzącymi przez
północ (typowo 12h, np. 20:00–08:00, albo 8h, np. 22:00–06:00) — nie
"edge case" jak u Dino, tylko codzienność. To odróżnia to zadanie od
istniejącego `no_night`/`night_constraint.py`, który **tylko zakazuje**
pracownikowi zmian *dotykających* nocy w obrębie zmian sklepowych
(OPEN/CLOSE/WORK_START/END) — nie tworzy żadnej nowej, samodzielnej zmiany
nocnej.

## 3. Kluczowa decyzja produktowa (do ustalenia z klientem/Tobą, zanim ruszy kod)

1. **Czy zmiana nocna jest jednym sztywnym blokiem** (np. zawsze
   22:00–06:00 per lokalizacja) **czy elastyczna** jak dzisiejsze
   `WORK_START_15..90`/`WORK_END_15..90` (przesunięcia co 15 min)?
   → Rekomendacja: zacząć od **jednego sztywnego bloku na lokalizację**
   (analogicznie do `SHIFT_OPEN`/`SHIFT_CLOSE`) — dużo mniejsza przestrzeń
   zmiennych CP-SAT, wystarcza do realnego przypadku ochrony (stała
   zmiana), rozszerzalne później.
2. **Do którego dnia liczą się godziny nocne** dla limitu miesięcznego /
   `max_consecutive_days` / bilansu? Kodeks pracy liczy **dobę
   pracowniczą** od momentu rozpoczęcia pracy (art. 128 §3 pkt 1) —
   więc cała zmiana nocna zaczęta w dniu D powinna liczyć się w całości
   do dnia D, nigdy dzielona między D i D+1. To upraszcza model: dzień D
   "posiada" całą zmianę, D+1 tylko wie, że pracownik jest zajęty do
   godziny końca.
3. **Czy lokalizacja może być otwarta 24/7 bez przerwy** (ochrona) w
   odróżnieniu od Dino (zamyka się, wszyscy idą do domu)? Jeśli tak,
   `open`/`close`-owe constrainty Dino (`min_open_staff`/`min_close_staff`,
   `no_night`, `no_afternoon`, mięso) muszą zostać wyłączone dla tego
   profilu (już dziś możliwe przez `ConstraintPolicy.DISABLED` +
   `BusinessProfile` — patrz sekcja 5, punkt F).

Bez odpowiedzi na (1) i (2) nie da się bezpiecznie ruszyć z Etapem B.

## 4. Docelowy model danych (minimalny, wsteczny kompatybilny)

- **`DaySchedule`**: dodać jawną obsługę `end <= start` jako "zmiana
  przechodzi przez północ" zamiast rzucania wyjątku — nowe pole
  `crosses_midnight: bool` (albo wyliczane on-the-fly z porównania
  stringów, żeby nie dokładać stanu). `total_duration()`/`total_minutes()`
  liczą `end + 1 dzień - start` gdy `end <= start`. Dla istniejących
  zmian Dino `end > start` zawsze, więc **zero zmiany zachowania**.
- **`MonthSchedule`**: bez zmian strukturalnych — zmiana nocna nadal
  mieszka w jednym `DaySchedule` (dzień D), zgodnie z decyzją #2 wyżej.
  Dzień D+1 pozostaje pusty/normalny; ograniczenie "zajętości" pracownika
  do godziny końca nocnej zmiany żyje wyłącznie w generatorze
  (rest constraint), nie w danych.
- **`LocationConfig`/`ShopConfig`**: nowe, opcjonalne pole per lokalizacja,
  np. `night_shift: {"start": "22:00", "end": "06:00"} | None`. `None`
  (domyślne) = brak zmiany nocnej, zero zmiany dla Dino i profili bez tej
  potrzeby.

## 5. Etapy wdrożenia

### Etap A — fundament w `DaySchedule` (bezpieczny, izolowany)
- `set_hours`/`total_duration`/`total_as_str`/`total_minutes` w
  `model/day_schedule.py` zaczynają rozumieć `end <= start` jako "koniec
  następnego dnia".
- Testy: `tests/test_shift_class.py`-podobny nowy plik
  `tests/test_overnight_shift.py` — zapis 22:00–06:00, liczenie czasu
  trwania (8h), serializacja/deserializacja projektu (`persistence/project_io.py`
  — sprawdzić, czy start/end string round-trip'uje bez zmian, powinien).
- Zero wpływu na generator/UI — tylko odblokowanie reprezentacji danych.

### Etap B — konfiguracja zmiany nocnej per lokalizacja
- `LocationConfig`/`ShopConfig`: pole `night_shift` (sekcja 4), `to_dict`/
  `from_dict`, walidacja (`end` ≠ `start`, oba wymagane albo oba puste).
- UI: zakładka "Lokalizacje" w `ui/config_dialog.py` — pola start/end dla
  zmiany nocnej (reużyć `ui/time_input.py::TimeInputWidget`, tak jak dla
  `open_hours`).
- Bez wpięcia w generator jeszcze — samo przechowywanie/edycja konfiguracji.

### Etap C — nowa zmiana w CP-SAT (rdzeń)
- Nowy `SHIFT_NIGHT` w `AutoScheduleGenerator`/`ConstraintContext`
  (`ALL_SHIFTS` rośnie o jeden element, analogicznie do `SHIFT_OPEN`).
  `x[e, d, SHIFT_NIGHT]` = "pracownik e zaczyna nocną zmianę w dniu d".
- `add_one_shift_per_day_constraint` — działa bez zmian (suma po
  `all_shifts` nadal ≤ 1 dla dnia D; noc "zajmuje" slot dnia D, nie D+1).
- **`rest_constraint.py`** — kluczowe miejsce. Trzeba dodać okno
  zmiany nocnej do `_build_shift_windows`/`windows_for`, z końcem
  wyrażonym jako "dzień D+1, godzina X" (już jest tam obsługa ujemnego
  odstępu przez `+= timedelta(days=1)`, więc mechanizm doliczania doby
  istnieje — trzeba tylko dodać `SHIFT_NIGHT` do zbioru wariantów zamiast
  zakładać, że każdy koniec zmiany jest "dziś"). Dodatkowo: zmiana nocna
  w dniu D musi wykluczać zwykłe zmiany dnia D+1, które zaczynają się
  *przed* końcem nocnej zmiany (realne nakładanie się w czasie, nie tylko
  odpoczynek 11h) — nowy, osobny constraint "brak nakładania" obok
  rest_11h.
- **`max_consecutive_days`, `monthly_hours`, `balance`** — zgodnie z
  decyzją #2, cała zmiana nocna liczy godziny do dnia D; te constrainty
  już sumują `x[e,d,s]`/`eff_hours` per dzień, więc wystarczy że
  `SHIFT_NIGHT` ma zdefiniowaną liczbę godzin (z `night_shift` configu, a
  nie z `get_effective_daily_hours`, bo długość zmiany nocnej może różnić
  się od standardowej — do ustalenia czy w ogóle powinna, patrz decyzja #1).
- **`solution_mapper.py`** — zapis rozwiązania: dla `SHIFT_NIGHT`
  wywołanie `schedule.set_day_hours(emp, d, night_start, night_end)`
  gdzie `night_end < night_start` (Etap A to już obsłuży).
- Constrainty specyficzne dla Dino (`meat`, `no_night`, `no_afternoon`,
  `open`/`close`) **nie dotykane** — `SHIFT_NIGHT` istnieje tylko dla
  profili, które go zadeklarują (patrz Etap F), więc `dino_retail`
  zachowuje się bajt-w-bajt tak samo (zgodnie z konwencją całej gałęzi
  `feature/business-profiles`).

### Etap D — UI
- `ui/grid_view.py` — wyświetlanie zmiany przechodzącej przez północ
  (np. `22:00 → 06:00 (+1)`), żeby użytkownik od razu widział, że koniec
  jest "jutro".
- `ui/day_edit_dialog.py`/`ui/day_override_dialog.py` — ręczne
  wprowadzanie/edycja zmiany nocnej (dziś formularz zapewne odziedziczy
  walidację `end > start` z `DaySchedule.set_hours` — trzeba dopilnować,
  żeby UI pozwalało wpisać `end <= start` świadomie jako "nocna").
- `logic/generator/manual_constraint.py` — ręcznie ustawiona/zablokowana
  zmiana nocna musi być poprawnie rozpoznawana jako `SHIFT_NIGHT` przy
  ponownym generowaniu (`is_fix=True`).

### Etap E — eksport i rozliczenia
- `export/excel_exporter.py`, `export/image_exporter.py` — upewnić się,
  że komórka z `end < start` renderuje się czytelnie (nie jako błąd/ujemna
  wartość).
- `logic/settlement_balancer.py` — bilans godzin musi liczyć zmianę nocną
  raz (do dnia D, decyzja #2), nie podwójnie i nie zerowo.

### Etap F — nowy profil biznesowy ("ochrona" / dowolny 24/7)
- Nowy `logic/generator/<profil>_profile.py` analogiczny do
  `dino_retail_profile.py`, ale z `SHIFT_NIGHT` jako główną zmianą,
  `open`/`close`/`meat`/`no_night`/`no_afternoon` pominięte (te
  constrainty w ogóle się nie rejestrują dla tego profilu — nie trzeba
  ich "wyłączać" politykami, po prostu nie wchodzą do `ALL_SPECS`).
- Ewentualnie: rozszerzenie kreatora custom profili
  (`ui/profile_wizard_dialog.py`, `model/custom_profile.py`,
  `logic/generator/generic_rules.py`) o nowy typ reguły
  `night_shift_coverage` (analogicznie do `min_staff_with_role`, ale
  liczący `SHIFT_NIGHT`), jeśli klient ma potrzebować **własnych** reguł
  obsady nocnej, a nie tylko wbudowanego profilu.

### Etap G — testy
- Jednostkowe: `DaySchedule` wrap-around (Etap A), budowa okien w
  `rest_constraint.py` z `SHIFT_NIGHT` (Etap C).
- Scenariuszowe: rozszerzyć `tests/run_scenarios.py`/
  `tests/stress_test_generator.py` o projekt z lokalizacją 24/7 i
  zmianą nocną — sprawdzić feasibility i brak nakładających się zmian.
- Regresja: cały istniejący `pytest tests/` musi zostać zielony bez zmian
  (obecny stan na branchu: 85 passed, 1 pre-existing fail niezwiązany).

## 6. Kolejność i punkt startu

Etapy A→G są zaprojektowane tak, by każdy dawał się scommitować i
przetestować osobno, bez zostawiania appki w stanie pośrednim (ta sama
zasada co przy `lokalizacjach`). **Najbezpieczniejszy pierwszy krok:
Etap A** — sam fundament w `DaySchedule`, zero wpływu na generator/UI,
łatwy do zweryfikowania testami jednostkowymi w izolacji.

Przed Etapem C konieczne są odpowiedzi na pytania z sekcji 3 (kształt
zmiany nocnej, przypisanie godzin do dnia D vs D+1) — inaczej ryzyko
przebudowy `rest_constraint.py` "na ślepo" i konieczność przerabiania.
