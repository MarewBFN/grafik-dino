# DinGO AI Instructions

## Cel

Pomagaj rozwijać aplikację DinGO.

Priorytetem jest czytelny kod i stabilny generator grafików.

## Zasady

- Nie zmieniaj architektury projektu.
- Nie twórz nowych folderów bez mojej zgody.
- Nie twórz nowych plików, jeśli wystarczy zmodyfikować istniejące.
- Nie przenoś kodu pomiędzy plikami bez uzasadnienia.
- Nie dodawaj nowych bibliotek bez mojej zgody.
- Nie twórz środowiska .venv ani nie zmieniaj sposobu uruchamiania projektu.
- Preferuj prostsze rozwiązania zamiast nadmiernej abstrakcji.
- Pracuj na branchu `integration/enyo-only` (lokalnie i na origin) - to jedyny roboczy branch obok `main`. Nie twórz nowych branchy (w tym branchy sesji/agenta) bez wyraźnej potrzeby i mojej zgody. Jeśli już jakiś powstanie (np. wymuszony przez środowisko pracy), scal go do `integration/enyo-only` i usuń najszybciej jak to możliwe, zamiast zostawiać go wiszący.

## Styl pracy

Przed rozpoczęciem zmian:

1. Krótko opisz plan.
2. Określ które pliki zamierzasz zmienić.
3. Wykonaj zmiany.
4. Uruchom odpowiednie testy.
5. Podsumuj co zostało zmienione.

## Generator

Generator jest najważniejszą częścią projektu.

Nie zmieniaj kilku constraintów jednocześnie, jeśli nie jest to konieczne.

Jeżeli zmieniasz constraint:

- wyjaśnij dlaczego,
- napisz lub popraw test,
- uruchom test,
- opisz wpływ na generator.

## Jeżeli czegoś nie jesteś pewien

Najpierw zapytaj.