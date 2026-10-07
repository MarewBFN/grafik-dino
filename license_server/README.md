# Serwer licencji (Cloudflare Workers + D1)

Mały serwer, do którego program zgłasza przy starcie (i co godzinę) **tylko**
swoje ID użytkownika, wersję i kanał (dino/enyo). Odsyła podpisany status:

| Status w panelu | Co dzieje się w programie |
|---|---|
| **Demo** | wersja demonstracyjna |
| **Test do dnia** (domyślny dla nowego ID: 7 dni) | pełna wersja do podanej daty (włącznie), potem sama wraca do demo. Bez internetu działa maks. 7 dni od ostatniego kontaktu z serwerem. |
| **Pełna** | pełna wersja bez terminu, działa też bez internetu |
| **Zablokowana** | demo, także gdy komputer ma stary 8-cyfrowy klucz |

Nowe ID (bez starego klucza) przy pierwszym połączeniu dostaje automatycznie
**Test do dnia** na 7 dni, licząc dzień instalacji, z notatką „auto: 7 dni
testu”. ID dodane wcześniej ręcznie w panelu zachowuje ustawiony status.

Stare 8-cyfrowe klucze dalej działają. Takie ID pojawia się w panelu
z etykietą „stary klucz” i statusem „Pełna”. Żeby je wyłączyć, ustaw
„Zablokowana” (status „Demo” nie wystarczy, bo stary klucz podniesie go z
powrotem do „Pełna”).

Zmiana w panelu dociera do programu przy następnym uruchomieniu, w ciągu
godziny, albo od razu po kliknięciu **Pomoc → Sprawdź licencję**. Gdy
program traci pełną wersję, pokazuje komunikat, że działa jako demo, a
projekty klienta zostają nietknięte.

Odpowiedzi serwera są podpisane kluczem Ed25519. W programie jest tylko
klucz publiczny, więc nie da się podrobić odpowiedzi ani ręcznie poprawić
zapamiętanego statusu (`license_status.json`).

Darmowy plan Cloudflare (100 000 zapytań dziennie) wystarczy z ogromnym
zapasem: jedno uruchomione stanowisko to ok. 24 zapytania na dobę.

---

## Wdrożenie (raz)

Potrzebujesz Node.js 18+ (https://nodejs.org) i darmowego konta Cloudflare
(https://dash.cloudflare.com/sign-up). Polecenia wpisujesz w PowerShellu,
w katalogu `license_server`:

```powershell
cd license_server
npm install
npx wrangler login                     # otworzy przeglądarkę - zaloguj się do Cloudflare
```

**1. Baza danych**

```powershell
npx wrangler d1 create dingo-licencje
```

Skopiuj wypisane `database_id` do `wrangler.toml` (w miejsce
`WPISZ-DATABASE-ID`), potem utwórz tabelę:

```powershell
npx wrangler d1 execute dingo-licencje --remote --file=schema.sql
```

**2. Klucze i hasło panelu**

```powershell
npm run keys
```

Wypisze trzy wartości. Dwie pierwsze to sekrety. Wpisz je do Cloudflare
(polecenie poprosi o wklejenie wartości) i zapisz w menedżerze haseł. Nigdy
ich nie commituj:

```powershell
npx wrangler secret put LICENSE_PRIVATE_KEY
npx wrangler secret put ADMIN_PASSWORD
```

**3. Wdrożenie**

```powershell
npx wrangler deploy
```

Wypisze adres, np. `https://dingo-licencje.twoja-nazwa.workers.dev`.
Panel jest pod `https://dingo-licencje.twoja-nazwa.workers.dev/admin`.

**4. Program**

W `licensing/online.py` wpisz:

```python
LICENSE_SERVER_URL = "https://dingo-licencje.twoja-nazwa.workers.dev"
LICENSE_PUBLIC_KEY = "<trzecia wartość z npm run keys>"
```

Zacommituj to i zbuduj nowe wydanie. Klucz publiczny i adres mogą być
jawne. Od tej wersji każde uruchomienie programu pojawi się w panelu.

> `npm run keys` uruchom tylko raz. Nowa para kluczy unieważnia statusy
> zapamiętane przez już wydane programy, bo mają wbudowany stary klucz
> publiczny.

### Własna domena (opcjonalnie)

Jeśli domena jest w Cloudflare, w panelu Cloudflare → Workers →
`dingo-licencje` → Settings → Domains & Routes możesz dodać np.
`licencje.madebykewin.pl`. Pamiętaj, żeby wtedy zmienić
`LICENSE_SERVER_URL` w programie **zanim** wydasz wersję z serwerem
licencji. Adresu `workers.dev` nie wyłączaj, dopóki działają programy,
które go używają.

---

## Typowy scenariusz: klient chce przetestować pełną wersję

1. Klient instaluje i uruchamia program. Jego ID pojawia się w panelu z
   etykietą „nowy” i automatycznym testem na 7 dni. ID jest też w prawym dolnym rogu okna programu, więc
   może Ci je podać.
2. Chcesz dać dłuższy test: w panelu zmień datę **Test do dnia**, dopisz
   notatkę (np. „Firma X”), kliknij **Zapisz**.
3. Klient restartuje program albo klika **Pomoc → Sprawdź licencję**. Nie
   musi nic wpisywać.
4. Zapłacił, to ustawiasz **Pełna**. Nie zapłacił, to nic nie robisz:
   po terminie program sam wraca do demo. Możesz też od razu ustawić
   **Zablokowana**.

## Lokalne testy serwera

```powershell
npx wrangler d1 execute dingo-licencje --local --file=schema.sql
# .dev.vars (nie commitować):
#   LICENSE_PRIVATE_KEY=...
#   ADMIN_PASSWORD=...
npx wrangler dev
```

## API

- `POST /api/check` `{user_id, legacy_key, app_version, channel}` →
  `{payload, signature}` (base64). `payload` to JSON
  `{v, user_id, status, expires_at, issued_at}`, a `status` przyjmuje
  wartości `demo`, `trial`, `full`, `blocked` albo `expired`.
- `GET /api/admin/licenses`, `POST /api/admin/licenses/<ID>`
  `{status, expires_at, note}`, `DELETE /api/admin/licenses/<ID>`.
  Wymagają nagłówka `Authorization: Bearer <ADMIN_PASSWORD>`.
