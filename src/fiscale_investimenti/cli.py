"""Riga di comando: registro fiscale, zainetto, piano di fine anno, simulazione e report.

Esempi::

    fiscale-investimenti --demo
    fiscale-investimenti --config esempi/cliente.json --output output/report.html
    fiscale-investimenti --demo --veloce --grafici docs/img
"""

from __future__ import annotations

import argparse
import sys

from . import configurazione
from .analisi import analizza
from .report import _eur, _num, _pct, build_report, salva_grafici

NOTA_DEMO = ("Caso dimostrativo: strumenti, prezzi e movimenti sono di fantasia, costruiti per mostrare i casi tipici "
             "del sistema fiscale italiano.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="fiscale-investimenti", description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--config", help="File JSON con strumenti, movimenti e prezzi di oggi")
    src.add_argument("--demo", action="store_true", help="Usa il caso dimostrativo")
    p.add_argument("--cliente", help="Nome del cliente nel report")
    p.add_argument("--output", default="output/report.html", help="Percorso del report HTML")
    p.add_argument("--grafici", help="Cartella dove salvare anche i grafici PNG (richiede kaleido)")
    p.add_argument("--offline", action="store_true", help="Include plotly.js nel report (funziona senza rete)")
    p.add_argument("--veloce", action="store_true", help="Salta la simulazione Monte Carlo")
    p.add_argument("--scenari", type=int, help="Numero di scenari della simulazione")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = configurazione.esempio() if args.demo else configurazione.carica(args.config)
    if args.cliente:
        cfg.cliente = args.cliente
    if args.veloce:
        cfg.simula = False
    if args.scenari:
        cfg.simulazione.scenari = args.scenari
    a = analizza(cfg)
    path = build_report(a, args.output, data_note=NOTA_DEMO if cfg.dimostrativo else "", offline=args.offline)
    if args.grafici:
        salva_grafici(a, args.grafici)

    anno = a.anno
    print(f"Imposte pagate: {_eur(a.imposte_totali)}")
    print(f"Zainetto al {cfg.data_analisi:%d/%m/%Y}: {_eur(a.zainetto_saldo)}")
    for k, v in a.zainetto_oggi.items():
        print(f"  scadenza 31/12/{k}: {_eur(v)}")
    p = a.piano
    print(f"\nIn scadenza il 31/12/{anno}: {_eur(p.obiettivo)}")
    for x in p.azioni:
        print(f"  vendere e riacquistare {_num(x.quantita, 0)} {x.strumento} a {_num(x.prezzo, 2)}: "
              f"recupera {_eur(x.recuperato)}, costo {_eur(x.costo, 2)}")
    if p.azioni:
        print(f"  imposta futura evitata {_eur(p.risparmio)}, valore attuale "
              f"{_eur(p.valore_attuale(cfg.anni_vendita, cfg.tasso_sconto))}")
    if p.perso > 0.5:
        print(f"  minusvalenze comunque perse: {_eur(p.perso)}")
    if a.simulazione is not None:
        s = a.simulazione.sintesi()
        print(f"\nSimulazione {anno + 1}–{anno + cfg.simulazione.anni} ({cfg.simulazione.scenari} scenari)")
        for n, r in s.iterrows():
            print(f"  {n:<30} netto {_eur(r['Patrimonio netto finale']):>12}"
                  f"   diff. media {_eur(r['Differenza media']):>9}"
                  f"   minus scadute {_eur(r['Minusvalenze scadute']):>9}   migliori {_pct(r['Scenari migliori'], 0)}")
    print(f"\nReport salvato in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
