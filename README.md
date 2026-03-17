# Grafik Dino V2

**Grafik Dino V2** is a desktop application for automatically generating employee work schedules for retail stores.

The system is based on **Google OR-Tools CP-SAT solver** and uses a modular constraint architecture to build valid schedules while respecting business rules.

The goal of the project is to eliminate errors and significantly speed up the process of creating monthly work schedules.

---

# Features

* automatic schedule generation
* support for **OPEN / CLOSE shifts**
* dynamic **WORK shifts with time offsets**
* **vacation management**
* enforcement of **11-hour rest between shifts**
* limit of **maximum consecutive work days**
* **monthly hour balancing**
* employee roles:

  * opener
  * meat
* manual override of shifts
* ability to **lock manually set days**
* save / load schedule from **JSON**
* graphical interface built with **Tkinter**

---

# How the generator works

The generator uses **Constraint Programming (CP-SAT)**.

The model is built from multiple independent constraint modules:

* **basic constraints** (one shift per day, non-trade days, leave)
* **staff constraints** (open/close staffing, consecutive days)
* **rest constraint** (11h break between shifts)
* **role constraints** (meat / opener coverage)
* **hour constraints** (monthly hours & balance)
* **manual constraints** (user-defined shifts)
* **logic constraints** (dependencies between shifts)

Each constraint can be configured as:

* **MANDATORY** → must be satisfied
* **PREFERRED** → may be violated with penalty
* **DISABLED** → ignored

The solver minimizes total penalty from all soft constraints.

---

# Project structure

```
grafik-dino-v2
│
├─ model                     # data models (schedule, employees, shop config)
├─ logic
│   ├─ generator
│   │   ├─ constraints_basic.py
│   │   ├─ constraints_staff.py
│   │   ├─ rest_constraint.py
│   │   ├─ meat_constraint.py
│   │   ├─ hours_constraint.py
│   │   ├─ manual_constraint.py
│   │   ├─ constraints_logic.py
│   │   ├─ objective.py
│   │   ├─ solver.py
│   │   └─ solution_mapper.py
│
├─ ui                        # Tkinter GUI
├─ main.py                   # application entry point
└─ README.md
```

---

# Running the project

Requirements:

* Python 3.11+
* OR-Tools

Install dependencies:

```bash
pip install ortools
```

Run the application:

```bash
python main.py
```

---

# Project status

The project is actively developed and already includes a fully working schedule generator.

Planned features:

* **manual shift drawing mode**
* remembering last shifts from the previous month
* **online auto-updates**
* multi-project schedule management
* performance improvements for large datasets

---

# Why this project exists

In many retail stores, schedules are still created manually, which often leads to:

* incorrect working hour calculations
* violations of rest regulations
* uneven workload distribution

This project automates the process and ensures consistent, constraint-based scheduling.

---

# Author

Personal project focused on learning:

* Python
* optimization algorithms
* constraint programming
* application architecture and modular design
