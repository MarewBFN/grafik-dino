"""Dane firmy (Plik -> "Dane firmy", ui/companies_dialog.py) - na razie
używane tylko w nagłówku wniosków urlopowych
(export/leave_request_exporter.py). Firm może być dowolnie wiele; pracownik
wskazuje swoją przez Employee.company_key. Trzymane na poziomie całego
projektu (MonthlyProject.companies), nie w ShopConfig danego miesiąca - firma
nie zmienia się z miesiąca na miesiąc."""

from dataclasses import asdict, dataclass, field
import re
import uuid

COMPANY_FIELDS = ("name", "nip", "street", "postal_code", "city", "phone", "email")


@dataclass
class Company:
    name: str = ""
    nip: str = ""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    phone: str = ""
    email: str = ""
    key: str = field(default_factory=lambda: uuid.uuid4().hex)

    def town(self) -> str:
        return " ".join(part for part in (self.postal_code, self.city) if part)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Nazwa firmy nie może być pusta")
        nip_digits = re.sub(r"[\s-]", "", self.nip)
        if nip_digits and not re.fullmatch(r"\d{10}", nip_digits):
            raise ValueError("NIP musi mieć 10 cyfr")
        if self.postal_code.strip() and not re.fullmatch(r"\d{2}-\d{3}", self.postal_code.strip()):
            raise ValueError("Kod pocztowy musi mieć format 00-000")
        if self.phone.strip() and not re.fullmatch(r"\+?[0-9 ()-]{6,20}", self.phone.strip()):
            raise ValueError("Nieprawidłowy numer telefonu (dozwolone cyfry, spacje, „+”, „-”)")
        email = self.email.strip()
        if email and (email.count("@") != 1 or "." not in email.split("@")[1] or " " in email):
            raise ValueError("Nieprawidłowy adres e-mail")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        values = {name: data.get(name) or "" for name in COMPANY_FIELDS}
        return cls(**values, key=data.get("key") or uuid.uuid4().hex)
