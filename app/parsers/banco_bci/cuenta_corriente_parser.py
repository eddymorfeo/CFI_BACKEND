import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoBciCuentaCorrienteParser(BaseParser):
    DATE_DDMMYYYY_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    PERIOD_PATTERN = re.compile(
        r"PERIODO\s+(\d{2}-\d{2}-\d{4})\s+al\s+(\d{2}-\d{2}-\d{4})",
        re.IGNORECASE,
    )

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._normalize_for_detection(first_page_text)

        return (
            "BCI- CARTOLA DE CUENTA CORRIENTE" in normalized_text
            and "CARTOLA DE CUENTA CORRIENTE" in normalized_text
            and "N CUENTA" in normalized_text
            and "SALDO DIARIO" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)
        pages = self._extract_pages(path)

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages)

        document_metadata["detected_statement_type"] = "CUENTA_CORRIENTE"

        return {
            "parser_code": "BANCO_BCI_CARTOLA_CUENTA_CORRIENTE",
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
        all_text = "\n".join(page["text"] for page in pages)
        compact_text = self._clean_text(all_text)

        holder_match = re.search(
            r"Sr\(a\)\s+(.+?)\s+N[°º]?\s+CUENTA",
            compact_text,
            re.IGNORECASE,
        )
        account_match = re.search(r"N[°º]?\s+CUENTA\s+(\d+)", compact_text, re.IGNORECASE)
        currency_match = re.search(r"MONEDA\s+([A-ZÁÉÍÓÚÑ]+)", compact_text, re.IGNORECASE)
        plan_match = re.search(r"PLAN:\s+(.+?)(?:\s+PERIODO|\s*$)", compact_text, re.IGNORECASE)

        periods = [page["period"] for page in pages if page["period"] is not None]
        document_date_from = min(period[0] for period in periods) if periods else None
        document_date_to = max(period[1] for period in periods) if periods else None

        return {
            "detected_institution_name": "BCI",
            "detected_holder_name": self._clean_text(holder_match.group(1)) if holder_match else None,
            "detected_account_number": account_match.group(1) if account_match else None,
            "detected_account_type": "CUENTA CORRIENTE",
            "detected_currency": currency_match.group(1) if currency_match else None,
            "detected_plan": self._clean_text(plan_match.group(1)) if plan_match else None,
            "document_date_from": document_date_from,
            "document_date_to": document_date_to,
        }

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements: list[dict] = []
        row_number = 1

        for page in pages:
            in_table = False
            lines = page["lines"]

            for index, line in enumerate(lines):
                line_text = self._line_text(line)
                normalized_line = self._normalize_for_detection(line_text)

                if not in_table:
                    if (
                        "FECHA" in normalized_line
                        and "SUCURSAL" in normalized_line
                        and "DESCRIPCION" in normalized_line
                        and "SALDO DIARIO" in normalized_line
                    ):
                        in_table = True
                    continue

                if self._is_stop_line(normalized_line):
                    break

                parsed_row = self._parse_movement_line(
                    lines=lines,
                    index=index,
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
        lines: list[dict],
        index: int,
        row_number: int,
        page_number: int,
    ) -> dict | None:
        line = lines[index]
        words = line["words"]

        if not words or not self.DATE_DDMMYYYY_PATTERN.match(words[0]["text"]):
            return None

        previous_description = self._description_from_adjacent_line(lines, index - 1, line["top"])
        next_description = self._description_from_adjacent_line(lines, index + 1, line["top"])
        description = self._clean_text(f"{previous_description} {next_description}")
        if not description:
            return None

        branch = self._clean_text(
            " ".join(word["text"] for word in words if 115 <= word["x0"] < 175)
        ) or None
        document_number = self._clean_text(
            " ".join(word["text"] for word in words if 270 <= word["x0"] < 335)
        ) or None

        charge_amount = self._parse_amount_words([word for word in words if 335 <= word["x0"] < 410])
        deposit_amount = self._parse_amount_words([word for word in words if 410 <= word["x0"] < 480])
        balance_amount = self._parse_amount_words([word for word in words if word["x0"] >= 480])
        detected_movement_type = self._detect_movement_type(description, charge_amount, deposit_amount)

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": datetime.strptime(words[0]["text"], "%d/%m/%Y").date(),
            "branch": branch,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": self._clean_text(
                f"{previous_description} {self._line_text(line)} {next_description}"
            ),
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_BCI_CARTOLA_CUENTA_CORRIENTE",
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.99"),
        }

    def _description_from_adjacent_line(
        self,
        lines: list[dict],
        index: int,
        movement_top: float,
    ) -> str:
        if index < 0 or index >= len(lines):
            return ""

        line = lines[index]
        if abs(line["top"] - movement_top) > 6:
            return ""

        words = [
            word["text"]
            for word in line["words"]
            if 170 <= word["x0"] < 270 and not self.DATE_DDMMYYYY_PATTERN.match(word["text"])
        ]

        return self._clean_text(" ".join(words))

    def _extract_page_period(self, page_text: str):
        period_match = self.PERIOD_PATTERN.search(page_text)
        if period_match is None:
            return None

        return (
            datetime.strptime(period_match.group(1), "%d-%m-%Y").date(),
            datetime.strptime(period_match.group(2), "%d-%m-%Y").date(),
        )

    def _detect_movement_type(
        self,
        description: str,
        charge_amount: Decimal,
        deposit_amount: Decimal,
    ) -> str:
        normalized_description = self._normalize_for_detection(description)

        if "TRANSFER" in normalized_description:
            if deposit_amount > 0:
                return "TRANSFER_IN"
            if charge_amount > 0:
                return "TRANSFER_OUT"

        if deposit_amount > 0:
            return "DEPOSIT"

        if charge_amount > 0:
            return "UNKNOWN"

        return "UNKNOWN"

    def _is_stop_line(self, normalized_line: str) -> bool:
        return (
            normalized_line.startswith("RESUMEN DEL PERIODO")
            or normalized_line.startswith("TOTAL CARGOS")
            or normalized_line.startswith("CONSIDERAMOS APROBADO")
            or normalized_line.startswith("HTTPS://")
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
        return self._clean_text(without_accents).upper().replace("N°", "N").replace("Nº", "N")
