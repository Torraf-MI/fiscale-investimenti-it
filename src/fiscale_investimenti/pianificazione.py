"""Pianificazione fiscale di fine anno: plus e minus latenti, recupero delle minusvalenze in scadenza,
valore di una minusvalenza e scelta del veicolo d'investimento."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .regole import ALIQUOTA, CAPITALE, DIVERSI, TOBIN, Tipo, commissione
from .strumenti import Strumento
from .zainetto import Zainetto


@dataclass
class Costi:
    percentuale: float = 0.0019
    minimo: float = 2.95
    massimo: float = 19.0
    riacquisto_stesso_giorno: bool = True     # saldo netto giornaliero nullo: niente Tobin tax

    def operazione(self, controvalore: float, s: Strumento, riacquisto: bool = True) -> float:
        """Costo di una vendita (e del riacquisto, se previsto): commissioni, spread ed eventuale Tobin tax."""
        c = commissione(controvalore, self.percentuale, self.minimo, self.massimo)
        if riacquisto:
            c += commissione(controvalore, self.percentuale, self.minimo, self.massimo) + s.spread * controvalore
            if s.regola.tobin and not self.riacquisto_stesso_giorno:
                c += TOBIN * controvalore
        else:
            c += s.spread * controvalore / 2
        return c


def latenti(posizioni: dict, prezzi: dict[str, float], strumenti: dict[str, Strumento]) -> pd.DataFrame:
    """Plusvalenze e minusvalenze non ancora realizzate, con la loro categoria fiscale e base imponibile."""
    righe = []
    for nome, p in posizioni.items():
        s = strumenti[nome]
        prezzo = float(prezzi[nome])
        valore = p.quantita * prezzo
        lat = valore - p.costo
        categoria = s.regola.plusvalenze if lat >= 0 else s.regola.minusvalenze
        righe.append({"strumento": nome, "tipo": s.regola.descrizione, "quantita": p.quantita,
                      "costo_medio": p.costo_medio, "prezzo": prezzo, "valore": valore, "latente": lat,
                      "categoria": categoria, "fattore": s.fattore, "imponibile": lat * s.fattore,
                      "compensabile": lat >= 0 and categoria == DIVERSI,
                      "imposta_latente": ALIQUOTA * lat * s.fattore if lat > 0 else 0.0})
    return pd.DataFrame(righe).set_index("strumento") if righe else pd.DataFrame()


@dataclass
class Azione:
    strumento: str
    quantita: float
    prezzo: float
    controvalore: float
    plusvalenza: float
    imponibile: float
    recuperato: float
    costo: float
    costo_medio_prima: float
    costo_medio_dopo: float


@dataclass
class Piano:
    anno: int
    obiettivo: float                      # minusvalenze che scadono il 31 dicembre
    azioni: list[Azione] = field(default_factory=list)
    capacita: float = 0.0                 # base imponibile delle plusvalenze latenti compensabili

    @property
    def recuperato(self) -> float:
        return sum(a.recuperato for a in self.azioni)

    @property
    def perso(self) -> float:
        return max(self.obiettivo - self.recuperato, 0.0)

    @property
    def costo(self) -> float:
        return sum(a.costo for a in self.azioni)

    @property
    def risparmio(self) -> float:
        """Imposta futura evitata: il costo fiscale sale e la plusvalenza futura scende di quanto recuperato."""
        return ALIQUOTA * self.recuperato

    def valore_attuale(self, anni: float = 5.0, tasso: float = 0.03) -> float:
        """Risparmio scontato all'anno in cui si venderebbe comunque, meno i costi di oggi."""
        return self.risparmio / (1 + tasso) ** anni - self.costo

    def tabella(self) -> pd.DataFrame:
        return pd.DataFrame([a.__dict__ for a in self.azioni])


def piano_recupero(posizioni: dict, prezzi: dict[str, float], strumenti: dict[str, Strumento], zainetto: Zainetto,
                   anno: int, costi: Costi | None = None, obiettivo: float | None = None,
                   escludi: tuple[str, ...] = ()) -> Piano:
    """Vendite e riacquisti che realizzano plusvalenze (redditi diversi) quanto basta per usare le minusvalenze in
    scadenza. Sceglie per primi gli strumenti con più plusvalenza per euro venduto, quindi con meno costi, e
    calcola la quantità che serve tenendo conto della riduzione al 48,08% per i titoli di Stato."""
    costi = costi or Costi()
    obiettivo = zainetto.in_scadenza(anno) if obiettivo is None else obiettivo
    lat = latenti(posizioni, prezzi, strumenti)
    piano = Piano(anno, obiettivo)
    if lat.empty:
        return piano
    cand = lat[lat["compensabile"] & (lat["imponibile"] > 0) & ~lat.index.isin(escludi)].copy()
    piano.capacita = float(cand["imponibile"].sum())
    cand["efficienza"] = cand["imponibile"] / cand["valore"]          # base imponibile per euro venduto
    resto = obiettivo
    for nome, r in cand.sort_values("efficienza", ascending=False).iterrows():
        if resto <= 0.5:
            break
        s = strumenti[nome]
        unita = (r["prezzo"] - r["costo_medio"]) * s.fattore
        q = min(r["quantita"], math.ceil(resto / unita - 1e-9))
        controvalore = q * r["prezzo"]
        plus = q * (r["prezzo"] - r["costo_medio"])
        base = plus * s.fattore
        costo = costi.operazione(controvalore, s)
        acquisto = commissione(controvalore, costi.percentuale, costi.minimo, costi.massimo)
        nuovo = (r["costo_medio"] * (r["quantita"] - q) + controvalore + acquisto) / r["quantita"]
        piano.azioni.append(Azione(nome, q, r["prezzo"], controvalore, plus, base, min(base, resto), costo,
                                   r["costo_medio"], nuovo))
        resto -= base
    return piano


def valore_minusvalenza(importo: float, probabilita_uso: float = 1.0, anni_uso: float = 1.0,
                        tasso: float = 0.03) -> float:
    """Valore attuale di una minusvalenza: imposta risparmiata se verrà usata, scontata all'anno di utilizzo."""
    return ALIQUOTA * importo * probabilita_uso / (1 + tasso) ** anni_uso


def valore_realizzo_perdita(perdita: float, s: Strumento, probabilita_uso: float, anni_uso: float,
                            anni_vendita: float, tasso: float = 0.03, costo: float = 0.0) -> float:
    """Convenienza di vendere e riacquistare uno strumento in perdita.

    Si guadagna una minusvalenza (redditi diversi) che vale solo se verrà usata entro quattro anni; in cambio il costo
    fiscale scende e alla vendita futura si pagherà di più. Per ETF e fondi quella imposta futura colpisce un reddito
    di capitale che lo zainetto non può compensare: se la minusvalenza resta inutilizzata, l'operazione fa pagare più
    tasse. Restituisce il valore attuale netto in euro."""
    base = perdita * s.fattore
    guadagno = valore_minusvalenza(base, probabilita_uso, anni_uso, tasso)
    imposta_futura = ALIQUOTA * base / (1 + tasso) ** anni_vendita
    return guadagno - imposta_futura - costo


def imposta_per_ordine(minus: float, plus: float) -> dict[str, float]:
    """Nel regime amministrato una minusvalenza compensa solo le plusvalenze successive: l'ordine conta."""
    return {"Prima la plusvalenza": ALIQUOTA * plus, "Prima la minusvalenza": ALIQUOTA * max(plus - minus, 0.0)}


VEICOLI = {
    "ETF azionario": (Tipo.ETF, 0.0),
    "Azioni, ETC, certificates": (Tipo.ETC, 0.0),
    "ETF di titoli di Stato": (Tipo.ETF, 1.0),
    "Titoli di Stato diretti": (Tipo.TITOLO_STATO, 1.0),
}


def confronto_veicoli(guadagno: float, zainetto: float) -> pd.DataFrame:
    """Imposta su uno stesso guadagno lordo a seconda dello strumento, con uno zainetto disponibile."""
    righe = []
    for nome, (tipo, quota) in VEICOLI.items():
        s = Strumento(nome, tipo, quota_stato=quota)
        base = guadagno * s.fattore
        usato = min(base, zainetto) if s.plus_compensabili and guadagno > 0 else 0.0
        imposta = ALIQUOTA * max(base - usato, 0.0) if guadagno > 0 else 0.0
        righe.append({"veicolo": nome, "categoria": s.regola.plusvalenze if guadagno >= 0 else DIVERSI,
                      "aliquota nominale": s.aliquota, "zainetto usato": usato, "imposta": imposta,
                      "netto": guadagno - imposta, "aliquota effettiva": imposta / guadagno if guadagno > 0 else 0.0})
    return pd.DataFrame(righe).set_index("veicolo")


def curva_veicoli(guadagni, zainetto: float) -> pd.DataFrame:
    return pd.DataFrame({g: confronto_veicoli(g, zainetto)["imposta"] for g in guadagni}).T


__all__ = ["CAPITALE", "DIVERSI", "Costi", "Piano", "Azione", "latenti", "piano_recupero", "valore_minusvalenza",
           "valore_realizzo_perdita", "imposta_per_ordine", "confronto_veicoli", "curva_veicoli"]
