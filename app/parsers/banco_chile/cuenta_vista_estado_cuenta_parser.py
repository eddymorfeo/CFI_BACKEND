import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoChileCuentaVistaEstadoCuentaParser(BaseParser):
    DATE_MM_PATTERN = re.compile(r"^\d{2}/\d{2}$")

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = " ".join(first_page_text.split()).upper()

        return (
            "ESTADO DE CUENTA" in normalized_text
            and "CUENTA VISTA" in normalized_text
            and "N° DE CUENTA" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)

        with pdfplumber.open(path) as pdf:
            pages = []
            for page_index, page in enumerate(pdf.pages):
                pages.append(
                    {
                        "page_number": page_index + 1,
                        "page": page,
                        "text": page.extract_text() or "",
                    }
                )

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages)

        return {
            "parser_code": "BANCO_CHILE_CUENTA_VISTA_ESTADO_CUENTA",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"]

        account_match = re.search(r"N° DE CUENTA\s*:\s*(\d+)", first_page_text, re.IGNORECASE)
        holder_match = re.search(
            r"Estado de Cuenta\s+.*?\s+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)\s+N° DE CUENTA",
            first_page_text,
            re.IGNORECASE | re.DOTALL,
        )

        period_match = re.search(
            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
            first_page_text,
            re.IGNORECASE,
        )

        return {
            "detected_institution_name": "Banco de Chile",
            "detected_holder_name": self._clean_text(holder_match.group(1)) if holder_match else None,
            "detected_account_number": account_match.group(1) if account_match else None,
            "document_date_from": datetime.strptime(period_match.group(1), "%d/%m/%Y").date() if period_match else None,
            "document_date_to": datetime.strptime(period_match.group(2), "%d/%m/%Y").date() if period_match else None,
        }

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements = []
        row_number = 1

        for page_info in pages:
            page_number = page_info["page_number"]
            page_text = page_info["text"]
            page_lines = [line.strip() for line in page_text.splitlines() if line.strip()]

            year = self._resolve_year_from_page(page_text)
            movement_lines = self._extract_relevant_lines(page_lines)
            parsed_lines = self._merge_multiline_movements(movement_lines)

            for line in parsed_lines:
                movement = self._parse_line(line, row_number, page_number, year)
                if movement is not None:
                    movements.append(movement)
                    row_number += 1

        return movements

    def _resolve_year_from_page(self, page_text: str) -> int:
        period_match = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})", page_text)
        if period_match:
            return datetime.strptime(period_match.group(2), "%d/%m/%Y").year
        return datetime.now().year

    def _extract_relevant_lines(self, page_lines: list[str]) -> list[str]:
        relevant = []
        in_table = False

        for line in page_lines:
            line_upper = line.upper()

            if "DETALLE DE TRANSACCION" in line_upper and "SALDO" in line_upper:
                in_table = True
                continue

            if not in_table:
                continue

            if line_upper.startswith("RETENCION A 1 DIA"):
                break

            if line_upper.startswith("INFÓRMESE") or line_upper.startswith("INFORMESE"):
                continue

            relevant.append(line)

        return relevant

    def _merge_multiline_movements(self, lines: list[str]) -> list[str]:
        merged = []
        current = None

        for line in lines:
            if self.DATE_MM_PATTERN.match(line[:5]):
                if current:
                    merged.append(current)
                current = line
            else:
                if current:
                    current = f"{current} {line}"

        if current:
            merged.append(current)

        return merged

    def _parse_line(self, line: str, row_number: int, page_number: int, year: int) -> dict | None:
        line_upper = line.upper()

        if "SALDO INICIAL" in line_upper or "SALDO FINAL" in line_upper:
            return None

        line = self._clean_text(line)

        date_raw = line[:5]
        if not self.DATE_MM_PATTERN.fullmatch(date_raw):
            return None

        full_date = datetime.strptime(f"{date_raw}/{year}", "%d/%m/%Y").date()

        numbers = re.findall(r"\b\d{1,3}(?:\.\d{3})*\b", line)

        balance_amount = Decimal("0")
        charge_amount = Decimal("0")
        deposit_amount = Decimal("0")

        if numbers:
            numeric_values = [Decimal(number.replace(".", "")) for number in numbers]
            if len(numeric_values) >= 1:
                balance_amount = numeric_values[-1]
            if len(numeric_values) >= 2:
                second_last = numeric_values[-2]
                if "TRASPASO DE:" in line_upper or "ABONO" in line_upper:
                    deposit_amount = second_last
                else:
                    charge_amount = second_last

        description = re.sub(r"^\d{2}/\d{2}\s*", "", line)
        description = re.sub(r"\b\d{1,3}(?:\.\d{3})*\b$", "", description).strip()
        description = self._clean_text(description)

        if not description:
            return None

        detected_movement_type = self._detect_movement_type(description)
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": full_date,
            "branch": None,
            "description": description,
            "document_number": None,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": line,
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_CHILE_CUENTA_VISTA",
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.90"),
        }

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if "TRASPASO A:" in description_upper:
            return "TRANSFER_OUT"

        if "TRASPASO DE:" in description_upper or "ABONO" in description_upper:
            return "TRANSFER_IN"

        if "PAGO:" in description_upper or "REGULARIZACION DE CARGOS" in description_upper:
            return "PURCHASE"

        return "UNKNOWN"

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())