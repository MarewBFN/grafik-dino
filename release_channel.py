# Kanał wydań, którego ten build ma pilnować przy sprawdzaniu aktualizacji.
#
# WAŻNE: wartość zacommitowana w repo MUSI zostać "dino" — to jest kanał
# domyślny, którego używają zwykłe buildy (Dino i inni klienci retail).
# Nie zmieniaj tego pliku ręcznie i nie zostawiaj innej wartości po
# zbudowaniu wariantu dla innego klienta.
#
# Budowanie exe dla innego kanału (np. "enyo") odbywa się przez
# scripts/build_release.ps1 -Channel enyo, który tymczasowo podmienia tę
# wartość na czas builda i automatycznie przywraca "dino" zaraz po nim.
RELEASE_CHANNEL = "dino"
