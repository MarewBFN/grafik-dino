import tkinter as tk
from tkinter import ttk, messagebox
from model.employee import Employee


class EmployeeDialog(tk.Toplevel):
    def __init__(self, parent, on_save, employee=None, schedule=None, shop=None):
        super().__init__(parent)
        self.title("Dodaj pracownika")
        self.resizable(False, False)
        self.on_save = on_save
        self.employee = employee
        self.schedule = schedule
        self.shop = shop

        self.last_name = tk.StringVar()
        self.first_name = tk.StringVar()
        self.is_opener = tk.BooleanVar()
        self.is_meat = tk.BooleanVar()
        self.daily_hours = tk.IntVar(value=8)

        if self.employee:
            self.last_name.set(self.employee.last_name)
            self.first_name.set(self.employee.first_name)
            self.is_opener.set(self.employee.is_opener)
            self.is_meat.set(self.employee.is_meat)
            self.daily_hours.set(self.employee.daily_hours)

        self._build()

    def _build(self):
        pad = {"padx": 10, "pady": 6}

        ttk.Label(self, text="Nazwisko").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.last_name).grid(row=0, column=1, **pad)

        ttk.Label(self, text="Imię").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.first_name).grid(row=1, column=1, **pad)

        ttk.Checkbutton(self, text="Otwarcie", variable=self.is_opener)\
            .grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        ttk.Checkbutton(self, text="Mięso", variable=self.is_meat)\
            .grid(row=3, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(self, text="Praca przez x godzin dziennie")\
            .grid(row=4, column=0, sticky="w", **pad)

        ttk.Combobox(
            self,
            values=[6, 7, 8],
            width=5,
            state="readonly",
            textvariable=self.daily_hours
        ).grid(row=4, column=1, sticky="w", **pad)

        btns = ttk.Frame(self)
        btns.grid(row=5, column=0, columnspan=2, pady=10)

        ttk.Button(btns, text="Anuluj", command=self.destroy).pack(side="right", padx=5)
        ttk.Button(btns, text="Dodaj", command=self._save).pack(side="right")

        # ===== ADVANCED =====
        self.adv_visible = False

        self.adv_btn = tk.Label(
            self,
            text="⚙️ Zaawansowane",
            fg="blue",
            cursor="hand2"
        )
        self.adv_btn.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 0))
        self.adv_btn.bind("<Button-1>", self._toggle_advanced)

        self.adv_frame = tk.Frame(self)
        self.adv_frame.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.adv_frame.grid_remove()

        # ===== AVAILABILITY UI =====

        self._availability = {}

        days = [
            ("mon", "Pon"),
            ("tue", "Wt"),
            ("wed", "Śr"),
            ("thu", "Czw"),
            ("fri", "Pt"),
            ("sat", "Sob"),
            ("sun", "Nd"),
        ]

        self.day_rows = {}

        for key, label in days:
            row = tk.Frame(self.adv_frame)
            row.pack(anchor="w", pady=2)

            tk.Label(row, text=label, width=5).pack(side="left")

            free_var = tk.BooleanVar()

            start_var = tk.StringVar(value="08:00")
            end_var = tk.StringVar(value="16:00")

            start_entry = tk.Entry(row, textvariable=start_var, width=6)
            end_entry = tk.Entry(row, textvariable=end_var, width=6)

            start_entry.pack(side="left", padx=2)
            tk.Label(row, text="-").pack(side="left")
            end_entry.pack(side="left", padx=2)

            def toggle(free_var=free_var, s=start_entry, e=end_entry):
                if free_var.get():
                    s.config(state="disabled")
                    e.config(state="disabled")
                else:
                    s.config(state="normal")
                    e.config(state="normal")

            tk.Checkbutton(
                row,
                text="Wolne",
                variable=free_var,
                command=toggle
            ).pack(side="left", padx=5)

            self.day_rows[key] = {
                "free": free_var,
                "start": start_var,
                "end": end_var
            }

        self.availability_type = tk.StringVar(value="soft")

        tk.Radiobutton(
            self.adv_frame,
            text="Preferowane",
            variable=self.availability_type,
            value="soft"
        ).pack(anchor="w")

        tk.Radiobutton(
            self.adv_frame,
            text="Twarde",
            variable=self.availability_type,
            value="hard"
        ).pack(anchor="w")

        tk.Button(
            self.adv_frame,
            text="Nanieś na grafik",
            command=self._apply_to_schedule
        ).pack(anchor="w", pady=5)
        
    def _apply_to_schedule(self):
        if not self.schedule or not self.shop:
            return

        emp = self.employee

        if not emp:
            print("Brak istniejącego pracownika – najpierw zapisz")
            return

        for day in range(1, self.schedule.days_in_month + 1):

            if not self.shop.is_trade_day(day):
                continue

            weekday = self.shop.weekday(day)

            row = self.day_rows.get(weekday)
            if not row:
                continue

            ds = self.schedule.get_day(emp, day)

            # 🔴 WOLNE
            if row["free"].get():
                ds.set_free()
                ds.is_locked = True
                continue

            start = row["start"].get()
            end = row["end"].get()

            ds.set_hours(start, end)

            if self.availability_type.get() == "hard":
                ds.is_locked = True
            else:
                ds.is_locked = False

        print("Naniesiono godziny na grafik")

    def _toggle_advanced(self, event=None):
        self.adv_visible = not self.adv_visible

        if self.adv_visible:
            self.adv_frame.grid()
        else:
            self.adv_frame.grid_remove()

    def _apply_availability(self):
        typ = self.availability_type.get()
        self._availability = {}

        for day, data in self.day_rows.items():

            if data["free"].get():
                self._availability[day] = [{
                    "type": typ,
                    "free": True
                }]
                continue

            start = data["start"].get()
            end = data["end"].get()

            self._availability[day] = [{
                "start": start,
                "end": end,
                "type": typ
            }]

        print("AVAILABILITY:", self._availability)

    def _save(self):
        try:
            emp = Employee(
                last_name=self.last_name.get().strip(),
                first_name=self.first_name.get().strip(),
                is_opener=self.is_opener.get(),
                is_meat=self.is_meat.get(),
                daily_hours=self.daily_hours.get(),
                availability=getattr(self, "_availability", {})
            )
            emp.validate()
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self.on_save(emp)
        self.destroy()