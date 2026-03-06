import tkinter as tk
from tkinter import ttk, messagebox
from model.employee import Employee


class EmployeeDialog(tk.Toplevel):
    def __init__(self, parent, on_save, employee=None):
        super().__init__(parent)
        self.title("Dodaj pracownika")
        self.resizable(False, False)
        self.on_save = on_save
        self.employee = employee
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

    def _save(self):
        try:
            emp = Employee(
                last_name=self.last_name.get().strip(),
                first_name=self.first_name.get().strip(),
                is_opener=self.is_opener.get(),
                is_meat=self.is_meat.get(),
                daily_hours=self.daily_hours.get(),
            )
            emp.validate()
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self.on_save(emp)
        self.destroy()
