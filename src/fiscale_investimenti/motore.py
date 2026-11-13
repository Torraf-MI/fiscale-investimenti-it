"""Motore del regime amministrato: applica le imposte movimento per movimento, come fa la banca.

Regole applicate:

- costo fiscale al **costo medio ponderato**, commissioni di acquisto comprese; le commissioni di vendita riducono
  il corrispettivo;
- plusvalenze e minusvalenze per differenza tra corrispettivo e costo medio, ridotte al 48,08% per la quota di
  titoli di Stato;
- le plusvalenze che sono redditi diversi si compensano subito con lo zainetto, partendo dalle minusvalenze più
  vecchie; le minusvalenze compensano solo le plusvalenze **successive** (nessun rimborso dell'imposta già pagata);
- i redditi di capitale (cedole, dividendi, proventi e plusvalenze di ETF e fondi) sono tassati senza compensazione;
- i dividendi esteri sono tassati al 26% sull'importo netto della ritenuta estera;
- all'inizio di ogni anno le minusvalenze del quinto anno precedente scadono.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .regole import ALIQUOTA, CAPITALE, DIVERSI
from .strumenti import Strumento
from .zainetto import TOLLERANZA, Zainetto

OPERAZIONI = ("acquisto", "vendita", "rimborso", "cedola", "dividendo", "premio", "provento")


@dataclass
class Movimento:
    data: date
    operazione: str
    strumento: str
    quantita: float = 0.0
    prezzo: float = 0.0
    importo: float = 0.0        # importo lordo di cedole, dividendi, premi e proventi
    commissioni: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.data, str):
            self.data = date.fromisoformat(self.data)
        elif isinstance(self.data, pd.Timestamp):
            self.data = self.data.date()
        if self.operazione not in OPERAZIONI:
            raise ValueError(f"Operazione sconosciuta: {self.operazione}")


@dataclass
class Posizione:
    quantita: float = 0.0
    costo_medio: float = 0.0

    @property
    def costo(self) -> float:
        return self.quantita * self.costo_medio


@dataclass
class Scadenza:
    anno_realizzo: int
    importo: float

    @property
    def scaduta_il(self) -> date:
        return date(self.anno_realizzo + 4, 12, 31)


@dataclass
class RegimeAmministrato:
    strumenti: dict[str, Strumento]
    zainetto: Zainetto = field(default_factory=Zainetto)
    posizioni: dict[str, Posizione] = field(default_factory=dict)
    liquidita: float = 0.0
    registra: bool = True
    righe: list[dict] = field(default_factory=list)
    scadute: list[Scadenza] = field(default_factory=list)
    anno: int | None = None

    # ------------------------------------------------------------------ tempo
    def vai_a(self, giorno: date) -> None:
        """Porta il motore a una data: al cambio d'anno elimina le minusvalenze scadute."""
        if self.anno is not None and giorno.year < self.anno:
            raise ValueError("I movimenti devono essere in ordine di data")
        if self.anno is None or giorno.year > self.anno:
            for a, v in self.zainetto.elimina_scadute(giorno.year).items():
                self.scadute.append(Scadenza(a, v))
            self.anno = giorno.year

    # ------------------------------------------------------------- movimenti
    def processa(self, movimenti: list[Movimento]) -> RegimeAmministrato:
        for m in sorted(movimenti, key=lambda m: m.data):
            self.esegui(m)
        return self

    def esegui(self, m: Movimento) -> dict:
        if m.strumento not in self.strumenti:
            raise KeyError(f"Strumento non definito: {m.strumento}")
        self.vai_a(m.data)
        s = self.strumenti[m.strumento]
        if m.operazione == "acquisto":
            return self._acquisto(m, s)
        if m.operazione in ("vendita", "rimborso"):
            return self._cessione(m, s)
        return self._flusso(m, s)

    def _acquisto(self, m: Movimento, s: Strumento) -> dict:
        if m.quantita <= 0 or m.prezzo <= 0:
            raise ValueError("Acquisto con quantità o prezzo non positivi")
        p = self.posizioni.setdefault(m.strumento, Posizione())
        costo = m.quantita * m.prezzo + m.commissioni
        p.costo_medio = (p.costo + costo) / (p.quantita + m.quantita)
        p.quantita += m.quantita
        self.liquidita -= costo
        return self._riga(m, s, "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {})

    def _cessione(self, m: Movimento, s: Strumento) -> dict:
        p = self.posizioni.get(m.strumento)
        if p is None or m.quantita > p.quantita + TOLLERANZA:
            raise ValueError(f"{m.data}: vendita di {m.quantita} {m.strumento} oltre la quantità posseduta")
        corrispettivo = m.quantita * m.prezzo - m.commissioni
        reddito = corrispettivo - m.quantita * p.costo_medio
        p.quantita -= m.quantita
        if p.quantita <= TOLLERANZA:
            del self.posizioni[m.strumento]
        imponibile = reddito * s.fattore
        compensato, imposta, minus, usate = 0.0, 0.0, 0.0, {}
        if reddito >= 0:
            categoria = s.regola.plusvalenze
            if categoria == DIVERSI:
                compensato, usate = self.zainetto.compensa(imponibile, m.data.year)
            imposta = ALIQUOTA * (imponibile - compensato)
        else:
            categoria = s.regola.minusvalenze
            minus = -imponibile
            self.zainetto.aggiungi(m.data.year, minus)
        self.liquidita += corrispettivo - imposta
        return self._riga(m, s, categoria, reddito, imponibile, compensato, imposta, 0.0, minus, usate)

    def _flusso(self, m: Movimento, s: Strumento) -> dict:
        categoria = s.regola.flussi
        ritenuta = m.importo * s.ritenuta_estera if m.operazione == "dividendo" else 0.0
        reddito = m.importo - ritenuta
        imponibile = reddito * s.fattore
        compensato, usate = 0.0, {}
        if categoria == DIVERSI and imponibile > 0:
            compensato, usate = self.zainetto.compensa(imponibile, m.data.year)
        imposta = ALIQUOTA * (imponibile - compensato)
        self.liquidita += reddito - imposta
        return self._riga(m, s, categoria, m.importo, imponibile, compensato, imposta, ritenuta, 0.0, usate)

    def _riga(self, m, s, categoria, reddito, imponibile, compensato, imposta, ritenuta, minus, usate) -> dict:
        r = {"data": m.data, "strumento": m.strumento, "tipo": s.regola.descrizione, "operazione": m.operazione,
             "quantita": m.quantita, "prezzo": m.prezzo, "categoria": categoria, "reddito": reddito,
             "imponibile": imponibile, "compensato": compensato, "imposta": imposta, "ritenuta_estera": ritenuta,
             "minus_generate": minus, "zainetto": self.zainetto.saldo(m.data.year),
             "usate_da": ", ".join(f"{a}: {v:.2f}" for a, v in usate.items())}
        if self.registra:
            self.righe.append(r)
        return r

    # --------------------------------------------------------------- risultati
    @property
    def registro(self) -> pd.DataFrame:
        return pd.DataFrame(self.righe)

    def riepilogo_annuo(self) -> pd.DataFrame:
        """Per ogni anno: imposte per categoria, minusvalenze generate, usate e scadute."""
        r = self.registro
        if r.empty:
            return pd.DataFrame()
        r = r.assign(anno=pd.to_datetime(r["data"]).dt.year)
        anni = range(int(r["anno"].min()), int(r["anno"].max()) + 1)
        g = r.groupby("anno")
        out = pd.DataFrame(index=pd.Index(anni, name="anno"))
        out["Imposte su redditi di capitale"] = r[r["categoria"] == CAPITALE].groupby("anno")["imposta"].sum()
        out["Imposte su redditi diversi"] = r[r["categoria"] == DIVERSI].groupby("anno")["imposta"].sum()
        out["Ritenute estere"] = g["ritenuta_estera"].sum()
        out["Minusvalenze generate"] = g["minus_generate"].sum()
        out["Minusvalenze usate"] = g["compensato"].sum()
        sc = pd.Series({s.anno_realizzo + 4: s.importo for s in self.scadute}, dtype=float)
        out["Minusvalenze scadute"] = sc.groupby(level=0).sum()
        out = out.fillna(0.0)
        out["Imposte totali"] = out["Imposte su redditi di capitale"] + out["Imposte su redditi diversi"]
        return out

    def imposte_per_voce(self) -> pd.DataFrame:
        """Imposte per anno e per tipo di reddito (cedole di Stato, dividendi, proventi ETF, plusvalenze...)."""
        r = self.registro
        r = r[r["imposta"] > 0].copy()
        r["anno"] = pd.to_datetime(r["data"]).dt.year

        def voce(x) -> str:
            if x["operazione"] in ("vendita", "rimborso"):
                return "Plusvalenze ETF e fondi" if x["categoria"] == CAPITALE else "Plusvalenze (redditi diversi)"
            if x["operazione"] == "cedola":
                return "Cedole titoli di Stato" if x["tipo"].startswith("Titoli di Stato") else "Cedole obbligazioni"
            nomi = {"dividendo": "Dividendi", "premio": "Premi certificates", "provento": "Proventi ETF"}
            return nomi[x["operazione"]]

        r["voce"] = r.apply(voce, axis=1)
        return r.pivot_table(index="anno", columns="voce", values="imposta", aggfunc="sum", fill_value=0.0)

    def imposte_non_compensate(self) -> pd.DataFrame:
        """Redditi di capitale tassati mentre lo zainetto aveva minusvalenze inutilizzabili per compensarli."""
        r = self.registro
        r = r[(r["categoria"] == CAPITALE) & (r["imposta"] > 0) & (r["zainetto"] > 0)]
        return r[["data", "strumento", "operazione", "reddito", "imposta", "zainetto"]]


def da_dataframe(df: pd.DataFrame) -> list[Movimento]:
    """Movimenti da una tabella con colonne data, operazione, strumento, quantita, prezzo, importo, commissioni."""
    df = df.copy()
    for c in ("quantita", "prezzo", "importo", "commissioni"):
        if c not in df:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c]).fillna(0.0)
    return [Movimento(pd.Timestamp(r.data).date(), str(r.operazione), str(r.strumento), float(r.quantita),
                      float(r.prezzo), float(r.importo), float(r.commissioni)) for r in df.itertuples()]


def leggi_movimenti(percorso) -> list[Movimento]:
    return da_dataframe(pd.read_csv(percorso, parse_dates=["data"]))
