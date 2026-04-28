"""
Parser para Estado de Cuenta Corriente - Banco de Chile
Soporta 3 formatos:
  - CLASSIC (coma)  : montos con coma  → 6,951,835  (PDFs históricos)
  - CLASSIC (punto) : montos con punto → 111.625    (PDFs nuevos 2025+)
  - NEW_FORMAT      : tabla web        → columnas separadas (descarga online)

Estrategia de extracción:
  - NEW_FORMAT : texto plano, último 3 tokens son cargo/abono/saldo (ya separados)
  - CLASSIC    : texto plano para descripción+sucursal+monto, tipo de movimiento
                 determina cargo vs abono (la cartola NO distingue en texto plano)
"""

import re
from datetime import date, datetime
from decimal import Decimal

import pdfplumber

try:
    from app.parsers.base_parser import BaseParser
except ImportError:
    class BaseParser:
        def validate_file_exists(self, file_path: str):
            from pathlib import Path
            p = Path(file_path)
            if not p.exists():
                raise FileNotFoundError(file_path)
            return p


# ─── Constantes ──────────────────────────────────────────────────────────────

_DATE_MM_RE       = re.compile(r"^\d{2}/\d{2}$")
_DATE_DDMMYYYY_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_AMOUNT_RE        = re.compile(r"^\d{1,3}(?:[.,]\d{3})*$")
_DOCUMENT_NUM_RE  = re.compile(r"^\d{7,}$")

_CLASSIC_BRANCHES = [
    "OFICINA LOS ANDES SERVICIO AL",
    "OFICINA SAN FELIPE SERVICIO AL",
    "OFICINA CENTRAL (SB)",
    "OFICINA CENTRAL",
    "OF. SAN FELIPE",
    "OF. LOS ANDES",
    "OF. BAN",
    "OF. SAN",
    "INTERNET",
    "CENTRAL",
    "BANCA MOVIL",
]

_NEW_FORMAT_CHANNELS = ["Oficina Central", "San Felipe", "Internet", "Banca Movil"]

# Tipos de movimiento que son ABONOS (entradas de dinero)
_CREDIT_TYPES = frozenset({
    "TRANSFER_IN",
    "DEPOSIT",
    "REFUND",
    "CREDIT_LINE_TRANSFER_IN",
    "SALARY_PAYMENT",
})

# Tipos que son CARGOS especiales (salidas que el banco puede poner en col abono)
# En el formato clásico la columna "MONTO DEPOSITOS O ABONOS" incluye:
# - ABONO POR CAPTACIONES → DEPOSIT
# - TRASPASO DE: → TRANSFER_IN
# - PAGO:DE SUELDOS → SALARY_PAYMENT
# - DEP.CHEQ.OTROS BANCOS → DEPOSIT
# Resto → CARGO


# ─── Parser principal ─────────────────────────────────────────────────────────

class BancoChileCuentaCorrienteEstadoCuentaParser(BaseParser):

    # ── Detección ─────────────────────────────────────────────────────────────

    def can_parse(self, file_path: str) -> bool:
        path = self.validate_file_exists(file_path)
        if path.suffix.lower() != ".pdf":
            return False
        with pdfplumber.open(path) as pdf:
            page_texts = [page.extract_text() or "" for page in pdf.pages]

        normalized_pages = [self._clean(text).upper() for text in page_texts]
        normalized_document = "\n".join(normalized_pages)

        if "CUENTA VISTA" in normalized_document and "CUENTA CORRIENTE" not in normalized_document:
            return False

        if "CUENTA CORRIENTE" not in normalized_document:
            return False

        return any(self._detect_format(text) != "UNKNOWN" for text in normalized_pages)

    @staticmethod
    def _detect_format(upper_text: str) -> str:
        if "SALDO Y MOVIMIENTOS DE CUENTA" in upper_text and "CARGOS (CLP)" in upper_text:
            return "NEW_FORMAT"
        if (
            "FECHA" in upper_text
            and "DESCRIP" in upper_text
            and "CARGOS (CLP)" in upper_text
            and "ABONOS (CLP)" in upper_text
            and "SALDO (CLP)" in upper_text
            and ("CANAL" in upper_text or "SUCURSAL" in upper_text)
        ):
            return "NEW_FORMAT"
        if "ESTADO DE CUENTA" in upper_text and "DETALLE DE TRANSACCION" in upper_text:
            return "CLASSIC"
        return "UNKNOWN"

    # ── Punto de entrada ──────────────────────────────────────────────────────

    def parse(self, file_path: str) -> dict:
        path = self.validate_file_exists(file_path)
        with pdfplumber.open(path) as pdf:
            pages_data = []
            for i, page in enumerate(pdf.pages):
                pages_data.append({
                    "page_number": i + 1,
                    "text": page.extract_text() or "",
                    "words": page.extract_words(x_tolerance=3, y_tolerance=3),
                })

        metadata  = self._extract_metadata(pages_data)
        movements = self._extract_movements(pages_data)

        return {
            "parser_code": "BANCO_CHILE_CUENTA_CORRIENTE_ESTADO_CUENTA",
            "document_metadata": {
                **metadata,
                "detected_statement_type": "CUENTA_CORRIENTE",
            },
            "movements": movements,
        }

    # ── Metadatos ─────────────────────────────────────────────────────────────

    def _extract_metadata(self, pages_data: list[dict]) -> dict:
        first_text = pages_data[0]["text"]
        clean = self._clean(first_text)

        account = None
        m = re.search(r"N°\s*DE\s*CUENTA\s*:\s*(\d+)", first_text, re.IGNORECASE)
        if m:
            account = m.group(1)
        else:
            m = re.search(r"\b(\d{2}-\d{3}-\d{5}-\d{2})\b", clean)
            if m:
                account = re.sub(r"\D", "", m.group(1))
            else:
                m = re.search(r"Cuenta\s+([\d-]+)", first_text, re.IGNORECASE)
                if m:
                    account = re.sub(r"\D", "", m.group(1))

        date_from = date_to = None
        for pg in pages_data:
            period = self._extract_period(pg["text"])
            if period:
                date_from, date_to = period
                break

        holder = self._extract_holder(first_text)

        def _bal(pattern: str):
            mm = re.search(pattern, clean, re.IGNORECASE)
            return self._parse_amount(mm.group(1)) if mm else None

        return {
            "detected_institution_name": "Banco de Chile",
            "detected_holder_name": holder,
            "detected_account_number": account,
            "document_date_from": date_from,
            "document_date_to": date_to,
            "detected_available_balance": _bal(r"Saldo\s+Disponible\s+([\d.,]+)"),
            "detected_accounting_balance": _bal(r"Saldo\s+Contable\s+([\d.,]+)"),
            "detected_total_charges": _bal(r"Total\s+Cargos\s+([\d.,]+)"),
            "detected_total_credits": _bal(r"Total\s+Abonos\s+([\d.,]+)"),
        }

    @staticmethod
    def _extract_holder(text: str) -> str | None:
        # Nuevo formato: "Sr(a).: Nombre  Rut.:"
        m = re.search(r"Sr\(a\)\.\s*:\s*(.*?)\s+Rut\.", text, re.IGNORECASE | re.DOTALL)
        if m:
            return " ".join(m.group(1).split())
        # Formato clásico: SR(A)(ES) en una línea, nombre en la línea siguiente
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "SR(A)(ES)" in line.upper():
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and not any(kw in candidate.upper() for kw in [
                        "APROBADO", "UTILIZADO", "DISPONIBLE", "VENCIMIENTO",
                        "@", "EJECUTIVO", "SUCURSAL", "TELEFONO", "LINEA DE CREDITO",
                    ]):
                        return " ".join(candidate.split())
                break
        return None

    # ── Movimientos ───────────────────────────────────────────────────────────

    def _extract_movements(self, pages_data: list[dict]) -> list[dict]:
        movements: list[dict] = []
        row_number = 1

        for page in pages_data:
            fmt = self._detect_format(self._clean(page["text"]).upper())
            if fmt == "NEW_FORMAT":
                rows = self._parse_new_format_page(page)
            elif fmt == "CLASSIC":
                rows = self._parse_classic_page(page)
            else:
                continue

            for mv in rows:
                mv["row_number"]  = row_number
                mv["page_number"] = page["page_number"]
                movements.append(mv)
                row_number += 1

        return movements

    # ─── Nuevo formato (web) ──────────────────────────────────────────────────

    def _parse_new_format_page(self, page: dict) -> list[dict]:
        lines    = [self._clean(l) for l in page["text"].splitlines() if self._clean(l)]
        rows: list[dict] = []
        in_table = False
        current_line: str | None = None
        pending_description_prefix: str | None = None

        def flush_current_line():
            nonlocal current_line
            if current_line:
                mv = self._parse_new_format_line(current_line)
                if mv:
                    rows.append(mv)
                current_line = None

        for line in lines:
            upper = line.upper()
            if not in_table:
                if "FECHA" in upper and "DESCRIP" in upper:
                    in_table = True
                continue
            if "INFORMESE" in upper or "INFÓRMESE" in upper:
                break
            if "CARGOS (CLP)" in upper or "ABONOS (CLP)" in upper or "SALDO (CLP)" in upper:
                continue
            if len(line) >= 10 and _DATE_DDMMYYYY_RE.fullmatch(line[:10]):
                flush_current_line()
                if pending_description_prefix:
                    current_line = f"{line[:10]} {pending_description_prefix} {line[10:].strip()}"
                    pending_description_prefix = None
                else:
                    current_line = line
                continue

            if current_line:
                if self._looks_like_new_format_description_prefix(line):
                    flush_current_line()
                    pending_description_prefix = line
                    continue

                current_line = f"{current_line} {line}"
                continue

            if pending_description_prefix:
                pending_description_prefix = f"{pending_description_prefix} {line}"
            else:
                pending_description_prefix = line

        flush_current_line()
        return rows

    def _parse_new_format_line(self, line: str) -> dict | None:
        tokens = line.split()
        if len(tokens) < 6:
            return None
        try:
            txn_date = datetime.strptime(tokens[0], "%d/%m/%Y").date()
        except ValueError:
            return None

        body = tokens[1:]
        if len(body) < 5:
            return None

        channel_match = self._find_new_channel(body)
        if channel_match is None:
            return None

        ch_start, ch_count, channel = channel_match
        desc_tokens = body[:ch_start]
        post_tokens = body[ch_start + ch_count:]

        if not desc_tokens:
            return None

        doc_num = None
        if post_tokens and not self._is_amount(post_tokens[0]):
            if post_tokens[0] != "-":
                doc_num = post_tokens[0]
            post_tokens = post_tokens[1:]

        amount_positions = [
            index for index, token in enumerate(post_tokens)
            if self._is_amount(token)
        ]

        if len(amount_positions) < 3:
            return None

        t_cargo = post_tokens[amount_positions[0]]
        t_abono = post_tokens[amount_positions[1]]
        t_saldo = post_tokens[amount_positions[2]]
        continuation_tokens = post_tokens[amount_positions[2] + 1:]

        description = " ".join([*desc_tokens, *continuation_tokens])

        charge  = self._parse_amount(t_cargo)
        deposit = self._parse_amount(t_abono)
        balance = self._parse_amount(t_saldo)
        mtype   = self._detect_movement_type(description)

        return {
            "transaction_date": txn_date,
            "branch": channel,
            "description": description,
            "document_number": doc_num,
            "charge_amount": charge,
            "deposit_amount": deposit,
            "balance_amount": balance,
            "raw_row_text": line,
            "raw_row_json": {
                "source_format": "BANCO_CHILE_CUENTA_CORRIENTE_NEW_FORMAT",
                "parsed_columns": {
                    "description": description, "branch": channel,
                    "document_number": doc_num,
                    "charge_amount": str(charge),
                    "deposit_amount": str(deposit),
                    "balance_amount": str(balance),
                },
            },
            "detected_movement_type": mtype,
            "is_transfer_candidate": mtype in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.99"),
        }

    def _find_new_channel(self, tokens: list[str]) -> tuple[int, int, str] | None:
        variants = sorted(
            [(ch.split(), ch) for ch in _NEW_FORMAT_CHANNELS],
            key=lambda x: len(x[0]),
            reverse=True,
        )
        for i in range(len(tokens)):
            for ch_tokens, original in variants:
                sl = tokens[i: i + len(ch_tokens)]
                if [t.upper() for t in sl] == [t.upper() for t in ch_tokens]:
                    return i, len(ch_tokens), original
        return None

    @staticmethod
    def _looks_like_new_format_description_prefix(line: str) -> bool:
        upper = " ".join(line.split()).upper()
        return upper.startswith(
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

    # ─── Formato clásico (texto plano + lógica de tipo) ───────────────────────

    def _parse_classic_page(self, page: dict) -> list[dict]:
        """
        Parsea una página de formato clásico usando texto plano.
        La columna cargo/abono se determina por el tipo de movimiento
        porque en el texto plano están aplanadas.
        """
        text   = page["text"]
        period = self._extract_period(text)
        lines  = [self._clean(l) for l in text.splitlines() if self._clean(l)]

        in_table = False
        results: list[dict] = []
        current_line: str | None = None

        for line in lines:
            upper = line.upper()

            if not in_table:
                if "DETALLE DE TRANSACCION" in upper and ("FECHA" in upper or "DIA" in upper):
                    in_table = True
                continue

            if upper.startswith("RETENCION A 1 DIA"):
                break
            if "INFORMESE" in upper or "INFÓRMESE" in upper:
                continue
            if upper in {"DIA/MES", "DIA/ME", "SUCURSAL", "N° DOCTO",
                         "MONTO CHEQUES", "O CARGOS", "MONTO DEPOSITOS", "O ABONOS", "SALDO",
                         "CHEQUES", "DEPOSITOS", "OTROS ABONOS", "OTROS CARGOS",
                         "GIROS CAJERO AUTOMATICO", "IMPUESTOS"}:
                continue

            # Línea de continuación ID:EXP
            if line.upper().startswith("ID:EXP") or line.upper().startswith("ID:"):
                if current_line:
                    current_line = current_line  # ignorar ID:EXP
                continue

            # Nueva fila de transacción
            if len(line) >= 5 and _DATE_MM_RE.fullmatch(line[:5]):
                if current_line and "SALDO INICIAL" not in current_line.upper() and "SALDO FINAL" not in current_line.upper():
                    mv = self._parse_classic_line(current_line, period)
                    if mv:
                        results.append(mv)
                current_line = line
                continue

            # Línea de continuación
            if current_line:
                if not self._looks_like_footer(line):
                    current_line = current_line + " " + line

        # Última línea pendiente
        if current_line and "SALDO INICIAL" not in current_line.upper() and "SALDO FINAL" not in current_line.upper():
            mv = self._parse_classic_line(current_line, period)
            if mv:
                results.append(mv)

        return results

    def _parse_classic_line(self, line: str, period: tuple[date, date] | None) -> dict | None:
        tokens = line.split()
        if not tokens:
            return None

        date_raw = tokens[0]
        if not (len(date_raw) == 5 and _DATE_MM_RE.fullmatch(date_raw)):
            return None

        body = tokens[1:]

        # Buscar sucursal (más larga primero)
        branch      = ""
        desc_tokens: list[str] = []
        trailing:   list[str] = []

        for bp in sorted(_CLASSIC_BRANCHES, key=len, reverse=True):
            bp_tokens = bp.split()
            n         = len(bp_tokens)
            for i in range(len(body) - n + 1):
                if [t.upper() for t in body[i:i+n]] == [t.upper() for t in bp_tokens]:
                    branch      = " ".join(body[i:i+n])  # usar el texto real (case original)
                    desc_tokens = body[:i]
                    trailing    = body[i+n:]
                    break
            if branch:
                break

        if not desc_tokens:
            # Sin sucursal reconocida — ignorar
            return None

        description = " ".join(desc_tokens)

        # Extraer número de documento y montos del trailing
        doc_num: str | None = None
        amounts: list[str] = []

        j = 0
        if j < len(trailing) and _DOCUMENT_NUM_RE.fullmatch(trailing[j]):
            doc_num = trailing[j]
            j += 1

        while j < len(trailing):
            t = trailing[j]
            if _AMOUNT_RE.fullmatch(t):
                amounts.append(t)
            j += 1

        if not amounts:
            return None

        # El primer monto es siempre el de la transacción
        # El segundo (si existe) es el saldo de corte
        txn_amount_str = amounts[0]
        saldo_str      = amounts[1] if len(amounts) > 1 else None

        txn_amount = self._parse_amount(txn_amount_str)
        balance    = self._parse_amount(saldo_str) if saldo_str else Decimal("0")

        mtype = self._detect_movement_type(description)

        if mtype in _CREDIT_TYPES:
            charge  = Decimal("0")
            deposit = txn_amount
        else:
            charge  = txn_amount
            deposit = Decimal("0")

        txn_date = self._resolve_classic_date(date_raw, period)
        row_text = self._clean(line)

        return {
            "transaction_date": txn_date,
            "branch": branch,
            "description": description,
            "document_number": doc_num,
            "charge_amount": charge,
            "deposit_amount": deposit,
            "balance_amount": balance,
            "raw_row_text": row_text,
            "raw_row_json": {
                "source_format": "BANCO_CHILE_CUENTA_CORRIENTE_CLASSIC",
                "parsed_columns": {
                    "description": description,
                    "branch": branch,
                    "document_number": doc_num,
                    "charge_amount": str(charge),
                    "deposit_amount": str(deposit),
                    "balance_amount": str(balance),
                },
            },
            "detected_movement_type": mtype,
            "is_transfer_candidate": mtype in {"TRANSFER_IN", "TRANSFER_OUT"},
            "confidence_score": Decimal("0.98"),
        }

    @staticmethod
    def _looks_like_footer(line: str) -> bool:
        n = " ".join(line.split())
        if re.fullmatch(r"0(?:\s+0)+", n):
            return True
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*(?:\s+\d{1,3}(?:[.,]\d{3})*)+", n):
            return True
        return False

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_period(text: str) -> tuple[date, date] | None:
        patterns = [
            r"DESDE\s*:\s*(\d{2}/\d{2}/\d{4})\s+HASTA\s*:\s*(\d{2}/\d{2}/\d{4})",
            r"Movimientos\s+desde\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})",
            r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
        ]

        m = None
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                break

        if not m:
            return None

        return (
            datetime.strptime(m.group(1), "%d/%m/%Y").date(),
            datetime.strptime(m.group(2), "%d/%m/%Y").date(),
        )

    @staticmethod
    def _resolve_classic_date(date_raw: str, period: tuple[date, date] | None) -> date:
        day   = int(date_raw[:2])
        month = int(date_raw[3:5])
        if period is None:
            return date(datetime.now().year, month, day)
        start, end = period
        if start.year == end.year:
            year = start.year
        else:
            year = start.year if month >= start.month else end.year
        return date(year, month, day)

    @staticmethod
    def _is_amount(value: str) -> bool:
        return bool(_AMOUNT_RE.fullmatch(value))

    @staticmethod
    def _parse_amount(value: str) -> Decimal:
        if not value:
            return Decimal("0")
        v = " ".join(str(value).split())
        m = re.search(r"\d{1,3}(?:[.,]\d{3})*", v)
        if not m:
            return Decimal("0")
        return Decimal(m.group(0).replace(".", "").replace(",", ""))

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(str(value).split())

    # ── Clasificación de movimientos ──────────────────────────────────────────

    @staticmethod
    def _detect_movement_type(description: str) -> str:
        u = description.upper()

        if "TRASPASO A:" in u or re.search(r"\bTRASPASO\s+A\s+CUENTA:?\s*\d+", u):
            return "TRANSFER_OUT"
        if "TRASPASO DE:" in u or re.search(r"\bTRASPASO\s+DE\s+CUENTA:?\s*\d+", u):
            return "TRANSFER_IN"
        if "ABONO POR CAPTACIONES" in u:
            return "DEPOSIT"
        if "DEP.CHEQ.OTROS BANCOS" in u or "DEPOSITO EN EFECTIVO" in u:
            return "DEPOSIT"
        if "TRANSFERENCIA DESDE LINEA DE CREDI" in u:
            return "CREDIT_LINE_TRANSFER_IN"
        if "PAGO:DE SUELDOS" in u or "PAGO DE SUELDOS" in u:
            return "SALARY_PAYMENT"
        if "DEVOLUCION:" in u:
            return "REFUND"
        if "PAGO:RETIRO PREVISIONAL" in u or "RETIRO PREVISIONAL" in u:
            return "DEPOSIT"  # es entrada de dinero
        if "CHEQUE DEPOSITADO DEVUELTO" in u:
            return "PURCHASE"
        if "GIRO CAJERO AUTOMATICO" in u:
            return "WITHDRAWAL"
        if any(kw in u for kw in [
            "CARGO POR PAGO TC",
            "CARGO POR CAPTACIONES",
            "CARGO POR CAPTACION",
            "PAGO AUTOMATICO TARJETA DE CREDITO",
            "PAGO TARJETA DE CREDITO",
            "PAGO LINEA DE CRED",
            "PAGO EN SERVIPAG",
            "PAGO EN SII.CL",
            "PAGO EN TESORERIA",
            "PAGO SERVICIO EN INTERNET",
            "PAGO SERVICIO EN MI BANCO",
            "INTERESES LINEA DE CREDITO",
            "IMPUESTO LINEA DE CREDITO",
            "PRIMA SEGURO DESGRAVAMEN",
            "APORTE TELETON",
            "RECAUDACION Y PAGOS DE SERVICIOS",
            "COMISION ADMIN.",
            "CPC.TRASP FONDO A CTA",
        ]) or u.startswith("PAGO:") or u.startswith("PAGO "):
            return "PURCHASE"

        return "UNKNOWN"
