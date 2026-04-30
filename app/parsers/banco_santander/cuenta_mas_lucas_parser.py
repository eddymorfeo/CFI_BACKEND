import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoSantanderCuentaMasLucasParser(BaseParser):
    DATE_DDMMYYYY_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    PERIOD_PATTERN = re.compile(
        r"SALDO\s+INICIAL\s+AL\s+(\d{2}/\d{2}/\d{4}).*?"
        r"SALDO\s+FINAL\s+AL\s+(\d{2}/\d{2}/\d{4})",
        re.IGNORECASE | re.DOTALL,
    )

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._normalize_for_detection(first_page_text)

        return (
            "SANTANDER" in normalized_text
            and "CUENTA MAS LUCAS" in normalized_text
            and "RESUMEN DEL PERIODO" in normalized_text
            and "FECHA MOV. DESCRIPCION CARGOS ABONOS SALDO" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)
        pages = self._extract_pages(path)

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages)

        document_metadata["detected_statement_type"] = "CUENTA_MAS_LUCAS"

        return {
            "parser_code": "BANCO_SANTANDER_CUENTA_MAS_LUCAS",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_pages(self, path: Path) -> list[dict]:
        pages = []

        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words(
                    x_tolerance=1,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                lines = self._group_words_by_line(words)
                text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""

                pages.append(
                    {
                        "page_number": page_index + 1,
                        "text": text,
                        "lines": lines,
                        "period": self._extract_page_period(text),
                    }
                )

        return pages

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"] if pages else ""
        first_page_lines = pages[0]["lines"] if pages else []
        compact_text = self._clean_text(first_page_text)

        account_number_match = re.search(r"\b\d-\d{3}-\d{2}-\d{5}-\d\b", compact_text)
        periods = [page["period"] for page in pages if page["period"] is not None]
        document_date_from = min(period[0] for period in periods) if periods else None
        document_date_to = max(period[1] for period in periods) if periods else None

        return {
            "detected_institution_name": "Banco Santander",
            "detected_holder_name": self._extract_holder_name(first_page_lines),
            "detected_account_number": account_number_match.group(0) if account_number_match else None,
            "detected_account_type": "CUENTA MAS LUCAS",
            "document_date_from": document_date_from,
            "document_date_to": document_date_to,
        }

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements: list[dict] = []
        row_number = 1

        for page in pages:
            in_table = False

            for line in page["lines"]:
                line_text = self._line_text(line)
                normalized_line = self._normalize_for_detection(line_text)

                if not in_table:
                    if (
                        "FECHA" in normalized_line
                        and "MOV." in normalized_line
                        and "DESCRIPCION" in normalized_line
                    ):
                        in_table = True
                    continue

                if self._is_stop_line(normalized_line):
                    break

                parsed_row = self._parse_movement_line(
                    line=line,
                    row_number=row_number,
                    page_number=page["page_number"],
                )
                if parsed_row is None:
                    continue

                movements.append(parsed_row)
                row_number += 1

        return movements

    def _parse_movement_line(
        self,
        line: dict,
        row_number: int,
        page_number: int,
    ) -> dict | None:
        words = line["words"]
        if not words or not self.DATE_DDMMYYYY_PATTERN.match(words[0]["text"]):
            return None

        description_words = [word for word in words if 150 <= word["x0"] < 330]
        charge_words = [word for word in words if 330 <= word["x0"] < 410]
        deposit_words = [word for word in words if 410 <= word["x0"] < 500]
        balance_words = [word for word in words if word["x0"] >= 500]

        document_number = None
        if description_words and re.fullmatch(r"\d{6,}", description_words[0]["text"]):
            document_number = description_words[0]["text"]
            description_words = description_words[1:]

        description = self._clean_text(" ".join(word["text"] for word in description_words))
        if not description:
            return None

        charge_amount = self._parse_amount_words(charge_words)
        deposit_amount = self._parse_amount_words(deposit_words)
        balance_amount = self._parse_amount_words(balance_words)
        detected_movement_type = self._detect_movement_type(description, charge_amount, deposit_amount)

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": datetime.strptime(words[0]["text"], "%d/%m/%Y").date(),
            "branch": None,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": self._line_text(line),
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_SANTANDER_CUENTA_MAS_LUCAS",
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.99"),
        }

    def _extract_page_period(self, page_text: str):
        period_match = self.PERIOD_PATTERN.search(page_text)
        if period_match is None:
            return None

        return (
            datetime.strptime(period_match.group(1), "%d/%m/%Y").date(),
            datetime.strptime(period_match.group(2), "%d/%m/%Y").date(),
        )

    def _extract_holder_name(self, lines: list[dict]) -> str | None:
        for line in lines:
            line_text = self._clean_text(self._line_text(line))
            normalized_line = self._normalize_for_detection(line_text)
            if "CUENTA MAS LUCAS" not in normalized_line:
                continue

            holder_name = re.sub(r"^\d+", "", line_text)
            holder_name = re.sub(r"\s+CUENTA\s+MAS\s+LUCAS.*$", "", holder_name, flags=re.IGNORECASE)
            return self._clean_text(holder_name) or None

        return None

    def _detect_movement_type(
        self,
        description: str,
        charge_amount: Decimal,
        deposit_amount: Decimal,
    ) -> str:
        normalized_description = self._normalize_for_detection(description)

        if deposit_amount > 0:
            if "TRANSF" in normalized_description:
                return "TRANSFER_IN"
            if "INTERESES" in normalized_description:
                return "INTEREST"
            return "DEPOSIT"

        if charge_amount > 0:
            if "TRANSF" in normalized_description:
                return "TRANSFER_OUT"
            return "UNKNOWN"

        return "UNKNOWN"

    def _is_stop_line(self, normalized_line: str) -> bool:
        return (
            normalized_line.startswith("RESUMEN DE COMISIONES")
            or normalized_line.startswith("SIN COMISIONES")
            or normalized_line.startswith("\"INFORMESE")
            or "CARTOLA SIN MOVIMIENTOS" in normalized_line
        )

    def _parse_amount_words(self, words: list[dict]) -> Decimal:
        amount_text = self._clean_text(" ".join(word["text"] for word in words))
        amount_match = re.search(r"\d{1,3}(?:\.\d{3})*|\d+", amount_text)
        if amount_match is None:
            return Decimal("0")

        return Decimal(amount_match.group(0).replace(".", ""))

    def _group_words_by_line(self, words: list[dict]) -> list[dict]:
        lines: list[dict] = []

        for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
            if not lines or abs(lines[-1]["top"] - word["top"]) > 2:
                lines.append({"top": word["top"], "words": [word]})
                continue

            lines[-1]["words"].append(word)

        return lines

    def _line_text(self, line: dict) -> str:
        return self._clean_text(" ".join(word["text"] for word in line["words"]))

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())

    def _normalize_for_detection(self, value: str) -> str:
        decomposed_value = unicodedata.normalize("NFD", str(value))
        without_accents = "".join(
            character for character in decomposed_value
            if unicodedata.category(character) != "Mn"
        )
        return self._clean_text(without_accents).upper()
