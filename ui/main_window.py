import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import date

from model.month_schedule import MonthSchedule
from model.shop_config import ShopConfig
from export.excel_exporter import export_schedule_to_excel
from persistence.project_io import save_project, load_project
from ui.config_dialog import ConfigDialog
from ui.employee_dialog import EmployeeDialog
from ui.day_edit_dialog import DayEditDialog
from ui.day_override_dialog import DayOverrideDialog
from ui import theme
from ui.grid_view import ScheduleGrid
from logic.schedule_controller import ScheduleController

class MainWindow:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Grafik Dino v2")
        self.root.geometry("1200x800")

        today = date.today()
        self.year_var = tk.IntVar(value=today.year)
        self.month_var = tk.IntVar(value=today.month)

        self.schedule: MonthSchedule | None = None
        self.shop_config: ShopConfig | None = None
        self._clipboard_day = None


        self._build_ui()
        self._init_state()

        # GRID
        self.grid = ScheduleGrid(
            parent=self.schedule_frame,
            schedule=self.schedule,
            shop_config=self.shop_config,
            on_edit_day=self._edit_day,
            on_edit_employee=self._edit_employee,
            on_context_menu=self._open_context_menu,
            on_header_menu=self._open_header_menu,
            on_add_employee=self._open_add_employee,
        )

        self.grid.frame.pack(fill="both", expand=True)
        self.grid.build()
        self.grid.refresh()
        self._try_load_last_project()

    # ==================================================
    # INIT / UNDO
    # ==================================================

    def _init_state(self):
        self.schedule = MonthSchedule(
            self.year_var.get(),
            self.month_var.get()
        )
        self.shop_config = ShopConfig(
            self.year_var.get(),
            self.month_var.get()
        )
        self.controller = ScheduleController(self.schedule, self.shop_config)
        self._update_nominal_hours_label()

    def _undo(self):
        new_schedule = self.controller.undo()
        self.schedule = new_schedule

        self.grid.schedule = self.schedule
        self.grid.build()
        self.grid.refresh()

    # ==================================================
    # UI
    # ==================================================

    def _build_ui(self):

        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Grafik na:").pack(side="left")

        ttk.Spinbox(
            top,
            from_=1,
            to=12,
            width=5,
            textvariable=self.month_var,
            command=self._on_date_change
        ).pack(side="left", padx=5)

        ttk.Spinbox(
            top,
            from_=2024,
            to=2035,
            width=7,
            textvariable=self.year_var,
            command=self._on_date_change
        ).pack(side="left")

        ttk.Button(
            top,
            text="Konfiguracja",
            command=self._open_config
        ).pack(side="left", padx=10)

        ttk.Button(
            top,
            text="Generuj grafik",
            command=self._generate_schedule
        ).pack(side="left", padx=5)

        self.nominal_hours_var = tk.StringVar()

        self.nominal_hours_label = tk.Label(
            top,
            textvariable=self.nominal_hours_var,
            bg=theme.BG_MAIN
        )
        self.nominal_hours_label.pack(side="left", padx=15)

        self._update_nominal_hours_label()

        # ===== CONTAINER =====
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=10, pady=5)

        # ===== CANVAS =====
        self.canvas = tk.Canvas(container, bg=theme.BG_MAIN)
        self.canvas.pack(side="left", fill="both", expand=True)

        # ===== PIONOWY SCROLL =====
        scrollbar_y = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.canvas.yview
        )
        scrollbar_y.pack(side="right", fill="y")

        # ===== POZIOMY SCROLL =====
        scrollbar_x = ttk.Scrollbar(
            self.root,
            orient="horizontal",
            command=self.canvas.xview
        )
        scrollbar_x.pack(fill="x")

        self.canvas.configure(
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set
        )

        # ===== FRAME W CANVAS =====
        self.schedule_frame = ttk.Frame(self.canvas)

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.schedule_frame,
            anchor="nw"
        )

        # ===== AUTO AKTUALIZACJA SCROLL REGION =====
        def _on_frame_configure(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        self.schedule_frame.bind("<Configure>", _on_frame_configure)

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")

        ttk.Button(bottom, text="Cofnij",
                command=self._undo).pack(side="left")
        
        ttk.Button(
            bottom,
            text="Wyczyść grafik",
            command=self._clear_schedule
        ).pack(side="left", padx=5)

        ttk.Button(bottom, text="Zapisz",
                command=self._save_project).pack(side="left", padx=5)

        ttk.Button(bottom, text="Wczytaj",
                command=self._load_project).pack(side="left")

        ttk.Button(bottom, text="Eksport Excel",
                command=self._export_excel).pack(side="left", padx=10)


    # ==================================================
    # DATE / CONFIG
    # ==================================================

    def _on_date_change(self):
        old_employees = self.schedule.employees if self.schedule else []

        self._init_state()

        for emp in old_employees:
            self.schedule.add_employee(emp)

        self.grid.schedule = self.schedule
        self.grid.shop_config = self.shop_config
        self.grid.build()
        self.grid.refresh()
        self._update_nominal_hours_label()

    def _open_config(self):
        ConfigDialog(
            self.root,
            self.shop_config,
            on_save=self._render_schedule
        )

    def _render_schedule(self):
        self.grid.shop_config = self.shop_config
        self.grid.build()
        self.grid.refresh()

    # ==================================================
    # EMPLOYEE
    # ==================================================

    def _open_add_employee(self):
        EmployeeDialog(self.root, self._add_employee)

    def _add_employee(self, emp):
        def action():
            self.controller.add_employee(emp)

        action()
        self.grid.build()
        self.grid.refresh()

    def _edit_employee(self, emp):
        EmployeeDialog(
            self.root,
            lambda new_emp: self._replace_employee(emp, new_emp),
            employee=emp
        )

    def _replace_employee(self, old, new):
        def action():
            self.controller.replace_employee(old, new)

        action()
        self.grid.build()
        self.grid.refresh()

    # ==================================================
    # DAY EDIT
    # ==================================================

    def _edit_day(self, emp, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return

        ds = self.controller.get_day(emp, day)

        DayEditDialog(
            self.root,
            ds,
            hours[0],
            hours[1],
            emp.daily_hours,
            on_save=lambda: self.grid.refresh()
        )

    # ==================================================
    # INTERNAL ACTION WRAPPER
    # ==================================================
    def _apply_and_refresh(self, action):
        action()
        self.grid.refresh()

    # ==================================================
    # CONTEXT MENU
    # ==================================================

    def _open_context_menu(self, event, emp, day):
        if not self.shop_config.is_trade_day(day):
            return

        menu = tk.Menu(self.root, tearoff=0)

        menu.add_command(
            label="🌅 Rano",
            command=lambda: self._ctx_morning(emp, day)
        )

        menu.add_command(
            label="🌇 Zamknięcie",
            command=lambda: self._ctx_close(emp, day)
        )

        menu.add_separator()

        menu.add_command(
            label="📋 Kopiuj dzień",
            command=lambda: self._ctx_copy(emp, day)
        )

        menu.add_command(
            label="📌 Wklej dzień",
            command=lambda: self._ctx_paste(emp, day)
        )

        menu.add_separator()

        menu.add_command(
            label="❌ Ustaw wolne",
            command=lambda: self._ctx_free(emp, day)
        )

        menu.add_command(
            label="🌴 Urlop",
            command=lambda: self._ctx_leave(emp, day)
        )


        menu.tk_popup(event.x_root, event.y_root)

    def _ctx_free(self, emp, day):
        self._apply_and_refresh(
            lambda: self.controller.set_day_free(emp, day)
        )

    def _ctx_leave(self, emp, day):
        self._apply_and_refresh(
            lambda: self.controller.set_day_leave(emp, day)
        )


    def _ctx_morning(self, emp, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return

        start = hours[0]
        end = self._calc_end_from_daily(start, emp.daily_hours)

        self._apply_and_refresh(
            lambda: self.controller.set_day_hours(emp, day, start, end)
        )

    def _ctx_close(self, emp, day):
        hours = self.shop_config.get_open_hours_for_day(day)
        if not hours:
            return

        end = hours[1]
        start = self._calc_start_from_daily(end, emp.daily_hours)

        self._apply_and_refresh(
            lambda: self.controller.set_day_hours(emp, day, start, end)
        )

    # ==================================================
    # HEADER MENU
    # ==================================================

    def _open_header_menu(self, event, day):

        # spróbuj pobrać godziny normalnie
        hours = self.shop_config.get_open_hours_for_day(day)

        # jeśli dzień niehandlowy → pobierz bazowe godziny z tygodnia
        if not hours:
            weekday = self.shop_config.weekday(day)
            hours = self.shop_config.get_open_hours_for_weekday(weekday)

        def save_override(start, end):
            self.controller.snapshot()
            self.shop_config.day_overrides[day] = (start, end)
            self._update_nominal_hours_label()
            self.grid.build()
            self.grid.refresh()

        DayOverrideDialog(
            self.root,
            day,
            hours,
            self.shop_config,
            on_save=save_override
        )


    # ==================================================
    # SAVE / LOAD / EXPORT
    # ==================================================

    def _save_project(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Projekt grafiku", "*.json")]
        )
        if not path:
            return

        # normalny zapis
        save_project(path, self.schedule, self.shop_config)

        # zapis jako ostatni projekt
        save_project("last_project.json", self.schedule, self.shop_config)

    def _load_project(self):
        path = filedialog.askopenfilename(
            filetypes=[("Projekt grafiku", "*.json")]
        )
        if not path:
            return

        self.schedule, self.shop_config = load_project(path)

        # 🔥 NOWY CONTROLLER DLA NOWEGO PROJEKTU
        self.controller = ScheduleController(
            self.schedule,
            self.shop_config
        )

        self.year_var.set(self.schedule.year)
        self.month_var.set(self.schedule.month)

        self.grid.schedule = self.schedule
        self.grid.shop_config = self.shop_config

        self.grid.build()
        self.grid.refresh()
        self._update_nominal_hours_label()


    def _export_excel(self):
        if not self.schedule.employees:
            messagebox.showinfo("Eksport", "Brak danych.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )

        if path:
            export_schedule_to_excel(
                self.schedule,
                self.year_var.get(),
                self.month_var.get(),
                path
            )

    # ==================================================
    # TIME HELPERS
    # ==================================================

    def _calc_end_from_daily(self, start_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        start = datetime.strptime(start_str, fmt)
        end = start + timedelta(hours=hours)
        return end.strftime(fmt)

    def _calc_start_from_daily(self, end_str, hours):
        from datetime import datetime, timedelta
        fmt = "%H:%M"
        end = datetime.strptime(end_str, fmt)
        start = end - timedelta(hours=hours)
        return start.strftime(fmt)

    def _ctx_copy(self, emp, day):
        ds = self.controller.get_day(emp, day)
        if ds.is_empty():
            self._clipboard_day = None
        else:
            self._clipboard_day = (ds.start, ds.end)


    def _ctx_paste(self, emp, day):
        if not self._clipboard_day:
            return

        start, end = self._clipboard_day

        self._apply_and_refresh(
            lambda: self.controller.set_day_hours(emp, day, start, end)
        )

    def _try_load_last_project(self):
        import os

        if not os.path.exists("last_project.json"):
            return

        try:
            self.schedule, self.shop_config = load_project("last_project.json")

            # 🔥 NOWY CONTROLLER
            self.controller = ScheduleController(self.schedule, self.shop_config)

            self.year_var.set(self.schedule.year)
            self.month_var.set(self.schedule.month)

            self.grid.schedule = self.schedule
            self.grid.shop_config = self.shop_config

            self.grid.build()
            self._update_nominal_hours_label()
            self.grid.refresh()

        except Exception:
            pass

    def _generate_schedule(self):
        self.controller.generate_schedule()

        # 🔥 zawsze zsynchronizuj referencję
        self.schedule = self.controller.schedule
        self.grid.schedule = self.schedule
        self.grid.shop_config = self.shop_config

        self.grid.build()
        self.grid.refresh()

    def _update_nominal_hours_label(self):
        if not self.shop_config:
            self.nominal_hours_var.set("")
            return

        hours = self.shop_config.get_full_time_nominal_hours()
        self.nominal_hours_var.set(f"Nominalny etat: {hours} h")

    def _clear_schedule(self):
        self.controller.clear_schedule()

        self.schedule = self.controller.schedule
        self.grid.schedule = self.schedule

        self.grid.build()
        self.grid.refresh()