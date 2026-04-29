import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoChileCuentaVistaEstadoCuentaParser(BaseParser):
    DATE_MM_PATTERN = re.compile(r"^\d{2}/\d{2}$")
    DATE_DDMMYYYY_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    DATE_PREFIX_PATTERN = re.compile(r"^(?P<date>\d{2}/\d{2})\s+(?P<body>.+)$")
    DATE_FULL_PREFIX_PATTERN = re.compile(r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<body>.+)$")
    DOCUMENT_NUMBER_PATTERN = re.compile(r"^\d{8,}$")

    BRANCH_OPTIONS = [
        "OFICINA LOS ANDES SERVICIO AL",
        "OFICINA SAN FELIPE SERVICIO AL",
        "OFICINA CENTRAL (SB)",
        "OFICINA CENTRAL",
        "OFICINA BANCA VIRTUAL",
        "OF. BANCA VIRTUAL",
        "OF. BAN",
        "OF. SAN",
        "INTERNET",
        "CENTRAL",
        "BANCA MOVIL",
    ]

    NEW_FORMAT_CHANNEL_OPTIONS = [
        "Oficina Central",
        "San Felipe",
        "Internet",
        "Banca Movil",
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
        "O ABONOS",
        "N° DOCTO MONTO CARGOS",
    }

    NEW_FORMAT_HEADER_STOP_LINES = {
        "FECHA",
        "DESCRIPCIÓN",
        "DESCRIPCION",
        "CANAL O",
        "SUCURSAL",
        "Nº DOCUMENTO",
        "N° DOCUMENTO",
        "CARGOS (CLP)",
        "ABONOS (CLP)",
        "SALDO (CLP)",
    }

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)

        if path.suffix.lower() != ".pdf":
            return False

        with pdfplumber.open(path) as pdf:
            page_texts = [page.extract_text() or "" for page in pdf.pages]

        normalized_pages = [self._clean_text(text).upper() for text in page_texts]
        normalized_document = "\n".join(normalized_pages)

        if "CUENTA CORRIENTE" in normalized_document and "CUENTA VISTA" not in normalized_document:
            return False

        has_classic_format = any(
            "ESTADO DE CUENTA" in normalized_text
            and "CUENTA VISTA" in normalized_text
            and "N° DE CUENTA" in normalized_text
            for normalized_text in normalized_pages
        )

        has_new_format = any(
            "SALDO Y MOVIMIENTOS DE CUENTA" in normalized_text
            and "MOVIMIENTOS DESDE" in normalized_text
            and ("Nº DOCUMENTO" in normalized_text or "N° DOCUMENTO" in normalized_text)
            and "CARGOS (CLP)" in normalized_text
            and "ABONOS (CLP)" in normalized_text
            and "SALDO (CLP)" in normalized_text
            for normalized_text in normalized_pages
        )

        return has_classic_format or ("CUENTA VISTA" in normalized_document and has_new_format)

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
            "document_metadata": {
                **document_metadata,
                "detected_statement_type": "CUENTA_VISTA",
            },
            "movements": movements,
        }

    def _extract_metadata(self, pages: list[dict]) -> dict:
        first_page_text = pages[0]["text"]
        normalized_first_page_text = self._clean_text(first_page_text)

        account_match = re.search(
            r"N° DE CUENTA\s*:\s*(\d+)",
            first_page_text,
            re.IGNORECASE,
        )

        account_match_value = None
        if account_match:
            account_match_value = account_match.group(1)
        else:
            dashed_account_match = re.search(
                r"\b\d{2}-\d{3}-\d{5}-\d{2}\b",
                normalized_first_page_text,
            )
            if dashed_account_match:
                account_match_value = re.sub(r"\D", "", dashed_account_match.group(0))

        document_period = None
        for page in pages:
            document_period = self._extract_period(page["text"])
            if document_period:
                break

        holder_name = self._extract_holder_name(first_page_text)

        available_balance_match = re.search(
            r"Saldo Disponible\s+([\d\.,]+)",
            normalized_first_page_text,
            re.IGNORECASE,
        )
        accounting_balance_match = re.search(
            r"Saldo Contable\s+([\d\.,]+)",
            normalized_first_page_text,
            re.IGNORECASE,
        )
        total_charges_match = re.search(
            r"Total Cargos\s+([\d\.,]+)",
            normalized_first_page_text,
            re.IGNORECASE,
        )
        total_credits_match = re.search(
            r"Total Abonos\s+([\d\.,]+)",
            normalized_first_page_text,
            re.IGNORECASE,
        )

        return {
            "detected_institution_name": "Banco de Chile",
            "detected_holder_name": holder_name,
            "detected_account_number": account_match_value,
            "document_date_from": document_period[0] if document_period else None,
            "document_date_to": document_period[1] if document_period else None,
            "detected_available_balance": self._parse_amount(available_balance_match.group(1)) if available_balance_match else None,
            "detected_accounting_balance": self._parse_amount(accounting_balance_match.group(1)) if accounting_balance_match else None,
            "detected_total_charges": self._parse_amount(total_charges_match.group(1)) if total_charges_match else None,
            "detected_total_credits": self._parse_amount(total_credits_match.group(1)) if total_credits_match else None,
        }

    def _extract_holder_name(self, page_text: str) -> str | None:
        sr_match = re.search(
            r"Sr\(a\)\.:\s*(.*?)\s+Rut\.:",
            page_text,
            re.IGNORECASE | re.DOTALL,
        )
        if sr_match:
            return self._clean_text(sr_match.group(1))

        lines = [self._clean_text(line) for line in page_text.splitlines() if self._clean_text(line)]

        ignored_markers = [
            "ESTADO DE CUENTA",
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
            "N° MONTO",
            "N° DOCTO",
            "SALDO Y MOVIMIENTOS DE CUENTA",
            "MOVIMIENTOS DESDE",
            "Nº DOCUMENTO",
            "N° DOCUMENTO",
            "CARGOS (CLP)",
            "ABONOS (CLP)",
            "SALDO (CLP)",
        ]

        for line in lines:
            upper_line = line.upper()
            if "@" in line:
                continue
            if any(marker in upper_line for marker in ignored_markers):
                continue
            if re.fullmatch(r"\d{8,}", line):
                continue
            if re.fullmatch(r"\d{2}-\d{3}-\d{5}-\d{2}", line):
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

            if self._is_new_format_page(page_text):
                new_format_rows = self._extract_new_format_rows(page_text)

                for row_text in new_format_rows:
                    movement = self._parse_new_format_row(
                        row_text=row_text,
                        row_number=row_number,
                        page_number=page_number,
                    )
                    if movement is not None:
                        movements.append(movement)
                        row_number += 1
                continue

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

    def _is_new_format_page(self, page_text: str) -> bool:
        normalized_text = self._clean_text(page_text).upper()
        has_full_header = (
            "SALDO Y MOVIMIENTOS DE CUENTA" in normalized_text
            and "MOVIMIENTOS DESDE" in normalized_text
            and ("Nº DOCUMENTO" in normalized_text or "N° DOCUMENTO" in normalized_text)
            and "CARGOS (CLP)" in normalized_text
            and "ABONOS (CLP)" in normalized_text
            and "SALDO (CLP)" in normalized_text
        )

        has_continuation_header = (
            "FECHA" in normalized_text
            and "DESCRIP" in normalized_text
            and "CARGOS (CLP)" in normalized_text
            and "ABONOS (CLP)" in normalized_text
            and "SALDO (CLP)" in normalized_text
            and ("CANAL" in normalized_text or "SUCURSAL" in normalized_text)
        )

        return has_full_header or has_continuation_header

    def _extract_new_format_rows(self, page_text: str) -> list[str]:
        page_lines = [self._clean_text(line) for line in page_text.splitlines() if self._clean_text(line)]

        relevant_rows: list[str] = []
        in_table = False
        current_row: str | None = None
        pending_description_prefix: str | None = None

        def flush_current_row():
            nonlocal current_row
            if current_row:
                relevant_rows.append(current_row)
                current_row = None

        for line in page_lines:
            line_upper = line.upper()

            if not in_table and "FECHA" in line_upper and "DESCRIP" in line_upper:
                in_table = True
                continue

            if not in_table:
                continue

            if "INFÓRMESE SOBRE LA GARANTÍA ESTATAL" in line_upper or "INFORMESE SOBRE LA GARANTIA ESTATAL" in line_upper:
                break

            if line_upper in self.NEW_FORMAT_HEADER_STOP_LINES:
                continue

            if "Nº DOCUMENTO" in line_upper or "N° DOCUMENTO" in line_upper:
                continue

            if "CARGOS (CLP)" in line_upper or "ABONOS (CLP)" in line_upper or "SALDO (CLP)" in line_upper:
                continue

            if len(line) >= 10 and self.DATE_DDMMYYYY_PATTERN.fullmatch(line[:10]):
                flush_current_row()
                if pending_description_prefix:
                    current_row = f"{line[:10]} {pending_description_prefix} {line[10:].strip()}"
                    pending_description_prefix = None
                else:
                    current_row = line
                continue

            if current_row:
                if self._looks_like_new_format_description_prefix(line):
                    flush_current_row()
                    pending_description_prefix = line
                    continue

                current_row = f"{current_row} {line}"
                continue

            if pending_description_prefix:
                pending_description_prefix = f"{pending_description_prefix} {line}"
            else:
                pending_description_prefix = line

        flush_current_row()
        return relevant_rows

    def _parse_new_format_row(
        self,
        row_text: str,
        row_number: int,
        page_number: int,
    ) -> dict | None:
        row_text = self._clean_text(row_text)

        date_match = self.DATE_FULL_PREFIX_PATTERN.match(row_text)
        if not date_match:
            return None

        transaction_date = datetime.strptime(date_match.group("date"), "%d/%m/%Y").date()
        body = date_match.group("body").strip()

        tokens = body.split()
        if len(tokens) < 5:
            return None

        channel_match = self._find_new_format_channel(tokens)
        if channel_match is None:
            return None

        channel_start_index, channel_token_count, channel_value = channel_match

        description_tokens = tokens[:channel_start_index]
        post_channel_tokens = tokens[channel_start_index + channel_token_count :]

        if not description_tokens:
            return None

        document_number = None
        if post_channel_tokens and not self._is_amount_token(post_channel_tokens[0]):
            candidate_document = post_channel_tokens[0]
            if candidate_document != "-":
                document_number = candidate_document
            post_channel_tokens = post_channel_tokens[1:]

        amount_positions = [
            index for index, token in enumerate(post_channel_tokens)
            if self._is_amount_token(token)
        ]

        if len(amount_positions) < 3:
            return None

        charge_token = post_channel_tokens[amount_positions[0]]
        deposit_token = post_channel_tokens[amount_positions[1]]
        balance_token = post_channel_tokens[amount_positions[2]]
        continuation_tokens = post_channel_tokens[amount_positions[2] + 1:]

        description = self._clean_text(" ".join([*description_tokens, *continuation_tokens]))
        branch = channel_value

        charge_amount = self._parse_amount(charge_token)
        deposit_amount = self._parse_amount(deposit_token)
        balance_amount = self._parse_amount(balance_token)

        detected_movement_type = self._detect_movement_type(description)
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
                "source_format": "BANCO_CHILE_CUENTA_VISTA_NEW_FORMAT",
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
            "confidence_score": Decimal("0.99"),
        }

    def _find_new_format_channel(self, tokens: list[str]) -> tuple[int, int, str] | None:
        channel_variants = []
        for channel_option in self.NEW_FORMAT_CHANNEL_OPTIONS:
            channel_tokens = channel_option.split()
            channel_variants.append((channel_tokens, channel_option))

        channel_variants.sort(key=lambda item: len(item[0]), reverse=True)

        for token_index in range(len(tokens)):
            for channel_tokens, original_value in channel_variants:
                token_slice = tokens[token_index : token_index + len(channel_tokens)]
                if [token.upper() for token in token_slice] == [token.upper() for token in channel_tokens]:
                    return token_index, len(channel_tokens), original_value

        return None

    def _looks_like_new_format_description_prefix(self, line: str) -> bool:
        upper_line = self._clean_text(line).upper()
        return upper_line.startswith(
            (
                "TRASPASO ",
                "PAGO:",
                "PAGO ",
                "CARGO ",
                "ABONO ",
                "GIRO ",
                "COMISION ",
                "REGULARIZACION ",
                "IMPUESTO ",
                "INTERESES ",
                "PRIMA ",
                "CPC.",
            )
        )

    def _resolve_year_from_page(self, page_text: str) -> int:
        period = self._extract_period(page_text)
        if period:
            return period[1].year
        return datetime.now().year

    @staticmethod
    def _extract_period(page_text: str):
        patterns = [
            r"DESDE\s*:\s*(\d{2}/\d{2}/\d{4})\s+HASTA\s*:\s*(\d{2}/\d{2}/\d{4})",
            r"Movimientos\s+desde\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in patterns:
            period_match = re.search(pattern, page_text, re.IGNORECASE)
            if period_match:
                return (
                    datetime.strptime(period_match.group(1), "%d/%m/%Y").date(),
                    datetime.strptime(period_match.group(2), "%d/%m/%Y").date(),
                )

        return None

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
        if len(tokens) < 3:
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

        parsed_new = self._try_parse_new_format(description, branch, trailing_tokens)
        if parsed_new is not None:
            return parsed_new

        parsed_old = self._try_parse_old_format(description, branch, trailing_tokens)
        if parsed_old is not None:
            return parsed_old

        return None

    def _try_parse_new_format(self, description: str, branch: str, trailing_tokens: list[str]) -> dict | None:
        if len(trailing_tokens) < 3:
            return None

        document_number = trailing_tokens[0]
        if not self.DOCUMENT_NUMBER_PATTERN.fullmatch(document_number):
            return None

        remainder_tokens = trailing_tokens[1:]
        amount_tokens = [token for token in remainder_tokens if self._is_amount_token(token)]

        if len(amount_tokens) < 2:
            return None

        movement_amount = self._parse_amount(amount_tokens[0])
        balance_amount = self._parse_amount(amount_tokens[1])

        continuation_tokens = [
            token for token in remainder_tokens
            if token not in amount_tokens[:2]
        ]

        embedded_document_number = self._extract_embedded_document_number(" ".join(continuation_tokens))
        if embedded_document_number and document_number == "00000000":
            document_number = embedded_document_number

        description_suffix = self._build_description_suffix(continuation_tokens)
        if description_suffix:
            description = self._clean_text(f"{description} {description_suffix}")

        movement_type = self._detect_movement_type(description)

        if movement_type in {"TRANSFER_IN", "REFUND"}:
            charge_amount = Decimal("0")
            deposit_amount = movement_amount
        else:
            charge_amount = movement_amount
            deposit_amount = Decimal("0")

        return {
            "description": description,
            "branch": branch,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
        }

    def _try_parse_old_format(self, description: str, branch: str, trailing_tokens: list[str]) -> dict | None:
        amount_tokens = [token for token in trailing_tokens if self._is_amount_token(token)]
        if len(amount_tokens) < 2:
            return None

        movement_amount = self._parse_amount(amount_tokens[0])
        balance_amount = self._parse_amount(amount_tokens[1])

        remaining_tokens = trailing_tokens.copy()

        for token in amount_tokens[:2]:
            if token in remaining_tokens:
                remaining_tokens.remove(token)

        document_number = None
        embedded_doc = self._extract_embedded_document_number(" ".join(remaining_tokens))
        if embedded_doc:
            document_number = embedded_doc
            remaining_tokens = [token for token in remaining_tokens if token != embedded_doc]

        description_suffix = self._build_description_suffix(remaining_tokens)
        if description_suffix:
            description = self._clean_text(f"{description} {description_suffix}")

        movement_type = self._detect_movement_type(description)

        if movement_type in {"TRANSFER_IN", "REFUND"}:
            charge_amount = Decimal("0")
            deposit_amount = movement_amount
        else:
            charge_amount = movement_amount
            deposit_amount = Decimal("0")

        return {
            "description": description,
            "branch": branch,
            "document_number": document_number,
            "charge_amount": charge_amount,
            "deposit_amount": deposit_amount,
            "balance_amount": balance_amount,
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

    def _build_description_suffix(self, tokens: list[str]) -> str:
        if not tokens:
            return ""

        suffix_tokens = []
        for token in tokens:
            if self.DOCUMENT_NUMBER_PATTERN.fullmatch(token):
                continue
            suffix_tokens.append(token)

        return self._clean_text(" ".join(suffix_tokens))

    def _extract_embedded_document_number(self, text: str) -> str | None:
        candidates = re.findall(r"\b\d{8,}\b", text)
        if not candidates:
            return None
        return candidates[0]

    def _is_amount_token(self, value: str) -> bool:
        cleaned_value = self._clean_text(value)
        return bool(re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*", cleaned_value))

    def _parse_amount(self, value: str) -> Decimal:
        cleaned_value = self._clean_text(str(value))
        if not cleaned_value:
            return Decimal("0")

        amount_match = re.search(r"\d{1,3}(?:[.,]\d{3})*", cleaned_value)
        if not amount_match:
            return Decimal("0")

        normalized_amount = amount_match.group(0).replace(".", "").replace(",", "")
        return Decimal(normalized_amount)

    def _detect_movement_type(self, description: str) -> str:
        description_upper = description.upper()

        if (
            "TRASPASO A:" in description_upper
            or re.search(r"\bTRASPASO\s+A\s+CUENTA:?\s*\d+", description_upper)
        ):
            return "TRANSFER_OUT"

        if (
            "TRASPASO DE:" in description_upper
            or re.search(r"\bTRASPASO\s+DE\s+CUENTA:?\s*\d+", description_upper)
        ):
            return "TRANSFER_IN"

        if "ABONO SEGUN INSTRUC." in description_upper:
            return "TRANSFER_IN"

        if "PAGO:PROVEEDORES" in description_upper or "PAGO PROVEEDORES" in description_upper:
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
