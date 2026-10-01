"""Bounded inputs, explicit evidence references, and deterministic validation."""

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


class LabError(ValueError):
    """A safe, user-facing failure without provider bodies or credentials."""


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LabError("JSON contém campos duplicados.")
        result[key] = value
    return result


def _bad_constant(_value):
    raise LabError("JSON contém número não finito.")


def parse_json(text: str):
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=_bad_constant)
    except (ValueError, RecursionError) as exc:
        raise LabError("JSON inválido ou excessivamente complexo.") from exc


def read_json(path: Path):
    # A bounded read also protects against a file growing after a stat check.
    with path.open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise LabError("Arquivo excede 64 KiB.")
    try:
        return parse_json(raw.decode("utf-8"))
    except UnicodeError as exc:
        raise LabError("O arquivo deve ser UTF-8.") from exc


def text(value, label: str, limit: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LabError(f"Campo inválido: {label}.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise LabError(f"Caracteres de controle em {label}.")
    return value


def fields(value, names: set[str], label: str):
    if not isinstance(value, dict) or set(value) != names:
        raise LabError(f"Campos inválidos em {label}.")


def https_url(value) -> str:
    value = text(value, "URL", 1000)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise LabError("URL inválida.") from exc
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or port not in (None, 443) or any(c.isspace() for c in value)):
        raise LabError("Use URL HTTPS sem credenciais e sem porta alternativa.")
    return value


def validate_evidence(bundle):
    fields(bundle, {"topic", "is_demo", "sources"}, "evidências")
    text(bundle["topic"], "tema", 200)
    if type(bundle["is_demo"]) is not bool:
        raise LabError("is_demo deve ser booleano.")
    sources = bundle["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= 12:
        raise LabError("Inclua entre 1 e 12 fontes.")
    ids = set()
    for source in sources:
        fields(source, {"id", "title", "url", "published_at", "excerpt"}, "fonte")
        sid = text(source["id"], "id", 40)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in ids:
            raise LabError("IDs de fonte devem ser únicos e simples.")
        ids.add(sid)
        text(source["title"], "título", 200)
        https_url(source["url"])
        text(source["excerpt"], "trecho", 4000)
        try:
            date.fromisoformat(text(source["published_at"], "data", 10))
        except ValueError as exc:
            raise LabError("Data da fonte inválida (AAAA-MM-DD).") from exc
    if len(canonical(bundle).encode()) > 48000:
        raise LabError("As evidências excedem o limite de contexto do laboratório.")
    return bundle


SECTIONS = {
    "facts": "Fatos apresentados pelas fontes",
    "bull_case": "Tese favorável — interpretação",
    "bear_case": "Contraponto — interpretação",
    "risks": "Riscos e hipóteses",
    "watch": "O que acompanhar",
}


ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "source_ids"],
    "additionalProperties": False,
}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        **{key: {"type": "array", "items": ITEM_SCHEMA} for key in SECTIONS},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", *SECTIONS, "gaps"],
    "additionalProperties": False,
}


def validate_analysis(analysis, bundle):
    fields(analysis, {"summary", *SECTIONS, "gaps"}, "análise")
    text(analysis["summary"], "resumo", 1500)
    ids = {s["id"] for s in bundle["sources"]}
    for key in SECTIONS:
        items = analysis[key]
        if not isinstance(items, list) or not 1 <= len(items) <= 8:
            raise LabError(f"A seção {key} deve conter entre 1 e 8 itens.")
        for item in items:
            fields(item, {"text", "source_ids"}, "item da análise")
            text(item["text"], "afirmação", 1500)
            references = item["source_ids"]
            if (not isinstance(references, list) or not references or len(references) > 12
                    or any(not isinstance(sid, str) or sid not in ids for sid in references)):
                raise LabError("Referência ausente ou não fornecida nas evidências.")
    gaps = analysis["gaps"]
    if not isinstance(gaps, list) or not 1 <= len(gaps) <= 8:
        raise LabError("Registre entre 1 e 8 lacunas.")
    for gap in gaps:
        text(gap, "lacuna", 1000)
    # A known source ID proves provenance, not that it supports the assertion.
    return analysis
