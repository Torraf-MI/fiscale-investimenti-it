"""Simulazione Monte Carlo pluriennale: quanto vale davvero gestire lo zainetto?

Dalla situazione di oggi si simulano i prezzi di fine anno per alcuni anni e si confrontano, sugli stessi scenari,
tre comportamenti del cliente:

- **Nessuna azione**: si incassano cedole, dividendi e premi e si vende tutto alla fine;
- **Recupero delle scadenze**: ogni dicembre si vendono e riacquistano strumenti in guadagno (redditi diversi)
  quanto basta per usare le minusvalenze che stanno per scadere;
- **Realizzo di tutte le perdite**: in più, ogni dicembre si vendono e riacquistano tutte le posizioni in perdita,
  ETF compresi, come suggerirebbe il tax-loss harvesting all'americana.

Alla fine dell'orizzonte si vende tutto, così il patrimonio finale è al netto di tutte le imposte, comprese quelle
sulle plusvalenze latenti. Imposte sui flussi, bollo, commissioni e spread passano dal motore del regime amministrato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from .motore import Movimento, Posizione, RegimeAmministrato
from .pianificazione import Costi, piano_recupero
from .regole import ALIQUOTA, BOLLO, Tipo, commissione
from .strumenti import Strumento

PASSIVA, RECUPERO, RACCOLTA = "Nessuna azione", "Recupero delle scadenze", "Realizzo di tutte le perdite"
STRATEGIE = (PASSIVA, RECUPERO, RACCOLTA)
GRUPPI = ("azioni", "obbligazioni", "oro")


@dataclass
class ParametriSimulazione:
    anni: int = 5
    scenari: int = 1000
    seme: int = 2026
    tasso_liquidita: float = 0.02
    soglia_perdita: float = 0.03            # si realizzano le perdite oltre il 3% del costo
    correlazione_gruppo: float = 0.7        # correlazione tra strumenti dello stesso gruppo
    correlazioni: dict = field(default_factory=lambda: {("azioni", "obbligazioni"): 0.1, ("azioni", "oro"): 0.1,
                                                        ("obbligazioni", "oro"): 0.2})

    def matrice(self) -> np.ndarray:
        c = np.eye(len(GRUPPI))
        for (a, b), v in self.correlazioni.items():
            i, j = GRUPPI.index(a), GRUPPI.index(b)
            c[i, j] = c[j, i] = v
        return c


def _anni(d0: date, d1: date) -> float:
    return (d1 - d0).days / 365.25


def date_decisione(oggi: date, anni: int) -> list[date]:
    return [date(oggi.year + k, 12, 15) for k in range(anni + 1)]


def simula_prezzi(strumenti: dict[str, Strumento], prezzi: dict[str, float], oggi: date,
                  par: ParametriSimulazione) -> dict[str, np.ndarray]:
    """Prezzi a metà dicembre di ogni anno (colonna 0 = oggi). Gli strumenti con scadenza seguono un ponte
    browniano verso il prezzo di rimborso, gli altri un moto browniano geometrico; i gruppi sono correlati."""
    rng = np.random.default_rng(par.seme)
    n, h = par.scenari, par.anni
    chol = np.linalg.cholesky(par.matrice())
    fattori = rng.standard_normal((n, h, len(GRUPPI))) @ chol.T
    tempi = [0.0] + [_anni(oggi, d) for d in date_decisione(oggi, h)[1:]]
    rho = par.correlazione_gruppo
    out = {}
    for nome, p0 in prezzi.items():
        s = strumenti[nome]
        shock = np.sqrt(rho) * fattori[:, :, GRUPPI.index(s.gruppo)] + np.sqrt(1 - rho) * rng.standard_normal((n, h))
        p = np.empty((n, h + 1))
        p[:, 0] = p0
        if s.scadenza is None:
            dt = np.diff(tempi)
            incr = (s.rendimento - 0.5 * s.volatilita**2) * dt + s.volatilita * np.sqrt(dt) * shock
            p[:, 1:] = p0 * np.exp(np.cumsum(incr, axis=1))
        else:
            fine = _anni(oggi, s.scadenza)
            d = np.full(n, np.log(p0 / s.rimborso))
            for k in range(1, h + 1):
                t0, t1 = tempi[k - 1], tempi[k]
                if t1 >= fine or t0 >= fine:
                    d = np.zeros(n)
                else:
                    media = d * (fine - t1) / (fine - t0)
                    var = s.volatilita**2 * (t1 - t0) * (fine - t1) / (fine - t0)
                    d = media + np.sqrt(var) * shock[:, k - 1]
                p[:, k] = s.rimborso * np.exp(d)
        out[nome] = p
    return out


@dataclass
class Simulatore:
    strumenti: dict[str, Strumento]
    costi: Costi = field(default_factory=Costi)
    par: ParametriSimulazione = field(default_factory=ParametriSimulazione)

    def _nuovo(self, base: RegimeAmministrato) -> RegimeAmministrato:
        pos = {k: Posizione(v.quantita, v.costo_medio) for k, v in base.posizioni.items()}
        return RegimeAmministrato(self.strumenti, base.zainetto.copia(), pos, 0.0, registra=False, anno=base.anno)

    def _vendi_riacquista(self, m: RegimeAmministrato, nome: str, q: float, prezzo: float, giorno: date,
                          conto: dict, riacquista: bool = True) -> None:
        s = self.strumenti[nome]
        pv = prezzo * (1 - s.spread / 2)
        cv = commissione(q * pv, self.costi.percentuale, self.costi.minimo, self.costi.massimo)
        conto["imposte"] += m.esegui(Movimento(giorno, "vendita", nome, q, pv, commissioni=cv))["imposta"]
        conto["costi"] += cv + q * prezzo * s.spread / 2
        if riacquista:
            pa = prezzo * (1 + s.spread / 2)
            ca = commissione(q * pa, self.costi.percentuale, self.costi.minimo, self.costi.massimo)
            m.esegui(Movimento(giorno, "acquisto", nome, q, pa, commissioni=ca))
            conto["costi"] += ca + q * prezzo * s.spread / 2

    def _decidi(self, m: RegimeAmministrato, strategia: str, prezzi: dict[str, float], giorno: date,
                conto: dict) -> None:
        m.vai_a(giorno)
        if strategia == PASSIVA:
            return
        if strategia == RACCOLTA:
            for nome, p in list(m.posizioni.items()):
                if prezzi[nome] < p.costo_medio * (1 - self.par.soglia_perdita):
                    self._vendi_riacquista(m, nome, p.quantita, prezzi[nome], giorno, conto)
        if m.zainetto.in_scadenza(giorno.year) > 1.0:
            piano = piano_recupero(m.posizioni, prezzi, self.strumenti, m.zainetto, giorno.year, self.costi)
            for a in piano.azioni:
                self._vendi_riacquista(m, a.strumento, a.quantita, prezzi[a.strumento], giorno, conto)

    def _flussi(self, m: RegimeAmministrato, anno: int, prezzi_prec: dict[str, float], conto: dict) -> None:
        eventi = []
        for nome, p in m.posizioni.items():
            s = self.strumenti[nome]
            scade = s.scadenza is not None and s.scadenza.year == anno
            mesi = s.scadenza.month / 12 if scade else 1.0
            if s.cedola > 0:
                eventi.append(Movimento(date(anno, 6, 30), "cedola", nome, importo=s.cedola * 100 * p.quantita * mesi))
            elif s.flusso > 0:
                base = 100.0 if s.tipo == Tipo.CERTIFICATE else prezzi_prec[nome]
                op = s.regola.nome_flusso
                eventi.append(Movimento(date(anno, 6, 30), op, nome, importo=s.flusso * base * p.quantita * mesi))
            if scade:
                eventi.append(Movimento(s.scadenza, "rimborso", nome, p.quantita, s.rimborso))
        if m.liquidita > 0:
            interessi = self.par.tasso_liquidita * m.liquidita
            m.liquidita += interessi * (1 - ALIQUOTA)
            conto["imposte"] += ALIQUOTA * interessi
        for e in sorted(eventi, key=lambda e: e.data):
            conto["imposte"] += m.esegui(e)["imposta"]

    def _bollo(self, m: RegimeAmministrato, prezzi: dict[str, float], conto: dict) -> None:
        valore = sum(p.quantita * prezzi[n] for n, p in m.posizioni.items()) + max(m.liquidita, 0.0)
        b = BOLLO * valore
        m.liquidita -= b
        conto["bollo"] += b

    def esegui(self, base: RegimeAmministrato, prezzi: dict[str, float], oggi: date,
               strategie: tuple[str, ...] = STRATEGIE) -> RisultatoSimulazione:
        par = self.par
        cammini = simula_prezzi(self.strumenti, {n: prezzi[n] for n in base.posizioni}, oggi, par)
        giorni = date_decisione(oggi, par.anni)
        righe = []
        for i in range(par.scenari):
            pz = [{n: float(c[i, k]) for n, c in cammini.items()} for k in range(par.anni + 1)]
            for strategia in strategie:
                m = self._nuovo(base)
                conto = {"imposte": 0.0, "costi": 0.0, "bollo": 0.0}
                self._decidi(m, strategia, pz[0], giorni[0], conto)
                for k in range(1, par.anni + 1):
                    self._flussi(m, giorni[k].year, pz[k - 1], conto)
                    self._bollo(m, pz[k], conto)
                    if k < par.anni:
                        self._decidi(m, strategia, pz[k], giorni[k], conto)
                ultimo = date(giorni[-1].year, 12, 30)
                for nome, p in list(m.posizioni.items()):
                    self._vendi_riacquista(m, nome, p.quantita, pz[-1][nome], ultimo, conto, riacquista=False)
                scadute = sum(s.importo for s in m.scadute)
                righe.append({"scenario": i, "strategia": strategia, "netto": m.liquidita,
                              "imposte": conto["imposte"], "costi": conto["costi"], "bollo": conto["bollo"],
                              "minus_scadute": scadute, "zainetto_finale": m.zainetto.saldo(ultimo.year)})
        return RisultatoSimulazione(pd.DataFrame(righe), par, cammini)


@dataclass
class RisultatoSimulazione:
    scenari: pd.DataFrame
    par: ParametriSimulazione
    prezzi: dict[str, np.ndarray]

    def netto(self) -> pd.DataFrame:
        return self.scenari.pivot(index="scenario", columns="strategia", values="netto")

    def differenze(self) -> pd.DataFrame:
        n = self.netto()
        return n.drop(columns=PASSIVA).sub(n[PASSIVA], axis=0)

    def sintesi(self) -> pd.DataFrame:
        g = self.scenari.groupby("strategia")
        out = pd.DataFrame({"Patrimonio netto finale": g["netto"].mean(), "Imposte pagate": g["imposte"].mean(),
                            "Costi di negoziazione": g["costi"].mean(),
                            "Minusvalenze scadute": g["minus_scadute"].mean(),
                            "Zainetto residuo": g["zainetto_finale"].mean()})
        d = self.differenze()
        out["Differenza media"] = d.mean().reindex(out.index).fillna(0.0)
        out["Differenza mediana"] = d.median().reindex(out.index).fillna(0.0)
        out["Differenza 5° percentile"] = d.quantile(0.05).reindex(out.index).fillna(0.0)
        out["Differenza 95° percentile"] = d.quantile(0.95).reindex(out.index).fillna(0.0)
        out["Scenari migliori"] = (d > 0.5).mean().reindex(out.index)
        out["Scenari peggiori"] = (d < -0.5).mean().reindex(out.index)
        return out.reindex([s for s in STRATEGIE if s in out.index])
