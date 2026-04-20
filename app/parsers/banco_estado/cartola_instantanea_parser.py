import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

from app.parsers.base_parser import BaseParser


class BancoEstadoCartolaInstantaneaParser(BaseParser):
    DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

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
            text = page_info["text"]
            
            lines = text.split('\n')
            lines = [line.strip() for line in lines if line.strip()]
            
            # Encontrar sección de movimientos
            movement_lines = []
            in_movements = False
            
            for line in lines:
                if 'Movimientos' in line:
                    in_movements = True
                    continue
                
                if in_movements:
                    if 'Saldos' in line or 'SALDOS' in line or 'retenciones' in line:
                        break
                    if 'Página' in line or 'WWW.CMFCHILE.CL' in line.upper() or 'GARANTIA ESTATAL' in line.upper():
                        continue
                    movement_lines.append(line)
            
            # Reconstruir movimientos
            movements_data = self._group_movement_lines_advanced(movement_lines)
            
            for movement_data in movements_data:
                movement = self._parse_movement_advanced(movement_data, row_number, page_number)
                if movement:
                    movements.append(movement)
                    row_number += 1

        return movements

    def _group_movement_lines_advanced(self, lines: list[str]) -> list[dict]:
        """Agrupa líneas detectando el patrón correcto según el diagnóstico."""
        movements = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Caso: La línea comienza con "STGO." (descripción pura)
            if line.startswith('STGO.'):
                if i + 2 < len(lines):
                    desc_line = line
                    date_line = lines[i + 1]
                    branch_line = lines[i + 2]
                    
                    # Verificar que la siguiente línea tiene fecha
                    if self.DATE_PATTERN.match(date_line[:10]):
                        movements.append({
                            'type': 'desc_separate',
                            'desc_line': desc_line,
                            'date_line': date_line,
                            'branch_line': branch_line
                        })
                        i += 3
                        continue
            
            # Caso: La línea comienza con fecha
            elif self.DATE_PATTERN.match(line[:10]):
                # Verificar si la descripción está en la misma línea
                # Extraer todo después de la fecha y número de operación
                remaining = line[10:].strip()
                
                # Si hay descripción en la misma línea (ej: "COMPRA WEB INTERN. FACEBK ADS")
                if remaining and '$' in remaining:
                    # La descripción está antes del primer $
                    desc_match = re.search(r'^(.*?)\s*\$', remaining)
                    if desc_match:
                        desc_inline = desc_match.group(1).strip()
                        movements.append({
                            'type': 'inline',
                            'date_line': line,
                            'inline_description': desc_inline
                        })
                        i += 1
                        continue
                
                # Si no hay descripción inline, buscar siguiente línea
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    movements.append({
                        'type': 'two_lines',
                        'date_line': line,
                        'desc_line': next_line
                    })
                    i += 2
                    continue
            
            i += 1
        
        return movements

    def _parse_movement_advanced(self, movement_data: dict, row_number: int, page_number: int) -> dict | None:
        """Parsea según el tipo detectado."""
        movement_type = movement_data.get('type')
        
        if movement_type == 'desc_separate':
            return self._parse_desc_separate(movement_data, row_number, page_number)
        elif movement_type == 'two_lines':
            return self._parse_two_lines(movement_data, row_number, page_number)
        elif movement_type == 'inline':
            return self._parse_inline(movement_data, row_number, page_number)
        
        return None

    def _parse_desc_separate(self, movement_data: dict, row_number: int, page_number: int) -> dict | None:
        """Parsea movimiento con descripción separada (3 líneas)."""
        desc_line = movement_data['desc_line']
        date_line = movement_data['date_line']
        branch_line = movement_data['branch_line']
        
        # Fecha
        fecha = date_line[:10]
        
        # Número de operación
        doc_match = re.search(r'(\d{6,})', date_line)
        documento = doc_match.group(1) if doc_match else None
        
        # Montos
        cargo, abono, saldo = self._extract_amounts(date_line)
        
        # Descripción: viene en desc_line (ej: "STGO. TEF A JAVIERA FRANCISCA PASTEN")
        desc_clean = re.sub(r'STGO\.\s*', '', desc_line, flags=re.IGNORECASE).strip()
        
        # Extraer palabra final de branch_line (ej: "NAVA" de "PRINCIPAL NAVA")
        last_word = ''
        if branch_line:
            branch_clean = re.sub(r'PRINCIPAL', '', branch_line, flags=re.IGNORECASE).strip()
            words = branch_clean.split()
            if words:
                last_word = words[-1]
        
        # Concatenar descripción + palabra final
        if last_word:
            descripcion = f"{desc_clean} {last_word}".strip()
        else:
            descripcion = desc_clean
        
        descripcion = self._clean_description(descripcion)
        
        return self._build_result(fecha, documento, descripcion, cargo, abono, saldo, row_number, page_number)

    def _parse_two_lines(self, movement_data: dict, row_number: int, page_number: int) -> dict | None:
        """Parsea movimiento con 2 líneas (fecha + descripción en línea siguiente)."""
        date_line = movement_data['date_line']
        desc_line = movement_data['desc_line']
        
        # Fecha
        fecha = date_line[:10]
        
        # Número de operación
        doc_match = re.search(r'(\d{6,})', date_line)
        documento = doc_match.group(1) if doc_match else None
        
        # Montos
        cargo, abono, saldo = self._extract_amounts(date_line)
        
        # Descripción: viene en desc_line, eliminar "STGO. PRINCIPAL" o "PRINCIPAL"
        descripcion = desc_line
        descripcion = re.sub(r'STGO\.\s*PRINCIPAL', '', descripcion, flags=re.IGNORECASE)
        descripcion = re.sub(r'STGO\.', '', descripcion, flags=re.IGNORECASE)
        descripcion = re.sub(r'PRINCIPAL', '', descripcion, flags=re.IGNORECASE)
        descripcion = descripcion.strip()
        descripcion = self._clean_description(descripcion)
        
        return self._build_result(fecha, documento, descripcion, cargo, abono, saldo, row_number, page_number)

    def _parse_inline(self, movement_data: dict, row_number: int, page_number: int) -> dict | None:
        """Parsea movimiento donde la descripción está en la misma línea de fecha."""
        date_line = movement_data['date_line']
        inline_description = movement_data.get('inline_description', '')
        
        # Fecha
        fecha = date_line[:10]
        
        # Número de operación
        doc_match = re.search(r'(\d{6,})', date_line)
        documento = doc_match.group(1) if doc_match else None
        
        # Montos
        cargo, abono, saldo = self._extract_amounts(date_line)
        
        # Descripción: usar la inline
        descripcion = inline_description
        descripcion = re.sub(r'STGO\.\s*PRINCIPAL', '', descripcion, flags=re.IGNORECASE)
        descripcion = re.sub(r'STGO\.', '', descripcion, flags=re.IGNORECASE)
        descripcion = re.sub(r'PRINCIPAL', '', descripcion, flags=re.IGNORECASE)
        descripcion = descripcion.strip()
        descripcion = self._clean_description(descripcion)
        
        return self._build_result(fecha, documento, descripcion, cargo, abono, saldo, row_number, page_number)

    def _extract_amounts(self, date_line: str) -> tuple[Decimal, Decimal, Decimal]:
        """Extrae cargo, abono y saldo de la línea de fecha."""
        amount_pattern = r'\$\s*(-?\d{1,3}(?:\.\d{3})*|\d+)'
        amounts = re.findall(amount_pattern, date_line)
        
        cargo = Decimal('0')
        abono = Decimal('0')
        saldo = Decimal('0')
        
        for amt in amounts:
            is_negative = amt.startswith('-')
            amt_clean = amt.replace('-', '').replace('.', '')
            
            try:
                value = Decimal(amt_clean)
                
                if is_negative:
                    cargo = value
                else:
                    if cargo > 0:
                        if saldo == 0:
                            saldo = value
                        else:
                            abono = value
                    else:
                        if abono == 0:
                            abono = value
                        else:
                            saldo = value
            except:
                pass
        
        # Caso especial: dos positivos sin negativo
        if cargo == 0 and len([a for a in amounts if not a.startswith('-')]) == 2:
            positive_amounts = [a for a in amounts if not a.startswith('-')]
            if len(positive_amounts) >= 2:
                try:
                    abono = Decimal(positive_amounts[0].replace('.', ''))
                    saldo = Decimal(positive_amounts[1].replace('.', ''))
                except:
                    pass
        
        return cargo, abono, saldo

    def _build_result(self, fecha: str, documento: str, descripcion: str,
                      cargo: Decimal, abono: Decimal, saldo: Decimal,
                      row_number: int, page_number: int) -> dict:
        """Construye el resultado final."""
        sucursal = 'STGO. PRINCIPAL'
        detected_movement_type = self._detect_movement_type(descripcion)
        is_transfer_candidate = detected_movement_type in {"TRANSFER_IN", "TRANSFER_OUT"}
        
        return {
            "row_number": row_number,
            "page_number": page_number,
            "transaction_date": datetime.strptime(fecha, "%d/%m/%Y").date(),
            "branch": sucursal,
            "description": descripcion,
            "document_number": documento,
            "charge_amount": cargo,
            "deposit_amount": abono,
            "balance_amount": saldo,
            "raw_row_text": f"{fecha} | {documento} | {descripcion}",
            "raw_row_json": {
                "page_number": page_number,
            },
            "detected_movement_type": detected_movement_type,
            "is_transfer_candidate": is_transfer_candidate,
            "confidence_score": Decimal("0.98"),
        }

    def _clean_description(self, description: str) -> str:
        """Limpia la descripción."""
        if not description:
            return ""
        
        garbage = [
            r'\$',
            r'Página\s+de\s+\d+',
            r'www\.[a-z0-9]+\.cl',
            r'CMFCHILE',
            r'Los depósitos en su banco',
            r'De acuerdo con la ley',
            r'INFORMESE SOBRE LA GARANTIA ESTATAL',
            r'DEPOSITOS',
            r'w{3}\.',
        ]
        
        for pattern in garbage:
            description = re.sub(pattern, '', description, flags=re.IGNORECASE)
        
        description = re.sub(r'\s+', ' ', description)
        
        return description.strip()

    def _detect_movement_type(self, description: str) -> str:
        desc_upper = description.upper()

        if 'TEF A' in desc_upper or 'TRANSFERENCIA A' in desc_upper:
            return 'TRANSFER_OUT'

        if 'TEF DE' in desc_upper or 'TRANSFERENCIA DE' in desc_upper:
            return 'TRANSFER_IN'

        if 'COMISION' in desc_upper:
            return 'COMMISSION'

        return 'UNKNOWN'

    def _clean_text(self, value: str) -> str:
        return ' '.join(str(value).split())