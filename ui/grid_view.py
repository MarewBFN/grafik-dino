import tkinter as tk
import calendar
from logic.schedule_presenter import SchedulePresenter
from logic.constraint_presenter import ConstraintPresenter
from ui import theme
from ui.tooltip import Tooltip


class ScheduleGrid:

    def __init__(
        self,
        parent,
        schedule,
        shop_config,
        on_edit_day,
        on_edit_employee,
        on_context_menu,
        on_header_menu,
        on_add_employee,
    ):
        self.parent = parent
        self.schedule = schedule
        self.shop_config = shop_config
        self._row_widgets = {}

        self.on_edit_day = on_edit_day
        self.on_edit_employee = on_edit_employee
        self.on_context_menu = on_context_menu
        self.on_header_menu = on_header_menu
        self.on_add_employee = on_add_employee

        self.frame = tk.Frame(parent, bg=theme.BG_MAIN)

        self._day_labels = {}
        self._total_labels = {}
        self._validation_cells = {}

    # ==================================================
    # PUBLIC API
    # ==================================================

    def build(self):
        self._build_grid()

    def refresh(self):
        self._refresh_values()

    # ==================================================
    # GRID BUILD
    # ==================================================

    def _build_grid(self):

        for w in self.frame.winfo_children():
            w.destroy()

        self._day_labels.clear()
        self._total_labels.clear()
        self._validation_cells.clear()

        if not self.schedule:
            return

        y = self.schedule.year
        m = self.schedule.month
        days = calendar.monthrange(y, m)[1]

        names = ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"]

        # ===== KOLUMNY DYNAMICZNE =====
        self.frame.grid_columnconfigure(0, weight=0, minsize=180)

        for col in range(1, days + 1):
            self.frame.grid_columnconfigure(col, weight=0, minsize=50)

        self.frame.grid_columnconfigure(days + 1, weight=0, minsize=70)

        # ===== HEADER PLUS =====
        plus = tk.Label(
            self.frame,
            text="+",
            bg=theme.BG_HEADER,
            cursor="hand2",
            highlightbackground=theme.GRID_BORDER,
            highlightthickness=1
        )
        plus.grid(row=0, column=0, rowspan=2, sticky="nsew")
        plus.bind("<Button-1>", lambda e: self.on_add_employee())

        # ===== HEADER DNI =====
        for d in range(1, days + 1):

            wd = calendar.weekday(y, m, d)

            if d in self.shop_config.public_holidays:
                bg = theme.BG_DISABLED
            elif not self.shop_config.is_trade_day(d):
                bg = theme.BG_DISABLED
            else:
                bg = theme.BG_WEEKEND if wd >= 5 else theme.BG_HEADER

            header = tk.Frame(
                self.frame,
                bg=bg,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            header.grid(row=0, column=d, rowspan=2, sticky="nsew")

            lbl_wd = tk.Label(header, text=names[wd], bg=bg)
            lbl_day = tk.Label(header, text=str(d), bg=bg)

            lbl_wd.pack(expand=True)
            lbl_day.pack(expand=True)

            if d in self.shop_config.day_overrides:
                tk.Label(header, text="🕒", bg=bg).pack()

            header.bind("<Button-3>", lambda ev, day=d: self.on_header_menu(ev, day))
            lbl_wd.bind("<Button-3>", lambda ev, day=d: self.on_header_menu(ev, day))
            lbl_day.bind("<Button-3>", lambda ev, day=d: self.on_header_menu(ev, day))

        # ===== KOLUMNY SUM =====
        headers = ["Praca", "Urlop", "Razem"]

        for i, title in enumerate(headers):
            col = days + 1 + i
            self.frame.grid_columnconfigure(col, weight=0, minsize=70)

            lbl = tk.Label(
                self.frame,
                text=title,
                bg=theme.BG_HEADER,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            lbl.grid(row=0, column=col, rowspan=2, sticky="nsew")

        start_row = 2

        # ===== EMPLOYEES =====
        for r, emp in enumerate(self.schedule.employees):

            row = start_row + r

            name_frame = tk.Frame(self.frame, bg=theme.BG_MAIN)
            name_frame.grid(row=row, column=0, sticky="nsew")
            self._row_widgets[emp] = [name_frame]

            name_label = tk.Label(
                name_frame,
                text=emp.display_name(),
                bg=theme.BG_MAIN,
                anchor="w",
                cursor="hand2"
            )
            name_label.pack(side="left", padx=(4, 2))

            icons = ""
            if emp.is_opener:
                icons += "🕓 "
            if emp.is_meat:
                icons += "🥩"

            icon_label = tk.Label(
                name_frame,
                text=icons,
                bg=theme.BG_MAIN,
                cursor="hand2"
            )
            icon_label.pack(side="left")

            for widget in (name_frame, name_label, icon_label):
                widget.bind(
                    "<Double-Button-1>",
                    lambda e, emp=emp: self.on_edit_employee(emp)
                )

            for d in range(1, days + 1):

                if d in self.shop_config.public_holidays:
                    cell_bg = theme.BG_DISABLED
                elif not self.shop_config.is_trade_day(d):
                    cell_bg = theme.BG_DISABLED
                else:
                    cell_bg = theme.BG_MAIN

                height = 32 if self.shop_config.cell_display_mode == "compact" else 55

                cell = tk.Frame(
                    self.frame,
                    bg=cell_bg,
                    height=height,
                    highlightbackground=theme.GRID_BORDER,
                    highlightthickness=1
                )
                cell.grid(row=row, column=d, sticky="nsew")
                cell.grid_propagate(False)

                self._row_widgets[emp].append(cell)

                lbl_start = tk.Label(cell, bg=cell_bg, anchor="center")
                lbl_end = tk.Label(cell, bg=cell_bg, anchor="center")
                lbl_total = tk.Label(
                    cell,
                    bg=cell_bg,
                    font=("Arial", 8, "bold"),
                    anchor="center"
                )

                cell.rowconfigure(0, weight=1)
                cell.rowconfigure(1, weight=1)
                cell.rowconfigure(2, weight=1)
                cell.columnconfigure(0, weight=1)

                lbl_start.grid(row=0, column=0, sticky="nsew")
                lbl_end.grid(row=1, column=0, sticky="nsew")
                lbl_total.grid(row=2, column=0, sticky="nsew")

                self._day_labels[(emp, d)] = (lbl_start, lbl_end, lbl_total)

                if self.shop_config.is_trade_day(d):

                    def bind_all(widget):
                        widget.bind(
                            "<Button-1>",
                            lambda ev, emp=emp, day=d:
                            self.on_edit_day(emp, day)
                        )
                        widget.bind(
                            "<Button-3>",
                            lambda ev, emp=emp, day=d:
                            self.on_context_menu(ev, emp, day)
                        )

                    bind_all(cell)
                    bind_all(lbl_start)
                    bind_all(lbl_end)
                    bind_all(lbl_total)

                    for widget in (cell, lbl_start, lbl_end, lbl_total):
                        widget.bind(
                            "<Enter>",
                            lambda e, emp=emp, day=d:
                            self._hover_enter(emp, day)
                        )
                        widget.bind(
                            "<Leave>",
                            lambda e, emp=emp, day=d:
                            self._hover_leave(emp, day)
                        )

            # ===== 3 KOLUMNY SUM =====
            work_lbl = tk.Label(
                self.frame,
                text="",
                anchor="center",
                bg=theme.BG_MAIN,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            work_lbl.grid(row=row, column=days + 1, sticky="nsew")

            leave_lbl = tk.Label(
                self.frame,
                text="",
                anchor="center",
                bg=theme.BG_MAIN,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            leave_lbl.grid(row=row, column=days + 2, sticky="nsew")

            total_lbl = tk.Label(
                self.frame,
                text="",
                anchor="center",
                bg=theme.BG_MAIN,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            total_lbl.grid(row=row, column=days + 3, sticky="nsew")

            self._total_labels[emp] = (work_lbl, leave_lbl, total_lbl)


        # ===== VALIDATION ROWS =====
        val_row = start_row + len(self.schedule.employees)

        for label, key in [("Otwarcie", "open"),
                        ("Zamknięcie", "close"),
                        ("Mięso", "meat")]:

            lbl = tk.Label(
                self.frame,
                text=label,
                anchor="w",
                bg=theme.BG_HEADER,
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
            lbl.grid(row=val_row, column=0, sticky="nsew")

            for d in range(1, days + 1):
                cell = tk.Label(
                    self.frame,
                    bg=theme.BG_MAIN,
                    highlightbackground=theme.GRID_BORDER,
                    highlightthickness=1
                )
                cell.grid(row=val_row, column=d, sticky="nsew")
                self._validation_cells[(key, d)] = cell

            val_row += 1

        self._refresh_values()

    # ==================================================
    # REFRESH
    # ==================================================

    def _refresh_values(self):

        if not self.schedule:
            return

        presenter = SchedulePresenter(self.schedule, self.shop_config)
        constraint_presenter = ConstraintPresenter(
            self.schedule,
            self.shop_config
        )

        y = self.schedule.year
        m = self.schedule.month
        days = calendar.monthrange(y, m)[1]

        for emp in self.schedule.employees:

            for d in range(1, days + 1):

                lbl_start, lbl_end, lbl_total = self._day_labels[(emp, d)]
                ds = self.schedule.get_day(emp, d)

                # ===== URLOP =====
                if ds.is_leave:
                    lbl_start.config(text="🌴", anchor="center", justify="center")
                    lbl_end.config(text="")
                    lbl_total.config(text="")

                    for lbl in (lbl_start, lbl_end, lbl_total):
                        lbl.config(bg=theme.BG_MAIN)

                    continue

                # ===== STANDARDOWE WYŚWIETLANIE =====
                cell_view = presenter.get_cell_view(emp, d)

                lbl_start.config(text=cell_view.text_start, anchor="center", justify="center")
                lbl_end.config(text=cell_view.text_end, anchor="center", justify="center")
                lbl_total.config(text=cell_view.text_total)

                if ds.is_locked:
                    bg = "#afa9a9"  # czerwony = LOCKED
                elif ds.is_leave:
                    bg = "#9999ff"  # opcjonalnie urlop
                else:
                    bg = cell_view.bg

                for lbl in (lbl_start, lbl_end, lbl_total):
                    lbl.config(bg=bg)

                for lbl in (lbl_start, lbl_end, lbl_total):
                    if hasattr(lbl, "_tooltip") and lbl._tooltip:
                        lbl._tooltip.destroy()
                        lbl._tooltip = None

                if cell_view.tooltip:
                    for lbl in (lbl_start, lbl_end, lbl_total):
                        lbl._tooltip = Tooltip(lbl, cell_view.tooltip)

                # BŁĄD KOMÓRKI PRACOWNIKA
                if constraint_presenter.get_cell_error(emp, d):
                    for lbl in (lbl_start, lbl_end, lbl_total):
                        lbl.config(bg=theme.ERR_RED)

            work_lbl, leave_lbl, total_lbl = self._total_labels[emp]

            work_lbl.config(
                text=self.schedule.total_hours_for_employee(emp)
            )

            leave_lbl.config(
                text=self.schedule.leave_hours_for_employee(emp)
            )

            total_lbl.config(
                text=self.schedule.total_with_leave_for_employee(emp)
            )



        # ===== RESET VALIDATION CELLS =====
        for cell in self._validation_cells.values():
            cell.config(bg=theme.BG_MAIN, text="")
            if hasattr(cell, "_tooltip") and cell._tooltip:
                cell._tooltip.destroy()
                cell._tooltip = None

        # ===== VALIDATION ROWS Z PRESENTERA =====
        for key in ("open", "close", "meat"):
            for d in range(1, days + 1):

                cell = self._validation_cells.get((key, d))
                if not cell:
                    continue

                # 🔹 dzień niehandlowy → wyszarz i pomiń walidację
                if d in self.shop_config.public_holidays or not self.shop_config.is_trade_day(d):
                    cell.config(bg=theme.BG_DISABLED)

                    if hasattr(cell, "_tooltip") and cell._tooltip:
                        cell._tooltip.destroy()
                        cell._tooltip = None

                    continue

                view = constraint_presenter.get_validation_cell_view(key, d)

                cell.config(bg=view.bg)

                if hasattr(cell, "_tooltip") and cell._tooltip:
                    cell._tooltip.destroy()
                    cell._tooltip = None

                if view.tooltip:
                    cell._tooltip = Tooltip(cell, view.tooltip)

    # ==================================================
    # HOVER
    # ==================================================

    def _hover_enter(self, emp, day):

        if not self.shop_config.is_trade_day(day):
            return

        lbls = self._day_labels.get((emp, day))
        if not lbls:
            return

        # podświetlenie komórki
        for lbl in lbls:
            if lbl.cget("bg") != theme.ERR_RED:
                lbl.config(bg="#e2e8f0")

        # czarna obramówka całego wiersza
        row_widgets = self._row_widgets.get(emp, [])

        if not row_widgets:
            return

        first = row_widgets[0]
        last = row_widgets[-1]

        for widget in row_widgets:
            widget.config(highlightthickness=0)

        # lewa krawędź
        first.config(highlightbackground="black", highlightthickness=2)

        # prawa krawędź
        last.config(highlightbackground="black", highlightthickness=2)

        # góra i dół – wszystkie
        for widget in row_widgets:
            widget.config(highlightbackground="black", highlightthickness=1)

    def _hover_leave(self, emp, day):

        lbls = self._day_labels.get((emp, day))
        if not lbls:
            return

        ds = self.schedule.get_day(emp, day)
        hours = self.shop_config.get_open_hours_for_day(day)

        if not self.shop_config.is_trade_day(day):
            base = theme.BG_DISABLED
        else:
            base = theme.BG_MAIN

        if ds.is_locked:
            base = "#afa9a9"
        elif hours and not ds.is_empty():
            open_t, close_t = hours

            if ds.start == open_t:
                base = theme.SHIFT_MORNING
            elif ds.end == close_t:
                base = theme.SHIFT_CLOSE

        for lbl in lbls:
            if lbl.cget("bg") != theme.ERR_RED:
                lbl.config(bg=base)

        # reset obramówki wiersza
        for widget in self._row_widgets.get(emp, []):
            widget.config(
                highlightbackground=theme.GRID_BORDER,
                highlightthickness=1
            )
