import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoChileCuentaFanAhorroParser(BaseParser):
    DATE_DDMMYYYY_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    DATE_AT_START_PATTERN = re.compile(r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$")

    HEADER_STOP_LINES = {
        "FECHA DESCRIPCIÓN OFICINA CARGO ABONO SALDO",
        "FECHA DESCRIPCION OFICINA CARGO ABONO SALDO",
        "FECHA",
        "DESCRIPCIÓN",
        "DESCRIPCION",
        "OFICINA",
        "CARGO",
        "ABONO",
        "SALDO",
    }

    BRANCH_OPTIONS = [
        "OFICINA CENTRAL",
        "INTERNET",
        "CENTRAL",
    ]

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._clean_text(first_page_text).upper()

        return (
            "CUENTA FAN AHORRO" in normalized_text
            and "LISTADO DE MOVIMIENTOS DESDE" in normalized_text
            and "CUENTA Nº" in normalized_text
        )

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)

        with pdfplumber.open(path) as pdf:
            pages = []
            for page_index, page in enumerate(pdf.pages):
                pages.append(
                    {
                        "page_number": page_index + 1,
                        "text": page.extract_text() or "",
                    }
                )

        document_metadata = self._extract_metadata(pages)
        movements = self._extract_movements(pages)

        document_metadata["detected_statement_type"] = "CUENTA_FAN_AHORRO"

        return {
            "parser_code": "BANCO_CHILE_CUENTA_FAN_AHORRO",
            "document_metadata": document_metadata,
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"]
        normalized_text = self._clean_text(first_page_text)

        holder_match = re.search(
            r"Titular Sr\(a\)\.:\s*(.*?)\s*Rut:",
            first_page_text,
            re.IGNORECASE | re.DOTALL,
        )

        rut_match = re.search(
            r"Rut:\s*([0-9kK\.-]+)",
            normalized_text,
            re.IGNORECASE,
        )

        account_match = re.search(
            r"Cuenta Nº:\s*(\d+)",
            normalized_text,
            re.IGNORECASE,
        )

        type_match = re.search(
            r"Tipo:\s*(.*?)\s*Estado:",
            first_page_text,
            re.IGNORECASE | re.DOTALL,
        )

        status_match = re.search(
            r"Estado:\s*([A-ZÁÉÍÓÚÑa-záéíóúñ]+)",
            normalized_text,
            re.IGNORECASE,
        )

        period_match = re.search(
            r"Listado de Movimientos desde el (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})",
            normalized_text,
            re.IGNORECASE,
        )

        return {
            "detected_institution_name": "Banco de Chile",
            "detected_holder_name": self._clean_text(holder_match.group(1)) if holder_match else None,
            "detected_holder_rut": rut_match.group(1) if rut_match else None,
            "detected_account_number": account_match.group(1) if account_match else None,
            "detected_account_type": self._clean_text(type_match.group(1)) if type_match else None,
            "detected_account_status": status_match.group(1) if status_match else None,
            "document_date_from": datetime.strptime(period_match.group(1), "%d/%m/%Y").date() if period_match else None,
            "document_date_to": datetime.strptime(period_match.group(2), "%d/%m/%Y").date() if period_match else None,
        }

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements: list[dict] = []
        row_number = 1

        for page_info in pages:
            page_number = page_info["page_number"]
            page_text = page_info["text"]

            table_lines = self._extract_table_lines(page_text)
            logical_rows = self._build_logical_rows(table_lines)

            for logical_row in logical_rows:
                movement = self._parse_logical_row(
                    logical_row=logical_row,
                    row_number=row_number,
                    page_number=page_number,
                )
                if movement is not None:
                    movements.append(movement)
                    row_number += 1

        return movements

    def _extract_table_lines(self, page_text: str) -> list[str]:
        page_lines = [self._clean_text(line) for line in page_text.splitlines() if self._clean_text(line)]

        relevant_lines: list[str] = []
        in_table = False

        for line in page_lines:
            line_upper = line.upper()

            if "FECHA DESCRIPCIÓN OFICINA CARGO ABONO SALDO" in line_upper or "FECHA DESCRIPCION OFICINA CARGO ABONO SALDO" in line_upper:
                in_table = True
                continue

            if not in_table:
                continue

            if "INFÓRMESE SOBRE LA GARANTÍA ESTATAL" in line_upper or "INFORMESE SOBRE LA GARANTIA ESTATAL" in line_upper:
                break

            if line_upper in self.HEADER_STOP_LINES:
                continue

            relevant_lines.append(line)

        return relevant_lines

    def _build_logical_rows(self, lines: list[str]) -> list[dict]:
        logical_rows: list[dict] = []
        index = 0

        while index < len(lines):
            current_line = lines[index]

            # Caso 1: descripción en una línea y fecha al inicio de la siguiente
            if self._is_description_prefix_line(current_line):
                if index + 1 < len(lines):
                    next_line = lines[index + 1]
                    date_match = self.DATE_AT_START_PATTERN.match(next_line)
                    if date_match:
                        logical_rows.append(
                            {
                                "date": date_match.group("date"),
                                "description_prefix": current_line,
                                "rest": date_match.group("body").strip(),
                            }
                        )
                        index += 2
                        continue

            # Caso 2: fecha al inicio y el resto de la fila en la misma línea
            date_match = self.DATE_AT_START_PATTERN.match(current_line)
            if date_match:
                logical_rows.append(
                    {
                        "date": date_match.group("date"),
                        "description_prefix": "",
                        "rest": date_match.group("body").strip(),
                    }
                )
                index += 1
                continue

            index += 1

        return logical_rows

    def _parse_logical_row(
        self,
        logical_row: dict,
        row_number: int,
        page_number: int,
    ) -> dict | None:
        transaction_date = datetime.strptime(logical_row["date"], "%d/%m/%Y").date()
        description_prefix = self._clean_text(logical_row["description_prefix"])
        rest = self._clean_text(logical_row["rest"])

        parsed_columns = self._split_row_columns(description_prefix, rest)
        if parsed_columns is None:
            return None

        description = parsed_columns["description"]
        branch = parsed_columns["branch"]
        charge_amount = parsed_columns["charge_amount"]
        deposit_amount = parsed_columns["deposit_amount"]
        balance_amount = parsed_columns["balance_amount"]

        detected_movement_type = self._detect_movement_type(description)
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}

        raw_row_text = self._clean_text(
            f"{logical_row['date']} {description_prefix} {rest}"
        )

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
            "raw_row_text": raw_row_text,
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_CHILE_CUENTA_FAN_AHORRO",
                "parsed_columns": {
                    "description": description,
                    "branch": branch,
                    "charge_amount": str(charge_amount),
                    "deposit_amount": str(deposit_amount),
                    "balance_amount": str(balance_amount),
                },
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.99"),
        }

    def _split_row_columns(self, description_prefix: str, rest: str) -> dict | None:
        tokens = rest.split()
        if not tokens:
            return None

        branch_match = self._find_branch(tokens)
        if branch_match is None:
            return None

        branch_start_index, branch_token_count, branch_value = branch_match

        description_tail_tokens = tokens[:branch_start_index]
        trailing_tokens = tokens[branch_start_index + branch_token_count :]

        description_parts = []
        if description_prefix:
            description_parts.append(description_prefix)
        if description_tail_tokens:
            description_parts.append(" ".join(description_tail_tokens))

        description = self._clean_text(" ".join(description_parts))
        branch = branch_value

        amount_tokens = [token for token in trailing_tokens if self._is_currency_amount_token(token)]
        if not amount_tokens:
            return None

        movement_type = self._detect_movement_type(description)

        if len(amount_tokens) == 1:
            movement_amount = self._parse_currency_amount(amount_tokens[0])

            if movement_type in {"TRANSFER_IN", "INTEREST"}:
                return {
                    "description": description,
                    "branch": branch,
                    "charge_amount": Decimal("0"),
                    "deposit_amount": movement_amount,
                    "balance_amount": Decimal("0"),
                }

            return {
                "description": description,
                "branch": branch,
                "charge_amount": movement_amount,
                "deposit_amount": Decimal("0"),
                "balance_amount": Decimal("0"),
            }

        first_amount = self._parse_currency_amount(amount_tokens[0])
        second_amount = self._parse_currency_amount(amount_tokens[1])

        if movement_type in {"TRANSFER_IN", "INTEREST"}:
            return {
                "description": description,
                "branch": branch,
                "charge_amount": Decimal("0"),
                "deposit_amount": first_amount,
                "balance_amount": second_amount,
            }

        return {
            "description": description,
            "branch": branch,
            "charge_amount": first_amount,
            "deposit_amount": Decimal("0"),
            "balance_amount": second_amount,
        }

    def _find_branch(self, tokens: list[str]) -> tuple[int, int, str] | None:
        branch_variants = []
        for branch_option in self.BRANCH_OPTIONS:
            branch_tokens = branch_option.split()
            branch_variants.append((branch_tokens, branch_option))

        for token_index in range(len(tokens)):
            for branch_tokens, original_value in branch_variants:
                token_slice = tokens[token_index : token_index + len(branch_tokens)]
                if [token.upper() for token in token_slice] == [token.upper() for token in branch_tokens]:
                    return token_index, len(branch_tokens), original_value

        return None

    def _is_description_prefix_line(self, line: str) -> bool:
        upper_line = self._clean_text(line).upper()
        return (
            upper_line.startswith("TRASPASO A")
            or upper_line.startswith("TRASPASO DE")
            or upper_line.startswith("LIQUIDACION DE")
        )

    def _is_currency_amount_token(self, value: str) -> bool:
        cleaned_value = self._clean_text(value)
        return bool(re.fullmatch(r"\$\d{1,3}(?:\.\d{3})*", cleaned_value))

    def _parse_currency_amount(self, value: str) -> Decimal:
        cleaned_value = self._clean_text(value)
        if not cleaned_value:
            return Decimal("0")

        amount_match = re.search(r"\d{1,3}(?:\.\d{3})*", cleaned_value)
        if not amount_match:
            return Decimal("0")

        normalized_amount = amount_match.group(0).replace(".", "")
        return Decimal(normalized_amount)

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if description_upper.startswith("TRASPASO A"):
            return "TRANSFER_OUT"

        if description_upper.startswith("TRASPASO DE"):
            return "TRANSFER_IN"

        if description_upper.startswith("LIQUIDACION DE INTERES"):
            return "INTEREST"

        return "UNKNOWN"

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())