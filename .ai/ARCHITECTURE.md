# Architektura

UI

↓

Controller

↓

Generator

↓

Models

↓

Persistence

UI nie powinno zawierać logiki biznesowej.

Generator nie powinien zależeć od UI.

Modele powinny być możliwie proste.

Przed proponowaniem zmian architektury zawsze oceń czy są one rzeczywiście potrzebne.

## Kwalifikacje pracowników

Role, umiejętności i uprawnienia pracowników to kwalifikacje
(`model/qualification.py`):

- `Qualification` - pozycja katalogu projektu (`MonthlyProject.qualifications`,
  Plik -> "Kwalifikacje"): nazwa, kod, ikona, rodzaj, opcjonalne poziomy,
  czy wymaga daty ważności. Katalog uzupełnia się o kwalifikacje profilu
  (`business_profile.default_qualifications`), nigdy nie nadpisując edycji.
- `EmployeeQualification` - przypisanie w `Employee.qualifications`: poziom,
  daty ważności (włącznie), placówki (puste = wszystkie).

Generator, walidacja siatki i diagnostyka pytają zawsze o konkretny dzień
(`has_on`, `level_on`, `is_opener_on`...). Widoki całego miesiąca (ikony,
"Flagi") używają `qualification_marks`. Dino: "otwarcie", "mieso" (1 =
pomocniczo, 2 = pełna obsługa), "kierownik"; Ochrona: "umowa",
"nie_chce_24h". `no_night`/`no_afternoon` są osobnymi polami `Employee`.

Reguła profilu custom "min. N osób z kwalifikacją X na poziomie >= L"
(otwarcie / zamknięcie / cały dzień / noc / okno godzin) ma jedną definicję
w `model/staffing_rules.py`: generator (`generic_rules.py`) buduje z niej
ograniczenia CP-SAT, walidacja siatki (`model/constraints.py::CustomStaffRule`)
sprawdza nią gotowy grafik. Test zgodności: tests/test_staffing_rules_grid.py.

Stare pliki (pola `is_opener`/`is_meat`/`is_meat_light`/`is_manager`/
`custom_roles`) migrują przy wczytaniu (`qualifications_from_legacy`);
przed pierwszym zapisem w nowym formacie powstaje kopia `<plik>.bak`.
