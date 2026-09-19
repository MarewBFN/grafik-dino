"""Miękka preferencja: gdy dzień dopuszcza wybór między jedną osobą na 24h
(weekend_full) a dwiema po 12h (weekend_half_a+half_b) -
add_duty_rotation_coverage_constraint (duty_rotation_constraint.py) już
dopuszcza oba jako równoważne, twardo wymagane pokrycie - ten moduł dokłada
karę za KAŻDE przypisanie do weekend_full, żeby solver przy realnym
wyborze wolał podział 12h+12h. Klient: "najczęściej po prostu dają dwóch
pracowników po 12h i my też będziemy chcieli do tego zachęcić generator".

Wyłącznie term celu (nie nowy ConstraintSpec/polityka) - weekend_full
zostaje w pełni dostępne i wybierane, gdy podział nie jest możliwy (np. za
mało osób dostępnych/chętnych na 12h tego dnia) - kara tylko *zniechęca*,
nigdy nie blokuje, więc nie może zrobić modelu niewykonalnym.
"""

from logic.generator.duty_rotation_constraint import group_employees_with_duty_rotation

# Wyraźnie mniejsze niż PRIORITY_WEIGHT (Umowa) czy generyczne wagi typu
# rest_11h - to ma nudge'ować wybór, nie przebijać żadnego realnego
# priorytetu (bilansu godzin, unikania nadgodzin itd.).
PREFER_SPLIT_WEIGHT = 5


def add_prefer_weekend_split_over_full_penalty(model, x, employees, days, shop, duty_shifts):
    penalties = []
    groups = group_employees_with_duty_rotation(employees, shop)
    weekend_full = duty_shifts["weekend_full"]

    for _, (rotation, indices) in groups.items():
        for d in days:
            wd = shop.weekday(d)
            # Te same dni, dla których add_duty_rotation_coverage_constraint
            # w ogóle stosuje wybór full-albo-half+half (weekend, albo
            # KAŻDY dzień przy only_12_24h) - w tygodniu bez only_12_24h
            # weekend_full nie jest tego dnia w ogóle osiągalne (patrz
            # add_duty_rotation_gate_constraint), więc kara byłaby pustym
            # no-opem, ale pomijamy jawnie zamiast polegać na tym.
            if wd < 5 and not rotation.get("only_12_24h"):
                continue
            penalties.extend(x[e, d, weekend_full] for e in indices)

    return [PREFER_SPLIT_WEIGHT * p for p in penalties]
