"""model/employee.py::Employee - imię jest opcjonalne (klient może nie
znać/nie chcieć podawać imion pracowników), tylko nazwisko jest wymagane
- patrz też ui/employee_dialog.py::_save()."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.employee import Employee


class ValidateTests(unittest.TestCase):
    def test_missing_first_name_does_not_raise(self):
        emp = Employee(last_name="Kowalski", first_name="")
        emp.validate()  # nie powinno rzucić

    def test_missing_last_name_still_raises(self):
        emp = Employee(last_name="", first_name="Jan")
        with self.assertRaises(ValueError):
            emp.validate()

    def test_blank_last_name_still_raises(self):
        emp = Employee(last_name="   ", first_name="Jan")
        with self.assertRaises(ValueError):
            emp.validate()

    def test_both_names_present_is_still_valid(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        emp.validate()  # nie powinno rzucić


class DisplayNameTests(unittest.TestCase):
    def test_both_names_present(self):
        emp = Employee(last_name="Kowalski", first_name="Jan")
        self.assertEqual(emp.display_name(), "Kowalski Jan")

    def test_missing_first_name_has_no_trailing_space(self):
        emp = Employee(last_name="Kowalski", first_name="")
        self.assertEqual(emp.display_name(), "Kowalski")


if __name__ == "__main__":
    unittest.main()
