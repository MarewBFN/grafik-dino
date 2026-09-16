# Plan: profil "ochrona" — analiza specyfikacji funkcjonalnej klienta

Branch: `claude/night-shift-generator-support-ex6pqc`. To jest wyłącznie
analiza + pytania + plan dla jednoznacznych punktów — **brak zmian w
kodzie**. Punkt wyjścia: notatki klienta (firma ochroniarska) wklejone w
całości do tej rozmowy, zweryfikowane względem aktualnego stanu repo
(nie zgadywane). Nawiązuje do `plan generalizacji branzowej.md` (sekcja
"Świadomie odłożone: Konkretny profil dla firmy ochroniarskiej — czeka na
wymagania od klienta" — to jest ten moment) i `plan zmiany nocne (24-7).md`
(Etapy A–G, już zaimplementowane na tym branchu wg `git log`).

Legenda: **(A)** istnieje, wystarczy skonfigurować · **(B)** częściowo
istnieje, wymaga rozszerzenia · **(C)** nie istnieje, trzeba zbudować.

---

## 1. Konfiguracja obiektu

### Godziny otwarcia — "bez zmian" / Niedziele handlowe — "bez zmian"

**(A) — istnieje.** `BusinessProfile.uses_trade_calendar` (`model/business_profile.py:45`)
jest `False` domyślnie dla każdego profilu poza `dino_retail`. Skutki,
zweryfikowane w kodzie:

- `ShopConfig.is_trade_day()` (`model/shop_config.py:148-161`) zwraca
  zawsze `True` dla profilu bez kalendarza handlowego — każdy dzień jest
  normalnym dniem roboczym.
- Zakładka "Niedziele handlowe" w Konfiguracji **w ogóle się nie
  pojawia** dla takiego profilu (`ui/config_dialog.py:231-232`,
  `if self.profile.uses_trade_calendar: tabs.addTab(...)`).
- Zakładka "Godziny otwarcia" zostaje — dla obiektu pracującego 24/7
  ustawia się tam po prostu bardzo szeroki zakres per dzień tygodnia
  (`ShopConfig.open_hours`, `model/shop_config.py:122-130`), tak jak
  dziś robi to Dino przy nietypowych dniach. Nic do zrobienia poza
  konfiguracją nowego profilu w kreatorze.

---

## 2. Limity czasu pracy

### 2.1 Maksymalna ilość godzin (pełny etat), np. 176h

**(A) — istnieje, ale to wartość liczona, nie wpisywana ręcznie.**
`ShopConfig.get_full_time_nominal_hours()` (`model/shop_config.py:304-327`)
liczy nominalny wymiar miesięczny wg formuły kodeksu pracy: liczba dni
roboczych pon-pt w miesiącu (pomniejszona o święta ustawowe) razy 8h.
To dokładnie ta sama liczba, którą HR/kadry liczą jako "wymiar czasu
pracy" na dany miesiąc — przykład klienta (176h) to typowa wartość dla
miesiąca z 22 dniami roboczymi. Nie ma dziś pola do ręcznego wpisania
innej, stałej liczby — pytanie do klienta w sekcji 5.

### 2.2 Wymuś 8h (nie 8:30) dla pracowników pełnoetatowych

**(A) — istnieje, to czysta konfiguracja.** To jest dokładnie odwrotność
istniejącej, świadomie zaszytej konwencji Dino:

- `logic/utils/time_utils.py::get_effective_daily_hours()` (linie 4-19):
  gdy `shop.constraints["force_fulltime_845"]` jest `True` i pracownik ma
  `employment_fraction == 1.0`, dzień liczy **8:30** zamiast
  `standard_daily_hours`. To pole steruje checkbox "Wymuś 8h 30 min dla
  pracowników pełnoetatowych" w Konfiguracji (`ui/config_dialog.py:486-491`),
  domyślnie zaznaczony (`model/shop_config.py:97`, `"force_fulltime_845": True`).
- Wyłączenie tego checkboxa (`force_fulltime_845 = False`) przy
  `standard_daily_hours = 8.0` (wartość domyślna) daje dokładnie
  "pełny etat = 8h, nie 8:30" — zero kodu, jedno odznaczenie w
  Konfiguracji nowego profilu.
- Dodatkowo istnieje już nawet gotowy wariant per-pracownik: pozycja
  "1/1 (pełny etat) max 8:00" w polu Wymiar etatu
  (`ui/employee_dialog.py:95`, `employment_fraction = 1.01` — wartość
  specjalna obsłużona w `get_effective_daily_hours` linia 6-7), gdyby
  klient chciał to różnicować pracownik-po-pracowniku zamiast globalnie.

### 2.3 Podświetlanie (na czerwono) przekroczenia miesięcznego limitu pełnoetatowych

**(C) — nie istnieje, trzeba zbudować. Mały-średni kawałek pracy.**
Sprawdzone w kodzie:

- `model/constraints.py::ConstraintEngine` (silnik, który dziś koloruje
  wiersze "Otwarcie"/"Zamknięcie"/"Mięso" na czerwono/żółto w gridzie)
  **nie ma żadnej reguły dot. godzin miesięcznych** — tylko
  `MaxConsecutiveDaysRule`, `MinStaffRule`, `Rest11hRule`,
  `MeatCoverageRule` (linie 38-192).
- Kolumna "Razem" w gridzie (`ui/grid_view.py::_fill_summary_cells`,
  linia 808-819) to zwykły `QTableWidgetItem` z jednolitym tłem
  (`theme.BG_PANEL`) — brak jakiegokolwiek porównania z limitem.
- Dobra wiadomość: **wszystkie liczby potrzebne do porównania już
  istnieją i są dokładnie te same, których używa generator** —
  `ShopConfig.get_full_time_nominal_hours()` (2.1) razy
  `emp.employment_fraction`, pomniejszone o urlop/L4, to dokładnie
  `target_minutes` z `logic/generator/hours_constraint.py:74`
  (`add_monthly_hours_constraint`); po stronie "ile faktycznie
  przepracował" to `schedule.total_with_leave_and_sick_minutes_for_employee(emp)`
  (już użyte w `logic/settlement_balancer.py:99` do dokładnie tego typu
  porównania, tylko w innym celu — bilansowaniu, nie kolorowaniu).
- Zakres pracy: jedna nowa funkcja pomocnicza (np.
  `logic/schedule_presenter.py` albo nowa reguła w
  `model/constraints.py`) licząca "czy pracownik przekroczył swój
  miesięczny limit", spięcie z kolumną "Razem" w `grid_view.py` (kolor
  tła), plus to samo porównanie w obu eksporterach (sekcja 4). Nie
  wymaga zmian w generatorze ani w CP-SAT — to czysto prezentacyjna
  warstwa nad już policzonymi liczbami.

### 2.4 Minimalna obsada pracowników

**(A) — istnieje jako opcja, klient świadomie z niej rezygnuje.** Klient
sam zauważa, że przez ustawienie dostępności (dni + max godzin) i
zmianę 24h nie potrzebuje twardej reguły "min. N osób" — obsada wynika
z tego, kto ma tego dnia zmianę. Zgadza się z architekturą: generyczna
reguła `min_staff_with_role` (`logic/generator/generic_rules.py:25-78`,
ze scope `"open"/"close"/"any_shift"/"night"`) jest dostępna z poziomu
kreatora profilu, ale nic nie zmusza do jej użycia — profil "ochrona"
po prostu nie definiuje takiej reguły. Zero pracy.

---

## 3. Zasady generatora

**(A) — istnieje.** Podliczenia z prawej strony grafiku (Praca / Urlop /
L4 / Razem) to nagłówki wpisane na stałe w `ui/grid_view.py:561`
(`headers.extend(["Praca\n(h)", "Urlop\n(h)", "L4\n(h)", "Razem\n(h)"])`)
i metody `MonthSchedule` (`total_hours_for_employee`,
`leave_hours_for_employee`, `sick_hours_for_employee`,
`total_with_leave_and_sick_for_employee`) — niezależne od profilu
biznesowego, widoczne zawsze, dla każdego profilu. "Zasady generatora"
specyficzne dla Dino (mięso, obsada otwarcia/zamknięcia, zakaz
popołudni) po prostu nie są tworzone dla profilu "ochrona" (nie trzeba
ich "usuwać" — nowy profil ich od razu nie ma, tak jak żaden dzisiejszy
custom profil ich nie ma). Zero pracy poza zbudowaniem profilu w
kreatorze.

---

## 4. Dane pracownika

### 4.1 Nazwisko / Imię

**(A) — istnieje.** `model/employee.py:20-21`, formularz
`ui/employee_dialog.py:85-86`.

### 4.2 Wymiar etatu: dodać 6/8 i "nieokreślony"

**"6/8" — (A), kosmetyka.** `employment_fraction` to `float`
(`model/employee.py:34`), a `6/8 = 0.75` to dokładnie ta sama wartość,
którą combo już oferuje pod etykietą "3/4" (`ui/employee_dialog.py:97`).
Żeby klient widział własną terminologię, wystarczy dodać/zmienić
pozycję na liście (`self.employment_fraction.addItem("6/8", 0.75)`) —
kosmetyczna zmiana jednej linijki UI, nie nowa logika.

**"Nieokreślony" — (C), nowa kategoria, wymaga decyzji produktowej
(patrz pytania, sekcja 5).** To nie jest kolejna wartość ułamkowa, tylko
inny **tryb** pracownika. Dziś `employment_fraction` pełni podwójną
rolę w generatorze:

- określa długość jego zmiany (`get_effective_daily_hours`,
  `logic/utils/time_utils.py:4-19`),
- **i jednocześnie** określa jego twardy miesięczny target godzin
  (`target_minutes = nominal_minutes * emp.employment_fraction - urlop - L4`,
  `logic/generator/hours_constraint.py:74`, potem
  `model.Add(total_minutes >= target_minutes)` / `<= target_minutes + daily_hours*60`
  — linie 76-78) oraz cel bilansu (`add_balance_constraint`, linie
  105-160, `total_minutes == nominal_minutes` w trybie twardym).

Pracownik "z doskoku" (łatanie luk, bez określonego wymiaru) potrzebuje
**odciążenia z drugiej roli** — generator ma go móc użyć 0-40h w
miesiącu bez wymuszania konkretnej sumy — przy zachowaniu pierwszej
(nadal potrzebuje jakiejś długości pojedynczej zmiany, żeby wiedzieć,
ile godzin dać mu za dany dzień). To wymaga: nowego rozróżnienia na
poziomie `Employee` (sentinel w `employment_fraction`, czy osobne pole
typu `employment_type: "fixed" | "flexible"`), zmian w
`add_monthly_hours_constraint`/`add_balance_constraint`, żeby pomijały
target dla takich pracowników (tylko "policz ile wyszło", bez
`model.Add(>=...)`/`==`), oraz walidacji w `Employee.validate()`
(dziś `employment_fraction <= 0` rzuca błąd — linia 74-75 w
`model/employee.py` — trzeba dodać legalną "pustą" wartość). Skala:
średni kawałek pracy, ale izolowany (dotyka 2-3 pliki generatora + model
+ UI), nie porównywalny z lokalizacjami/zmianami nocnymi.

### 4.3 Nie pracuje w nocy (22-6) / nie pracuje popołudniami

**(A) — istnieje jako mechanizm generyczny, "może zostać" dosłownie.**
To dokładnie te same pola co u Dino (`no_night`/`no_afternoon`,
`_ROLE_FIELDS` w `model/employee.py:6`), ale dla **nowego** custom
profilu trzeba je odtworzyć jako własne role przez kreator (nie
dziedziczą się automatycznie — `RoleDef` dino'owe `no_night`/
`no_afternoon` z `model/business_profile.py:72-73` są przypięte
wyłącznie do profilu `dino_retail`). Mechanizm generyczny już to
wspiera 1:1: `logic/generator/generic_rules.py::build_role_time_restriction`
(linie 91-155) to dokładnie ogólna wersja `no_night`/`no_afternoon` —
sparametryzowana oknem godzinowym (`window_start_hour`/`window_end_hour`),
wpisywalna z kreatora (`ui/profile_wizard_dialog.py:42,131,140-141`,
spinboxy godzin już istnieją w UI kreatora). Dla ochrony: zdefiniować w
kreatorze rolę np. "Nie pracuje nocą" z regułą "Zakaz pracy w oknie
czasowym" 22-6, drugą rolę "Tylko dzień" z oknem popołudniowym, i
zaznaczać checkbox przy konkretnym pracowniku w `EmployeeDialog` —
identycznie jak dziś robi się to dla `is_meat`/`is_opener`. Zero nowego
kodu, tylko konfiguracja profilu.

### 4.4 Dni robocze (ptaszki) + maksymalna liczba godzin **per dzień tygodnia**

**(C) — nie istnieje w tej postaci, i to jest realnie nowy przypadek,
różny od wszystkiego co jest dziś w generatorze.** Sprawdzone dokładnie,
bo to jeden z punktów, które podejrzewałeś:

- Istnieje `Employee.availability: Dict[int, dict]` (`model/employee.py:37`)
  per dzień tygodnia — **ale to nie jest "ile godzin", tylko "w jakim
  oknie czasowym mieści się zmiana"** (para `start`/`end` + tryb
  `hard`/`soft`, `Employee.validate()` linie 77-87). Używane wyłącznie
  do przefiltrowania, które z **z góry ustalonych** zmian
  (OPEN/CLOSE/START_15..90/END_15..90 — sloty wyznaczone godzinami
  otwarcia sklepu) mieszczą się w tym oknie
  (`logic/generator/availability_mapper.py::get_allowed_shifts_for_day`,
  linie 13-80). Nie ma tu w ogóle koncepcji "ta zmiana ma być długa na
  X godzin, inna na Y godzin, zależnie od dnia tygodnia".
- **Nie ma dziś żadnego UI do edycji `availability`.** Sprawdzone: `grep`
  po całym katalogu `ui/` za "availability"/"dostępność"/"dyspozycyjność"
  nic nie znajduje. Pole istnieje w modelu i jest w pełni wpięte w
  generator, ale można je dziś ustawić wyłącznie ręczną edycją pliku
  JSON projektu — nie ma formularza. To osobny brak, niezależny od
  tego, czy dodamy "max godzin per dzień", czy nie.
- Długość zmiany (`get_effective_daily_hours`, `logic/utils/time_utils.py:4-19`)
  jest dziś **jedna wartość na pracownika**, stała dla każdego dnia
  miesiąca — `standard_daily_hours * employment_fraction`, bez pojęcia
  dnia tygodnia. Żeby mieć "16h pon-pt, 12h sob-nd" per pracownik,
  potrzeba nowego pola (np. `Employee.weekday_max_hours: dict[int, float]`
  albo rozszerzenia istniejącego `availability` o wartość godzin obok
  okna) i przepisania `get_effective_daily_hours` (i każdego miejsca,
  które je wywołuje — `hours_constraint.py`, `availability_mapper.py`,
  `generic_rules.py`, `settlement_balancer.py` — dziś zawsze 1 argument
  `(emp, shop)`, musiałoby przyjmować też dzień/dzień tygodnia).
- To samo dotyczy checkboxów "które dni może pracować" — dziś
  `availability` per dzień tygodnia **istnieje** koncepcyjnie (brak
  wpisu = "brak ograniczeń", cokolwiek), ale nie ma prostego "dzień
  wyłączony = nie pracuje w ten dzień w ogóle" bez podawania okna
  godzinowego — dałoby się to wyrazić przez `hard`-owe okno 0 minut,
  ale to nie jest dziś zamierzony, przetestowany przypadek.

Skala: to nie jest mała poprawka. Wymaga: (1) nowego modelu danych per
(pracownik, dzień tygodnia) — czy dzień dostępny, i ile max godzin; (2)
UI do tego (które dziś nie istnieje nawet dla samego `availability`);
(3) przepisania `get_effective_daily_hours` i wszystkich jego wywołań na
świadomość dnia tygodnia; (4) decyzji, jak to współgra z pkt. 6 (zmiana
24h) — patrz sekcja 6. Kaliber zbliżony do Etapu 3 lokalizacji, ale
węziej zakrojony (dotyczy pracownika, nie całego obiektu).

---

## 5. Tryb szybki

**(A) — istnieje, dokładnie taki, jak opisano.** Podwójne kliknięcie w
komórkę dnia w gridzie otwiera `DayEditDialog`
(`ui/day_edit_dialog.py`, spięte przez `ui/main_window.py:796-809,
_edit_day`) z przyciskami **Wolne / Urlop / Chorobowe** oraz ręcznym
wpisaniem godzin — dokładnie scenariusz klienta ("ktoś dzwoni, bierze
chorobowe → zaznacz L4 temu, dodaj zmianę komuś innemu"). Ręczna zmiana
dostaje `is_locked = True` i generator przy ponownym uruchomieniu jej
nie rusza (potwierdzone też dla `SHIFT_NIGHT` po ostatnich poprawkach z
`git log`: `3b162af`, `3c10759`, `0e20055`). Zero pracy — to już działa,
najwyżej do pokazania klientowi jak z tego korzystać.

---

## 6. Wydruk grafiku wewnętrzny

### 6.1 Cały grafik, nadgodziny na czerwono

**(B) — częściowo istnieje.** Wydruk całości działa dziś dwiema
ścieżkami: `export/image_exporter.py` (JPG, używany też przez
"Drukuj..." w `ui/main_window.py:1091-1103`) i `export/excel_exporter.py`
(XLSX). Żaden z nich nie koloruje niczego na czerwono — to czysto
czarno-białe/szare renderowanie (`export/image_exporter.py` — stałe
`GRID`/`SATURDAY`/`SUNDAY`, brak logiki błędów; podobnie
`excel_exporter.py`, sprawdzone na nagłówku pliku). Zależy wprost od
punktu 2.3 — jak tylko istnieje funkcja "czy pracownik przekroczył
limit", dodanie czerwonego tła do kolumny "Razem" w obu eksporterach to
mechaniczne powtórzenie tej samej logiki (openpyxl ma `PatternFill` już
zaimportowany i używany, Pillow ma `draw.rectangle(fill=...)` już
używane) — nie osobny kawałek architektury, tylko konsekwencja 2.3.

### 6.2 Wydruk dla jednego pracownika z osobna

**(C) — nie istnieje, ale mały kawałek pracy.** Sprawdzone: `main.py`/
`ui/main_window.py` ma tylko jedną akcję eksportu/druku, zawsze dla
całego `schedule` (`export_schedule_to_image(self.schedule, ...)`,
`ui/main_window.py:1074,1103` — bez wyboru pracownika). Oba eksportery
budują listę wierszy wprost z `schedule.employees` (`image_exporter.py:13`,
analogicznie w Excelu) — nie przyjmują dziś podzbioru. Rozwiązanie: dodać
opcjonalny parametr `employees` do obu funkcji eksportu (domyślnie
`schedule.employees`, żeby nic się nie zmieniło dla istniejącego użycia),
i nowy wpis w menu/dialogu wyboru pracownika w `main_window.py`, który
woła eksport z listą jednoelementową. Mechaniczna zmiana, brak nowej
logiki domenowej.

---

## 7. Punkt, o który pytałeś wprost: czy SHIFT_NIGHT (Etap C) obsłuży zmianę 24h?

**Nie — to inny, nowy przypadek, i to podważa nie tylko "24h", ale też
całą wariację 16h/12h z sekcji 4.4.** Zweryfikowane wprost w kodzie:

- `SHIFT_NIGHT` to dziś **jeden, sztywny blok czasowy na całą
  lokalizację** (`LocationConfig.night_shift: dict | None`,
  `model/location.py:57-61`) — ten sam start/koniec dla **każdego**
  pracownika przypisanego do tej lokalizacji
  (`night_shift_minutes_for_employee`, `logic/generator/night_shift_constraint.py:40-46`,
  bierze `shop.get_location(employee).get_night_shift_hours()` — nie ma
  tam nic per-pracownik). Klient chce coś przeciwnego: różna długość
  zależnie od pracownika (zgadza się na 24h czy nie) i od dnia tygodnia
  (16h pon-pt, 12h/24h weekend) — to wymaga N różnych "zmian" per
  lokalizacja, nie jednej.
- **24h w ogóle nie da się dziś skonfigurować jako `night_shift`** —
  `normalize_night_shift()` (`model/location.py:31-45`) jawnie odrzuca
  `start == end` (`raise ValueError("Godzina początku i końca zmiany
  nocnej nie mogą być takie same")`, linia 44) — a zmiana 00:00→24:00
  (pełna doba) to matematycznie `start == end` w reprezentacji "HH:MM
  bez daty", którą cała aplikacja i tak używa (ten sam powód, dla
  którego `standard_daily_hours` ma dziś twardy limit 23,75h — patrz
  `plan generalizacji branzowej.md`, punkt 2). Nawet obejście "prawie
  cała doba" (00:00–23:45) nie zadziała tu tak jak dla Dino, bo Dino
  używa go dla stanu "sklep właściwie zawsze otwarty", nie dla
  "pojedyncza zmiana trwa 24h" — dla ochrony to musiałaby być jedna,
  ciągła zmiana jednej osoby, a nie sklep-otwarty-cały-czas z wieloma
  nachodzącymi na siebie zmianami (co jest założeniem modelu Dino
  wszędzie indziej: `min_open_staff`/`min_close_staff`, obsada
  wielo-osobowa w danym momencie).
- Głębszy problem strukturalny: model zmian w tej appce (OPEN/CLOSE/
  START_15..90/END_15..90/NIGHT) zakłada **kilku pracowników jednocześnie
  na miejscu, z nachodzącymi się godzinami** (typowy sklep). Posterunek
  ochrony to zwykle **dokładnie jedna osoba na zmianę, zmiany stykają
  się krawędziami bez przerwy i bez nakładania** (koniec zmiany A =
  początek zmiany B). To inny kształt problemu niż "ilu ludzi jest w
  oknie X" — bliżej "jak różnej długości bloki układają się w ciągłą
  linię 24/7 bez dziur i bez nakładania", z dodatkowym ograniczeniem
  odpoczynku (11h to prawdopodobnie za mało po zmianie 24h — patrz
  pytania, sekcja 8).

**Wniosek: to nie jest rozszerzenie Etapu C zmian nocnych, tylko osobny,
nowy typ zmiany/mechanizmu generatora.** Realistyczna skala: **duży
kawałek pracy**, porównywalny albo większy niż same lokalizacje (Etap
3a-3d) i zmiany nocne (Etap A-G) razem wzięte — bo łączy w sobie: (a)
zmienną długość zmiany per pracownik/dzień tygodnia (sekcja 4.4), (b)
brak nakładania się zamiast obsady wielo-osobowej, (c) prawdopodobnie
inny reżim odpoczynku po długiej zmianie, (d) decyzję, czy to w ogóle
ten sam "silnik" CP-SAT co dziś, czy osobna ścieżka generowania dla
takich obiektów. **Nie planuję tego niżej w sekcji 9** — czeka na
odpowiedzi z sekcji 8.

---

## 8. Pytania do Ciebie / decyzje produktowe

Pogrupowane od najbardziej blokujących w dół.

### Blokujące (bez tego nie da się ruszyć z sekcją 4.4 / 7)

1. **Jak faktycznie wygląda pokrycie doby na jednym obiekcie?** Czy to
   zawsze dokładnie 1 osoba na miejscu (klasyczny posterunek), czy
   czasem więcej (patrol + recepcja jednocześnie)? Czy zmiany zawsze
   stykają się bez przerwy (koniec = początek następnej), czy
   dopuszczalne są luki (np. obiekt bez ochrony w środku dnia)?
2. **Jak dokładnie wygląda "16h pon-pt"?** Czy to jedna 16h zmiana +
   luka 8h bez ochrony, czy 16h + druga osoba na 8h (czyli de facto 2
   zmiany, jedna z nich to zwykła "krótsza" zmiana)? Bez tego nie da
   się zaprojektować mechanizmu "różnej długości zmian per dzień
   tygodnia" (sekcja 4.4/7) — to determinuje, czy to w ogóle 1 typ
   zmiany, czy 2-3 równoległe typy.
3. **Odpoczynek po zmianie 24h.** Dzisiejszy `rest_11h`
   (`ConstraintPolicy.MANDATORY` domyślnie) zakłada min. 11h przerwy —
   to jest zgodne z kodeksem pracy dla zwykłych zmian, ale przy 24h
   służbie ochrony częsta jest praktyka dłuższego odpoczynku (np. 24h
   pracy / 48h+ wolnego, albo szczególny system równoważny czasu pracy
   dla dozoru mienia, art. 136 k.p.). Jaki odpoczynek ma wymuszać
   generator po zmianie 24h? Po zmianie 16h? Czy to osobna reguła, czy
   nadal "min. 11h", tylko liczone poprawnie względem końca 24h zmiany?
4. **Czy pracownik może w tym samym miesiącu robić i zmiany 16h w
   tygodniu, i 24h w weekend** (czyli to jest właściwość dnia tygodnia,
   nie pracownika), **czy pracownicy dzielą się na dwie stałe grupy**
   ("ja zawsze 24h w weekend" / "ja zawsze 2x12h") i to jest właściwość
   pracownika ustawiana raz w jego profilu? Wpływa wprost na kształt
   danych z sekcji 4.4 (per-dzień czy per-pracownik-i-dzień).

### Ważne, ale nie blokują startu (dotyczą punktów jednoznacznych)

5. **"Nieokreślony" wymiar etatu (sekcja 4.2)** — czy to oznacza (a)
   brak jakiegokolwiek miesięcznego targetu/limitu (generator używa
   takiej osoby wyłącznie do łatania dziur, bez dążenia do konkretnej
   sumy godzin), czy (b) limit ustawiany ręcznie każdorazowo per taki
   pracownik (bliżej dzisiejszego trybu rozliczeniowego,
   `logic/settlement_balancer.py`, gdzie cel wpisuje się ręcznie w
   gridzie), czy (c) coś trzeciego? To decyduje, czy w ogóle trzeba
   ruszać `hours_constraint.py`, czy wystarczy istniejący mechanizm
   celu rozliczeniowego.
6. **Maksymalna liczba godzin pełnoetatowych (sekcja 2.1)** — czy
   wystarczy dzisiejsza automatyczna kalkulacja wg kodeksu pracy
   (dni robocze × 8h, różna co miesiąc), czy klient chce **wpisywać
   ręcznie stałą liczbę** (np. zawsze "176h" niezależnie od
   faktycznego miesiąca)? Jeśli to drugie — skąd ta liczba (osobna
   umowa/regulamin firmy ochroniarskiej, niekoniecznie zgodna z k.p.
   1:1)?
7. **Podświetlanie przekroczenia (sekcja 2.3)** — podświetlać tylko
   kolumnę "Razem" (podsumowanie), czy też np. nazwisko pracownika/cały
   wiersz? Czy próg to dokładnie ten sam `target_minutes`, którego
   pilnuje dziś generator (`nominal × wymiar_etatu − urlop − L4`), czy
   inny (np. zwykłe "176h" bez pomniejszania o urlopy)?
8. **Wydruk per pracownik (sekcja 6.2)** — pojedynczy plik na
   pracownika (N plików za jedno kliknięcie "eksportuj wszystkich"), czy
   wybór jednego pracownika naraz z listy? Czy potrzebny też per
   pracownik w Excelu, czy wystarczy JPG/wydruk?
9. **UI dla `availability` (per-dzień okno godzinowe, sekcja 4.4)** —
   to dziś jest "martwe" pole bez formularza. Czy przy okazji budowania
   checkboxów "które dni + ile godzin" (4.4) ma powstać to samo miejsce
   w UI, czy to strukturalnie osobny formularz od tego, co opisujesz w
   4.4 (bo jak ustaliliśmy w sekcji 4.4, dzisiejsze `availability` to
   inna koncepcja — "okno godzinowe", nie "limit godzin")?

---

## 9. Wstępny plan działania (tylko punkty jednoznaczne — kategoria A i proste C)

Nic z sekcji 4.2 ("nieokreślony"), 4.4 i 7 (24h/16h/12h) nie jest tu
ujęte — czeka na odpowiedzi z sekcji 8.

1. **Zbudować sam profil "Ochrona" przez kreator** (`ui/profile_wizard_dialog.py`)
   — role, brak `uses_trade_calendar`, brak reguł `min_staff_with_role`.
   Zero kodu, czysta konfiguracja w już istniejącym narzędziu.
2. **Skonfigurować limity godzinowe nowego profilu**: `standard_daily_hours = 8.0`,
   `force_fulltime_845 = False` w Konfiguracji tego projektu (sekcja 2.2).
   Zero kodu.
3. **Dodać "6/8" jako etykietę w `ui/employee_dialog.py:94-101`**
   (wartość `0.75`, już istniejąca pod etykietą "3/4") — kosmetyczna
   zmiana jednej listy.
4. **Odtworzyć `no_night`/`no_afternoon` jako role custom profilu**
   przez kreator, z regułą `role_time_restriction` (sekcja 4.3) — zero
   nowego kodu, tylko konfiguracja.
5. **Podświetlanie przekroczenia miesięcznego limitu (sekcja 2.3)** —
   jedyny kawałek kodu w tej liście, ale jednoznaczny (liczby już
   istnieją, brakuje tylko porównania + koloru):
   - nowa funkcja pomocnicza licząca `(przepracowane_minuty, limit_minuty, przekroczono: bool)`
     dla jednego pracownika (najbliżej `logic/schedule_presenter.py` albo
     nowy plik obok `model/constraints.py`),
   - podpięcie do kolumny "Razem" w `ui/grid_view.py::_fill_summary_cells`
     (kolor tła `theme.ERR_RED` przy przekroczeniu, wzorem istniejącego
     wzorca w `_fill_validation_rows`),
   - to samo porównanie w `export/image_exporter.py::_draw_employee`
     (kolumna "Razem") i `export/excel_exporter.py` (odpowiadająca
     komórka + `PatternFill` już zaimportowany).
   - Testy: nowy `tests/test_overtime_highlight.py` (nazwa przykładowa)
     analogiczny do istniejących testów prezentacji
     (`tests/test_location_presentation.py` jako wzorzec stylu testu UI-logiki).
6. **Wydruk per pracownik (sekcja 6.2)** — dodać opcjonalny parametr
   `employees: list[Employee] | None` do `export_schedule_to_image` i
   `export_schedule_to_excel` (domyślnie `None` = wszyscy, zero zmiany
   istniejącego zachowania), plus wpis w menu `ui/main_window.py` z
   wyborem pracownika. Mechaniczna zmiana, niska niepewność.

Punkty 5-6 warto zrobić po ustaleniu pytania 7/8 z sekcji 8 (żeby nie
przerabiać koloru/układu wydruku dwa razy), ale są **niezależne
technicznie** od pytań blokujących w sekcji 8 (1-4) — mogły ruszyć od
razu (i faktycznie ruszyły — patrz commity `e5dce9b`..`f512d17` na
`client-demo/enyo-ochrona`).

---

## 10. Ustalenia klienta (2026-09-16, cd.) — odpowiedzi na blokujące pytania z sekcji 8

Klient odpowiedział wprost na pytania blokujące 1-4 z sekcji 8, plus
dodał nowe wymagania spoza pierwotnej specyfikacji. Poniżej — co się
przez to rozstrzygnęło, i co mimo to nadal wymaga decyzji przed
ruszeniem z kodem generatora (sekcja 7 pozostaje w mocy jako ocena
skali, ta sekcja tylko aktualizuje stan wiedzy).

### Rozstrzygnięte

1. **Kształt pokrycia doby (pytania 1-2 z sekcji 8):** potwierdzone
   wprost — **dokładnie jedna osoba na zmianie na placówkę jednocześnie**,
   zmiany **nie zazębiają się** (koniec jednej = początek następnej, bez
   przerwy i bez nakładania), **zawsze pełne pokrycie 24/7** (żadnych
   dziur, nigdy "obiekt bez ochrony"). To dokładnie scenariusz opisany w
   sekcji 7 tego planu jako "inny kształt problemu niż obsada
   wielo-osobowa" — teraz potwierdzony, nie tylko podejrzewany.
2. **Opt-out z 24h w weekendy (pytanie 4 z sekcji 8, częściowo):**
   potwierdzone — część pracowników ma zamiast 24h w weekend robić 12h,
   **musimy to uszanować** (klient użył słowa "musimy" — MANDATORY, nie
   PREFERRED). Kto pokrywa drugie 12h takiego dnia — patrz pytania niżej,
   nierozstrzygnięte.
3. **Umowa vs brak umowy:** potwierdzone, że część pracowników nie ma
   umowy o pracę — to uzasadnia flagę `umowa` dodaną w commicie
   `f512d17` na `client-demo/enyo-ochrona` (zwykły checkbox bez efektu w
   generatorze). Klient **nie powiedział jeszcze**, jaki konkretnie
   wpływ na reguły ma brak umowy — patrz pytania niżej.
4. **Balans / nominalny czas pracy — WYŁĄCZONE, nie tylko miękkie:**
   nowa, jednoznaczna decyzja: **nie stosujemy w ogóle** constraintów
   `balance` i `monthly_hours` (dziś `base_specs.py`, wspólne dla
   każdego profilu custom, w tym demo "Ochrona") dla tego klienta. Cel
   generatora to wyłącznie pełne pokrycie miesiąca — nadgodziny (nawet
   rzędu kilkudziesięciu godzin/miesiąc na osobę) są oczekiwane i
   akceptowane, nie karane ani nie wygładzane. To **upraszcza** jeden
   wymiar problemu (brak potrzeby ważenia spread/balance penalty w
   `objective.py`), nawet jeśli inny wymiar (pokrycie 24/7 jedną osobą,
   zmiennej długości zmiany) jest istotnie trudniejszy niż cokolwiek w
   dzisiejszym generatorze.
5. **Podświetlanie nadgodzin — doprecyzowane:** zamiast (albo obok)
   czerwonego tła istniejącej kolumny "Praca" (`ui/grid_view.py`,
   wdrożone w commicie `4092e68`), klient chce **osobną kolumnę
   podsumowującą z liczbą nadgodzin**, obok kolumny "Razem". Drobne
   rozszerzenie już zbudowanej `logic/monthly_hours_status.py` (ma już
   `over_minutes`) + nowa kolumna w `ui/grid_view.py`/obu eksporterach -
   nie wymaga zmian w generatorze, tylko w warstwie prezentacji.
6. **Wiele placówek z osobną listą pracowników, przełączanych z menu:**
   nowe wymaganie spoza pierwotnej specyfikacji klienta z pierwszej tury.
   Dzisiejszy `LocationConfig`/`ShopConfig.locations` (Etap 3a-3d planu
   lokalizacji) to lokalizacje **w ramach jednego projektu**, ze
   **wspólną listą pracowników** (pracownik ma `location_key`, ale
   wszyscy pracownicy żyją w jednym `MonthSchedule`) i wspólnym profilem
   biznesowym. Klient chce placówek z **osobną listą pracowników** i
   **niecodziennie takimi samymi zasadami** — to nie pasuje 1:1 do
   dzisiejszego mechanizmu bez rozbudowy. Patrz pytanie 2 niżej — dwie
   różne drogi o bardzo różnym koszcie.

### Nadal otwarte — bez tego nie da się bezpiecznie ruszyć z rdzeniem generatora

1. **Dokładny wzór odpoczynku po zmianie 24h zależnego od liczby osób.**
   "Nie mniej niż 24h" to tylko dolna granica. Bez wzoru/tabeli
   (np. klasyczny system "doba za dobę": przy N osobach na rotacji
   odpoczynek = (N-1)×24h, czyli 3 osoby → 24h pracy/48h odpoczynku,
   4 osoby → 24h/72h) nie da się zakodować `rest_constraint` dla zmiany
   24h - a to jest **prawny, nie tylko produktowy** parametr (odpoczynek
   po dyżurze), więc zgadywanie go jest ryzykowne.
2. **Architektura "wielu placówek z osobną listą pracowników":** czy to
   ma być (A) **osobne pliki projektu** per placówka + nowe menu
   "Placówki" jako wygodne przełączanie między nimi (mały, bezpieczny
   zakres — każda placówka to dziś już w pełni wspierany, niezależny
   projekt/plik, nic nowego w modelu danych) czy (B) **rozszerzenie
   dzisiejszego `LocationConfig`** o własną listę pracowników w ramach
   JEDNEGO pliku projektu (duża przebudowa — dziś `MonthSchedule.employees`
   jest globalna dla całego projektu, nie per lokalizacja).
3. **Kto pokrywa drugie 12h dnia, gdy dana osoba robi tylko 12h zamiast
   24h w weekend?** Czy to zawsze inny, konkretny pracownik (para na
   dany weekend), czy generator ma to dobierać dowolnie z dostępnych?
   Wpływa na to, czy weekendowy "slot" ma zmienną granulację (raz 1 blok
   24h, raz 2 bloki 12h) zależną od tego, kto akurat go obsługuje.
4. **Realny wpływ braku umowy o pracę na reguły generatora** - inny
   limit/brak limitu godzin? Zwolnienie z regulacji odpoczynku (kodeks
   pracy dotyczy umowy o pracę, nie każdej formy współpracy)? Dziś to
   tylko checkbox bez znaczenia (`umowa` w profilu demo) - do
   sprecyzowania, zanim zacznie znaczyć cokolwiek w generatorze.
5. **Model reprezentacji zmiany w CP-SAT:** czy zamknięty katalog
   długości (24h / 16h / 12h / 8h jako nowe stałe typy zmian, podobnie do
   dzisiejszego `SHIFT_NIGHT`) wystarczy, czy potrzebna w pełni
   elastyczna godzina startu/końca (interval variables) - zależy wprost
   od odpowiedzi na pytanie 3 wyżej i od tego, czy weekday nadal ma być
   sztywne 16h (oryginalna specyfikacja klienta z pierwszej tury) czy to
   też się zmieniło.

Punkty A→G z "plan zmiany nocne (24-7).md" (SHIFT_NIGHT, jeden sztywny
blok na lokalizację) **nie są tu wystarczające** - to inny, prostszy
przypadek (patrz sekcja 7 wyżej) niż wielo-długościowa rotacja jedno-
osobowa z zależnym od obsady odpoczynkiem. Realnie to osobny,
porównywalny kalibrem etap pracy, nie rozszerzenie istniejącego.

---

## 11. Decyzje klienta na pytania z sekcji 10 (2026-09-16, cd.)

Cztery pytania blokujące z sekcji 10 - wszystkie rozstrzygnięte,
klient wybrał rekomendowaną opcję w każdym:

1. **Odpoczynek po zmianie 24h:** system "doba za dobę" -
   `odpoczynek = (N-1) × 24h`, gdzie N = liczba pracowników na rotacji
   tej placówki (3 osoby → 24h pracy / 48h odpoczynku, 4 osoby → 24h/72h).
   **Do doprecyzowania przy kodowaniu** (nie było osobnego pytania o to):
   czy N liczy WSZYSTKICH pracowników przypisanych do placówki, czy tylko
   tych zdolnych/chętnych robić 24h (bez flagi `nie_chce_24h`) - patrz
   Etap C niżej, przyjmuję na razie to drugie jako założenie robocze
   (bo to oni faktycznie rotują na zmianie 24h), do potwierdzenia.
2. **Wiele placówek:** osobne pliki projektu + nowe menu "Placówki" do
   szybkiego przełączania. Bez zmian w modelu danych - każdy plik
   projektu już dziś niesie własną listę pracowników i własny
   `ShopConfig` (w tym własny `business_type`/profil). Tylko UI: lista
   ostatnio używanych/zarejestrowanych plików projektu z jednym
   kliknięciem otwarcia.
3. **Drugie 12h weekendu:** generator dobiera dowolnego dostępnego
   pracownika, bez sztywnego parowania - upraszcza model (12h to
   "zwykły" typ zmiany jak każdy inny, bez dodatkowej logiki parowania).
4. **Model zmian w CP-SAT:** zamknięty katalog nowych, stałych typów
   zmian (analogicznie do `SHIFT_NIGHT`) zamiast interval variables.

## 12. Konkretna propozycja implementacji (do potwierdzenia przed Etapem A)

Na bazie decyzji z sekcji 11 i oryginalnej specyfikacji klienta z tury 1
("16h pon-pt, 12h lub 24h weekend") - **to jest propozycja do
zatwierdzenia/poprawienia, nie ustalony fakt**, bo część szczegółów
(dokładne godziny startowe, czy N w rotacji liczy tylko chętnych na 24h)
nie padła wprost w odpowiedziach klienta:

### Nowe typy zmian (per lokalizacja, analogicznie do `night_shift`)
- `SHIFT_16H` - długa zmiana dzienna w tygodniu (pon-pt), np. 06:00-22:00.
- `SHIFT_8H_NIGHT` - dopełnienie doby w tygodniu, np. 22:00-06:00.
- `SHIFT_24H` - pełna doba w weekend (sob-nd), np. 06:00-06:00 (+1).
- `SHIFT_12H_A` / `SHIFT_12H_B` - dwie połowy doby weekendowej, gdy nikt
  odpowiedni nie chce/nie może 24h, np. 06:00-18:00 / 18:00-06:00 (+1).

### Reguły pokrycia (nowy constraint, nie istnieje dziś w żadnej formie)
- Pon-pt: **dokładnie 1** pracownik na `SHIFT_16H` i **dokładnie 1** na
  `SHIFT_8H_NIGHT` każdego dnia (nie "co najmniej", jak dzisiejsze
  `min_staff_with_role` - tu nadmiar też byłby błędem, bo złamałby
  "dokładnie jedna osoba na zmianie").
- Sob-nd: **albo** dokładnie 1 pracownik na `SHIFT_24H` **albo** dokładnie
  po 1 na `SHIFT_12H_A` i `SHIFT_12H_B` - nigdy oba warianty naraz, nigdy
  żaden. (`use_24h[d]` jako pomocnicza zmienna 0/1 przełączająca między
  wariantami, podobnie do przełączników już używanych w innych miejscach
  generatora.)
- Pracownicy z flagą `nie_chce_24h` mają `x[e, d, SHIFT_24H] = 0` na
  twardo (brama, analogicznie do `add_night_shift_gate_constraint`) -
  nie ograniczenie miękkie, bo klient powiedział "musimy to uszanować".

### Odpoczynek (rozszerzenie/nowy constraint obok `rest_constraint.py`)
- Po `SHIFT_16H`: standardowe 11h (mieści się w dzisiejszym mechanizmie,
  po uogólnieniu go na zmienną długość zmiany).
- Po `SHIFT_24H`: `(N-1) × 24h`, N = pracownicy tej lokalizacji bez flagi
  `nie_chce_24h` (założenie robocze z sekcji 11 pkt 1 - do potwierdzenia).
- Po `SHIFT_12H_A`/`SHIFT_12H_B`: do ustalenia - domyślnie standardowe
  11h, chyba że klient chce inaczej (nie padło wprost).

### Balans / nominalne godziny
- `balance` i `monthly_hours` z `base_specs.py` - `ConstraintPolicy.DISABLED`
  dla tego profilu (konfiguracja `ShopConfig.constraint_policies`, nie
  zmiana kodu generatora).
- Nowa kolumna "Nadgodziny" w gridzie/eksportach obok "Razem" - rozszerzenie
  już zbudowanego `logic/monthly_hours_status.py` (ma `over_minutes`),
  czysto prezentacyjne, niezależne od reszty tego planu.

### Wiele placówek
- Nowe menu "Placówki" w `ui/main_window.py` - lista zapamiętanych ścieżek
  plików projektu (podobny mechanizm co dzisiejsze `last_project.json`,
  tylko lista zamiast jednego wpisu), każdy wpis otwiera dany plik przez
  istniejące `load_project`. Zero zmian w `model`/`logic`.

### Kolejność (Etapy, analogicznie do "plan zmiany nocne")
- **Etap A** - nowe stałe typy zmian + pola konfiguracji per lokalizacja
  (godziny `SHIFT_16H`/`SHIFT_8H_NIGHT`/`SHIFT_24H`/`SHIFT_12H_*`), bez
  wpięcia w generator. Bezpieczny start, izolowany.
- **Etap B** - reguła pokrycia (dokładnie 1 osoba/zmiana, przełącznik
  24h vs 12h+12h dla weekendu) + brama `nie_chce_24h`.
- **Etap C** - odpoczynek zależny od zmiany (11h dla 16h/12h, (N-1)×24h
  dla 24h) - najbardziej ryzykowny etap, prawny parametr.
- **Etap D** - wyłączenie `balance`/`monthly_hours` dla profilu, nowa
  kolumna nadgodzin w UI/eksportach.
- **Etap E** - menu "Placówki" (niezależne od A-D, może iść równolegle).
- **Etap F** - testy scenariuszowe (pełny miesiąc, kilka osób, sprawdzić
  brak dziur/nakładania i poprawność rotacji odpoczynku).

Rekomendacja: zacząć od Etapu A (fundament, zero ryzyka), potwierdzić
konkretne godziny startowe zmian i założenie o N w odpoczynku przed
Etapem C.

---

## 13. Stan wdrożenia (2026-09-16, cd.) — Etapy A, B, C zrobione

Branch: `claude/night-shift-generator-support-ex6pqc`. Klient potwierdził
kierunek ("tak, jedziemy") i założenie o N w odpoczynku (tylko pracownicy
bez `nie_chce_24h`). `pytest tests/` → **218 passed, zero regresji** po
każdym z trzech etapów. Nazwy w kodzie różnią się nieco od roboczych
nazw z sekcji 12 (`SHIFT_16H` → `SHIFT_DUTY_WEEKDAY_LONG` itd.) — sam
mechanizm jest identyczny z propozycją.

### Etap A — fundament danych (commit `3348695`)

- `model/day_schedule.py`: `DaySchedule.set_full_day_shift(start)` — nowe
  pole `is_full_day: bool`. `end == start` w `set_hours()` **nadal**
  pozostaje błędem (niejednoznaczne z pustym dniem) — zmiana 24h
  wymaga tego dedykowanego settera. `crosses_midnight()`/`total_duration()`
  rozumieją nową flagę; wszystkie pozostałe settery (`set_free`/
  `set_leave`/`set_sick`/`set_shift_class`/`set_hours`) ją czyszczą.
  Świadomie **nie dotknięte**: ok. 9 miejsc w `logic/`/`ui/`, które
  czyszczą `start`/`end` wprost bez przechodzenia przez te settery —
  bezpieczne, bo `crosses_midnight()`/`total_duration()` sprawdzają
  `is_empty()`/`start is not None` przed `is_full_day`.
- `model/location.py` / `model/shop_config.py`: `LocationConfig.duty_rotation`
  (+ ten sam mechanizm na `ShopConfig`, jak `night_shift`) — pięć okien:
  `weekday_long`/`weekday_short`/`weekend_full`/`weekend_half_a`/
  `weekend_half_b`. `normalize_duty_rotation()` wymaga albo wszystkich
  pięciu okien naraz, albo żadnego.
- Testy: `tests/test_full_day_shift.py` (8), `tests/test_duty_rotation.py` (15).

### Etap B — reguła pokrycia + brama w generatorze (commity `27a6dc0`, `1154e8b`)

- `logic/auto_generator.py`: pięć nowych stałych zmian
  (`SHIFT_DUTY_WEEKDAY_LONG/SHORT/WEEKEND_FULL/WEEKEND_HALF_A/B` = 15-19,
  słownik `DUTY_SHIFTS`), analogicznie do `SHIFT_NIGHT`.
- `logic/generator/duty_rotation_constraint.py` (nowy plik):
  - `add_duty_rotation_gate_constraint` (always_on) — duty-rotation i stary
    model zmian (OPEN/CLOSE/START/END/NIGHT) wzajemnie wyłączne per
    pracownik; **do tego dołączone** (po odkryciu luki) zablokowanie
    zmian dnia roboczego w weekend i odwrotnie — fakt kalendarzowy, nie
    preferencja.
  - `add_duty_rotation_coverage_constraint` (polityka `duty_rotation_coverage`,
    domyślnie MANDATORY) — dokładnie 1 osoba na `weekday_long`/
    `weekday_short` w dni robocze (grupowane per lokalizacja); w weekend
    zmienna `use_24h` przełącza między dokładnie-1-na-`weekend_full` a
    dokładnie-po-1-na-obu-połówkach, nigdy mix.
  - `add_duty_rotation_no24h_gate_constraint` (polityka `duty_rotation_no24h`,
    domyślnie MANDATORY) — `nie_chce_24h` blokuje `weekend_full` na twardo.
- `model/shop_config.py`: obie nowe polityki wpięte w domyślny
  `constraint_policies` (MANDATORY) dla **każdego** profilu (w tym Dino) —
  no-opy dopóki żadna lokalizacja nie ma `duty_rotation`, więc zero
  zmiany zachowania istniejących projektów. Świadomie **nie dodane** do
  `GENERIC_POLICY_LABELS` (pokazywałyby się w "Zasadach generatora"
  KAŻDEGO profilu, myląc UI Dino czymś nieistotnym) — ekran do edycji
  tych dwóch polityk to zadanie Etapu D/E, dziś edytowalne tylko
  programowo.
- **Dwa realne bugi znalezione i naprawione po drodze** (nie zgadywane —
  wykryte przez testy end-to-end, ta sama kategoria pułapki co przy
  SHIFT_NIGHT: kod, który iteruje `all_shifts` z założeniem "każda
  nienazwana zmiana to zwykła zmiana"):
  - `logic/generator/availability_constraint.py` — dostępność blokowałaby
    zmiany rotacji każdemu pracownikowi z jakimikolwiek ograniczeniami
    dostępności (nieaktualne dziś w praktyce, bo `availability` i tak nie
    ma UI, ale realny bug w kodzie).
  - `logic/generator/constraints_logic.py::add_work_dependency_constraint` —
    **to faktycznie blokowało pierwszy test end-to-end** (natychmiastowy
    INFEASIBLE, 0 konfliktów solvera): wymuszało `x[e,d,s] <= 0` na każdej
    zmianie rotacji dla lokalizacji bez obsady OPEN/CLOSE, wprost
    sprzeczne z "dokładnie 1 osoba" z coverage constraint.
  - Przy okazji: `logic/generator/hours_constraint.py::_shift_minutes_by_type`
    przebudowane z dwóch pozycyjnych argumentów na słownik `overrides` (bo
    inaczej monthly_hours/balance liczyłyby zmiany rotacji jako standardowe
    8h zamiast ich realnego czasu trwania) — zaktualizowane wszystkie 3
    wywołania (`hours_constraint.py`, `logic/generator/fix.py`, testy).
- Testy: `tests/test_duty_rotation_constraint.py` (13, w tym pełny
  end-to-end `AutoScheduleGenerator.generate()`).

### Etap C — odpoczynek "doba za dobę" (commit `968a6a3`)

- `logic/generator/duty_rotation_rest_constraint.py` (nowy plik),
  dołączony do polityki `rest_11h` (ta sama, nie osobna — koncepcyjnie to
  wciąż jedna zasada odpoczynku, tylko rozszerzona). Standardowe 11h dla
  czterech "zwykłych" zmian rotacji, `(N-1)×24h` dla `weekend_full`
  (N = pracownicy lokalizacji bez `nie_chce_24h`, potwierdzone przez
  klienta), dolna granica 24h przy N≤1.
- **Różnica względem `night_shift_adjacency_constraint`**: tamto sprawdza
  tylko dzień d wobec d+1 (11h/19h zawsze mieści się w jednej dobie
  różnicy). `(N-1)×24h` przy N≥3 przekracza 24h — samo "jutro" by nie
  wystarczyło. Dodane sprawdzanie d wobec każdego późniejszego dnia w
  ograniczonym oknie (`lookahead = wymagane_godziny/24 + 2`), z wczesnym
  przerwaniem, gdy najwcześniejsza zmiana danego dnia już mieści wymagany
  odpoczynek.
- Testy: `tests/test_duty_rotation_rest_constraint.py` (10) — w tym
  dokładna granica 48h dla N=3 (poniedziałek wciąż za wcześnie, wtorek
  dokładnie na granicy już dozwolony) i potwierdzenie, że pracownik z
  `nie_chce_24h` nie liczy się do N.

### Zostało z sekcji 12 (nietknięte)

- **Etap D** — `ConstraintPolicy.DISABLED` dla `balance`/`monthly_hours`
  na realnym projekcie klienta (konfiguracja, nie kod) + nowa kolumna
  "Nadgodziny" w gridzie/eksportach obok "Razem" (rozszerzenie
  `logic/monthly_hours_status.py`, ma już `over_minutes`).
- **Etap E** — menu "Placówki" w `ui/main_window.py` (osobne pliki
  projektu + lista do szybkiego przełączania). Wymaga jednej drobnej
  decyzji: gdzie trzymać listę znanych plików (proponowane:
  `%LOCALAPPDATA%\GrafikDino\known_projects.json`, ten sam katalog co
  `custom_profiles.json`).
- **Etap F** — testy scenariuszowe pełnego miesiąca/kilku lokalizacji
  naraz (dziś pokryte tylko pojedynczymi tygodniami/wycinkami w testach
  jednostkowych Etapów B/C, nie pełnym miesiącem end-to-end).

### Świadomie poza zakresem A-C (udokumentowane, nie przeoczone)

- Ręczna edycja / rozpoznawanie zablokowanych komórek w trybie "Napraw
  grafik" dla pięciu nowych zmian (`logic/generator/manual_constraint.py`,
  `logic/generator/fix.py`) — dziś nie ma nawet UI do ręcznego ustawienia
  tych zmian, więc nieosiągalne w praktyce; zostawione dla przyszłego
  etapu UI.
- Wiele placówek **w ramach jednego pliku projektu** z osobną listą
  pracowników (opcja B z pytania w sekcji 10) — klient wybrał opcję A
  (osobne pliki), więc `LocationConfig` nadal ma jedną, wspólną listę
  pracowników per projekt; `duty_rotation` per lokalizacja działa już
  dziś poprawnie dla tego przypadku (grupowanie po `location_key` w
  `duty_rotation_constraint.py`), gdyby jednak opcja B była kiedyś
  potrzebna.

---

## 14. Stan wdrożenia, cd. (2026-09-16, cd.) — Etapy D, E, F zrobione

Na prośbę: `client-demo/enyo-ochrona` scalone do tego brancha (commit
`22271bc`) — jedno miejsce pracy zamiast dwóch, `CLIENT_DEMO_README.md`
zaktualizowany (`40ebed6`) żeby to odzwierciedlić. Dalej: Etapy D/E/F z
sekcji 12 dokończone. `pytest tests/` → **244 passed, zero regresji**.

### Etap D — kolumna "Nadgodziny" + wyłączenie balance/monthly_hours (commity `ccab109`, `7092cc2`)

- `ui/grid_view.py` — nowa kolumna "Nadgodziny\n(h)" zaraz po "Razem\n(h)"
  (kolumna "Cel" trybu rozliczeniowego przesunięta o jeden indeks).
  Istniejące czerwone tło kolumny "Praca" **zostaje** — oba mechanizmy
  współistnieją.
- `export/excel_exporter.py`/`export/image_exporter.py` — ta sama
  kolumna w obu eksportach.
- `demo/install_demo.py` — **przepisany, żeby faktycznie używać
  `duty_rotation` z Etapów A-C** zamiast starszego przybliżenia przez
  `night_shift` (16h+8h w tygodniu, 24h/12h+12h w weekend, dokładnie
  jak w oryginalnej specyfikacji klienta). `balance`/`monthly_hours` →
  `DISABLED`. Załoga zmniejszona do 4 osób (celowo skromna, jak klient
  opisał: "braki zatrudnienia... duża ilość nadgodzin") — zweryfikowane
  po wygenerowaniu: dwie osoby po 24h nadgodzin, jedna 4h, jedna
  niedociążona (140h) - naturalny wynik braku balansu, nie ręcznie
  dogrywana zmiana jak w poprzedniej wersji demo.
- Testy: `tests/test_overtime_column.py` (3 - grid, Excel, JPG).

### Etap E — menu "Placówki" (commit `84c6782`)

- `persistence/known_projects_store.py` (nowy plik) — lista
  zapamiętanych ścieżek plików projektu w
  `%LOCALAPPDATA%\GrafikDino\known_projects.json`, most-recently-used
  first.
- `ui/main_window.py` — nowe menu "Placówki" w pasku menu, budowane na
  nowo przy każdym otwarciu (`aboutToShow`). Zapis/wczytanie projektu
  rejestruje ścieżkę pod nazwą z `ShopConfig.name` (albo nazwą pliku).
  Brakujący plik usuwa się z listy zamiast cicho failować.
- Testy: `tests/test_known_projects_store.py` (7).

### Etap F — testy scenariuszowe pełnego miesiąca (commit `5f1b6c4`)

- `tests/test_duty_rotation_scenario.py` — generuje **cały miesiąc**
  (nie wycinek) i weryfikuje wynik **niezależnie od kodu constraintów**
  (licząc rzeczywiste godziny wprost z zapisanego `DaySchedule`, nie
  przez ponowne wywołanie tych samych funkcji budujących model CP-SAT).
  Trzy scenariusze: 4 osoby/1 `nie_chce_24h` (jak załoga demo), 3
  osoby/0 `nie_chce_24h` (najbardziej wymagający - N=3 daje 48h
  odpoczynku po każdej z wielu zmian 24h w miesiącu, test wielodniowego
  "lookahead" z Etapu C), 5 osób/2 `nie_chce_24h`. Wszystkie feasible,
  solver <1.5s łącznie.

### Domknięte tym samym — rdzeń generatora rotacji 24/7 gotowy end-to-end

Etapy A→F z sekcji 12 tego planu są kompletne. To, co zostaje poza
zakresem, jest wymienione wyżej w sekcji "Świadomie poza zakresem A-C"
(ręczna edycja/UI dla nowych typów zmian, multi-placówka w ramach
jednego pliku) — żadne z nich nie blokuje realnego użycia przez klienta
z dzisiejszym kształtem (osobne pliki per placówka, generowanie
automatyczne, bez ręcznej edycji zmian rotacji).
