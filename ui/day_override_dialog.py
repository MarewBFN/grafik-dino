import tkinter as tk
from tkinter import ttk, messagebox


class DayOverrideDialog(tk.Toplevel):
    def __init__(self, parent, day, current_hours, shop_config, on_save):
        super().__init__(parent)
        self.title(f"Godziny dla dnia {day}")
        self.resizable(False, False)

        self.day = day
        self.shop_config = shop_config
        self.on_save = on_save

        self.start_var = tk.StringVar(value=current_hours[0])
        self.end_var = tk.StringVar(value=current_hours[1])

        self.holiday_var = tk.BooleanVar(
            value=self.day in self.shop_config.public_holidays
        )

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        ttk.Label(self, text="Otwarcie").grid(row=0, column=0, **pad)
        ttk.Entry(self, width=7, textvariable=self.start_var)\
            .grid(row=0, column=1, **pad)

        ttk.Label(self, text="Zamknięcie").grid(row=1, column=0, **pad)
        ttk.Entry(self, width=7, textvariable=self.end_var)\
            .grid(row=1, column=1, **pad)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(btns, text="Anuluj", command=self.destroy)\
            .pack(side="right", padx=5)

        ttk.Button(btns, text="Zapisz", command=self._save)\
            .pack(side="right")

        # Checkbox święta ustawowego
        ttk.Checkbutton(
            self,
            text="Dzień wolny ustawowo",
            variable=self.holiday_var
        ).grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10))

    def _save(self):
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()

        if not start or not end:
            messagebox.showerror("Błąd", "Godziny nie mogą być puste")
            return

        # zapis święta
        if self.holiday_var.get():
            self.shop_config.public_holidays.add(self.day)
        else:
            self.shop_config.public_holidays.discard(self.day)

        self.on_save(start, end)
        self.destroy()
