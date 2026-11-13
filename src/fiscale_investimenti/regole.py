"""Regole fiscali italiane sui redditi finanziari delle persone fisiche (regime amministrato).

Le costanti riflettono la normativa in vigore nel 2026:

- aliquota del 26% su redditi di capitale e redditi diversi di natura finanziaria;
- aliquota del 12,5% sui titoli di Stato italiani, dei Paesi della white list e degli enti sovranazionali, ottenuta
  tassando al 26% il 48,08% del reddito (12,5 / 26);
- per gli OICR (fondi ed ETF) la quota di reddito riferibile ai titoli di Stato, indicata nel prospetto semestrale
  del fondo, è ridotta nella stessa proporzione;
- le minusvalenze (redditi diversi) si compensano con le plusvalenze dello stesso anno e dei quattro successivi;
- i proventi positivi di fondi ed ETF sono redditi di capitale e non si compensano con le minusvalenze, mentre le
  loro perdite sono redditi diversi e finiscono nello zainetto fiscale;
- imposta di bollo dello 0,20% annuo sul valore dei prodotti finanziari; Tobin tax dello 0,10% sugli acquisti di
  azioni italiane in borsa, calcolata sul saldo netto giornaliero.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ALIQUOTA = 0.26
ALIQUOTA_STATO = 0.125
QUOTA_IMPONIBILE_STATO = ALIQUOTA_STATO / ALIQUOTA      # 48,08%
ANNI_RIPORTO = 4
BOLLO = 0.002
TOBIN = 0.001

CAPITALE = "Redditi di capitale"
DIVERSI = "Redditi diversi"


class Tipo(StrEnum):
    AZIONE_IT = "azione_it"
    AZIONE_ESTERA = "azione_estera"
    OBBLIGAZIONE = "obbligazione"
    TITOLO_STATO = "titolo_stato"
    ETF = "etf"
    ETC = "etc"
    CERTIFICATE = "certificate"


@dataclass(frozen=True)
class Regola:
    """Come vengono classificati i redditi di una tipologia di strumento."""

    descrizione: str
    plusvalenze: str        # categoria dei guadagni da cessione o rimborso
    minusvalenze: str       # categoria delle perdite (sempre redditi diversi, tranne eccezioni)
    flussi: str             # categoria di cedole, dividendi, premi, proventi periodici
    nome_flusso: str
    tobin: bool = False
    quota_stato: float = 0.0


REGOLE: dict[Tipo, Regola] = {
    Tipo.AZIONE_IT: Regola("Azioni italiane", DIVERSI, DIVERSI, CAPITALE, "dividendo", tobin=True),
    Tipo.AZIONE_ESTERA: Regola("Azioni estere", DIVERSI, DIVERSI, CAPITALE, "dividendo"),
    Tipo.OBBLIGAZIONE: Regola("Obbligazioni societarie", DIVERSI, DIVERSI, CAPITALE, "cedola"),
    Tipo.TITOLO_STATO: Regola("Titoli di Stato white list", DIVERSI, DIVERSI, CAPITALE, "cedola", quota_stato=1.0),
    Tipo.ETF: Regola("ETF e fondi armonizzati", CAPITALE, DIVERSI, CAPITALE, "provento"),
    Tipo.ETC: Regola("ETC ed ETN", DIVERSI, DIVERSI, DIVERSI, "provento"),
    Tipo.CERTIFICATE: Regola("Certificates", DIVERSI, DIVERSI, DIVERSI, "premio"),
}


def fattore_imponibile(quota_stato: float) -> float:
    """Frazione del reddito che concorre alla base imponibile: 1 senza titoli di Stato, 48,08% con soli titoli
    di Stato."""
    if not 0.0 <= quota_stato <= 1.0:
        raise ValueError("La quota di titoli di Stato deve essere tra 0 e 1")
    return 1.0 - quota_stato * (1.0 - QUOTA_IMPONIBILE_STATO)


def aliquota_effettiva(quota_stato: float = 0.0) -> float:
    """Aliquota sul reddito lordo: 26% senza titoli di Stato, 12,5% con soli titoli di Stato."""
    return ALIQUOTA * fattore_imponibile(quota_stato)


def ultimo_anno_utile(anno_realizzo: int) -> int:
    """Le minusvalenze realizzate in un anno si usano fino al 31 dicembre del quarto anno successivo."""
    return anno_realizzo + ANNI_RIPORTO


def commissione(controvalore: float, percentuale: float = 0.0019, minimo: float = 2.95, massimo: float = 19.0) -> float:
    """Commissione di negoziazione tipica di una banca online (percentuale con minimo e massimo)."""
    if controvalore <= 0:
        return 0.0
    return float(min(max(controvalore * percentuale, minimo), massimo))
