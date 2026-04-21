from app.parsers.banco_estado.cartola_historica_parser import BancoEstadoCartolaHistoricaParser
from app.parsers.banco_estado.cartola_instantanea_parser import BancoEstadoCartolaInstantaneaParser
from app.parsers.banco_chile.cuenta_vista_estado_cuenta_parser import (
    BancoChileCuentaVistaEstadoCuentaParser,
)
from app.parsers.banco_chile.cuenta_corriente_estado_cuenta_parser import (
    BancoChileCuentaCorrienteEstadoCuentaParser,
)
from app.parsers.banco_chile.cuenta_fan_ahorro_parser import (
    BancoChileCuentaFanAhorroParser,
)


def get_available_parsers():
    return [
        BancoEstadoCartolaHistoricaParser(),
        BancoEstadoCartolaInstantaneaParser(),
        BancoChileCuentaVistaEstadoCuentaParser(),
        BancoChileCuentaCorrienteEstadoCuentaParser(),
        BancoChileCuentaFanAhorroParser(),
    ]