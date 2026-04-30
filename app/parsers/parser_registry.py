from app.parsers.banco_estado.chequera_electronica_parser import BancoEstadoChequeraElectronicaParser
from app.parsers.banco_estado.cartola_historica_parser import BancoEstadoCartolaHistoricaParser
from app.parsers.banco_estado.cartola_instantanea_parser import BancoEstadoCartolaInstantaneaParser
from app.parsers.banco_estado.cartola_instantanea_ahorro_parser import (
    BancoEstadoCartolaInstantaneaAhorroParser,
)
from app.parsers.banco_chile.cuenta_vista_estado_cuenta_parser import (
    BancoChileCuentaVistaEstadoCuentaParser,
)
from app.parsers.banco_chile.cuenta_corriente_estado_cuenta_parser import (
    BancoChileCuentaCorrienteEstadoCuentaParser,
)
from app.parsers.banco_chile.cuenta_fan_ahorro_parser import (
    BancoChileCuentaFanAhorroParser,
)
from app.parsers.banco_santander.cuenta_corriente_fan_parser import (
    BancoSantanderCuentaCorrienteFanParser,
)
from app.parsers.banco_santander.cuenta_mas_lucas_parser import (
    BancoSantanderCuentaMasLucasParser,
)
from app.parsers.banco_bci.cuenta_corriente_parser import BancoBciCuentaCorrienteParser


def get_available_parsers():
    return [
        BancoEstadoChequeraElectronicaParser(),
        BancoEstadoCartolaHistoricaParser(),
        BancoEstadoCartolaInstantaneaAhorroParser(),
        BancoEstadoCartolaInstantaneaParser(),
        BancoChileCuentaVistaEstadoCuentaParser(),
        BancoChileCuentaCorrienteEstadoCuentaParser(),
        BancoChileCuentaFanAhorroParser(),
        BancoSantanderCuentaCorrienteFanParser(),
        BancoSantanderCuentaMasLucasParser(),
        BancoBciCuentaCorrienteParser(),
    ]
