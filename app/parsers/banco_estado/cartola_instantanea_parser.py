import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoEstadoCartolaInstantaneaParser(BaseParser):
    DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    DOC_PATTERN = re.compile(r"^\d{6,}$")
    AMOUNT_PATTERN = re.compile(r"^-?\d{1,3}(?:\.\d{3})*$|^-?\d+$")

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = " ".join(first_page_text.split()).upper()

        return (
            "CARTOLA INSTANTÁNEA" in normalized_text
            or (
                "CARTOLA" in normalized_text
                and "INSTANTÁNEA" in normalized_text
                and "CUENTARUT" in normalized_text
                and "N° OPERACIÓN" in normalized_text
            )
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
            "parser_code": "BANCO_ESTADO_CARTOLA_INSTANTANEA",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"]

        holder_match = re.search(
            r"Nombre:\s*(.*?)\s+Cuenta:\s*(\d+)\s+Fecha y hora",
            first_page_text,
            re.IGNORECASE | re.DOTALL,
        )

        return {
            "detected_institution_name": "BancoEstado",
            "detected_holder_name": self._clean_text(holder_match.group(1)) if holder_match else None,
            "detected_account_number": holder_match.group(2) if holder_match else None,
            "document_date_from": None,
            "document_date_to": None,
        }

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements = []
        row_number = 1

        for page_info in pages:
            page_number = page_info["page_number"]
            page = page_info["page"]

            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                x_tolerance=2,
                y_tolerance=3,
            )

            rows = self._group_words_by_row(words)
            movement_rows = self._filter_movement_rows(rows)
            logical_rows = self._merge_multiline_rows(movement_rows)

            for logical_row in logical_rows:
                movement = self._parse_row(logical_row, row_number, page_number)
                if movement is not None:
                    movements.append(movement)
                    row_number += 1

        return movements

    def _group_words_by_row(self, words: list[dict], y_threshold: float = 3.5) -> list[list[dict]]:
        if not words:
            return []

        sorted_words = sorted(words, key=lambda item: (round(float(item["top"]), 1), float(item["x0"])))
        rows = []
        current_row = []
        current_top = None

        for word in sorted_words:
            word_top = float(word["top"])

            if current_top is None:
                current_row = [word]
                current_top = word_top
                continue

            if abs(word_top - current_top) <= y_threshold:
                current_row.append(word)
            else:
                rows.append(sorted(current_row, key=lambda item: float(item["x0"])))
                current_row = [word]
                current_top = word_top

        if current_row:
            rows.append(sorted(current_row, key=lambda item: float(item["x0"])))

        return rows

    def _filter_movement_rows(self, rows: list[list[dict]]) -> list[list[dict]]:
        filtered = []
        in_movements = False

        for row in rows:
            row_text = self._row_text(row).upper()

            if "FECHA" in row_text and "N° OPERACIÓN" in row_text and "SALDO" in row_text:
                in_movements = True
                continue

            if not in_movements:
                continue

            if "SALDOS Y RETENCIONES" in row_text or "RETENCIONES" in row_text:
                continue

            filtered.append(row)

        return filtered

    def _merge_multiline_rows(self, rows: list[list[dict]]) -> list[list[list[dict]]]:
        logical_rows = []
        current_group = []

        for row in rows:
            first_token = self._clean_text(row[0]["text"]) if row else ""

            if self.DATE_PATTERN.fullmatch(first_token):
                if current_group:
                    logical_rows.append(current_group)
                current_group = [row]
            else:
                if current_group:
                    current_group.append(row)

        if current_group:
            logical_rows.append(current_group)

        return logical_rows

    def _parse_row(self, logical_row: list[list[dict]], row_number: int, page_number: int) -> dict | None:
        all_words = []
        for row in logical_row:
            all_words.extend(sorted(row, key=lambda item: float(item["x0"])))

        if not all_words:
            return None

        transaction_date_raw = self._clean_text(all_words[0]["text"])
        if not self.DATE_PATTERN.fullmatch(transaction_date_raw):
            return None

        branch_parts = []
        description_parts = []
        document_number = None

        numeric_tokens: list[tuple[float, Decimal]] = []

        for word in all_words[1:]:
            text = self._clean_text(word["text"])
            x0 = float(word["x0"])

            if text == "$":
                continue

            if self._looks_like_amount(text):
                parsed_amount = self._parse_amount(text)
                numeric_tokens.append((x0, parsed_amount))
                continue

            if x0 < 180:
                branch_parts.append(text)
            elif x0 < 280 and self.DOC_PATTERN.fullmatch(text):
                document_number = text
            else:
                description_parts.append(text)

        description = self._clean_text(" ".join(description_parts))
        branch = self._clean_text(" ".join(branch_parts)) or None

        if not description:
            return None

        charge_amount = Decimal("0")
        deposit_amount = Decimal("0")
        balance_amount = Decimal("0")

        # Tomamos los tres últimos montos detectados como cargo/abono/saldo
        # y resolvemos según signo y posición.
        if numeric_tokens:
            amounts_only = [amount for _x0, amount in numeric_tokens]

            if len(amounts_only) >= 3:
                first_amount, second_amount, third_amount = amounts_only[-3], amounts_only[-2], amounts_only[-1]

                if first_amount < 0:
                    charge_amount = abs(first_amount)
                else:
                    charge_amount = first_amount

                if second_amount > 0:
                    deposit_amount = second_amount

                balance_amount = abs(third_amount)

            elif len(amounts_only) == 2:
                first_amount, second_amount = amounts_only[-2], amounts_only[-1]

                if first_amount < 0:
                    charge_amount = abs(first_amount)
                else:
                    deposit_amount = abs(first_amount)

                balance_amount = abs(second_amount)

            elif len(amounts_only) == 1:
                balance_amount = abs(amounts_only[-1])

        detected_movement_type = self._detect_movement_type(description)
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": datetime.strptime(transaction_date_raw, "%d/%m/%Y").date(),
            "branch": branch,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": self._clean_text(" ".join(self._clean_text(word["text"]) for word in all_words)),
            "raw_row_json": {
                "page_number": page_number,
                "row_group_size": len(logical_row),
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.96"),
        }

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if description_upper.startswith("TEF A") or "TEF A " in description_upper:
            return "TRANSFER_OUT"

        if (
            "TEF DE " in description_upper
            or "TRANSFERENCIA DE " in description_upper
        ):
            return "TRANSFER_IN"

        if "COMISION" in description_upper:
            return "COMMISSION"

        return "UNKNOWN"

    def _looks_like_amount(self, value: str) -> bool:
        normalized_value = value.replace("$", "").replace(" ", "")
        return self.AMOUNT_PATTERN.fullmatch(normalized_value) is not None

    def _parse_amount(self, raw_amount: str | None) -> Decimal:
        if raw_amount is None:
            return Decimal("0")

        normalized_amount = (
            str(raw_amount)
            .replace("$", "")
            .replace(".", "")
            .replace(" ", "")
            .strip()
        )

        if normalized_amount in {"", "-"}:
            return Decimal("0")

        try:
            return Decimal(normalized_amount)
        except InvalidOperation:
            return Decimal("0")

    def _row_text(self, row_words: list[dict]) -> str:
        return " ".join(self._clean_text(word["text"]) for word in row_words)

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())