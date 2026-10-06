# Wydawanie aktualizacji (Dino + Enyo)

Dwa niezależne kanały, budowane z dwóch różnych branchy, ale współdzielące
**jeden** mechanizm sprawdzania aktualizacji, który zawsze czyta dane
z brancha `main` — to jest źródło większości pomyłek przy wydaniach, patrz
sekcja "Najważniejsza pułapka" niżej.

| | Dino (DinGo!) | Enyo |
|---|---|---|
| Branch z kodem | `main` | `integration/enyo-only` |
| Plik wersji | `version.py` → `"X.Y.Z"` | `version.py` → `"X.Y.Z.enyo"` |
| Instalator (.iss) | `dla inno.iss` | `enyo.iss` |
| Manifest aktualizacji | `releases/dino.json` | `releases/enyo.json` |
| Tag gita | `vX.Y.Z` (bez sufiksu) | `vX.Y.Z-enyo` |
| Plik wynikowy (Output\\) | `DingoSetup.exe` | `EnyoSetup.exe` |
| PyInstaller .spec | `Dingo! - narzędzie do grafików pracy.spec` | `Enyo - Grafik Pracy.spec` |

## Najważniejsza pułapka: manifesty zawsze czytane z `main`

`update_checker.py::MANIFEST_BASE_URL` jest **na sztywno** ustawiony na
`.../grafik-dino/main/releases/` — apka, niezależnie z jakiego brancha ją
zbudowano, zawsze pyta o `releases/{dino,enyo}.json` z brancha `main` na
GitHubie (`RELEASE_CHANNEL` w `release_channel.py` wybiera tylko *który*
plik: `dino.json` czy `enyo.json`).

**Konsekwencja:** przy KAŻDYM wydaniu Enyo trzeba zaktualizować
`releases/enyo.json` w dwóch miejscach - raz na `integration/enyo-only`
(żeby branch miał spójną historię), i **jeszcze raz na `main`** (bo stamtąd
apka faktycznie czyta). Łatwo o tym zapomnieć, bo commit z wydaniem Enyo
robi się na innym branchu niż `main` - jeśli pominiesz krok 8 poniżej,
klienci Enyo nigdy nie zobaczą dostępnej aktualizacji, mimo że tag i
installer są gotowe.

`releases/dino.json` tego problemu nie ma - wydania Dino i tak robi się
bezpośrednio na `main`.

## Licencja online przed buildem

`licensing/online.py` musi mieć wpisane `LICENSE_SERVER_URL` i
`LICENSE_PUBLIC_KEY` (patrz `license_server/README.md`). Puste wartości
dają build bez sprawdzania online, w którym działa tylko stary klucz
produktu. Licencja online jest na branchu Enyo (`integration/enyo-only`).
Dino (`main`) dostanie ją dopiero po przeniesieniu tych zmian na `main`.

## Wydanie Dino (na `main`)

1. Upewnij się, że jesteś na `main` i working tree jest czyste (`git
   status`).
2. Zbuduj i uruchom cały test suite (`pytest tests/`) - zero regresji.
3. Zbump wersję w trzech plikach:
   - `version.py` → `APP_VERSION = "X.Y.Z"`
   - `dla inno.iss` → `#define MyAppVersion "X.Y.Z"`
   - `releases/dino.json` → `latest_version: "X.Y.Z"`, `download_url:
     ".../releases/download/vX.Y.Z/DingoSetup.exe"`, `changelog` - krótki
     opis zmian dla użytkownika.
4. Commit: `Wydanie X.Y.Z`, potem tag: `git tag -a vX.Y.Z -m "Wydanie X.Y.Z"`.
5. Build exe: `pyinstaller -y "Dingo! - narzędzie do grafików pracy.spec"`
   (bezpośrednio, **nie** przez `scripts\build_release.ps1` - ten skrypt
   nie umie budować kanału "dino", bo to już jest wartość zacommitowana w
   `release_channel.py` i próba podmiany "dino" → "dino" wygląda dla niego
   jak błąd, patrz sekcja "Znane problemy ze skryptem" niżej). Flaga `-y`
   jest ważna - bez niej PyInstaller odmówi nadpisania niepustego `dist\`.
6. Kompilacja instalatora: `ISCC.exe "dla inno.iss"` (Inno Setup 6, domyślnie
   `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`) → wynik w
   `Output\DingoSetup.exe`.
7. `git push origin main --tags` (albo osobno `git push origin main` i
   `git push origin vX.Y.Z`).
8. Na GitHubie: utwórz Release na tagu `vX.Y.Z`, dołącz
   `Output\DingoSetup.exe` jako asset (nazwa pliku dowolna, liczy się
   `download_url` w manifeście z kroku 3 - ale trzymaj się konwencji
   `DingoSetup.exe`, żeby nie trzeba było o tym pamiętać).

## Wydanie Enyo (na `integration/enyo-only`)

1. `git checkout integration/enyo-only`, working tree czyste.
2. Testy jak wyżej.
3. Zbump wersję w trzech plikach (na tym branchu):
   - `version.py` → `APP_VERSION = "X.Y.Z.enyo"`
   - `enyo.iss` → `#define MyAppVersion "X.Y.Z.enyo"`
   - `releases/enyo.json` → `latest_version: "X.Y.Z.enyo"`, `download_url:
     ".../releases/download/vX.Y.Z-enyo/EnyoSetup.exe"`, `changelog`.
4. Commit: `Wydanie X.Y.Z.enyo`, tag: `git tag -a vX.Y.Z-enyo -m "Wydanie X.Y.Z.enyo"`
   (pamiętaj o sufiksie `-enyo` w tagu - inaczej niż przy Dino).
5. Jeśli `dist\Enyo - Grafik Pracy\` już istnieje z poprzedniego builda,
   usuń go najpierw (`Remove-Item -Recurse -Force "dist\Enyo - Grafik Pracy"`)
   - skrypt niżej nie ma flagi `-y` i inaczej się wywali w połowie (patrz
     "Znane problemy ze skryptem").
6. Build exe: `scripts\build_release.ps1 -Channel enyo -SpecFile "Enyo - Grafik Pracy.spec"`
   - ten skrypt tymczasowo podmienia `release_channel.py` na `"enyo"` na
     czas builda i **zawsze** przywraca `"dino"` po (nawet gdy build się
     wywali) - sprawdź na końcu, że faktycznie wrócił (`git status --
     release_channel.py` powinno być puste).
7. Kompilacja instalatora: `ISCC.exe "enyo.iss"` → wynik w
   `Output\EnyoSetup.exe`.
8. `git push origin integration/enyo-only --tags`.
9. **Krytyczny, łatwy do pominięcia krok:** przełącz się na `main`
   (`git checkout main`), skopiuj świeżo zaktualizowany
   `releases/enyo.json` z `integration/enyo-only` (`git show
   integration/enyo-only:releases/enyo.json > releases/enyo.json`),
   commit ("Zsynchronizuj releases/enyo.json na main z wydaniem X.Y.Z.enyo")
   i `git push origin main` - patrz "Najważniejsza pułapka" wyżej. Bez
   tego kroku wydanie jest zbudowane i otagowane, ale klienci Enyo nigdy
   się o nim nie dowiedzą.
10. Na GitHubie: Release na tagu `vX.Y.Z-enyo`, asset
    `Output\EnyoSetup.exe`.
11. Wróć na `integration/enyo-only`, jeśli tam dalej pracujesz
    (`git checkout integration/enyo-only`) - zgodnie z `.ai/AGENTS.md`,
    to jedyny roboczy branch obok `main`.

## Znane problemy ze skryptem `scripts\build_release.ps1`

- **Nie buduje kanału "dino"** - podmienia `RELEASE_CHANNEL` regexem
  `"dino"` → `"dino"`, co wygląda jak "nic się nie zmieniło" i skrypt
  rzuca błąd bezpieczeństwa ("Nie udało się podmienić..."). Dla Dino
  buduj przez `pyinstaller` bezpośrednio (krok 5 wyżej), skrypt jest
  potrzebny tylko dla kanałów innych niż domyślny (dziś: `enyo`).
- **Nie czyści `dist\`** - PyInstaller bez `-y` odmawia nadpisania
  niepustego katalogu wyjściowego z poprzedniego builda. Usuń
  `dist\<Nazwa z .spec>\` ręcznie przed uruchomieniem skryptu, albo
  dodaj `-y` gdybyś kiedyś edytował skrypt.
- Po każdym uruchomieniu (sukces czy porażka) skrypt przywraca
  `release_channel.py` do stanu z gita (czyli `"dino"`) - zawsze warto
  to zweryfikować (`git status`) zanim zrobisz kolejny commit, żeby
  przypadkiem nie zacommitować złego kanału.

## Skróty pamięciowe

- Tag Dino: **bez** sufiksu (`v1.3.1`). Tag Enyo: **z** sufiksem
  (`v1.1.4-enyo`).
- `version.py`, `dla inno.iss`/`enyo.iss`, `releases/dino.json`/
  `releases/enyo.json` - zawsze bumpować w komplecie, na właściwym
  branchu.
- `releases/enyo.json` - jedyny plik, który trzeba zaktualizować na
  **obu** branchach przy wydaniu Enyo.
- Nazwa GitHub Release asset ma znaczenie tylko pośrednio (przez
  `download_url` w manifeście) - ale trzymaj się `DingoSetup.exe`/
  `EnyoSetup.exe`, to już jest wpisane wszędzie indziej (nazwy plików
  `OutputBaseFilename` w .iss, `INSTALLER_ASSET_NAME` w
  `update_checker.py`).
