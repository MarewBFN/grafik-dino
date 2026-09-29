# Audyt: zachowanie generatora dla Dino zmieniło się od v1.2.0

Data: 2026-09-26. Zakres: porównanie taga `v1.2.0` (release na kanał
dino) z HEAD tej gałęzi (`claude/pre-release-correctness-audit-rp6zi9`,
o 124 commity dalej). `main` w chwili audytu = v1.2.0 + manifest
aktualizacji dla kanału enyo, więc obecni klienci Dino tych zmian jeszcze
nie mają - dotknęłyby ich dopiero po wydaniu tej gałęzi (albo integracji
z niej) w kanale dino.

**To jest złamanie zasady #2 z `ENYO_ONLY_CHANGES.md`** ("nigdy nie
zmieniaj zachowania constraintów pisanych pod Dino" / zmiana we
wspólnym kodzie wolno tylko, gdy to prawdziwy bug *przetestowany na
pełnym zestawie danych Dino"). Poniższe zmiany trafiły do wspólnego
kodu (`night_shift`/godziny otwarcia per lokalizacja/norma godzin) bez
takiej weryfikacji.

## Metoda

Statyczny diff `git diff v1.2.0..HEAD` dla każdego pliku dotykającego
generatora + empiryczne uruchomienie obu wersji kodu (worktree z v1.2.0)
na tych samych 40 losowych projektach Dino (5 miesięcy, seedy 1-3,
8-12 osób, z urlopami/L4/blokadami/ograniczeniami dostępności),
zapisanych w formacie 1.2.0. Bez zmian w repozytorium - tylko odczyt i
uruchamianie kodu z dwóch wersji równolegle.

## Błędy (regresje, nie zamierzone zmiany)

### 1. Automatyczne wykrywanie zmiany nocnej dokłada nocki 22:00-06:00 zwykłym pracownikom

Od commita `6eeae32` (18.09, "Dodaj zarządzanie wieloma lokalizacjami")
`LocationConfig.get_night_shift_hours()` zwraca stałe okno 22:00-06:00,
gdy KTÓRYKOLWIEK dzień tygodnia w godzinach otwarcia nachodzi na porę
nocną. Domyślne godziny Dino (otwarcie do 22:45/23:00) spełniają ten
warunek, więc SHIFT_NIGHT jest dla każdej takiej lokalizacji dostępny.

- W 18 z 20 rozwiązanych testowych projektów pojawiły się nocki (4-23
  w miesiącu na projekt, 10-osobowy zespół). W v1.2.0: zero.
- Solver używa ich, żeby trafić dokładnie w normę miesięczną: pełny etat
  ma zwykłą zmianę 8,5h, a nocka liczy się jako 8h - łatwiej dobić do
  176h kombinacją zmian różnej długości.
- `no_night`/ograniczenia dostępności pracownika NIE blokują nocek
  (SHIFT_NIGHT nie jest w ogóle mapowany na `availability`, patrz
  `logic/generator/availability_constraint.py`).
- Jakość grafiku (wartość celu solvera) spada o ok. 20% w testach
  (potwierdzone w 3 powtórzeniach, także przy wydłużeniu limitu czasu
  solvera z 30s do 120s). Po wyłączeniu wykrywania nocki wynik wraca do
  poziomu 1.2.0.

**Reprodukcja:** wygeneruj dowolny projekt Dino z domyślnymi godzinami
otwarcia (zamknięcie 22:00 lub później którykolwiek dzień tygodnia) i
porównaj liczbę komórek grafiku z `end <= start` (nocki) między v1.2.0
a HEAD.

### 2. Niedziele handlowe zaznaczone w Konfiguracji dają 0 obsady

Zakładka "Niedziele handlowe" w `ui/config_dialog.py::_save()` zapisuje
wybrane niedziele wyłącznie do `self.shop_config.trade_sundays`
(poziom projektu). Generator i grid czytają
`shop.get_location(emp).is_trade_day()`, czyli `LocationConfig.
trade_sundays` - osobne, puste pole. Efekt: niedziela oznaczona jako
handlowa w Konfiguracji pozostaje dla każdego pracownika niehandlowa.

- Test (grudzień 2026, dwie zaznaczone niedziele): v1.2.0 dało 8 i 7
  zmian tego dnia, HEAD dało 0 i 0.
- Błąd istnieje od `6eeae32` (ten sam commit co punkt 1).

**Reprodukcja:** w Konfiguracji zaznacz niedzielę jako handlową, zapisz,
wygeneruj grafik - nikt nie dostanie zmiany w tę niedzielę mimo że
powinna być traktowana jak dzień roboczy.

### 3. Obsada mięsa liczona wg starych (projektowych) godzin otwarcia

`logic/generator/meat_constraint.py` i `meat_light_budget.py` nadal
wołają `shop.get_open_hours_for_day(d)` (poziom projektu) zamiast
`shop.get_location(emp).get_open_hours_for_day(d)`. Po zmianie godzin
konkretnej lokalizacji w nowym oknie Konfiguracji (per-lokalizacja)
reguły mięsne liczą pokrycie względem STARYCH, nieaktualnych godzin.

**Reprodukcja:** w Konfiguracji zmień godziny otwarcia lokalizacji (np.
z 05:30-22:45 na 07:00-21:00), zapisz, sprawdź okno czasowe używane
przez `add_meat_constraint`/`add_meat_coverage_constraint` - nadal
05:30-22:45.

## Zamierzone zmiany z widocznymi skutkami ubocznymi dla klienta

### 4. Automatyczne zamykanie w polskie święta ustawowe

v1.2.0 obsadzało święta normalnie, chyba że ktoś ręcznie zaznaczył
dzień jako wolny. Teraz `LocationConfig.closed_on_public_holidays`
(domyślnie `True`) automatycznie zamyka lokalizację w każde święto z
biblioteki `holidays` (kalendarz polski). W testach: od 6 do 31
"utraconych" zmian na projekt w zależności od miesiąca.

Dwa efekty uboczne tej zmiany, oba dowiedzione w testach:

- **Kierowniczka nadal dostaje sztywną zmianę w zamknięte święto**
  (`logic/manager_schedule.py` nie sprawdza zamknięcia lokalizacji per
  pracownik, tylko `shop.is_trade_day()` na poziomie projektu - dla
  Dino to wciąż `True`, bo `is_trade_day` nie wie nic o świętach
  ustawowych z biblioteki `holidays`).
- **Zmiana zablokowana bezpośrednio przed świętem traci ochronę
  odpoczynku 11h wobec tego święta** - w jednym z testów wyszła przerwa
  8h zamiast wymaganych 11h, bo dzień świąteczny nie buduje już żadnych
  "okien" do porównania.

### 5. Norma godzin w miesiącu (pełny etat) zmieniła się dla większości miesięcy

`ShopConfig.get_full_time_nominal_hours()` teraz automatycznie odejmuje
święta ustawowe (z biblioteki `holidays`, nie tylko ręcznie zaznaczone)
i dodatkowo obniża normę o dzień za święto wypadające w sobotę (art.
130 §2¹ KP). Zmierzone różnice na testowych miesiącach:

| miesiąc | v1.2.0 | HEAD | powód różnicy |
|---|---|---|---|
| wrzesień 2026 | 176h | 176h | brak święta w tygodniu |
| sierpień 2026 | 168h | 160h | 15.08 wypada w sobotę (art. 130 §2¹) |
| listopad 2026 | 168h | 160h | 11.11 |
| grudzień 2026 | 184h | 160h | 24 (sob), 25, 26.12 |
| styczeń 2027 | 168h | 152h | 1.01, 6.01 |

Dodatkowo: ręczne zaznaczenie dnia jako "Święto" w nagłówku grafiku
(`day_overrides`) już NIE obniża normy (w v1.2.0 obniżało) - teraz
liczą się wyłącznie automatycznie wykryte święta ustawowe plus
`shop.public_holidays`.

### 6. Bilans godzin (`balance`) uwzględnia teraz urlop/L4

v1.2.0: pracownik z urlopem/L4 był mimo to "dociągany" do pełnej normy
miesięcznej przez `add_balance_constraint` - w teście pełny etat z 5
dniami urlopu dostał 178,5h (powinno być ~133,5h), czyli ok. 45h
nadgodzin wygenerowanych tylko po to, żeby zaspokoić bilans liczony bez
odjęcia urlopu. HEAD odejmuje urlop/L4 od celu bilansu - poprawka, ale
zmienia realny wynik grafiku dla każdego takiego pracownika.

### 7. Drobniejsze, potwierdzone zmiany zachowania

- `no_night` przestał błędnie blokować starty zmian 06:00-06:59 i
  zmiany kończące się dokładnie o 22:00 (błąd zaokrąglenia `>=`/`<=` w
  starym kodzie).
- Doszła "pamięć poprzedniego miesiąca": wymóg 11h odpoczynku na
  początku nowego miesiąca względem końca ostatniej zmiany poprzedniego.
- Ręczny wpis godzin 22:00-06:00 (dokładnie zmiana nocna) jest teraz
  poprawnie rozpoznawany i akceptowany zamiast cicho odrzucany.

## Co się NIE zmieniło (potwierdzone)

- W miesiącu bez świąt i bez urlopów/L4 (wrzesień 2026, `clean_202609`)
  HEAD ocenia identyczny grafik z v1.2.0 tą samą wartością celu solvera
  (-2344824 w obu wersjach) - twarde reguły i wagi punktacji są
  identyczne, różnicę robi wyłącznie dostępność nocek (punkt 1).
- Wykonalność (feasible/infeasible) była identyczna w każdym z 40
  testowych projektów - żadna zmiana nie zamieniła rozwiązywalnego
  miesiąca w nierozwiązywalny ani odwrotnie.
- Moduł mięsa (poza godzinami z punktu 3), obsługa kierowniczek (poza
  świętami z punktu 4), zakaz pracy popołudniowej i sam solver CP-SAT
  są niezmienione od v1.2.0.

## Ograniczenia tego audytu

- Projekty testowe są syntetyczne/losowe (`build_random_project`), nie
  prawdziwe dane klienta Dino.
- Limit czasu solvera w testach: głównie 30s (domyślny w aplikacji:
  60s); jeden zestaw dodatkowo sprawdzony przy 120s (bez zmiany wniosku
  o punkcie 1).
- Nie testowano trybu "Popraw" (`is_fix=True`) ani eksportów (PDF/karta
  pracownika) pod kątem tych regresji.
- Do porównania pobrano pełną historię git (repo było shallow) - nie
  zmieniło to żadnego pliku w repozytorium.

## Rekomendacja

Przed wydaniem dla klientów Dino: naprawić punkty 1-3 (prawdziwe błędy,
nie kwestia decyzji produktowej). Punkty 4-6 są uzasadnionymi zmianami
(zgodność z Kodeksem pracy, poprawność bilansu), ale wymagają
świadomej decyzji i komunikatu do klientów Dino, bo zauważalnie zmieniają
liczbę godzin i obsadę względem tego, do czego są przyzwyczajeni.
