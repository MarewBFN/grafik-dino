"""polityka_prywatnosci.txt - plik czytany przez Inno Setup (InfoBeforeFile)
i otwierany z menu Pomoc -> Polityka prywatności."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "polityka_prywatnosci.txt"


def test_policy_is_utf8_with_bom_for_inno_setup():
    raw = POLICY.read_bytes()
    # Bez BOM Inno Setup czyta .txt jako ANSI i psuje polskie znaki.
    assert raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")


def test_both_installers_show_and_install_policy():
    for name in ("enyo.iss", "dla inno.iss"):
        script = (ROOT / name).read_text(encoding="utf-8-sig")
        assert re.search(r"^InfoBeforeFile=polityka_prywatnosci\.txt$", script, re.M), name
        assert 'Source: "polityka_prywatnosci.txt"; DestDir: "{app}"' in script, name


def test_policy_has_no_unfilled_placeholders_besides_known_ones():
    text = POLICY.read_text(encoding="utf-8-sig")
    placeholders = set(re.findall(r"\[[A-ZĄĆĘŁŃÓŚŹŻ ,.\-–0-9a-ząćęłńóśźż]+\]", text))
    # Do uzupełnienia przed wydaniem - patrz README, sekcja licencji.
    assert placeholders <= {
        "[DATA, np. 1 listopada 2026 r.]",
        "[ADRES DO KORESPONDENCJI – opcjonalnie]",
        "[ADRES E-MAIL]",
    }
