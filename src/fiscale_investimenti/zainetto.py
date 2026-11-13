"""Zainetto fiscale: minusvalenze per anno di realizzo, compensazione dalla più vecchia, scadenze."""

from __future__ import annotations

from dataclasses import dataclass, field

from .regole import ANNI_RIPORTO, ultimo_anno_utile

TOLLERANZA = 1e-9


@dataclass
class Zainetto:
    """Minusvalenze residue per anno di realizzo, già ridotte al 48,08% per la quota di titoli di Stato."""

    residui: dict[int, float] = field(default_factory=dict)

    def aggiungi(self, anno: int, importo: float) -> None:
        if importo < 0:
            raise ValueError("L'importo delle minusvalenze deve essere positivo")
        if importo > TOLLERANZA:
            self.residui[anno] = self.residui.get(anno, 0.0) + importo

    def validi(self, anno: int) -> dict[int, float]:
        """Residui ancora utilizzabili nell'anno, per anno di realizzo."""
        return {a: v for a, v in sorted(self.residui.items()) if anno - ANNI_RIPORTO <= a <= anno and v > TOLLERANZA}

    def saldo(self, anno: int) -> float:
        return float(sum(self.validi(anno).values()))

    def in_scadenza(self, anno: int) -> float:
        """Minusvalenze che scadono il 31 dicembre dell'anno se non vengono usate."""
        return float(self.residui.get(anno - ANNI_RIPORTO, 0.0))

    def per_scadenza(self, anno: int) -> dict[int, float]:
        """Residui utilizzabili indicati con l'ultimo anno utile."""
        return {ultimo_anno_utile(a): v for a, v in self.validi(anno).items()}

    def elimina_scadute(self, anno: int) -> dict[int, float]:
        """Toglie le minusvalenze non più utilizzabili nell'anno e le restituisce per anno di realizzo."""
        scadute = {a: v for a, v in self.residui.items() if a < anno - ANNI_RIPORTO and v > TOLLERANZA}
        for a in [a for a in self.residui if a < anno - ANNI_RIPORTO]:
            del self.residui[a]
        return scadute

    def compensa(self, importo: float, anno: int) -> tuple[float, dict[int, float]]:
        """Usa le minusvalenze più vecchie per prime fino a coprire l'importo.

        Restituisce quanto è stato usato e da quali anni di realizzo."""
        if importo <= 0:
            return 0.0, {}
        resto, usate = importo, {}
        for a, v in self.validi(anno).items():
            u = min(v, resto)
            if u <= TOLLERANZA:
                continue
            self.residui[a] = v - u
            usate[a] = u
            resto -= u
            if resto <= TOLLERANZA:
                break
        return importo - max(resto, 0.0), usate

    def copia(self) -> Zainetto:
        return Zainetto(dict(self.residui))
