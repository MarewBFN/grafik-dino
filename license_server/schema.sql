-- Jedna linijka na komputer (ID użytkownika z paska stanu programu).
--
-- status:
--   demo     - wersja demonstracyjna
--   trial    - pełna wersja do dnia expires_at (włącznie); nowe ID bez
--              starego klucza dostaje go automatycznie na 7 dni
--   full     - pełna wersja bez terminu
--   blocked  - wyłączona; wyłącza też stary 8-cyfrowy klucz produktu
CREATE TABLE IF NOT EXISTS licenses (
    user_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'demo',
    expires_at  TEXT,
    note        TEXT NOT NULL DEFAULT '',
    channel     TEXT,
    app_version TEXT,
    legacy_key  INTEGER NOT NULL DEFAULT 0,
    first_seen  TEXT,
    last_seen   TEXT,
    checks      INTEGER NOT NULL DEFAULT 0
);
