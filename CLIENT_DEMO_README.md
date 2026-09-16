# ⚠️ BRANCH DEMONSTRACYJNY — NIE MERGOWAĆ BEZ ŚWIADOMEJ DECYZJI ⚠️

Ten branch (`client-demo/enyo-ochrona`) to **prototyp do poklikania dla
jednego, konkretnego klienta** (Michał, Enyo — firma ochroniarska), nie
kolejny etap rozwoju głównego produktu.

**NIE mergować tego brancha do `main` ani do `feature/business-profiles`
bez świadomej decyzji i przeglądu.** Powody:

1. Zawiera dane demonstracyjne (przykładowy projekt, przykładowi
   pracownicy) specyficzne dla tego jednego klienta/pokazu — nie mają
   sensu w głównym produkcie.
2. Profil "Ochrona" w tym branchu ilustruje **tylko** punkty 1-4 z
   sekcji 9 `plan profil ochrona (analiza specyfikacji klienta).md`
   ("Wstępny plan działania — tylko punkty jednoznaczne"). Świadomie
   **pomija** zmienne godziny pracy per dzień tygodnia i zmianę 24h/16h/12h
   (sekcje 4.4 i 7 tego samego planu) — te czekają na odpowiedzi klienta
   na pytania blokujące (sekcja 8) i nie są tu w żaden sposób
   rozwiązane, tylko obładomnie ominięte. Grafik przykładowy w tym
   branchu **nie pokazuje** prawdziwej rotacji 24/7 ochrony — to
   uproszczenie na potrzeby demo, nie docelowy kształt funkcji.
3. Kosmetyczne zmiany w UI (patrz "Co się różni" niżej) są zrobione pod
   kątem "to demo nie powinno zdradzać, że to ten sam program co dla
   sklepów Dino" — część z nich może nie być tym, co finalnie trafi do
   głównego produktu.

## Co jest w tym branchu

- Poprawka rzeczywistego błędu w `logic/generator/generic_rules.py`
  (`_shift_touches_window`) — dotyczyła każdego custom profilu
  używającego reguły "Zakaz pracy w oknie czasowym" (`role_time_restriction`)
  przeciwko zwykłym zmianom (OPEN/CLOSE/START/END), nie tylko `SHIFT_NIGHT`.
  Ta poprawka **nie jest specyficzna dla demo** — to prawdziwy fix,
  bezpieczny do zabrania też do `feature/business-profiles` przy okazji
  następnego przeglądu (patrz commit i `tests/test_night_shift_role_restriction.py`).
- Profil biznesowy "Ochrona" (custom profile, budowany tym samym
  mechanizmem co `ProfileWizardDialog` — patrz `demo/enyo_ochrona/`).
- Podświetlanie na czerwono przekroczenia miesięcznego limitu godzin
  pełnoetatowych — w gridzie i w obu eksporterach (JPG, Excel).
- Wydruk/eksport dla pojedynczego pracownika (JPG i Excel).
- Drobne kosmetyczne zmiany w UI, żeby nic nie zdradzało "Dino"/"sklepu"
  w widoku dla tego profilu.
- Gotowy projekt demonstracyjny (`demo/enyo_ochrona/`) + skrypt
  `demo/install_demo.py`, który instaluje profil i projekt tak, żeby
  aplikacja otworzyła się od razu z gotowym przykładem.

## Czego w tym branchu NIE ma (celowo)

- Zmiennej długości zmiany per pracownik/dzień tygodnia (16h pon-pt,
  12h/24h weekend) — sekcja 4.4 planu.
- Prawdziwej zmiany 24h — sekcja 7 planu. Demo pokazuje istniejący,
  wcześniej wdrożony mechanizm `SHIFT_NIGHT` (jeden sztywny blok nocny
  na lokalizację, Etap A-G "plan zmiany nocne (24-7).md"), nie nowy
  mechanizm zmian o zmiennej długości.
- Trzeciej kategorii wymiaru etatu "nieokreślony" — czeka na decyzję
  produktową (pytanie 5, sekcja 8 planu).
- Jakiejkolwiek reguły minimalnej obsady — klient świadomie z tego
  zrezygnował (sekcja 2.4 planu).

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
