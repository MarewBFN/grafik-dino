import tkinter as tk
from tkinter import ttk, messagebox
import calendar


class ConfigDialog(tk.Toplevel):
    def __init__(self, parent, shop_config, on_save):
        super().__init__(parent)
        self.title("Konfiguracja")
        self.geometry("420x360")
        self.resizable(False, False)

        self.shop_config = shop_config
        self.on_save = on_save

        self._build_ui()

    # ==================================================
    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_open_hours_tab(notebook)
        self._build_trade_sundays_tab(notebook)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=5)

        ttk.Button(bottom, text="Zamknij", command=self._close).pack(side="right")

    # ==================================================
    # GODZINY OTWARCIA
    # ==================================================
    def _build_open_hours_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Godziny otwarcia")

        self.open_vars = {}

        days = ["Pon", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

        for wd, name in enumerate(days):
            ttk.Label(tab, text=name).grid(row=wd, column=0, padx=10, pady=5, sticky="w")

            start, end = self.shop_config.open_hours[wd]

            sv = tk.StringVar(value=start)
            ev = tk.StringVar(value=end)

            ttk.Entry(tab, width=6, textvariable=sv).grid(row=wd, column=1, padx=5)
            ttk.Label(tab, text="–").grid(row=wd, column=2)
            ttk.Entry(tab, width=6, textvariable=ev).grid(row=wd, column=3, padx=5)

            self.open_vars[wd] = (sv, ev)

    # ==================================================
    # NIEDZIELE HANDLOWE
    # ==================================================
    def _build_trade_sundays_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Niedziele handlowe")

        self.sunday_vars = {}

        cal = calendar.Calendar()
        sundays = [
            d for d, wd in cal.itermonthdays2(
                self.shop_config.year,
                self.shop_config.month
            )
            if d != 0 and wd == 6
        ]

        for day in sundays:
            var = tk.BooleanVar(value=day in self.shop_config.trade_sundays)
            self.sunday_vars[day] = var

            ttk.Checkbutton(
                tab,
                text=f"{day}.{self.shop_config.month}.{self.shop_config.year}",
                variable=var
            ).pack(anchor="w", padx=10, pady=4)

    # ==================================================
    def _close(self):
        # zapis godzin
        try:
            for wd, (sv, ev) in self.open_vars.items():
                s = sv.get().strip()
                e = ev.get().strip()
                if not s or not e:
                    raise ValueError("Godziny nie mogą być puste")
                self.shop_config.open_hours[wd] = (s, e)
        except Exception as ex:
            messagebox.showerror("Błąd", str(ex))
            return

        # zapis niedziel
        self.shop_config.trade_sundays = {
            day for day, var in self.sunday_vars.items() if var.get()
        }

        self.on_save()
        self.destroy()
