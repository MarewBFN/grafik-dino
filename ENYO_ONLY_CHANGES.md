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

## Znane kandydaci do przeglądu (jeszcze nietknięte)

Lista z analizy przed rozpoczęciem cięcia - do przejścia po kolei, nie
jeszcze zrobione:

- `is_dino_style()` / `business_type ==` - dispatch w ~12 miejscach
  (`export/export_style.py`, `export/image_exporter.py`,
  `export/security_image_exporter.py`, `export/excel_exporter.py`,
  `export/security_excel_exporter.py`, `ui/config_dialog.py`,
  `model/business_profile.py` i inne).
- `demo/install_demo.py` - używa starszego mechanizmu `night_shift`
  zamiast nowego `duty_rotation` (Etapy A-C z "plan profil ochrona...md").
- Branding "Dino"/"sklep" - nazwa aplikacji, ikony (`dingo_icon.ico`),
  installer (`dla inno.iss`), tytuły okien, README.
- `ui/business_profile_picker.py`, `ui/profile_wizard_dialog.py`,
  `ui/new_project_dialog.py` - czy klient w ogóle widzi wybór/kreator
  profilu, czy projekt startuje od razu jako Ochrona.
- Role/pola Dino-specyficzne w `model/employee.py` (`is_opener`,
  `is_meat`, `is_meat_light`, `is_manager`, `no_night`, `no_afternoon`).
