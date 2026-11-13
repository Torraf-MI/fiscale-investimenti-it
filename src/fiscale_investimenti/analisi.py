"""Analisi completa: storico fiscale, zainetto, latenti, piano di fine anno, veicoli e simulazione."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .configurazione import Configurazione
from .motore import RegimeAmministrato
from .pianificazione import Piano, confronto_veicoli, curva_veicoli, latenti, piano_recupero
from .regole import CAPITALE
from .simulazione import RACCOLTA, RECUPERO, RisultatoSimulazione, Simulatore
from .zainetto import Zainetto


@dataclass
class Analisi:
    cfg: Configurazione
    motore: RegimeAmministrato
    riepilogo: pd.DataFrame
    voci: pd.DataFrame
    latenti: pd.DataFrame
    piano: Piano
    zainetto_oggi: dict[int, float]          # per ultimo anno utile
    zainetto_dopo: dict[int, float]          # dopo il piano
    veicoli: pd.DataFrame
    curva: pd.DataFrame
    guadagno_veicoli: float
    simulazione: RisultatoSimulazione | None
    storia: pd.Series                        # saldo dello zainetto dopo ogni movimento

    @property
    def anno(self) -> int:
        return self.cfg.data_analisi.year

    @property
    def registro(self) -> pd.DataFrame:
        return self.motore.registro

    @property
    def imposte_totali(self) -> float:
        return float(self.riepilogo["Imposte totali"].sum())

    @property
    def zainetto_saldo(self) -> float:
        return float(sum(self.zainetto_oggi.values()))

    @property
    def capitale_con_zainetto(self) -> float:
        """Imposte pagate su redditi di capitale mentre lo zainetto aveva minusvalenze."""
        return float(self.motore.imposte_non_compensate()["imposta"].sum())

    @property
    def plus_etf_con_zainetto(self) -> pd.DataFrame:
        r = self.motore.imposte_non_compensate()
        return r[r["operazione"] == "vendita"]

    def raccolta_vs_recupero(self) -> pd.Series | None:
        if self.simulazione is None:
            return None
        n = self.simulazione.netto()
        return n[RACCOLTA] - n[RECUPERO]


def analizza(cfg: Configurazione) -> Analisi:
    z = Zainetto()
    for a, v in cfg.zainetto_iniziale.items():
        z.aggiungi(a, v)
    motore = RegimeAmministrato(cfg.strumenti, z)
    motore.processa([m for m in cfg.movimenti if m.data <= cfg.data_analisi])
    motore.vai_a(cfg.data_analisi)
    anno = cfg.data_analisi.year

    mancanti = [n for n in motore.posizioni if n not in cfg.prezzi]
    if mancanti:
        raise ValueError(f"Manca il prezzo di oggi per: {', '.join(mancanti)}")
    lat = latenti(motore.posizioni, cfg.prezzi, cfg.strumenti)
    piano = piano_recupero(motore.posizioni, cfg.prezzi, cfg.strumenti, motore.zainetto, anno, cfg.costi)

    dopo = motore.zainetto.copia()
    dopo.compensa(piano.recuperato, anno)
    dopo.elimina_scadute(anno + 1)

    # stesso guadagno lordo su veicoli diversi, con lo zainetto che resterà dopo il piano
    saldo_dopo = dopo.saldo(anno + 1)
    guadagno = float(np.ceil(max(saldo_dopo * 2, 10_000) / 1_000) * 1_000)
    veicoli = confronto_veicoli(guadagno, saldo_dopo)
    curva = curva_veicoli(np.linspace(0, 2 * guadagno, 41), saldo_dopo)

    sim = None
    if cfg.simula and motore.posizioni:
        sim = Simulatore(cfg.strumenti, cfg.costi, cfg.simulazione).esegui(motore, cfg.prezzi, cfg.data_analisi)

    reg = motore.registro
    storia = pd.Series(reg["zainetto"].values, index=pd.to_datetime(reg["data"])) if not reg.empty else pd.Series()
    storia = storia.groupby(level=0).last()
    return Analisi(cfg, motore, motore.riepilogo_annuo(), motore.imposte_per_voce(), lat, piano,
                   motore.zainetto.per_scadenza(anno), dopo.per_scadenza(anno + 1), veicoli, curva, guadagno, sim,
                   storia)


__all__ = ["Analisi", "analizza", "CAPITALE"]
