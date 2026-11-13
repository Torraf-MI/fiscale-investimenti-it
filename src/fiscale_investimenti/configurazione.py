"""Configurazione dell'analisi: caso dimostrativo o file JSON del cliente."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import dati
from .motore import Movimento, leggi_movimenti
from .pianificazione import Costi
from .simulazione import ParametriSimulazione
from .strumenti import Strumento


@dataclass
class Configurazione:
    cliente: str
    data_analisi: date
    strumenti: dict[str, Strumento]
    movimenti: list[Movimento]
    prezzi: dict[str, float]
    zainetto_iniziale: dict[int, float] = field(default_factory=dict)   # minusvalenze portate da un'altra banca
    costi: Costi = field(default_factory=Costi)
    simulazione: ParametriSimulazione = field(default_factory=ParametriSimulazione)
    anni_vendita: float = 5.0              # tra quanti anni si venderebbero comunque gli strumenti
    tasso_sconto: float = 0.03
    simula: bool = True
    dimostrativo: bool = False


def esempio() -> Configurazione:
    return Configurazione("Famiglia Rossi", dati.DATA_ANALISI, dati.strumenti_dimostrativi(),
                          dati.movimenti_dimostrativi(), dict(dati.PREZZI_OGGI), dimostrativo=True)


def carica(percorso: str | Path) -> Configurazione:
    percorso = Path(percorso)
    d = json.loads(percorso.read_text(encoding="utf-8"))
    strumenti = {s["nome"]: Strumento.da_dict(s) for s in d["strumenti"]}
    mov = d["movimenti"]
    movimenti = leggi_movimenti(percorso.parent / mov) if isinstance(mov, str) else [Movimento(**m) for m in mov]
    sim = d.get("simulazione", {})
    if "correlazioni" in sim:
        sim["correlazioni"] = {tuple(k.split("-")): v for k, v in sim["correlazioni"].items()}
    return Configurazione(
        cliente=d.get("cliente", "Cliente"),
        data_analisi=date.fromisoformat(d["data_analisi"]),
        strumenti=strumenti,
        movimenti=movimenti,
        prezzi={k: float(v) for k, v in d["prezzi"].items()},
        zainetto_iniziale={int(k): float(v) for k, v in d.get("zainetto_iniziale", {}).items()},
        costi=Costi(**d.get("costi", {})),
        simulazione=ParametriSimulazione(**sim),
        anni_vendita=float(d.get("anni_vendita", 5.0)),
        tasso_sconto=float(d.get("tasso_sconto", 0.03)),
        simula=bool(d.get("simula", True)),
    )
