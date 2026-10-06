// Generuje parę kluczy Ed25519 do podpisywania odpowiedzi serwera licencji
// oraz losowe hasło do panelu. Uruchom RAZ, u siebie: `npm run keys`.
//
// - KLUCZ PRYWATNY i HASŁO wpisujesz tylko jako sekrety Cloudflare
//   (`npx wrangler secret put ...`). Nigdzie ich nie commituj.
// - KLUCZ PUBLICZNY wklejasz do licensing/online.py w programie
//   (LICENSE_PUBLIC_KEY) - on może być jawny.
//
// Wygenerowanie nowej pary unieważnia odpowiedzi zapamiętane przez już
// wydane programy, więc rób to tylko przy pierwszym wdrożeniu.
import { generateKeyPairSync, randomBytes } from "node:crypto";

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const privateB64 = privateKey.export({ format: "der", type: "pkcs8" }).toString("base64");
// Surowy klucz publiczny = ostatnie 32 bajty struktury SPKI.
const publicB64 = publicKey.export({ format: "der", type: "spki" }).subarray(-32).toString("base64");
const adminPassword = randomBytes(18).toString("base64url");

console.log(`
LICENSE_PRIVATE_KEY (sekret Cloudflare - npx wrangler secret put LICENSE_PRIVATE_KEY):
${privateB64}

ADMIN_PASSWORD (sekret Cloudflare - npx wrangler secret put ADMIN_PASSWORD; zapisz w menedżerze haseł):
${adminPassword}

LICENSE_PUBLIC_KEY (wklej do licensing/online.py w programie):
${publicB64}
`);
