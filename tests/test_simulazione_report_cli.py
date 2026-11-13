import json
from datetime import date

import numpy as np
import pytest

from fiscale_investimenti import cli, configurazione, dati
from fiscale_investimenti.analisi import analizza
from fiscale_investimenti.report import build_report
from fiscale_investimenti.simulazione import (
    PASSIVA,
    RECUPERO,
    ParametriSimulazione,
    Simulatore,
    simula_prezzi,
)
from fiscale_investimenti.strumenti import Strumento


def test_prezzi_simulati():
    s = {"A": Strumento("A", "etf", rendimento=0.05, volatilita=0.2),
         "B": Strumento("B", "obbligazione", scadenza=date(2028, 6, 30), volatilita=0.05, gruppo="obbligazioni")}
    par = ParametriSimulazione(anni=3, scenari=20_000, seme=1)
    p = simula_prezzi(s, {"A": 100, "B": 90}, date(2025, 12, 15), par)
    assert p["A"].shape == (20_000, 4) and (p["A"][:, 0] == 100).all()
    assert np.mean(p["A"][:, 1]) == pytest.approx(100 * np.exp(0.05), rel=0.01)
    assert np.allclose(p["B"][:, 3], 100)                      # rimborsato a scadenza
    assert np.mean(p["B"][:, 1]) == pytest.approx(90 + 10 / 2.54, abs=1.0)   # ponte verso la pari


def test_simulazione_recupero_conviene(motore_demo):
    st = dati.strumenti_dimostrativi()
    r = Simulatore(st, par=ParametriSimulazione(scenari=40)).esegui(motore_demo, dati.PREZZI_OGGI, dati.DATA_ANALISI)
    s = r.sintesi()
    assert s.loc[RECUPERO, "Differenza media"] > 1_000
    assert s.loc[PASSIVA, "Minusvalenze scadute"] > s.loc[RECUPERO, "Minusvalenze scadute"] + 6_000
    assert len(r.scenari) == 3 * 40
    # il motore di partenza non viene modificato dalla simulazione
    assert motore_demo.zainetto.in_scadenza(2026) > 6_000


def test_analisi_e_report(analisi_demo, tmp_path):
    a = analisi_demo
    assert a.piano.recuperato == pytest.approx(a.piano.obiettivo)
    assert a.capitale_con_zainetto > 1_600 and len(a.plus_etf_con_zainetto) == 1
    assert 2026 not in a.zainetto_dopo and a.zainetto_oggi[2026] == pytest.approx(a.piano.obiettivo)
    out = build_report(a, tmp_path / "r.html", data_note="nota di prova")
    html = out.read_text(encoding="utf-8")
    assert "Il piano di fine anno" in html and "ETC Oro fisico" in html and "nota di prova" in html
    assert "Redditi di capitale" in html and "Simulazione" in html


def test_configurazione_json_e_cli(tmp_path, capsys):
    cfg = json.loads(open("esempi/cliente.json", encoding="utf-8").read())
    cfg["movimenti"] = "movimenti.csv"
    (tmp_path / "movimenti.csv").write_text(open("data/movimenti_esempio.csv", encoding="utf-8").read(),
                                            encoding="utf-8")
    cfg["simulazione"]["scenari"] = 20
    cfg["zainetto_iniziale"] = {"2023": 1000}
    p = tmp_path / "cliente.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    c = configurazione.carica(p)
    assert c.zainetto_iniziale == {2023: 1000.0} and len(c.movimenti) == len(dati.movimenti_dimostrativi())
    c.simula = False
    base = configurazione.esempio()
    base.simula = False
    # le minusvalenze 2023 portate da un'altra banca sono più recenti di quelle 2022: si usano dopo e restano
    assert analizza(c).zainetto_saldo == pytest.approx(analizza(base).zainetto_saldo + 1000)
    assert analizza(c).zainetto_oggi[2027] == pytest.approx(1000)
    assert cli.main(["--config", str(p), "--output", str(tmp_path / "out.html"), "--veloce"]) == 0
    assert (tmp_path / "out.html").exists()
    assert "In scadenza il 31/12/2026" in capsys.readouterr().out
