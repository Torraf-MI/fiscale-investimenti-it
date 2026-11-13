"""Grafici interattivi (plotly) e report HTML per il cliente."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, PackageLoader, select_autoescape
from plotly.offline import get_plotlyjs, get_plotlyjs_version

from .analisi import Analisi
from .regole import ALIQUOTA, ANNI_RIPORTO, CAPITALE, DIVERSI, QUOTA_IMPONIBILE_STATO, REGOLE, aliquota_effettiva
from .simulazione import PASSIVA, RACCOLTA, RECUPERO

BLU, BLU_SCURO, ACQUA, ARANCIO = "#2a78d6", "#1c5cab", "#1baf7a", "#eb6834"
ROSSO, GIALLO, VIOLA, GRIGIO = "#e34948", "#e8a317", "#8a5cd1", "#8c8b86"
TESTO, TESTO_SECONDARIO, GRIGLIA = "#222222", "#52514e", "#e6e5e1"
COLORE_VOCE = {"Plusvalenze ETF e fondi": ROSSO, "Dividendi": BLU_SCURO, "Cedole obbligazioni": VIOLA,
               "Cedole titoli di Stato": ACQUA, "Proventi ETF": ARANCIO, "Plusvalenze (redditi diversi)": GIALLO,
               "Premi certificates": GRIGIO}
COLORE_VEICOLO = {"ETF azionario": ROSSO, "Azioni, ETC, certificates": BLU_SCURO, "ETF di titoli di Stato": ARANCIO,
                  "Titoli di Stato diretti": ACQUA}
COLORE_STRATEGIA = {PASSIVA: GRIGIO, RECUPERO: BLU_SCURO, RACCOLTA: ARANCIO}
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"


def _eur(x: float, dec: int = 0) -> str:
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'−' if x < -0.5 * 10**-dec else ''}{s} €"


def _pct(x: float, dec: int = 1, segno: bool = False) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    s = f"{x * 100:+.{dec}f}%" if segno else f"{x * 100:.{dec}f}%"
    return s.replace(".", ",").replace("-", "−")


def _num(x: float, dec: int = 2) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def _data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _layout(fig: go.Figure, titolo: str, altezza: int = 420) -> go.Figure:
    fig.update_layout(
        title={"text": titolo, "x": 0, "font": {"size": 15, "color": TESTO}},
        height=altezza, template="plotly_white",
        font={"family": "Segoe UI, Helvetica, Arial, sans-serif", "size": 12, "color": TESTO_SECONDARIO},
        margin={"l": 70, "r": 20, "t": 60, "b": 50}, separators=",.",
        hoverlabel={"bgcolor": "white", "font_color": TESTO}, legend={"orientation": "h", "y": -0.16, "x": 0},
    )
    fig.update_xaxes(gridcolor=GRIGLIA, zeroline=False)
    fig.update_yaxes(gridcolor=GRIGLIA, zerolinecolor="#bdbcb6")
    return fig


# ----------------------------------------------------------------------------- grafici
def grafico_imposte(a: Analisi) -> go.Figure:
    v = a.voci
    fig = go.Figure()
    for c in v.columns:
        fig.add_bar(x=v.index.astype(str), y=v[c], name=c, marker_color=COLORE_VOCE.get(c, GRIGIO),
                    hovertemplate=f"{c}<br>%{{x}}: %{{y:,.0f}} €<extra></extra>")
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="Imposte pagate (€)", tickformat=",.0f")
    return _layout(fig, "Imposte pagate ogni anno, per tipo di reddito")


def grafico_storia(a: Analisi) -> go.Figure:
    s = a.storia
    fig = go.Figure()
    fig.add_scatter(x=s.index, y=s.values, mode="lines", line={"shape": "hv", "color": BLU_SCURO, "width": 2.5},
                    fill="tozeroy", fillcolor="rgba(28,92,171,0.12)", name="Zainetto",
                    hovertemplate="%{x|%d/%m/%Y}: %{y:,.0f} €<extra></extra>")
    r = a.registro
    plus = r[(r["categoria"] == CAPITALE) & (r["operazione"] == "vendita") & (r["imposta"] > 0)]
    if not plus.empty:
        fig.add_scatter(x=pd.to_datetime(plus["data"]), y=plus["zainetto"], mode="markers+text",
                        name="Plusvalenza ETF tassata",
                        marker={"color": ROSSO, "size": 11, "symbol": "x"}, text=[_eur(x) for x in plus["imposta"]],
                        textposition="top center", hovertemplate="Plusvalenza ETF: imposta %{text}<extra></extra>")
    fig.add_vline(x=pd.Timestamp(a.cfg.data_analisi), line_dash="dot", line_color=GRIGIO)
    fig.update_yaxes(title="Minusvalenze disponibili (€)", tickformat=",.0f", rangemode="tozero")
    return _layout(fig, "Lo zainetto fiscale nel tempo")


def grafico_zainetto(a: Analisi) -> go.Figure:
    anni = sorted(set(a.zainetto_oggi) | set(a.zainetto_dopo))
    oggi = [a.zainetto_oggi.get(x, 0.0) for x in anni]
    dopo = [a.zainetto_dopo.get(x, 0.0) for x in anni]
    fig = go.Figure()
    fig.add_bar(x=[f"31/12/{x}" for x in anni], y=oggi, name="Oggi",
                marker_color=[ROSSO if x == a.anno else BLU_SCURO for x in anni],
                hovertemplate="Scadenza %{x}: %{y:,.0f} €<extra>oggi</extra>")
    fig.add_bar(x=[f"31/12/{x}" for x in anni], y=dopo, name="Dopo il piano di fine anno", marker_color=ACQUA,
                hovertemplate="Scadenza %{x}: %{y:,.0f} €<extra>dopo il piano</extra>")
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Ultimo giorno utile per usare le minusvalenze", type="category")
    fig.update_yaxes(title="Minusvalenze (€)", tickformat=",.0f")
    return _layout(fig, "Lo zainetto per scadenza")


def grafico_latenti(a: Analisi) -> go.Figure:
    lat = a.latenti.sort_values("latente")
    colori = [ROSSO if r["latente"] < 0 else (ACQUA if r["compensabile"] else GIALLO) for _, r in lat.iterrows()]
    etich = ["Minusvalenza latente" if r["latente"] < 0 else (DIVERSI + ": usa lo zainetto" if r["compensabile"]
             else CAPITALE + ": 26% pieno") for _, r in lat.iterrows()]
    fig = go.Figure(go.Bar(y=lat.index, x=lat["latente"], orientation="h", marker_color=colori, customdata=etich,
                           text=[_eur(x) for x in lat["latente"]], textposition="outside", cliponaxis=False,
                           showlegend=False, hovertemplate="%{y}<br>%{x:,.0f} €<br>%{customdata}<extra></extra>"))
    for nome, col in ((DIVERSI + " (compensabili)", ACQUA), (CAPITALE + " (non compensabili)", GIALLO),
                      ("Minusvalenze", ROSSO)):
        fig.add_scatter(x=[None], y=[None], mode="markers", marker={"color": col, "size": 10, "symbol": "square"},
                        name=nome)
    lo, hi = min(lat["latente"].min(), 0.0), max(lat["latente"].max(), 0.0)
    fig.update_xaxes(title="Plusvalenza o minusvalenza non realizzata (€)", tickformat=",.0f",
                     range=[lo - 0.12 * (hi - lo), hi + 0.1 * (hi - lo)])
    fig.update_yaxes(automargin=True)
    return _layout(fig, "Plusvalenze e minusvalenze latenti, per categoria fiscale", 400)


def grafico_piano(a: Analisi) -> go.Figure:
    p = a.piano
    voci = [(f"In scadenza il 31/12/{p.anno}", p.obiettivo, ROSSO)]
    voci += [(f"Recuperate vendendo {_num(x.quantita, 0)} {x.strumento}", x.recuperato, ACQUA) for x in p.azioni]
    if p.perso > 0.5:
        voci.append(("Perse comunque", p.perso, GRIGIO))
    voci = voci[::-1]
    fig = go.Figure(go.Bar(y=[v[0] for v in voci], x=[v[1] for v in voci], orientation="h",
                           marker_color=[v[2] for v in voci], text=[_eur(v[1]) for v in voci], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}: %{x:,.0f} €<extra></extra>"))
    fig.update_xaxes(title="Minusvalenze (€)", tickformat=",.0f")
    fig.update_yaxes(automargin=True)
    return _layout(fig, "Piano di fine anno: le minusvalenze in scadenza e come recuperarle", 120 + 60 * len(voci))


def grafico_veicoli(a: Analisi) -> go.Figure:
    c = a.curva
    fig = go.Figure()
    for v in c.columns:
        fig.add_scatter(x=c.index, y=c[v], mode="lines", name=v, line={"color": COLORE_VEICOLO[v], "width": 2.5},
                        hovertemplate=f"{v}<br>guadagno %{{x:,.0f}} €: imposta %{{y:,.0f}} €<extra></extra>")
    fig.update_xaxes(title="Guadagno lordo futuro (€)", tickformat=",.0f")
    fig.update_yaxes(title="Imposta (€)", tickformat=",.0f")
    saldo = sum(a.zainetto_dopo.values())
    return _layout(fig, f"Stesso guadagno, imposta diversa: zainetto disponibile di {_eur(saldo)}")


def grafico_aliquote() -> go.Figure:
    q = np.linspace(0, 1, 21)
    fig = go.Figure(go.Scatter(x=q, y=[aliquota_effettiva(x) for x in q], mode="lines+markers",
                               line={"color": BLU_SCURO, "width": 2.5},
                               hovertemplate="Titoli di Stato %{x:.0%}: aliquota %{y:.2%}<extra></extra>"))
    fig.update_xaxes(title="Quota di titoli di Stato nel fondo o nell'ETF", tickformat=".0%")
    fig.update_yaxes(title="Aliquota effettiva", tickformat=".1%", range=[0.10, 0.28])
    return _layout(fig, "Aliquota effettiva di un ETF in funzione della quota di titoli di Stato", 340)


def grafico_simulazione(a: Analisi) -> go.Figure:
    d = a.simulazione.differenze()
    fig = go.Figure()
    for s in d.columns:
        fig.add_histogram(x=d[s], name=s, marker_color=COLORE_STRATEGIA[s], opacity=0.7, nbinsx=50,
                          hovertemplate=f"{s}<br>%{{x:,.0f}} €: %{{y}} scenari<extra></extra>")
    fig.update_layout(barmode="overlay")
    fig.add_vline(x=0, line_color=GRIGIO)
    fig.update_xaxes(title=f"Patrimonio netto finale rispetto a «{PASSIVA}» (€)", tickformat=",.0f")
    fig.update_yaxes(title="Scenari")
    periodo = f"{a.anno + 1}–{a.anno + a.cfg.simulazione.anni}"
    return _layout(fig, f"Simulazione {periodo}: guadagno netto della gestione dello zainetto")


def grafico_raccolta(a: Analisi) -> go.Figure:
    d = a.raccolta_vs_recupero()
    fig = go.Figure(go.Histogram(x=d, marker_color=ARANCIO, nbinsx=50,
                                 hovertemplate="%{x:,.0f} €: %{y} scenari<extra></extra>"))
    fig.add_vline(x=0, line_color=GRIGIO)
    fig.update_xaxes(title=f"«{RACCOLTA}» meno «{RECUPERO}» (€)", tickformat=",.0f")
    fig.update_yaxes(title="Scenari")
    return _layout(fig, "Realizzare tutte le perdite conviene?", 340)


def _grafici(a: Analisi) -> dict:
    g = {"imposte": grafico_imposte(a), "storia": grafico_storia(a), "zainetto": grafico_zainetto(a),
         "latenti": grafico_latenti(a), "piano": grafico_piano(a), "veicoli": grafico_veicoli(a),
         "aliquote": grafico_aliquote()}
    if a.simulazione is not None:
        g["simulazione"] = grafico_simulazione(a)
        g["raccolta"] = grafico_raccolta(a)
    return g


def salva_grafici(a: Analisi, cartella: str | Path, scala: float = 2.0) -> list[Path]:
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    out = []
    for nome, fig in _grafici(a).items():
        p = cartella / f"{nome}.png"
        fig.write_image(str(p), width=1000, height=fig.layout.height or 420, scale=scala)
        out.append(p)
    return out


# ----------------------------------------------------------------------------- contesto
def contesto(a: Analisi) -> dict:
    p, anno = a.piano, a.anno
    sim = a.simulazione
    kpi = [
        ("Imposte pagate", _eur(a.imposte_totali), f"dal {a.registro['data'].min().year} a oggi"),
        ("Zainetto oggi", _eur(a.zainetto_saldo), f"{len(a.zainetto_oggi)} annualità"),
        (f"In scadenza il 31/12/{anno}", _eur(p.obiettivo), "perse se non usate"),
        ("Recuperabili con il piano", _eur(p.recuperato), f"costo delle operazioni {_eur(p.costo)}"),
        ("Imposta futura evitata", _eur(p.risparmio),
         f"valore attuale {_eur(p.valore_attuale(a.cfg.anni_vendita, a.cfg.tasso_sconto))}"),
        ("Imposte ETF con zainetto pieno", _eur(float(a.plus_etf_con_zainetto["imposta"].sum())),
         "plusvalenze ETF: reddito di capitale"),
    ]
    regole = [{"tipo": r.descrizione, "plus": r.plusvalenze, "minus": r.minusvalenze, "flussi": r.flussi,
               "nome_flusso": r.nome_flusso, "aliquota": _pct(aliquota_effettiva(r.quota_stato), 1)}
              for r in REGOLE.values()]
    riep = [{"anno": int(i), **{k: _eur(v) for k, v in r.items()}} for i, r in a.riepilogo.iterrows()]
    reg = a.registro
    reg = reg[reg["operazione"] != "acquisto"]
    registro = [{"data": _data(r["data"]), "strumento": r["strumento"], "operazione": r["operazione"],
                 "categoria": r["categoria"], "reddito": _eur(r["reddito"], 2), "imponibile": _eur(r["imponibile"], 2),
                 "compensato": _eur(r["compensato"], 2) if r["compensato"] else "", "imposta": _eur(r["imposta"], 2),
                 "minus": _eur(r["minus_generate"], 2) if r["minus_generate"] else "", "zainetto": _eur(r["zainetto"]),
                 "neg": r["reddito"] < 0} for _, r in reg.iterrows()]
    lat = [{"strumento": n, "tipo": r["tipo"], "quantita": _num(r["quantita"], 0), "costo": _num(r["costo_medio"], 2),
            "prezzo": _num(r["prezzo"], 2), "valore": _eur(r["valore"]), "latente": _eur(r["latente"]),
            "categoria": r["categoria"], "fattore": _pct(r["fattore"], 2), "imposta": _eur(r["imposta_latente"]),
            "compensabile": "sì" if r["compensabile"] else ("–" if r["latente"] < 0 else "no"), "neg": r["latente"] < 0}
           for n, r in a.latenti.iterrows()]
    azioni = [{"strumento": x.strumento, "quantita": _num(x.quantita, 0), "prezzo": _num(x.prezzo, 2),
               "controvalore": _eur(x.controvalore), "plus": _eur(x.plusvalenza), "base": _eur(x.imponibile),
               "recuperato": _eur(x.recuperato), "costo": _eur(x.costo, 2), "prima": _num(x.costo_medio_prima, 2),
               "dopo": _num(x.costo_medio_dopo, 2)} for x in p.azioni]
    zain = [{"scadenza": f"31/12/{k}", "realizzo": k - ANNI_RIPORTO, "oggi": _eur(v),
             "dopo": _eur(a.zainetto_dopo.get(k, 0.0)), "rosso": k == anno} for k, v in a.zainetto_oggi.items()]
    veic = [{"veicolo": n, "categoria": r["categoria"], "nominale": _pct(r["aliquota nominale"], 1),
             "usato": _eur(r["zainetto usato"]), "imposta": _eur(r["imposta"]), "netto": _eur(r["netto"]),
             "effettiva": _pct(r["aliquota effettiva"], 1)} for n, r in a.veicoli.iterrows()]
    etf_plus = a.plus_etf_con_zainetto
    ctx = {
        "cliente": a.cfg.cliente, "oggi": _data(date.today()), "data_analisi": _data(a.cfg.data_analisi),
        "anno": anno, "kpi": kpi, "regole": regole, "riepilogo": riep, "colonne_riepilogo": list(a.riepilogo.columns),
        "registro": registro, "latenti": lat, "azioni": azioni, "piano": p, "zainetto": zain, "veicoli": veic,
        "guadagno_veicoli": _eur(a.guadagno_veicoli), "saldo_dopo": _eur(sum(a.zainetto_dopo.values())),
        "etf_plus": [{"data": _data(r["data"]), "strumento": r["strumento"], "reddito": _eur(r["reddito"]),
                      "imposta": _eur(r["imposta"]), "zainetto": _eur(r["zainetto"])} for _, r in etf_plus.iterrows()],
        "quota_stato": _pct(QUOTA_IMPONIBILE_STATO, 2), "aliquota": _pct(ALIQUOTA, 0),
        "anni_vendita": _num(a.cfg.anni_vendita, 0), "tasso": _pct(a.cfg.tasso_sconto, 0),
        "valore_attuale": _eur(p.valore_attuale(a.cfg.anni_vendita, a.cfg.tasso_sconto)),
        "risparmio": _eur(p.risparmio), "recuperato": _eur(p.recuperato), "obiettivo": _eur(p.obiettivo),
        "perso": _eur(p.perso), "costo": _eur(p.costo), "capacita": _eur(p.capacita),
        "eur": _eur, "pct": _pct, "num": _num,
    }
    if sim is not None:
        s = sim.sintesi()
        ctx["sim"] = [{"strategia": n, "colore": COLORE_STRATEGIA[n], "netto": _eur(r["Patrimonio netto finale"]),
                       "imposte": _eur(r["Imposte pagate"]), "costi": _eur(r["Costi di negoziazione"]),
                       "scadute": _eur(r["Minusvalenze scadute"]),
                       "media": _eur(r["Differenza media"]) if n != PASSIVA else "–",
                       "p5": _eur(r["Differenza 5° percentile"]) if n != PASSIVA else "–",
                       "p95": _eur(r["Differenza 95° percentile"]) if n != PASSIVA else "–",
                       "migliori": _pct(r["Scenari migliori"], 0) if n != PASSIVA else "–"} for n, r in s.iterrows()]
        rr = a.raccolta_vs_recupero()
        ctx["sim_par"] = sim.par
        ctx["sim_anni"] = f"{anno + 1}–{anno + sim.par.anni}"
        ctx["rec_media"] = _eur(s.loc[RECUPERO, "Differenza media"])
        ctx["rec_migliori"] = _pct(s.loc[RECUPERO, "Scenari migliori"], 0)
        ctx["scad_passiva"] = _eur(s.loc[PASSIVA, "Minusvalenze scadute"])
        ctx["racc_media"] = _eur(rr.mean())
        ctx["racc_peggio"] = _pct(float((rr < -0.5).mean()), 0)
        ctx["racc_meglio"] = _pct(float((rr > 0.5).mean()), 0)
    return ctx


def build_report(a: Analisi, output: str | Path, data_note: str = "", offline: bool = False) -> Path:
    env = Environment(loader=PackageLoader("fiscale_investimenti", "templates"), autoescape=select_autoescape())
    g = {k: f.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})
         for k, f in _grafici(a).items()}
    html = env.get_template("report.html.j2").render(
        **contesto(a), grafici=g, data_note=data_note, plotly_cdn=PLOTLY_CDN,
        plotly_inline=get_plotlyjs() if offline else None)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
