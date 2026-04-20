from app.parsers.banco_estado.cartola_historica_parser import BancoEstadoCartolaHistoricaParser
from app.parsers.banco_estado.cartola_instantanea_parser import BancoEstadoCartolaInstantaneaParser
from app.parsers.banco_chile.cuenta_vista_estado_cuenta_parser import (
    BancoChileCuentaVistaEstadoCuentaParser,
)


def get_available_parsers():
    return [
        BancoEstadoCartolaHistoricaParser(),
        BancoEstadoCartolaInstantaneaParser(),
        BancoChileCuentaVistaEstadoCuentaParser(),
    ]