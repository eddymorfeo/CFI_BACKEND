from app.parsers.parser_registry import get_available_parsers


def test_cada_pdf_de_muestra_tiene_un_unico_parser(pdf_path):
    expected_parsers = {
        "BE_CartolaMambuPDF OK.pdf": "BancoEstadoCartolaHistoricaParser",
        "CARTOLA HISTORICA 1 OK.pdf": "BancoEstadoCartolaInstantaneaParser",
        "CARTOL_1.PDF": "BancoEstadoChequeraElectronicaParser",
        "CV Sandra Sanhueza.pdf": "BancoChileCuentaVistaEstadoCuentaParser",
        "Cuenta Corriente Chile OK.pdf": "BancoChileCuentaCorrienteEstadoCuentaParser",
        "TOF-25000068 Andrea Sanhueza Álvarez cta cte OK.pdf": "BancoChileCuentaCorrienteEstadoCuentaParser",
    }

    parsers = get_available_parsers()

    for file_name, expected_parser_name in expected_parsers.items():
        path = pdf_path(file_name)
        matching_parsers = [
            parser.__class__.__name__
            for parser in parsers
            if parser.can_parse(str(path))
        ]

        assert matching_parsers == [expected_parser_name]
