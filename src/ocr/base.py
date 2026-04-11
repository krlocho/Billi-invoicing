from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedTransaction:
    date: str
    value_date: str | None = None
    description: str = ""
    amount: float = 0.0
    balance: float | None = None
    raw_text: str = ""


@dataclass
class BankStatementResult:
    transactions: list[ExtractedTransaction] = field(default_factory=list)
    raw_text: str = ""
    bank_detected: str | None = None
    errors: list[str] = field(default_factory=list)


class OCRStrategy(ABC):
    @abstractmethod
    def extract(self, pdf_path: str) -> BankStatementResult:
        ...
