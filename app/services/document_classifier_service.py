class DocumentClassifierService:
    @staticmethod
    def detect_document_group(parser_code: str | None) -> str | None:
        if not parser_code:
            return None

        parser_code_upper = parser_code.upper()

        if "TRANSFER" in parser_code_upper:
            return "Cartola Transferencias"

        if "CARTOLA" in parser_code_upper:
            return "Cartola Bancaria"

        return "Documento Bancario"

    @staticmethod
    def detect_document_type(parser_code: str | None) -> str | None:
        if not parser_code:
            return None

        parser_code_upper = parser_code.upper()

        if "CARTOLA_HISTORICA" in parser_code_upper:
            return "Cartola Histórica"

        if "CARTOLA_INSTANTANEA" in parser_code_upper:
            return "Cartola Instantánea"

        if "TRANSFER" in parser_code_upper:
            return "Cartola Transferencias"

        return "Desconocido"