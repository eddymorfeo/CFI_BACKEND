import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoChileCuentaVistaEstadoCuentaParser(BaseParser):
    DATE_MM_PATTERN = re.compile(r"^\d{2}/\d{2}$")
    DATE_PREFIX_PATTERN = re.compile(r"^(?P<date>\d{2}/\d{2})\s+(?P<body>.+)$")
    DOCUMENT_NUMBER_PATTERN = re.compile(r"^\d{8,}$")

    BRANCH_OPTIONS = [
        "OFICINA BANCA VIRTUAL",
        "OFICINA LOS ANDES SERVICIO AL",
        "OFICINA SAN FELIPE SERVICIO AL",
        "OF. BANCA VIRTUAL",
        "OF. BAN",
        "INTERNET",
        "CENTRAL",
    ]

    HEADER_STOP_LINES = {
        "DIA/MES",
        "SUCURSAL",
        "CARGOS",
        "SALDO",
        "N°",
        "MONTO",
        "DEPOSITOS Y",
        "OTROS ABONOS",
    }

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""

        normalized_text = self._clean_text(first_page_text).upper()

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

        account_match = re.search(
            r"N° DE CUENTA\s*:\s*(\d+)",
            first_page_text,
            re.IGNORECASE,
        )

        period_match = re.search(
            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
            first_page_text,
            re.IGNORECASE,
        )

        holder_name = self._extract_holder_name(first_page_text)

        return {
            "detected_institution_name": "Banco de Chile",
            "detected_holder_name": holder_name,
            "detected_account_number": account_match.group(1) if account_match else None,
            "document_date_from": datetime.strptime(period_match.group(1), "%d/%m/%Y").date() if period_match else None,
            "document_date_to": datetime.strptime(period_match.group(2), "%d/%m/%Y").date() if period_match else None,
        }

    def _extract_holder_name(self, page_text: str) -> str | None:
        lines = [self._clean_text(line) for line in page_text.splitlines() if self._clean_text(line)]

        ignored_markers = [
            "Estado de Cuenta",
            "CUENTA VISTA",
            "N° DE CUENTA",
            "MONEDA",
            "EJECUTIVO DE CUENTA",
            "SUCURSAL",
            "TELEFONO",
            "CARTOLA N°",
            "DESDE",
            "HASTA",
            "N° DE PAGINA",
            "FECHA",
            "DETALLE DE TRANSACCION",
            "RETENCION",
            "SALDO DISPONIBLE",
        ]

        for index, line in enumerate(lines):
            upper_line = line.upper()
            if "CUENTA VISTA" in upper_line:
                for candidate in lines[index + 1 : index + 8]:
                    candidate_upper = candidate.upper()
                    if "@" in candidate:
                        continue
                    if any(marker in candidate_upper for marker in ignored_markers):
                        continue
                    if re.fullmatch(r"\d{8,}", candidate):
                        continue
                    return candidate.strip()

        for line in lines:
            line_upper = line.upper()
            if "@" in line:
                continue
            if any(marker in line_upper for marker in ignored_markers):
                continue
            if re.fullmatch(r"\d{8,}", line):
                continue
            if len(line.split()) >= 2:
                return line.strip()

        return None

    def _extract_movements(self, pages: list[dict]) -> list[dict]:
        movements: list[dict] = []
        row_number = 1

        for page_info in pages:
            page_number = page_info["page_number"]
            page_text = page_info["text"]

            year = self._resolve_year_from_page(page_text)
            table_lines = self._extract_table_lines(page_text)
            merged_rows = self._merge_multiline_rows(table_lines)

            for merged_row in merged_rows:
                movement = self._parse_row(
                    row_text=merged_row,
                    row_number=row_number,
                    page_number=page_number,
                    year=year,
                )
                if movement is not None:
                    movements.append(movement)
                    row_number += 1

        return movements

    def _resolve_year_from_page(self, page_text: str) -> int:
        period_match = re.search(
            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
            page_text,
            re.IGNORECASE,
        )
        if period_match:
            return datetime.strptime(period_match.group(2), "%d/%m/%Y").year
        return datetime.now().year

    def _extract_table_lines(self, page_text: str) -> list[str]:
        page_lines = [self._clean_text(line) for line in page_text.splitlines() if self._clean_text(line)]

        relevant_lines: list[str] = []
        in_table = False

        for line in page_lines:
            line_upper = line.upper()

            if "FECHA" in line_upper and "DETALLE DE TRANSACCION" in line_upper:
                in_table = True
                continue

            if not in_table:
                continue

            if line_upper.startswith("RETENCION A 1 DIA"):
                break

            if "INFÓRMESE" in line_upper or "INFORMESE" in line_upper:
                continue

            if line_upper in self.HEADER_STOP_LINES:
                continue

            if re.fullmatch(r"0(?:\s+0)+\s+\d{1,3}(?:[.,]\d{3})*", line_upper):
                continue

            if re.fullmatch(r"0(?:\s+0)+", line_upper):
                continue

            relevant_lines.append(line)

        return relevant_lines

    def _merge_multiline_rows(self, lines: list[str]) -> list[str]:
        merged_rows: list[str] = []
        current_parts: list[str] = []

        for line in lines:
            if self._starts_with_date(line):
                if current_parts:
                    merged_rows.append(" ".join(current_parts))
                current_parts = [line]
                continue

            if not current_parts:
                continue

            current_parts.append(line)

        if current_parts:
            merged_rows.append(" ".join(current_parts))

        return merged_rows

    def _starts_with_date(self, line: str) -> bool:
        if len(line) < 5:
            return False
        return bool(self.DATE_MM_PATTERN.fullmatch(line[:5]))

    def _parse_row(
        self,
        row_text: str,
        row_number: int,
        page_number: int,
        year: int,
    ) -> dict | None:
        row_text = self._clean_text(row_text)
        row_upper = row_text.upper()

        if "SALDO INICIAL" in row_upper or "SALDO FINAL" in row_upper:
            return None

        date_match = self.DATE_PREFIX_PATTERN.match(row_text)
        if not date_match:
            return None

        date_raw = date_match.group("date")
        body = date_match.group("body").strip()

        parsed_columns = self._split_row_columns(body)
        if parsed_columns is None:
            return None

        description = parsed_columns["description"]
        branch = parsed_columns["branch"]
        document_number = parsed_columns["document_number"]
        charge_amount = parsed_columns["charge_amount"]
        deposit_amount = parsed_columns["deposit_amount"]
        balance_amount = parsed_columns["balance_amount"]

        detected_movement_type = self._detect_movement_type(description)

        if detected_movement_type in {"TRANSFER_IN", "REFUND"} and charge_amount > 0 and deposit_amount == 0:
            deposit_amount = charge_amount
            charge_amount = Decimal("0")

        if detected_movement_type in {"PURCHASE", "TRANSFER_OUT"} and deposit_amount > 0 and charge_amount == 0:
            charge_amount = deposit_amount
            deposit_amount = Decimal("0")

        transaction_date = datetime.strptime(f"{date_raw}/{year}", "%d/%m/%Y").date()
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}

        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": transaction_date,
            "branch": branch,
            "description": description,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
            "raw_row_text": row_text,
            "raw_row_json": {
                "page_number": page_number,
                "source_format": "BANCO_CHILE_CUENTA_VISTA",
                "parsed_columns": {
                    "description": description,
                    "branch": branch,
                    "document_number": document_number,
                    "charge_amount": str(charge_amount),
                    "deposit_amount": str(deposit_amount),
                    "balance_amount": str(balance_amount),
                },
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.98"),
        }

    def _split_row_columns(self, body: str) -> dict | None:
        tokens = body.split()
        if len(tokens) < 4:
            return None

        branch_match = self._find_branch(tokens)
        if branch_match is None:
            return None

        branch_start_index, branch_token_count, branch_value = branch_match
        if branch_start_index == 0:
            return None

        description_tokens = tokens[:branch_start_index]
        trailing_tokens = tokens[branch_start_index + branch_token_count :]

        if len(trailing_tokens) < 2:
            return None

        description = self._clean_text(" ".join(description_tokens))
        branch = branch_value

        document_number = trailing_tokens[0]
        if not self.DOCUMENT_NUMBER_PATTERN.fullmatch(document_number):
            return None

        amount_tokens = trailing_tokens[1:]
        parsed_amounts = self._parse_amount_columns(amount_tokens, description)

        if parsed_amounts is None:
            return None

        embedded_document_number = self._extract_embedded_document_number(description)
        if embedded_document_number and document_number == "00000000":
            document_number = embedded_document_number

        return {
            "description": description,
            "branch": branch,
            "document_number": document_number,
            "charge_amount": parsed_amounts["charge_amount"],
            "deposit_amount": parsed_amounts["deposit_amount"],
            "balance_amount": parsed_amounts["balance_amount"],
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

    def _parse_amount_columns(self, tokens: list[str], description: str) -> dict | None:
        amount_like_tokens = [token for token in tokens if self._is_amount_token(token)]

        if len(amount_like_tokens) < 2:
            return None

        if len(amount_like_tokens) == 2:
            movement_amount = self._parse_amount(amount_like_tokens[0])
            balance_amount = self._parse_amount(amount_like_tokens[1])

            movement_type = self._detect_movement_type(description)
            if movement_type in {"TRANSFER_IN", "REFUND"}:
                return {
                    "charge_amount": Decimal("0"),
                    "deposit_amount": movement_amount,
                    "balance_amount": balance_amount,
                }

            return {
                "charge_amount": movement_amount,
                "deposit_amount": Decimal("0"),
                "balance_amount": balance_amount,
            }

        first_amount = self._parse_amount(amount_like_tokens[0])
        second_amount = self._parse_amount(amount_like_tokens[1])
        balance_amount = self._parse_amount(amount_like_tokens[2])

        if first_amount == 0 and second_amount > 0:
            return {
                "charge_amount": Decimal("0"),
                "deposit_amount": second_amount,
                "balance_amount": balance_amount,
            }

        if second_amount == 0 and first_amount > 0:
            return {
                "charge_amount": first_amount,
                "deposit_amount": Decimal("0"),
                "balance_amount": balance_amount,
            }

        return {
            "charge_amount": first_amount,
            "deposit_amount": second_amount,
            "balance_amount": balance_amount,
        }

    def _extract_embedded_document_number(self, text: str) -> str | None:
        candidates = re.findall(r"\b\d{8,}\b", text)
        if not candidates:
            return None
        return candidates[0]

    def _is_amount_token(self, value: str) -> bool:
        cleaned_value = self._clean_text(value)
        return bool(re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*", cleaned_value))

    def _parse_amount(self, value: str) -> Decimal:
        cleaned_value = self._clean_text(value)
        if not cleaned_value:
            return Decimal("0")

        amount_match = re.search(r"\d{1,3}(?:[.,]\d{3})*", cleaned_value)
        if not amount_match:
            return Decimal("0")

        normalized_amount = amount_match.group(0).replace(".", "").replace(",", "")
        return Decimal(normalized_amount)

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if "TRASPASO A:" in description_upper or "TRASPASO A CUENTA:" in description_upper:
            return "TRANSFER_OUT"

        if "TRASPASO DE:" in description_upper or "TRASPASO DE CUENTA:" in description_upper:
            return "TRANSFER_IN"

        if "ABONO SEGUN INSTRUC." in description_upper:
            return "TRANSFER_IN"

        if "DEVOLUCION:" in description_upper:
            return "REFUND"

        if (
            "PAGO:" in description_upper
            or "REGULARIZACION DE CARGOS" in description_upper
            or "CARGO POR PAGO TC" in description_upper
            or "GIRO CAJERO AUTOMATICO" in description_upper
            or "COMISION " in description_upper
            or "COMISION GIRO" in description_upper
            or "COMISION GIROS" in description_upper
            or "PAP " in description_upper
        ):
            return "PURCHASE"

        return "UNKNOWN"

    def _clean_text(self, value: str) -> str:
        return " ".join(str(value).split())