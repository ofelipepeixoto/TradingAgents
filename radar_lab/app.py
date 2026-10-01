"""Research reports and a local human gate; no trading or publishing adapters."""

import html
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .contracts import SECTIONS, LabError, digest, validate_analysis, validate_evidence
from .provider import generate
from .store import money


def demo_bundle():
    return {
        "topic": "Empresa fictícia Aurora: expansão de infraestrutura de IA",
        "is_demo": True,
        "sources": [
            {"id": "F1", "title": "Comunicado fictício — demanda e capacidade",
             "url": "https://example.org/aurora-demanda", "published_at": "2026-09-29",
             "excerpt": "EXEMPLO FICTÍCIO. A Aurora relata demanda maior que sua capacidade atual "
                        "e estuda ampliar a infraestrutura. Não divulga contratos ou orçamento."},
            {"id": "F2", "title": "Nota fictícia — energia e financiamento",
             "url": "https://example.org/aurora-riscos", "published_at": "2026-09-29",
             "excerpt": "EXEMPLO FICTÍCIO. A expansão depende de energia e financiamento. "
                        "Não há prazo confirmado, custos ou projeção de receita."},
        ],
    }


def demo_analysis():
    def item(value, *sources):
        return {"text": value, "source_ids": list(sources)}

    return {
        "summary": "DEMONSTRAÇÃO FICTÍCIA: demanda indicada pode justificar expansão, mas "
                   "faltam contratos, custos e prazo. O cenário não permite concluir viabilidade.",
        "facts": [item("No comunicado fictício, a Aurora relata demanda superior à capacidade.", "F1")],
        "bull_case": [item("Hipótese: ampliar capacidade pode atender demanda hoje não atendida.", "F1")],
        "bear_case": [item("Contraponto: demanda relatada não comprova receita contratada ou retorno.", "F1", "F2")],
        "risks": [item("Energia e financiamento são dependências; seu custo e disponibilidade não foram demonstrados.", "F2")],
        "watch": [item("Acompanhar confirmação de contratos, orçamento, energia e cronograma.", "F1", "F2")],
        "gaps": ["Não há dados reais, balanços, contratos ou evidência de rentabilidade neste exemplo."],
    }


def run(store, *, bundle=None, pricing=None, run_limit="0.50", day_limit="2.00",
        max_output_tokens=3000, transport=None):
    is_demo = bundle is None
    bundle = validate_evidence(demo_bundle() if is_demo else bundle)
    run_id = uuid.uuid4().hex
    if is_demo:
        store.reserve(run_id, 0, money(run_limit), money(day_limit))
        analysis, usage = demo_analysis(), {"input_tokens": 0, "output_tokens": 0,
                                          "reserved_usd_micro": 0, "actual_usd_micro": 0}
    else:
        if pricing is None:
            raise LabError("Informe tarifas revisadas para usar a API.")
        analysis, usage = generate(bundle, pricing, store, run_id,
                                   run_limit=money(run_limit), day_limit=money(day_limit),
                                   max_output_tokens=max_output_tokens, transport=transport)
    try:
        validate_analysis(analysis, bundle)
        report = {"schema_version": 1, "lab_version": __version__, "run_id": run_id,
                  "created_at": datetime.now(UTC).isoformat(), "mode": "demo" if is_demo else "live",
                  "model": "offline-fixture" if is_demo else pricing["model"],
                  "pricing": None if is_demo else pricing, "evidence_hash": digest(bundle),
                  "evidence": bundle, "analysis": analysis, "usage": usage,
                  "scope": "Pesquisa com revisão humana; sem execução de ordens ou publicação."}
        store.complete(run_id, report, usage["actual_usd_micro"])
        return run_id
    except Exception:
        store.fail(run_id)
        raise


def _md(value):
    # Model text is plain text, never executable HTML or active Markdown links.
    value = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", value).replace("\n", " ")


def markdown(row, report):
    analysis = report["analysis"]
    title = "Radar de Teses e Riscos"
    lines = [f"# {title}", "", f"**{_md(report['evidence']['topic'])}**", "",
             f"Status: **{row['status']}** · Modo: **{report['mode']}**", "",
             "**DEMONSTRAÇÃO COM DADOS FICTÍCIOS — sem valor de análise financeira.**"
             if report["mode"] == "demo" else
             "**Pesquisa baseada em trechos fornecidos; as URLs não foram visitadas pelo laboratório.**",
             "", _md(analysis["summary"]), ""]
    for key, heading in SECTIONS.items():
        lines.extend([f"## {heading}", ""])
        for item in analysis[key]:
            lines.append(f"- {_md(item['text'])} [fontes: {', '.join(item['source_ids'])}]")
        lines.append("")
    lines.extend(["## Lacunas", "", *[f"- {_md(gap)}" for gap in analysis["gaps"]], "",
                  "## Evidências fornecidas", ""])
    for source in report["evidence"]["sources"]:
        lines.extend([f"- **{source['id']}** — {_md(source['title'])} ({source['published_at']})",
                      f"  URL: {_md(source['url'])}", f"  Trecho: {_md(source['excerpt'])}", ""])
    usage = report["usage"]
    lines.extend(["## Registro de revisão e custo", "",
                  f"- Execução: `{report['run_id']}`", f"- Hash: `{row['hash']}`",
                  f"- Versão: {_md(report['lab_version'])}; modelo: {_md(report['model'])}",
                  f"- Reserva conservadora: USD {usage['reserved_usd_micro'] / 1000000:.6f}",
                  f"- Custo calculado pelas tarifas informadas: USD {usage['actual_usd_micro'] / 1000000:.6f}",
                  f"- Revisor: {_md(row.get('reviewer') or 'pendente')}",
                  f"- Justificativa: {_md(row.get('note') or 'pendente')}",
                  f"- Validade da aprovação: {_md(row.get('expires_at') or 'pendente')}", "",
                  "A aprovação permite somente exportar este relatório local. Não autoriza ordens ou publicação.", ""])
    return "\n".join(lines)


def preview(store, run_id):
    row, report = store.get(run_id)
    content = html.escape(markdown(row, report))
    page = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Radar de Teses e Riscos — revisão</title>
<style>body{{background:#10141a;color:#e6edf3;font:16px/1.65 system-ui;margin:2rem auto;padding:0 1.5rem;max-width:960px}}
header{{border-left:5px solid #fbc205;padding:1rem;background:#19212a}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}
strong{{color:#fbc205}}</style><header><strong>RADAR · TESES E RISCOS</strong>
<p>Prévia para revisão local. Fontes, afirmações e riscos precisam ser conferidos por uma pessoa.</p></header>
<pre>{content}</pre></html>"""
    path = store.directory / f"{run_id}-preview.html"
    _write_private(path, page)
    return path


def _write_private(path: Path, content: str):
    # Refuse overwriting files (including symlinks) outside our managed store.
    with path.open("x", encoding="utf-8") as handle:
        path.chmod(0o600)
        handle.write(content)


def export(store, run_id):
    row, report = store.approved(run_id)
    path = store.directory / f"{run_id}-approved-{uuid.uuid4().hex[:8]}.md"
    _write_private(path, markdown(row, report))
    return path
