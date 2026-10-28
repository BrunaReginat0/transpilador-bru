# Arquivo GERADO por bru.py a partir de exemplos/valido1_basico.bru. Não edite à mão.
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Alerta:
    nome: str
    minimo: Optional[float] = None
    maximo: Optional[float] = None

    def disparou(self, valor):
        """True se o valor ficou fora do intervalo [minimo, maximo]."""
        if self.minimo is not None and valor < self.minimo:
            return True
        if self.maximo is not None and valor > self.maximo:
            return True
        return False


ALERTAS = [
    Alerta(nome='temperatura_sensor', minimo=10, maximo=80),
    Alerta(nome='clima_tempo', maximo=35.5),
]
