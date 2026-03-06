# Grafik Dino V2

**Grafik Dino V2** is a desktop application for automatically generating employee work schedules for retail stores.
The program uses **Google OR-Tools CP-SAT solver** to build valid schedules while respecting multiple constraints.

The goal of the project is to eliminate errors and significantly speed up the process of creating monthly work schedules.

---

# Features

* automatic schedule generation
* support for **OPEN / CLOSE shifts**
* **vacation management**
* enforcement of **11-hour rest between shifts**
* limit of **maximum consecutive work days**
* **hour balancing** between employees
* employee roles:

  * opener
  * meat
* manual editing of schedule cells
* ability to **lock manually set days**
* save / load schedule from **JSON**
* graphical interface built with **Tkinter**

---

# How the generator works

The generator is based on **Constraint Programming (CP-SAT)** from Google OR-Tools.

The solver searches for a solution that satisfies all **mandatory constraints**, while trying to optimize **preferred constraints**.

Example rules:

* exactly **3 employees on OPEN shift**
* exactly **3 employees on CLOSE shift**
* at least one employee with the **opener role**
* at least one employee with the **meat role**
* minimum **11 hours of rest between shifts**
* limit on consecutive work days
* balanced working hours between employees

---

# Project structure

```
grafik-dino-v2
│
├─ model           # data models (employee, day schedule, month schedule)
├─ solver          # CP-SAT schedule generator
├─ ui              # graphical user interface
├─ config          # shop configuration and shift definitions
│
├─ main.py         # application entry point
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

The project is currently under active development.

Planned features:

* **manual shift drawing mode**
* remembering last shifts from the previous month
* **online application updates**
* multi-project schedule management

---

# Why this project exists

In many retail stores, work schedules are still created manually on paper.
This often leads to problems such as:

* incorrect working hour calculations
* broken rest regulations
* uneven distribution of shifts

This project aims to automate the process and ensure correct scheduling.

---

# Author

Personal learning project created while learning Python and optimization algorithms.
