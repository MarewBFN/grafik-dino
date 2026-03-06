import tkinter as tk

class Tooltip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None

        # zapamiętaj ID bindingów
        self._enter_id = widget.bind("<Enter>", self.show)
        self._leave_id = widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip or not self.text:
            return

        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + 15

        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")

        tk.Label(
            self.tip,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Arial", 9)
        ).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

    def destroy(self):
        # usuń tooltip jeśli widoczny
        self.hide()

        # odłącz bindingi
        if self._enter_id:
            self.widget.unbind("<Enter>", self._enter_id)
        if self._leave_id:
            self.widget.unbind("<Leave>", self._leave_id)
