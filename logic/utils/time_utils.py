from datetime import timedelta

# Przeniesione do model/location.py (żeby model/ nie zaczęło importować z
# logic/) - re-eksportowane tutaj, żeby istniejące importy w logic/generator/*
# i testach zostały bez zmian.
from model.location import (  # noqa: F401
    daily_subintervals,
    daily_windows_overlap,
    hour_window_overlaps_time_range,
)


def get_effective_daily_hours(emp, shop):
    # 🔴 specjalny fulltime max 8h
    if emp.employment_fraction == 1.01:
        hours = 8.0

    # 🔴 normalny fulltime z wymuszeniem 8:30
    elif shop.constraints.get("force_fulltime_845", False) and emp.employment_fraction == 1.0:
        hours = 8.50

    else:
        hours = shop.standard_daily_hours * emp.employment_fraction

    minutes = int(hours * 60)
    minutes = (minutes // 15) * 15

    return minutes / 60


def is_next_calendar_month(old_year: int, old_month: int, new_year: int, new_month: int) -> bool:
    """Czy (new_year, new_month) to dokładnie jeden miesiąc kalendarzowy po
    (old_year, old_month) - używane przy przejmowaniu "pamięci poprzedniego
    miesiąca" (patrz ui/main_window.py::_save_date_clicked): skok o więcej
    niż jeden miesiąc (albo wstecz) czyni koniec ostatniej zmiany starego
    grafiku nieaktualnym (między miesiącami był z pewnością pełny
    odpoczynek), więc nie ma sensu go przejmować."""
    return old_year * 12 + old_month + 1 == new_year * 12 + new_month


MONTH_NAMES_PL = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]


def format_month_label(year: int, month: int, *, capitalize: bool = True) -> str:
    """"Styczeń 2026" (albo "styczeń 2026" z capitalize=False, do wstawienia
    w środku zdania) - współdzielone przez ui/month_picker_dialog.py i
    notatki o zasięgu zmian konfiguracji/lokalizacji/pracowników w
    ui/config_dialog.py, ui/locations_dialog.py, ui/employee_dialog.py."""
    name = MONTH_NAMES_PL[month - 1]
    if capitalize:
        name = name.capitalize()
    return f"{name} {year}"


def month_scope_note(year: int, month: int) -> str:
    """Tekst wyjaśniający zasięg zmian wprowadzanych w oknach Konfiguracja/
    Lokalizacje/Pracownik - pamięć wielu miesięcy (model/monthly_project.py)
    sprawia, że każdy miesiąc ma własny, niezależny ShopConfig/MonthSchedule,
    więc te okna zawsze edytują TYLKO jeden, konkretny miesiąc (plus
    dziedziczą go miesiące utworzone od teraz - patrz ui/main_window.py::
    _switch_to_month). Świadoma decyzja (2026-09-21): zmiana NIE propaguje
    się automatycznie do już istniejących, późniejszych miesięcy, żeby nic
    nie zmieniało się po cichu w miesiącu, który mógł już zostać
    sprawdzony/wygenerowany - stąd ta notka, żeby klient wiedział, czego się
    spodziewać, zamiast się tego domyślać."""
    return (
        f"Zmiany w tym oknie dotyczą tylko miesiąca {format_month_label(year, month, capitalize=False)} "
        "i miesięcy utworzonych od teraz. Wcześniejsze miesiące oraz już "
        "istniejące późniejsze miesiące zachowują swoje dotychczasowe ustawienia."
    )


def previous_calendar_month(year: int, month: int) -> tuple[int, int]:
    """(year, month) kalendarzowo bezpośrednio poprzedzający podany miesiąc,
    z przeniesieniem roku wstecz na granicy stycznia. Używane przez pamięć
    wielu miesięcy (model/monthly_project.py) do ustalenia, KTÓRY zapamiętany
    miesiąc jest właściwym źródłem "pamięci poprzedniego miesiąca" dla
    nowo tworzonego miesiąca - niezależnie od tego, który miesiąc był
    aktualnie otwarty w chwili przełączenia (patrz ui/main_window.py::
    _switch_to_month, swobodna nawigacja między miesiącami)."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def fraction_hour(time_str: str) -> str:
    """Sama godzina (bez zera wiodącego) dla trybu wyświetlania "Ułamki"
    (menu Wygląd -> "Widok trybu szybkiego") - np. "08:00" -> "8". Niepełne
    godziny (minuty != 00) są na razie tylko prosto zaokrąglane do
    najbliższej pełnej godziny (np. "8:30" -> "9") - dokładniejszy zapis
    ułamków godziny to świadomie odłożone rozszerzenie. Współdzielone przez
    logic/schedule_presenter.py (widok rozszerzony) i ui/grid_view.py
    (widok kompaktowy - patrz komentarz w _fill_day_cells), żeby oba
    widoki zaokrąglały identycznie."""
    h, m = time_str.split(":")
    hour = int(h)
    if int(m) >= 30:
        hour = (hour + 1) % 24
    return str(hour)


def format_hours_as_fraction(start: str, end: str) -> str:
    """Godzina początku nad godziną końca (jedna cyfra pod drugą, nie obok
    siebie), żeby zmieściło się w wąskiej komórce siatki grafiku - np.
    "08:00"/"20:00" -> "8\\n20"."""
    return f"{fraction_hour(start)}\n{fraction_hour(end)}"


def classify_shift_as_morning_or_afternoon(shift_start, shift_end, shop_open_dt, shop_close_dt):
    """Classify a shift based on the actual shop opening/closing window.

    The previous logic used a fixed noon-like assumption and misclassified
    special days such as 10:00-18:00 or 05:30-22:45. We now compare the
    midpoint of the assigned shift to the midpoint of the shop's operating
    window so that the split is based on real opening/closing hours.
    """

    if not shop_open_dt or not shop_close_dt:
        return None

    if shift_start is None or shift_end is None:
        return None

    if shift_end <= shift_start:
        return "morning"

    window = shop_close_dt - shop_open_dt
    if window <= timedelta(0):
        return "morning"

    shop_midpoint = shop_open_dt + (window / 2)
    shift_midpoint = shift_start + ((shift_end - shift_start) / 2)

    return "morning" if shift_midpoint <= shop_midpoint else "afternoon"