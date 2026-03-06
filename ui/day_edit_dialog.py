import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta


class DayEditDialog(tk.Toplevel):
    def __init__(self, parent, day_schedule, open_start, open_end, daily_hours, on_save):
        super().__init__(parent)
        self.title("Edycja dnia")
        self.resizable(False, False)

        self.daily_hours = daily_hours
        self._manual_end = False
        self._updating_suggestion = False

        self.day_schedule = day_schedule
        self.on_save = on_save

        self.start_h = tk.StringVar()
        self.start_m = tk.StringVar()
        self.end_h = tk.StringVar()
        self.end_m = tk.StringVar()

        self.allowed_times = self._generate_times(open_start, open_end)

        self._prefill()
        self._build()

        self._on_time_change()

    # -----------------------------
    def _generate_times(self, start: str, end: str):
        fmt = "%H:%M"
        s = datetime.strptime(start, fmt)
        e = datetime.strptime(end, fmt)

        times = []
        while s <= e:
            times.append(s.strftime(fmt))
            s += timedelta(minutes=15)
        return times

    def _prefill(self):
        if self.day_schedule.start:
            h, m = self.day_schedule.start.split(":")
            self.start_h.set(h)
            self.start_m.set(m)
        if self.day_schedule.end:
            h, m = self.day_schedule.end.split(":")
            self.end_h.set(h)
            self.end_m.set(m)

    def _build(self):
        pad = {"padx": 10, "pady": 6}

        # --- budowa mapy godzin -> minut
        def split(times):
            hours_map = {}
            for t in times:
                h, m = t.split(":")
                hours_map.setdefault(h, []).append(m)

            hours = sorted(hours_map.keys())
            return hours, hours_map

        hours, self._hours_map = split(self.allowed_times)

        # ---------------- START ----------------
        ttk.Label(self, text="Start").grid(row=0, column=0, **pad)

        ttk.Combobox(self, values=hours,
                     textvariable=self.start_h,
                     width=4, state="readonly")\
            .grid(row=0, column=1, **pad)

        self.start_m_cb = ttk.Combobox(
            self,
            textvariable=self.start_m,
            width=4,
            state="readonly"
        )
        self.start_m_cb.grid(row=0, column=2, **pad)

        # ---------------- KONIEC ----------------
        ttk.Label(self, text="Koniec").grid(row=1, column=0, **pad)

        self.end_h_cb = ttk.Combobox(
            self,
            values=hours,
            textvariable=self.end_h,
            width=4,
            state="readonly"
        )
        self.end_h_cb.grid(row=1, column=1, **pad)

        self.end_m_cb = ttk.Combobox(
            self,
            textvariable=self.end_m,
            width=4,
            state="readonly"
        )
        self.end_m_cb.grid(row=1, column=2, **pad)

        # --- aktualizacja dostępnych minut
        self.start_h.trace_add("write", self._update_minute_options)
        self.end_h.trace_add("write", self._update_minute_options)

        # --- wykrycie ręcznej zmiany końca
        def mark_manual(*_):
            if self._updating_suggestion:
                return
            self._manual_end = True
            self.end_h_cb.configure(foreground="black")
            self.end_m_cb.configure(foreground="black")

        self.end_h.trace_add("write", mark_manual)
        self.end_m.trace_add("write", mark_manual)

        # --- licznik czasu
        self.duration_label = ttk.Label(self, text="Czas pracy: 0:00")
        self.duration_label.grid(row=2, column=0, columnspan=3, pady=(0, 5))

        # --- trigger logiki
        self.start_h.trace_add("write", self._on_time_change)
        self.start_m.trace_add("write", self._on_time_change)
        self.end_h.trace_add("write", self._update_duration_only)
        self.end_m.trace_add("write", self._update_duration_only)

        # --- przyciski
        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, columnspan=3, pady=10)

        ttk.Button(btns, text="Wolne", command=self._set_free)\
            .pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.destroy)\
            .pack(side="right", padx=5)
        ttk.Button(btns, text="Zapisz", command=self._save)\
            .pack(side="right")

        # --- domyślne minuty
        self._update_minute_options()

        if not self.start_m.get() and self.start_h.get():
            self.start_m.set(self._hours_map[self.start_h.get()][0])

        if not self.end_m.get() and self.end_h.get():
            self.end_m.set(self._hours_map[self.end_h.get()][0])

    # -----------------------------
    def _set_free(self):
        self.day_schedule.set_free()
        self.on_save()
        self.destroy()

    def _save(self):
        try:
            start = f"{self.start_h.get()}:{self.start_m.get()}"
            end = f"{self.end_h.get()}:{self.end_m.get()}"
            self.day_schedule.set_hours(start, end)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self.on_save()
        self.destroy()

    # -----------------------------
    def _on_time_change(self, *_):
        if not self.start_h.get() or not self.start_m.get():
            return

        try:
            fmt = "%H:%M"
            start = datetime.strptime(
                f"{self.start_h.get()}:{self.start_m.get()}",
                fmt
            )

            if not self._manual_end:
                suggested = start + timedelta(hours=self.daily_hours)

                self._updating_suggestion = True
                self.end_h.set(suggested.strftime("%H"))
                self.end_m.set(suggested.strftime("%M"))
                self._updating_suggestion = False

                self.end_h_cb.configure(foreground="gray")
                self.end_m_cb.configure(foreground="gray")

            self._update_duration_only()

        except Exception:
            pass

    # -----------------------------
    def _update_duration_only(self, *_):
        if not self.start_h.get() or not self.start_m.get():
            return

        if not self.end_h.get() or not self.end_m.get():
            return

        try:
            fmt = "%H:%M"
            start = datetime.strptime(
                f"{self.start_h.get()}:{self.start_m.get()}",
                fmt
            )
            end = datetime.strptime(
                f"{self.end_h.get()}:{self.end_m.get()}",
                fmt
            )

            duration = end - start
            minutes = int(duration.total_seconds() // 60)

            if minutes >= 0:
                h = minutes // 60
                m = minutes % 60
                self.duration_label.config(
                    text=f"Czas pracy: {h}:{m:02d}"
                )
        except Exception:
            pass

    # -----------------------------
    def _update_minute_options(self, *_):
        h = self.start_h.get()
        if h in self._hours_map:
            values = self._hours_map[h]
            self.start_m_cb["values"] = values

            # 🔥 wymuś ustawienie pierwszej dozwolonej minuty
            if self.start_m.get() not in values:
                self.start_m.set(values[0])

        h_end = self.end_h.get()
        if h_end in self._hours_map:
            values = self._hours_map[h_end]
            self.end_m_cb["values"] = values

            if self.end_m.get() not in values:
                self.end_m.set(values[0])
