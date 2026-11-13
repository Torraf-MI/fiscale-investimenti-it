"""Strumenti finanziari, con la classificazione fiscale e i parametri per la simulazione."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .regole import REGOLE, Regola, Tipo, aliquota_effettiva, fattore_imponibile


@dataclass
class Strumento:
    nome: str
    tipo: Tipo
    quota_stato: float | None = None       # quota di titoli di Stato (ETF e fondi); None = valore della tipologia
    ritenuta_estera: float = 0.0           # ritenuta alla fonte estera sui dividendi (es. 15% USA con W-8BEN)
    cedola: float = 0.0                    # cedola annua sul nominale (obbligazioni e titoli di Stato)
    scadenza: date | None = None           # scadenza (obbligazioni, titoli di Stato, certificates)
    rimborso: float = 100.0                # prezzo di rimborso a scadenza
    # parametri della simulazione Monte Carlo
    rendimento: float = 0.0                # rendimento atteso annuo del prezzo (strumenti senza scadenza)
    volatilita: float = 0.0
    flusso: float = 0.0                    # dividendi o premi annui in percentuale del prezzo o del nominale
    gruppo: str = "azioni"                 # fattore comune: azioni, obbligazioni, oro
    spread: float = 0.001                  # costo denaro-lettera di un'andata e ritorno

    def __post_init__(self) -> None:
        self.tipo = Tipo(self.tipo)
        if isinstance(self.scadenza, str):
            self.scadenza = date.fromisoformat(self.scadenza)
        if self.quota_stato is not None and not 0.0 <= self.quota_stato <= 1.0:
            raise ValueError(f"{self.nome}: quota di titoli di Stato fuori da [0, 1]")
        if self.tipo == Tipo.TITOLO_STATO:
            self.quota_stato = 1.0

    @property
    def regola(self) -> Regola:
        return REGOLE[self.tipo]

    @property
    def quota(self) -> float:
        return self.regola.quota_stato if self.quota_stato is None else self.quota_stato

    @property
    def fattore(self) -> float:
        return fattore_imponibile(self.quota)

    @property
    def aliquota(self) -> float:
        return aliquota_effettiva(self.quota)

    @property
    def plus_compensabili(self) -> bool:
        """True se i guadagni sono redditi diversi e quindi possono assorbire lo zainetto."""
        return self.regola.plusvalenze == "Redditi diversi"

    @classmethod
    def da_dict(cls, d: dict) -> Strumento:
        return cls(**d)
