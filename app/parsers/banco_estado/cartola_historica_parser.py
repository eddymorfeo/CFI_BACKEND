import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoEstadoCartolaHistoricaParser(BaseParser):
    DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    DOC_PATTERN = re.compile(r"^\d{6,}$")

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = " ".join(first_page_text.split()).upper()

        return (
            "CARTOLA HISTÓRICA" in normalized_text
            and "CUENTARUT" in normalized_text
            and "MOVIMIENTOS" in normalized_text
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
        movements = self._extract_movements_from_pages(pages)

        return {
            "parser_code": "BANCO_ESTADO_CARTOLA_HISTORICA",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"]

        holder_name_match = re.search(
            r"Titular 1:\s*(.*?)\s*Titular 2:",
            first_page_text,
            re.IGNORECASE | re.DOTALL,
        )

        account_match = re.search(
            r"Cuenta:\s*(\d+)",
            first_page_text,
            re.IGNORECASE,
        )

        period_match = re.search(
            r"Desde:\s*(\d{2}-\d{2}-\d{4})\s*Hasta:\s*(\d{2}-\d{2}-\d{4})",
            first_page_text,
            re.IGNORECASE,
        )

        return {
            "detected_institution_name": "BancoEstado",
            "detected_holder_name": self._clean_text(holder_name_match.group(1)) if holder_name_match else None,
            "detected_account_number": account_match.group(1) if account_match else None,
            "document_date_from": self._parse_date(period_match.group(1), "%d-%m-%Y") if period_match else None,
            "document_date_to": self._parse_date(period_match.group(2), "%d-%m-%Y") if period_match else None,
        }

    def _extract_movements_from_pages(self, pages: list[dict]) -> list[dict]:
        movements: list[dict] = []
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

            row_groups = self._group_words_by_row(words)
            relevant_row_groups = self._filter_rows_to_movements_section(row_groups)
            logical_rows = self._build_logical_rows(relevant_row_groups)

            for logical_row in logical_rows:
                parsed_movement = self._parse_logical_row(
                    logical_row=logical_row,
                    row_number=row_number,
                    page_number=page_number,
                )

                if parsed_movement is not None:
                    movements.append(parsed_movement)
                    row_number += 1

        return movements

    def _group_words_by_row(self, words: list[dict], y_threshold: float = 3.5) -> list[list[dict]]:
        if not words:
            return []

        sorted_words = sorted(words, key=lambda item: (round(float(item["top"]), 1), float(item["x0"])))
        rows: list[list[dict]] = []
        current_row: list[dict] = []
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

    def _filter_rows_to_movements_section(self, row_groups: list[list[dict]]) -> list[list[dict]]:
        filtered: list[list[dict]] = []
        in_movements = False

        for row_words in row_groups:
            row_text = self._row_text(row_words).upper()

            if (
                ("Nº DOCUMENTO" in row_text or "N° DOCUMENTO" in row_text)
                and "DESCRIPCIÓN" in row_text
                and "SALDO" in row_text
            ):
                in_movements = True
                continue

            if not in_movements:
                continue

            if row_text.startswith("GIROS:"):
                break

            if row_text.startswith("INFORMACIÓN REFERENCIAL"):
                break

            if row_text.startswith("INFORMESE SOBRE LA GARANTIA"):
                continue

            filtered.append(row_words)

        return filtered

    def _build_logical_rows(self, row_groups: list[list[dict]]) -> list[dict]:
        anchors: list[dict] = []
        floating_rows: list[dict] = []

        for index, row_words in enumerate(row_groups):
            if not row_words:
                continue

            first_token = self._clean_text(row_words[0]["text"])
            row_top = min(float(word["top"]) for word in row_words)
            row_text = self._row_text(row_words).upper()

            if self._is_header_or_footer_row(row_text):
                continue

            row_data = {
                "index": index,
                "top": row_top,
                "row_words": row_words,
                "prefix_rows": [],
                "suffix_rows": [],
            }

            if self.DOC_PATTERN.fullmatch(first_token):
                anchors.append(row_data)
            elif self._is_description_only_row(row_words):
                floating_rows.append(row_data)

        if not anchors:
            return []

        for floating_row in floating_rows:
            target_anchor, attach_as = self._find_best_anchor_for_floating_row(anchors, floating_row)
            if target_anchor is None:
                continue

            if attach_as == "prefix":
                target_anchor["prefix_rows"].append(floating_row["row_words"])
            else:
                target_anchor["suffix_rows"].append(floating_row["row_words"])

        logical_rows: list[dict] = []

        for anchor in anchors:
            logical_rows.append(
                {
                    "anchor_row": anchor["row_words"],
                    "prefix_rows": sorted(
                        anchor["prefix_rows"],
                        key=lambda row: min(float(word["top"]) for word in row),
                    ),
                    "suffix_rows": sorted(
                        anchor["suffix_rows"],
                        key=lambda row: min(float(word["top"]) for word in row),
                    ),
                }
            )

        return logical_rows

    def _is_description_only_row(self, row_words: list[dict]) -> bool:
        cleaned_texts = [self._clean_text(word["text"]) for word in row_words if self._clean_text(word["text"])]

        if not cleaned_texts:
            return False

        if any(self.DOC_PATTERN.fullmatch(text) for text in cleaned_texts):
            return False

        if any(self.DATE_PATTERN.fullmatch(text) for text in cleaned_texts):
            return False

        if any(text == "$" for text in cleaned_texts):
            return False

        for word in row_words:
            x0 = float(word["x0"])
            if x0 >= 300:
                return False

        return True

    def _find_best_anchor_for_floating_row(self, anchors: list[dict], floating_row: dict) -> tuple[dict | None, str | None]:
        previous_anchor = None
        next_anchor = None

        for anchor in anchors:
            if anchor["index"] < floating_row["index"]:
                previous_anchor = anchor
            elif anchor["index"] > floating_row["index"]:
                next_anchor = anchor
                break

        if previous_anchor is None and next_anchor is None:
            return None, None

        if previous_anchor is None:
            return next_anchor, "prefix"

        if next_anchor is None:
            return previous_anchor, "suffix"

        distance_to_previous = abs(floating_row["top"] - previous_anchor["top"])
        distance_to_next = abs(next_anchor["top"] - floating_row["top"])

        if distance_to_next < distance_to_previous:
            return next_anchor, "prefix"

        return previous_anchor, "suffix"

    def _parse_logical_row(
        self,
        logical_row: dict,
        row_number: int,
        page_number: int,
    ) -> dict | None:
        anchor_row = logical_row["anchor_row"]
        prefix_rows = logical_row["prefix_rows"]
        suffix_rows = logical_row["suffix_rows"]

        anchor_words = sorted(anchor_row, key=lambda item: float(item["x0"]))
        anchor_first_word = self._clean_text(anchor_words[0]["text"])

        if not self.DOC_PATTERN.fullmatch(anchor_first_word):
            return None

        document_number = anchor_first_word

        prefix_words = [word for row in prefix_rows for word in sorted(row, key=lambda item: float(item["x0"]))]
        suffix_words_flat = [word for row in suffix_rows for word in sorted(row, key=lambda item: float(item["x0"]))]

        description_parts: list[str] = []
        charge_tokens: list[str] = []
        deposit_tokens: list[str] = []
        balance_tokens: list[str] = []
        transaction_date_raw = None

        for word in prefix_words:
            text = self._clean_text(word["text"])
            x0 = float(word["x0"])
            if text and x0 < 300:
                description_parts.append(text)

        for word in anchor_words[1:]:
            text = self._clean_text(word["text"])
            x0 = float(word["x0"])

            if text == "$":
                continue

            if self.DATE_PATTERN.fullmatch(text):
                transaction_date_raw = text
                continue

            if x0 < 300:
                description_parts.append(text)
            elif 300 <= x0 < 390:
                if self._looks_like_amount(text):
                    charge_tokens.append(text)
            elif 390 <= x0 < 450:
                if self._looks_like_amount(text):
                    deposit_tokens.append(text)
            elif x0 >= 530:
                if self._looks_like_amount(text):
                    balance_tokens.append(text)

        for word in suffix_words_flat:
            text = self._clean_text(word["text"])
            x0 = float(word["x0"])
            if text and x0 < 300:
                description_parts.append(text)

        description = self._clean_text(" ".join(description_parts))

        charge_amount_raw = charge_tokens[0] if charge_tokens else None
        deposit_amount_raw = deposit_tokens[0] if deposit_tokens else None
        balance_amount_raw = balance_tokens[0] if balance_tokens else None

        if not description:
            return None

        if transaction_date_raw is None:
            return None

        charge_amount = self._parse_amount(charge_amount_raw)
        deposit_amount = self._parse_amount(deposit_amount_raw)
        balance_amount = self._parse_amount(balance_amount_raw)

        detected_movement_type = self._detect_movement_type(description)
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}

        raw_row_text = " ".join(
            self._clean_text(word["text"])
            for word in (prefix_words + anchor_words + suffix_words_flat)
        )

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": self._parse_date(transaction_date_raw, "%d/%m/%Y"),
            "branch": None,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": raw_row_text,
            "raw_row_json": {
                "page_number": page_number,
                "word_count": len(prefix_words + anchor_words + suffix_words_flat),
                "prefix_rows_count": len(prefix_rows),
                "suffix_rows_count": len(suffix_rows),
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.99"),
        }

    def _is_header_or_footer_row(self, row_text: str) -> bool:
        return (
            "Nº DOCUMENTO" in row_text
            or "N° DOCUMENTO" in row_text
            or "DESCRIPCIÓN" in row_text
            or "GIROS/CARGOS" in row_text
            or "DEPÓSITOS/ABONOS" in row_text
            or row_text.startswith("GIROS:")
            or row_text.startswith("OTROS CARGOS:")
            or row_text.startswith("DEPÓSITOS:")
            or row_text.startswith("DEPOSITOS:")
            or row_text.startswith("OTROS ABONOS:")
            or row_text.startswith("NUEVO SALDO:")
            or row_text.startswith("INFORMACIÓN REFERENCIAL")
            or row_text.startswith("INFORMESE SOBRE LA GARANTIA")
        )

    def _row_text(self, row_words: list[dict]) -> str:
        return " ".join(self._clean_text(word["text"]) for word in row_words)

    def _looks_like_amount(self, value: str) -> bool:
        return re.fullmatch(r"[0-9\.\-]+", value) is not None

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if "TEF A " in description_upper or description_upper.startswith("TEF A"):
            return "TRANSFER_OUT"

        if (
            "TEF DE " in description_upper
            or "TEF DESDE " in description_upper
            or "TRANSFERENCIA DE " in description_upper
        ):
            return "TRANSFER_IN"

        if "COMISION" in description_upper:
            return "COMMISSION"

        if "COMPRA" in description_upper:
            return "PURCHASE"

        if "GIRO" in description_upper:
            return "WITHDRAWAL"

        return "UNKNOWN"

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

        return Decimal(normalized_amount)

    def _parse_date(self, raw_date: str, fmt: str):
        return datetime.strptime(raw_date, fmt).date()

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())