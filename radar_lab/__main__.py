"""A small Portuguese CLI. Demo has no dependency on TradingAgents or API keys."""

import argparse
import sys
from pathlib import Path

from .app import export, preview, run
from .contracts import LabError, read_json
from .store import CHECKS, Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="Radar de Teses e Riscos — laboratório local")
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".radar-teses-riscos")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Exemplo fictício sem API e sem custo")
    live = commands.add_parser("analyze", help="Analisar trechos fornecidos usando OpenAI")
    live.add_argument("--evidence", type=Path, required=True)
    live.add_argument("--pricing", type=Path, required=True)
    live.add_argument("--live", action="store_true", help="Autorizar envio de evidências à API")
    live.add_argument("--run-limit-usd", default="0.50")
    live.add_argument("--day-limit-usd", default="2.00")
    live.add_argument("--max-output-tokens", type=int, default=3000)
    show = commands.add_parser("show", help="Ver hash, status e relatório")
    show.add_argument("run_id")
    review = commands.add_parser("review", help="Aprovar ou rejeitar a versão revisada")
    review.add_argument("run_id")
    review.add_argument("--hash", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--decision", choices=["approve", "reject"], required=True)
    review.add_argument("--note", required=True)
    for check in CHECKS:
        review.add_argument(f"--checked-{check}", action="store_true")
    out = commands.add_parser("export", help="Exportar apenas relatório aprovado e válido")
    out.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        store = Store(args.data_dir)
        if args.command in ("demo", "analyze"):
            if args.command == "analyze":
                if not args.live:
                    raise LabError("Use --live para autorizar envio dos trechos à OpenAI.")
                run_id = run(store, bundle=read_json(args.evidence), pricing=read_json(args.pricing),
                             run_limit=args.run_limit_usd, day_limit=args.day_limit_usd,
                             max_output_tokens=args.max_output_tokens)
            else:
                run_id = run(store)
            row, _ = store.get(run_id)
            print(f"Execução: {run_id}\nStatus: {row['status']}\nHash: {row['hash']}")
            print(f"Prévia: {preview(store, run_id)}")
        elif args.command == "show":
            from .app import markdown
            row, report = store.get(args.run_id)
            print(markdown(row, report))
        elif args.command == "review":
            checks = [name for name in CHECKS if getattr(args, f"checked_{name}")]
            store.review(args.run_id, expected_hash=args.hash, reviewer=args.reviewer,
                         decision="APPROVED" if args.decision == "approve" else "REJECTED",
                         checks=checks, note=args.note)
            print("Revisão registrada. Aprovação permite apenas exportação local por 24 horas.")
        else:
            print(f"Relatório aprovado: {export(store, args.run_id)}")
    except (LabError, OSError) as exc:
        # No raw provider body, URL, request object or credentials in error output.
        print(f"Bloqueado: {exc}" if isinstance(exc, LabError)
              else "Bloqueado: falha de arquivo ou armazenamento local.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
