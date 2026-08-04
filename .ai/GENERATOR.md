# Generator

Generator wykorzystuje OR-Tools CP-SAT.

Każdy constraint odpowiada za jedną konkretną regułę.

Nie należy mieszać odpowiedzialności pomiędzy constraintami.

Podczas analizy generatora:

1. ustal który constraint odpowiada za dane zachowanie,
2. nie zmieniaj wielu constraintów naraz,
3. po każdej zmianie uruchom testy.

Jeżeli generator zachowuje się niepoprawnie:

najpierw ustal który constraint jest odpowiedzialny,

dopiero później zmieniaj kod.