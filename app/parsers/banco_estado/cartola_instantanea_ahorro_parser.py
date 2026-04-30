import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoEstadoCartolaInstantaneaAhorroParser(BaseParser):
    DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._normalize_for_detection(first_page_text)

        return (
            "AHORRO: CARTOLA INSTANTANEA" in normalized_text
            and "ESTADO DE MOVIMIENTOS" in normalized_text
            and "AHORRO PESOS" in normalized_text
            and "CARGOS O GIROS" in normalized_text
            and "ABONOS O DEPOSITOS" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)
        pages = self._extract_pages(path)

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages)

        document_metadata["detected_statement_type"] = "AHORRO_CARTOLA_INSTANTANEA"

        return {
            "parser_code": "BANCO_ESTADO_AHORRO_CARTOLA_INSTANTANEA",
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
                pages.append(
                    {
                        "page_number": page_index + 1,
                        "text": page.extract_text(x_tolerance=1, y_tolerance=3) or "",
                        "lines": self._group_words_by_line(words),
                    }
                )

        return pages

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"] if pages else ""
        first_page_lines = pages[0]["lines"] if pages else []
        compact_text = self._clean_text(first_page_text)

        rut_match = re.search(r"Rut\s+([0-9kK\.-]+)", compact_text, re.IGNORECASE)
        holder_match = re.search(
            r"Rut\s+[0-9kK\.-]+\s+Nombre\s+(.+?)\s+Ejecutivo",
            compact_text,
            re.IGNORECASE,
        )
        account_match = re.search(
            r"NOMBRE\s+N[º°]?\s+CTA\.\s+AHORRO\s+OFICINA\s+.+?\s+(\d{6,})\s+",
            compact_text,
            re.IGNORECASE | re.DOTALL,
        )

        product_row = self._find_row_after_header(first_page_lines, "PRODUCTO", "SALDO ANTERIOR")
        product_metadata = self._parse_product_row(product_row)

        holder_name = self._clean_text(holder_match.group(1)) if holder_match else None
        account_number = account_match.group(1) if account_match else product_metadata.get("account_number")

        return {
            "detected_institution_name": "BancoEstado",
            "detected_holder_name": holder_name,
            "detected_holder_rut": rut_match.group(1) if rut_match else None,
            "detected_account_number": account_number,
            "detected_account_type": product_metadata.get("account_type"),
            "detected_branch": product_metadata.get("branch"),
            "detected_statement_number": product_metadata.get("statement_number"),
            "document_issue_date": product_metadata.get("issue_date"),
            "document_date_from": product_metadata.get("date_from"),
            "document_date_to": product_metadata.get("date_to"),
            "previous_balance": product_metadata.get("previous_balance"),
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
                        "DESCRIPCION DE MOVIMIENTOS" in normalized_line
                        and "CARGOS O GIROS" in normalized_line
                        and "ABONOS O DEPOSITOS" in normalized_line
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

    def _parse_movement_line(self, line: dict, row_number: int, page_number: int) -> dict | None:
        words = line["words"]
        date_words = [word for word in words if self.DATE_PATTERN.match(word["text"])]
        if not date_words:
            return None

        description = self._clean_text(
            " ".join(word["text"] for word in words if float(word["x0"]) < 230)
        )
        if not description:
            return None

        branch = self._clean_text(
            " ".join(word["text"] for word in words if 230 <= float(word["x0"]) < 275)
        ) or None
        charge_amount = self._parse_amount_words(
            [word for word in words if 275 <= float(word["x0"]) < 370]
        )
        deposit_amount = self._parse_amount_words(
            [word for word in words if 370 <= float(word["x0"]) < 480]
        )
        balance_amount = self._parse_amount_words(
            [word for word in words if float(word["x0"]) >= 525]
        )
        transaction_date = datetime.strptime(date_words[0]["text"], "%d/%m/%Y").date()
        detected_movement_type = self._detect_movement_type(description, charge_amount, deposit_amount)

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": transaction_date,
            "branch": branch,
            "description": description,
            "document_number": None,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": self._line_text(line),
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_ESTADO_AHORRO_CARTOLA_INSTANTANEA",
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.99"),
        }

    def _find_row_after_header(self, lines: list[dict], *header_parts: str) -> dict | None:
        for index, line in enumerate(lines):
            normalized_line = self._normalize_for_detection(self._line_text(line))
            if all(part in normalized_line for part in header_parts):
                return lines[index + 1] if index + 1 < len(lines) else None

        return None

    def _parse_product_row(self, row: dict | None) -> dict:
        if row is None:
            return {}

        words = row["words"]
        account_type = self._clean_text(
            " ".join(word["text"] for word in words if float(word["x0"]) < 200)
        ) or None
        statement_number = self._clean_text(
            " ".join(word["text"] for word in words if 200 <= float(word["x0"]) < 270)
        ) or None
        issue_date = self._parse_first_date(words, 270, 350)
        date_from = self._parse_first_date(words, 350, 405)
        date_to = self._parse_first_date(words, 405, 460)
        previous_balance = self._parse_amount_words(
            [word for word in words if float(word["x0"]) >= 530]
        )

        return {
            "account_type": account_type,
            "statement_number": statement_number,
            "issue_date": issue_date,
            "date_from": date_from,
            "date_to": date_to,
            "previous_balance": previous_balance,
        }

    def _parse_first_date(self, words: list[dict], x0_min: float, x0_max: float):
        for word in words:
            if x0_min <= float(word["x0"]) < x0_max and self.DATE_PATTERN.match(word["text"]):
                return datetime.strptime(word["text"], "%d/%m/%Y").date()

        return None

    def _detect_movement_type(
        self,
        description: str,
        charge_amount: Decimal,
        deposit_amount: Decimal,
    ) -> str:
        normalized_description = self._normalize_for_detection(description)

        if deposit_amount > 0:
            if "TRANSFERENCIA" in normalized_description:
                return "TRANSFER_IN"
            if normalized_description.startswith("DEP "):
                return "DEPOSIT"
            return "DEPOSIT"

        if charge_amount > 0:
            if "TRANSFERENCIA" in normalized_description:
                return "TRANSFER_OUT"
            if normalized_description.startswith("GIRO"):
                return "WITHDRAWAL"

        return "UNKNOWN"

    def _is_stop_line(self, normalized_line: str) -> bool:
        return (
            normalized_line.startswith("RESUMEN DEL PERIODO")
            or normalized_line.startswith("N GIROS")
            or normalized_line.startswith("INFORMESE")
            or normalized_line.startswith("PAGINA")
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
        return self._clean_text(without_accents).upper().replace("Nº", "N").replace("N°", "N")
