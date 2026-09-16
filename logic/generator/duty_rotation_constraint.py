"""Rotacja służby 24/7 (np. ochrona) - "plan profil ochrona (analiza
specyfikacji klienta).md", sekcja 12, Etap B.

Pięć nowych typów zmian (patrz AutoScheduleGenerator/LocationConfig.duty_rotation):

- weekday_long / weekday_short: dwie zmiany pokrywające razem całą dobę w
  tygodniu (pon-pt), dokładnie 1 osoba na każdej.
- weekend_full: sztywna zmiana 24h w weekend (sob-nd), dokładnie 1 osoba.
- weekend_half_a / weekend_half_b: dwuosobowa alternatywa dla weekend_full,
  gdy nikt odpowiedni nie chce/może 24h - też razem cała doba.

Trzy constrainty:

- add_duty_rotation_gate_constraint: strukturalny fakt (jak
  night_shift_gate) - lokalizacja albo używa WYŁĄCZNIE tych pięciu typów
  zmian (stary model OPEN/CLOSE/START/END/NIGHT jej nie dotyczy), albo nie
  używa ich wcale. Zawsze twardy, poza systemem polityk.
- add_duty_rotation_no24h_gate_constraint: pracownicy z flagą
  "nie_chce_24h" nie dostają weekend_full - to reguła biznesowa
  ("musimy to uszanować" - klient), więc idzie przez system polityk
  (domyślnie MANDATORY), nie always_on.
- add_duty_rotation_coverage_constraint: dokładnie 1 osoba na
  weekday_long/weekday_short każdego dnia roboczego; w weekend albo
  dokładnie 1 na weekend_full, albo dokładnie po 1 na obu połówkach -
  nigdy inna kombinacja. Też przez system polityk (domyślnie MANDATORY -
  klient: "ZAWSZE musi być pokrycie 24/7").

Grupowanie: rotacja jest per lokalizacja (klient: multi-placówka to
osobne pliki projektu, ale w ramach jednego pliku nadal może być kilka
LocationConfig z osobnymi duty_rotation) - pracownicy bez przypisanej
lokalizacji dzielą jedną grupę opartą o ShopConfig.duty_rotation.
"""

from logic.generator.night_shift_constraint import night_shift_duration_minutes

DUTY_ROTATION_KEYS = ("weekday_long", "weekday_short", "weekend_full", "weekend_half_a", "weekend_half_b")

FULL_DAY_MINUTES = 24 * 60


def duty_rotation_minutes_for_employee(shop, employee, duty_shifts) -> dict:
    """{shift_id: minuty} dla każdej z pięciu zmian rotacji 24/7, wg
    konfiguracji lokalizacji tego pracownika - pusty dict gdy lokalizacja
    nie ma duty_rotation (spójne z night_shift_minutes_for_employee, które
    i tak nie pozwoli ich przydzielić - patrz add_duty_rotation_gate_constraint)."""
    rotation = shop.get_location(employee).get_duty_rotation()
    if not rotation:
        return {}

    minutes = {}
    for key, shift_id in duty_shifts.items():
        if key == "weekend_full":
            minutes[shift_id] = FULL_DAY_MINUTES
        else:
            window = rotation[key]
            minutes[shift_id] = night_shift_duration_minutes((window["start"], window["end"]))
    return minutes


def _group_employees_with_duty_rotation(employees, shop) -> dict:
    """{location_key: (duty_rotation_dict, [employee_indices])} - tylko dla
    pracowników, których lokalizacja faktycznie ma skonfigurowaną rotację.
    Reużywane przez duty_rotation_rest_constraint.py (Etap C)."""
    groups: dict[str, tuple[dict, list[int]]] = {}
    for e, emp in enumerate(employees):
        rotation = shop.get_location(emp).get_duty_rotation()
        if not rotation:
            continue
        key = emp.location_key or ""
        if key not in groups:
            groups[key] = (rotation, [])
        groups[key][1].append(e)
    return groups


_WEEKDAY_KEYS = ("weekday_long", "weekday_short")
_WEEKEND_KEYS = ("weekend_full", "weekend_half_a", "weekend_half_b")


def add_duty_rotation_gate_constraint(model, x, employees, days, shop, duty_shifts, all_shifts, trace=None):
    if trace is not None:
        trace.log_constraint(
            "duty_rotation_gate",
            "duty-rotation shift types and the old OPEN/CLOSE/START/END/NIGHT model are mutually exclusive per "
            "employee, and weekday/weekend duty shift types can't be assigned on the wrong kind of day",
        )

    duty_shift_ids = set(duty_shifts.values())
    other_shift_ids = [s for s in all_shifts if s not in duty_shift_ids]
    weekday_ids = {duty_shifts[k] for k in _WEEKDAY_KEYS}
    weekend_ids = {duty_shifts[k] for k in _WEEKEND_KEYS}

    for e, emp in enumerate(employees):
        has_rotation = bool(shop.get_location(emp).get_duty_rotation())

        for d in days:
            if not has_rotation:
                for s in duty_shift_ids:
                    model.Add(x[e, d, s] == 0)
                continue

            for s in other_shift_ids:
                model.Add(x[e, d, s] == 0)

            # Zmiany dnia roboczego nie istnieją w weekend i odwrotnie - to
            # fakt strukturalny (kalendarzowy), nie preferencja biznesowa.
            wrong_kind = weekend_ids if shop.weekday(d) < 5 else weekday_ids
            for s in wrong_kind:
                model.Add(x[e, d, s] == 0)


def add_duty_rotation_no24h_gate_constraint(model, x, employees, days, duty_shifts, soft=False, trace=None):
    if trace is not None:
        trace.log_constraint("duty_rotation_no24h", f"soft={soft}")

    violations = []
    weekend_full = duty_shifts["weekend_full"]

    for e, emp in enumerate(employees):
        if not emp.custom_roles.get("nie_chce_24h", False):
            continue
        for d in days:
            if soft:
                v = model.NewBoolVar(f"duty_no24h_violation_e{e}_d{d}")
                model.Add(x[e, d, weekend_full] <= v)
                violations.append(v)
            else:
                model.Add(x[e, d, weekend_full] == 0)

    return violations


def add_duty_rotation_coverage_constraint(model, x, employees, days, shop, duty_shifts, soft=False, trace=None):
    if trace is not None:
        trace.log_constraint("duty_rotation_coverage", f"soft={soft}")

    violations = []
    groups = _group_employees_with_duty_rotation(employees, shop)

    weekday_long = duty_shifts["weekday_long"]
    weekday_short = duty_shifts["weekday_short"]
    weekend_full = duty_shifts["weekend_full"]
    weekend_half_a = duty_shifts["weekend_half_a"]
    weekend_half_b = duty_shifts["weekend_half_b"]

    def _exactly(count, target, max_count, label):
        """count == target (hard), albo |count - target| jako kara miękka."""
        if not soft:
            model.Add(count == target)
            return
        under = model.NewIntVar(0, max_count, f"{label}_under")
        over = model.NewIntVar(0, max_count, f"{label}_over")
        model.Add(count + under - over == target)
        violations.extend([under, over])

    for location_key, (_, indices) in groups.items():
        max_count = max(len(indices), 1)

        for d in days:
            wd = shop.weekday(d)

            if wd < 5:
                _exactly(
                    sum(x[e, d, weekday_long] for e in indices), 1, max_count,
                    f"duty_weekday_long_{location_key}_d{d}",
                )
                _exactly(
                    sum(x[e, d, weekday_short] for e in indices), 1, max_count,
                    f"duty_weekday_short_{location_key}_d{d}",
                )
                continue

            # Weekend: albo dokładnie 1 osoba na całej dobie (weekend_full),
            # albo dokładnie po 1 na każdej połówce - nigdy oba naraz, nigdy
            # żaden z wariantów. use_24h koduje, który wariant wybrano.
            use_24h = model.NewBoolVar(f"duty_use_24h_{location_key}_d{d}")

            full_count = sum(x[e, d, weekend_full] for e in indices)
            half_a_count = sum(x[e, d, weekend_half_a] for e in indices)
            half_b_count = sum(x[e, d, weekend_half_b] for e in indices)

            if not soft:
                model.Add(full_count == use_24h)
                model.Add(half_a_count == 1 - use_24h)
                model.Add(half_b_count == 1 - use_24h)
            else:
                _exactly(full_count, use_24h, max_count, f"duty_full_{location_key}_d{d}")
                _exactly(half_a_count, 1 - use_24h, max_count, f"duty_half_a_{location_key}_d{d}")
                _exactly(half_b_count, 1 - use_24h, max_count, f"duty_half_b_{location_key}_d{d}")

    return violations
