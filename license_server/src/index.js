// Serwer licencji DinGo! / Enyo.
//
// POST /api/check            - program przy starcie (i co godzinę) zgłasza swoje
//                              ID, serwer zapisuje je i odsyła PODPISANY status.
// GET  /admin                - panel do przełączania licencji (hasło ADMIN_PASSWORD).
// GET  /api/admin/licenses   - lista ID (dla panelu).
// POST /api/admin/licenses/X - zmiana statusu/terminu/notatki ID X.
// DELETE /api/admin/licenses/X
//
// Odpowiedź /api/check jest podpisana kluczem Ed25519 (sekret
// LICENSE_PRIVATE_KEY). Program ma wbudowany tylko klucz publiczny, więc
// nie da się podrobić odpowiedzi ani przerobić zapamiętanego statusu.

import ADMIN_HTML from "./admin.html";

const USER_ID_RE = /^[0-9A-F]{6}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const STATUSES = ["demo", "trial", "full", "blocked"];
const PAYLOAD_VERSION = 1;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/api/check" && request.method === "POST") {
        return await handleCheck(request, env);
      }
      if (path === "/admin" && request.method === "GET") {
        return new Response(ADMIN_HTML, {
          headers: {
            "content-type": "text/html; charset=utf-8",
            "cache-control": "no-store",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
          },
        });
      }
      if (path.startsWith("/api/admin/")) {
        const denied = await checkAdmin(request, env);
        if (denied) return denied;
        return await handleAdmin(request, env, path);
      }
      return json({ error: "not_found" }, 404);
    } catch (err) {
      console.error(err);
      return json({ error: "server_error" }, 500);
    }
  },
};

// --- /api/check -------------------------------------------------------------

async function handleCheck(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad_json" }, 400);
  }

  const userId = String(body.user_id || "").trim().toUpperCase();
  if (!USER_ID_RE.test(userId)) {
    return json({ error: "bad_user_id" }, 400);
  }
  const appVersion = cleanText(body.app_version, 32);
  const channel = cleanText(body.channel, 16);
  const legacy = body.legacy_key === true ? 1 : 0;
  const now = new Date().toISOString();

  // Nowe ID dostaje "demo", chyba że program ma ważny stary klucz - wtedy
  // "full" (stare klucze dalej działają). Stary klucz podniesie też
  // istniejące "demo" do "full"; żeby go wyłączyć, ustaw w panelu "blocked".
  const row = await env.DB.prepare(
    `INSERT INTO licenses (user_id, status, channel, app_version, legacy_key, first_seen, last_seen, checks)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?6, 1)
     ON CONFLICT(user_id) DO UPDATE SET
       channel = excluded.channel,
       app_version = excluded.app_version,
       legacy_key = MAX(licenses.legacy_key, excluded.legacy_key),
       first_seen = COALESCE(licenses.first_seen, excluded.first_seen),
       last_seen = excluded.last_seen,
       checks = licenses.checks + 1,
       status = CASE
         WHEN excluded.legacy_key = 1 AND licenses.status = 'demo' THEN 'full'
         ELSE licenses.status
       END
     RETURNING status, expires_at`
  )
    .bind(userId, legacy ? "full" : "demo", channel, appVersion, legacy, now)
    .first();

  const payload = {
    v: PAYLOAD_VERSION,
    user_id: userId,
    status: effectiveStatus(row.status, row.expires_at, now),
    expires_at: row.expires_at || null,
    issued_at: now,
  };
  return json(await signPayload(payload, env));
}

// Termin testu jest włącznie; po nim serwer odpowiada "expired".
function effectiveStatus(status, expiresAt, nowIso) {
  if (status !== "trial") return status;
  if (!expiresAt || expiresAt < nowIso.slice(0, 10)) return "expired";
  return "trial";
}

let signingKeyPromise = null;

function getSigningKey(env) {
  if (!signingKeyPromise) {
    if (!env.LICENSE_PRIVATE_KEY) {
      throw new Error("Brak sekretu LICENSE_PRIVATE_KEY");
    }
    signingKeyPromise = crypto.subtle
      .importKey("pkcs8", base64ToBytes(env.LICENSE_PRIVATE_KEY), { name: "Ed25519" }, false, ["sign"])
      .catch((err) => {
        signingKeyPromise = null;
        throw err;
      });
  }
  return signingKeyPromise;
}

async function signPayload(payload, env) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const key = await getSigningKey(env);
  const signature = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, key, bytes));
  return { payload: bytesToBase64(bytes), signature: bytesToBase64(signature) };
}

// --- panel ------------------------------------------------------------------

async function checkAdmin(request, env) {
  if (!env.ADMIN_PASSWORD) {
    return json({ error: "admin_disabled" }, 503);
  }
  const header = request.headers.get("authorization") || "";
  const given = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!(await sameSecret(given, env.ADMIN_PASSWORD))) {
    // Spowalnia zgadywanie hasła.
    await new Promise((resolve) => setTimeout(resolve, 1000));
    return json({ error: "unauthorized" }, 401);
  }
  return null;
}

async function handleAdmin(request, env, path) {
  if (path === "/api/admin/licenses" && request.method === "GET") {
    const { results } = await env.DB.prepare(
      `SELECT user_id, status, expires_at, note, channel, app_version, legacy_key,
              first_seen, last_seen, checks
       FROM licenses ORDER BY COALESCE(last_seen, first_seen) DESC`
    ).all();
    return json({ licenses: results, today: new Date().toISOString().slice(0, 10) });
  }

  const match = path.match(/^\/api\/admin\/licenses\/([^/]+)$/);
  if (!match) return json({ error: "not_found" }, 404);
  const userId = decodeURIComponent(match[1]).trim().toUpperCase();
  if (!USER_ID_RE.test(userId)) return json({ error: "bad_user_id" }, 400);

  if (request.method === "DELETE") {
    await env.DB.prepare("DELETE FROM licenses WHERE user_id = ?1").bind(userId).run();
    return json({ ok: true });
  }

  if (request.method === "POST") {
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "bad_json" }, 400);
    }
    const status = String(body.status || "");
    if (!STATUSES.includes(status)) return json({ error: "bad_status" }, 400);
    const expiresAt = body.expires_at ? String(body.expires_at) : null;
    if (expiresAt !== null && !isValidDate(expiresAt)) return json({ error: "bad_date" }, 400);
    if (status === "trial" && !expiresAt) return json({ error: "trial_needs_date" }, 400);
    const note = cleanText(body.note, 500) || "";

    // Pozwala też dodać ID z wyprzedzeniem, zanim program się zgłosi.
    await env.DB.prepare(
      `INSERT INTO licenses (user_id, status, expires_at, note) VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(user_id) DO UPDATE SET
         status = excluded.status, expires_at = excluded.expires_at, note = excluded.note`
    )
      .bind(userId, status, status === "trial" ? expiresAt : null, note)
      .run();
    return json({ ok: true });
  }

  return json({ error: "method_not_allowed" }, 405);
}

// --- pomocnicze -------------------------------------------------------------

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function cleanText(value, maxLength) {
  if (value === undefined || value === null) return null;
  return String(value).replace(/[\u0000-\u001f]/g, " ").trim().slice(0, maxLength);
}

function isValidDate(value) {
  if (!DATE_RE.test(value)) return false;
  const parsed = new Date(value + "T00:00:00Z");
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().startsWith(value);
}

async function sameSecret(a, b) {
  // Porównanie skrótów stałej długości - bez wycieku przez czas porównania.
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

function base64ToBytes(value) {
  const binary = atob(value.trim());
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToBase64(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
