# Architektura

UI

↓

Controller

↓

Generator

↓

Models

↓

Persistence

UI nie powinno zawierać logiki biznesowej.

Generator nie powinien zależeć od UI.

Modele powinny być możliwie proste.

Przed proponowaniem zmian architektury zawsze oceń czy są one rzeczywiście potrzebne.