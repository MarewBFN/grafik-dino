# Praca dla klienta: Enyo (ochrona) — stan bieżący

Ten branch (`claude/night-shift-generator-support-ex6pqc`) to **jedyne,
bieżące miejsce pracy** nad profilem dla klienta z firmy ochroniarskiej
(Michał, Enyo). Wcześniej istniał osobny, wydzielony branch demo
(`client-demo/enyo-ochrona`, wyłącznie kosmetyka/dane) obok tego brancha
(rdzeń generatora) — na prośbę scalone tutaj 2026-09-16, żeby dalsza
praca (Etapy D/E/F i kolejne) toczyła się w jednym miejscu, nie dwóch
rozjeżdżających się liniach.

Pełny, szczegółowy log decyzji i etapów: **`plan profil ochrona (analiza
specyfikacji klienta).md`** w katalogu głównym repo — ten plik to tylko
szybkie streszczenie i instrukcja odpalenia demo.

## Co tu jest (stan na 2026-09-16)

Rdzeń generatora rotacji 24/7 (etapy z sekcji 12 planu):

- **Etap A** — `DaySchedule.set_full_day_shift()` (prawdziwa zmiana 24h)
  + `LocationConfig.duty_rotation` (5 skonfigurowanych okien czasowych).
- **Etap B** — reguła pokrycia w CP-SAT: dokładnie 1 osoba na zmianę,
  przełącznik 24h-albo-12h+12h w weekend, twarda brama "nie chce 24h".
- **Etap C** — odpoczynek "doba za dobę" `(N-1)×24h` po zmianie 24h.

Warstwa demo/prezentacyjna (z dawnego brancha `client-demo/enyo-ochrona`):

- Profil biznesowy "Ochrona" (custom profile) z dwiema flagami-checkboxami
  "Umowa"/"Nie chce 24h" (dziś czyste dane, bez efektu w generatorze -
  patrz plan, sekcja "Świadomie poza zakresem").
- Podświetlanie na czerwono przekroczenia miesięcznego limitu godzin
  pełnoetatowych (`logic/monthly_hours_status.py`) — w gridzie i w obu
  eksporterach (JPG, Excel).
- Wydruk/eksport dla pojedynczego pracownika (JPG i Excel).
- Kosmetyczne zmiany w UI, żeby żaden ekran nie zdradzał "Dino"/"sklepu"
  niezależnie od wybranego profilu.
- `demo/install_demo.py` — instaluje przykładowy projekt (dziś wciąż na
  starszym mechanizmie `night_shift`, nie na nowym `duty_rotation` z
  Etapów A-C — patrz "Do zrobienia" niżej).
- Prawdziwy fix w `logic/generator/generic_rules.py` (`_shift_touches_window`)
  — dotyczy każdego custom profilu, nie tylko tego klienta.

## Do zrobienia (z sekcji 12/13 planu)

- **Etap D** — wyłączenie `balance`/`monthly_hours` dla tego profilu +
  nowa kolumna "Nadgodziny" w gridzie/eksportach.
- **Etap E** — menu "Placówki" (osobne pliki projektu + szybkie
  przełączanie).
- **Etap F** — testy scenariuszowe pełnego miesiąca.
- Zaktualizować `demo/install_demo.py`, żeby przykładowy projekt używał
  nowego mechanizmu `duty_rotation` (Etapy A-C) zamiast starszego
  przybliżenia przez `night_shift` — dziś demo i rdzeń generatora nie są
  jeszcze spięte w jedną, spójną prezentację.

## Jak odpalić demo

```
python demo/install_demo.py
python main.py
```

`install_demo.py` zapisuje profil "Ochrona" do
`%LOCALAPPDATA%\GrafikDino\custom_profiles.json` (dokładnie tam, gdzie
normalnie zapisuje go `ProfileWizardDialog`) i podmienia
`last_project.json` w katalogu repo (plik już w `.gitignore`, więc to
nie rusza kontroli wersji) na gotowy przykładowy projekt. Uruchomienie
`main.py` po tym otwiera aplikację z tym projektem od razu.
