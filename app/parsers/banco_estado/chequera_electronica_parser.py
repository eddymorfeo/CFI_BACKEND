import re
import unicodedata
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoEstadoChequeraElectronicaParser(BaseParser):
    ROW_PATTERN = re.compile(
        r"^(?P<document_number>\d{7})\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<branch>\d{3})\s+"
        r"(?P<amount>\d{1,3}(?:\.\d{3})*|\d+)\s+"
        r"(?P<date>\d{2}/\d{2})\s+"
        r"(?P<balance>\d{1,3}(?:\.\d{3})*|\d+)$"
    )

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._normalize_for_detection(first_page_text)

        return (
            "CARTOLA HISTORICA" in normalized_text
            and "CHEQUERA ELECTRONICA" in normalized_text
            and "CUENTA VISTA" in normalized_text
            and "SALDO ANTERIOR" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)

        with pdfplumber.open(path) as pdf:
            pages = [
                {
                    "page_number": page_index + 1,
                    "text": page.extract_text() or "",
                }
                for page_index, page in enumerate(pdf.pages)
            ]

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages, document_metadata)

        return {
            "parser_code": "BANCO_ESTADO_CHEQUERA_ELECTRONICA",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"] if pages else ""
        compact_text = self._clean_text(first_page_text)

        holder_name = None
        account_number = None
        document_date_from = None
        document_date_to = None
        previous_balance = Decimal("0")

        holder_period_match = re.search(
            r"NOMBRE\s+DESDE\s+HASTA\s+(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
            compact_text,
            re.IGNORECASE,
        )
        if holder_period_match:
            holder_name = self._clean_text(holder_period_match.group(1))
            document_date_from = self._parse_date(holder_period_match.group(2), "%d/%m/%Y")
            document_date_to = self._parse_date(holder_period_match.group(3), "%d/%m/%Y")

        account_match = re.search(
            r"CUENTA\s+VISTA\s+OFICINA\s+MONEDA\s+([0-9-]+)\s+",
            compact_text,
            re.IGNORECASE,
        )
        if account_match:
            account_number = account_match.group(1)

        previous_balance_match = re.search(
            r"SALDO\s+ANTERIOR\s+(\d{1,3}(?:\.\d{3})*|\d+)",
            compact_text,
            re.IGNORECASE,
        )
        if previous_balance_match:
            previous_balance = self._parse_amount(previous_balance_match.group(1))

        return {
            "detected_institution_name": "BancoEstado",
            "detected_holder_name": holder_name,
            "detected_account_number": account_number,
            "document_date_from": document_date_from,
            "document_date_to": document_date_to,
            "previous_balance": previous_balance,
        }

    def _extract_movements(self, pages: list[dict], document_metadata: dict) -> list[dict]:
        movements: list[dict] = []
        row_number = 1
        previous_balance = document_metadata.get("previous_balance") or Decimal("0")
        date_from = document_metadata.get("document_date_from")
        date_to = document_metadata.get("document_date_to")

        for page in pages:
            page_number = page["page_number"]
            in_movements = False

            for raw_line in page["text"].splitlines():
                line = self._clean_text(raw_line)
                line_upper = self._normalize_for_detection(line)

                if not in_movements:
                    if "N DOCTO" in line_upper and "DESCRIPCION" in line_upper:
                        in_movements = True
                    continue

                if line_upper.startswith("RESUMEN DEL PERIODO"):
                    break

                parsed_row = self._parse_movement_line(
                    line=line,
                    previous_balance=previous_balance,
                    row_number=row_number,
                    page_number=page_number,
                    date_from=date_from,
                    date_to=date_to,
                )
                if parsed_row is None:
                    continue

                movements.append(parsed_row)
                previous_balance = parsed_row["balance_amount"]
                row_number += 1

        return movements

    def _parse_movement_line(
        self,
        line: str,
        previous_balance: Decimal,
        row_number: int,
        page_number: int,
        date_from,
        date_to,
    ) -> dict | None:
        row_match = self.ROW_PATTERN.match(line)
        if not row_match:
            return None

        document_number = row_match.group("document_number")
        description = self._clean_text(row_match.group("description"))
        branch = row_match.group("branch")
        movement_amount = self._parse_amount(row_match.group("amount"))
        balance_amount = self._parse_amount(row_match.group("balance"))

        charge_amount, deposit_amount = self._split_amount_by_balance(
            movement_amount=movement_amount,
            previous_balance=previous_balance,
            balance_amount=balance_amount,
            description=description,
        )

        detected_movement_type = self._detect_movement_type(description)

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": self._resolve_date(row_match.group("date"), date_from, date_to),
            "branch": branch,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": line,
            "raw_row_json": {
                "page_number": page_number,
                "previous_balance": str(previous_balance),
                "movement_amount": str(movement_amount),
                "source_format": "BANCO_ESTADO_CHEQUERA_ELECTRONICA",
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.99"),
        }

    def _split_amount_by_balance(
        self,
        movement_amount: Decimal,
        previous_balance: Decimal,
        balance_amount: Decimal,
        description: str,
    ) -> tuple[Decimal, Decimal]:
        if previous_balance + movement_amount == balance_amount:
            return Decimal("0"), movement_amount

        if previous_balance - movement_amount == balance_amount:
            return movement_amount, Decimal("0")

        movement_type = self._detect_movement_type(description)
        if movement_type in {"TRANSFER_IN", "DEPOSIT"}:
            return Decimal("0"), movement_amount

        return movement_amount, Decimal("0")

    def _resolve_date(self, raw_date: str, date_from, date_to):
        day = int(raw_date[:2])
        month = int(raw_date[3:5])

        if date_from is None or date_to is None:
            return datetime(datetime.now().year, month, day).date()

        if date_from.year == date_to.year:
            return datetime(date_from.year, month, day).date()

        year = date_from.year if month >= date_from.month else date_to.year
        return datetime(year, month, day).date()

    def _detect_movement_type(self, description: str) -> str:
        description_upper = self._normalize_for_detection(description)

        if "TEF BANCOESTADO A " in description_upper or description_upper.startswith("TRANSF A "):
            return "TRANSFER_OUT"

        if "TEF BANCOESTADO DE " in description_upper or description_upper.startswith("TEF DE "):
            return "TRANSFER_IN"

        if "COMPRA" in description_upper or "PAGO " in description_upper:
            return "PURCHASE"

        if "BONO " in description_upper or description_upper.startswith("BCO "):
            return "DEPOSIT"

        return "UNKNOWN"

    def _parse_amount(self, raw_amount: str | None) -> Decimal:
        if raw_amount is None:
            return Decimal("0")

        normalized_amount = str(raw_amount).replace(".", "").replace(" ", "").strip()
        if normalized_amount in {"", "-"}:
            return Decimal("0")

        return Decimal(normalized_amount)

    def _parse_date(self, raw_date: str, fmt: str):
        return datetime.strptime(raw_date, fmt).date()

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())

    def _normalize_for_detection(self, value: str) -> str:
        decomposed_value = unicodedata.normalize("NFD", str(value))
        without_accents = "".join(
            character for character in decomposed_value
            if unicodedata.category(character) != "Mn"
        )
        return self._clean_text(without_accents).upper().replace("N°", "N")
