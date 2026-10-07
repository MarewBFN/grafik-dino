"""Globalna blokada scrolla rolką na polach wyboru (QComboBox, QSpinBox,
QDoubleSpinBox, QDateEdit/QTimeEdit) dopóki pole nie ma fokusu - inaczej
najechanie kursorem i przewinięcie strony po cichu zmieniało np. placówkę
pracownika.

Dwa elementy:
- przy Polish polityka fokusu WheelFocus -> StrongFocus, bo z WheelFocus Qt
  nadaje fokus samym kółkiem (przed filtrami), więc sprawdzenie hasFocus()
  nic by nie dało;
- wheel na niesfocusowanym polu: ignore() + True - widget nie zmienia
  wartości, a nieprzyjęte zdarzenie Qt propaguje do rodzica (np.
  QScrollArea), więc strona dalej się przewija."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox

_GUARDED = (QComboBox, QAbstractSpinBox)


class WheelGuard(QObject):
    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.Type.Polish and isinstance(obj, _GUARDED):
            if obj.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                obj.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        elif etype == QEvent.Type.Wheel and isinstance(obj, _GUARDED):
            if not obj.hasFocus():
                event.ignore()
                return True
        return False


def install_wheel_guard(app) -> WheelGuard:
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    return guard
