"""Atomic reservations and hash-bound human review for a single local operator."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from .contracts import LabError, canonical, digest, parse_json, text

CHECKS = ("sources", "claims", "risks")


def money(value) -> int:
    """USD to integer microdollars; no binary floating-point budget arithmetic."""
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise LabError("Valor monetário inválido.") from exc
    if not amount.is_finite() or not Decimal("0") < amount <= Decimal("10000"):
        raise LabError("O valor deve ser positivo e finito, até USD 10.000.")
    return int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING))


def cost(input_tokens: int, output_tokens: int, input_rate, output_rate) -> int:
    # Rates are USD per million tokens, so the result is already microdollars.
    amount = input_tokens * Decimal(str(input_rate)) + output_tokens * Decimal(str(output_rate))
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def now_utc():
    return datetime.now(UTC)


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "lab.sqlite3"
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS budgets (
                    day TEXT PRIMARY KEY, limit_usd_micro INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL,
                    reserved INTEGER NOT NULL, actual INTEGER,
                    status TEXT NOT NULL, report TEXT, hash TEXT,
                    reviewer TEXT, reviewed_at TEXT, expires_at TEXT, note TEXT
                );
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def reserve(self, run_id: str, amount: int, run_limit: int, day_limit: int, *, at=None):
        if not all(type(v) is int and v >= 0 for v in (amount, run_limit, day_limit)):
            raise LabError("Reserva inválida.")
        if amount > run_limit:
            raise LabError("A reserva máxima excede o orçamento por execução.")
        day = (at or now_utc()).astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if amount:
                row = conn.execute("SELECT * FROM budgets WHERE day=?", (day,)).fetchone()
                if row and row["limit_usd_micro"] != day_limit:
                    raise LabError("O orçamento diário já foi fixado hoje neste diretório.")
                conn.execute("INSERT OR IGNORE INTO budgets VALUES (?, ?)", (day, day_limit))
                used = conn.execute("SELECT COALESCE(SUM(reserved), 0) FROM runs WHERE day=?", (day,)).fetchone()[0]
                if used + amount > day_limit:
                    raise LabError("Orçamento diário esgotado; nenhuma geração foi iniciada.")
            try:
                conn.execute("INSERT INTO runs (id, day, reserved, status) VALUES (?, ?, ?, 'RUNNING')",
                             (run_id, day, amount))
            except sqlite3.IntegrityError as exc:
                raise LabError("Esta execução já foi registrada; não será repetida.") from exc

    def complete(self, run_id: str, report: dict, actual: int = 0):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["status"] != "RUNNING":
                raise LabError("Execução não está aberta.")
            if actual > row["reserved"]:
                # Charge the overrun to the ledger and quarantine the output.
                conn.execute("UPDATE runs SET status='ERROR', actual=?, reserved=? WHERE id=?",
                             (actual, actual, run_id))
            else:
                conn.execute("UPDATE runs SET status='PENDING_REVIEW', actual=?, report=?, hash=? WHERE id=?",
                             (actual, canonical(report), digest(report), run_id))
        if actual > row["reserved"]:
            raise LabError("Uso excedeu a reserva; relatório bloqueado e custo registrado.")

    def fail(self, run_id: str):
        # Never refund an uncertain call: timeout does not mean no billable work.
        with self.connection() as conn:
            conn.execute("UPDATE runs SET status='ERROR' WHERE id=? AND status='RUNNING'", (run_id,))

    def quarantine(self, run_id: str, actual: int):
        with self.connection() as conn:
            conn.execute("UPDATE runs SET status='ERROR', actual=?, reserved=MAX(reserved, ?) "
                         "WHERE id=? AND status='RUNNING'", (actual, actual, run_id))

    def get(self, run_id: str):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row or not row["report"]:
            raise LabError("Relatório não disponível.")
        report = parse_json(row["report"])
        if digest(report) != row["hash"]:
            raise LabError("O relatório mudou; revisão inválida.")
        return dict(row), report

    def review(self, run_id, *, expected_hash, reviewer, decision, checks=(), note="", at=None):
        text(reviewer, "revisor", 100)
        text(note, "justificativa", 1000)
        if decision not in ("APPROVED", "REJECTED"):
            raise LabError("Decisão inválida.")
        if decision == "APPROVED" and set(checks) != set(CHECKS):
            raise LabError("Confirme fontes, afirmações e riscos antes de aprovar.")
        at = at or now_utc()
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["status"] != "PENDING_REVIEW":
                raise LabError("A execução não está pendente de revisão.")
            if row["hash"] != expected_hash or digest(parse_json(row["report"])) != expected_hash:
                raise LabError("Hash diferente do relatório revisado.")
            conn.execute("""UPDATE runs SET status=?, reviewer=?, reviewed_at=?, expires_at=?, note=?
                            WHERE id=?""", (decision, reviewer, at.isoformat(),
                                            (at + timedelta(hours=24)).isoformat(), note, run_id))

    def approved(self, run_id, *, at=None):
        row, report = self.get(run_id)
        if row["status"] != "APPROVED":
            raise LabError("Exportação bloqueada: aguarda aprovação humana.")
        if datetime.fromisoformat(row["expires_at"]) <= (at or now_utc()):
            raise LabError("Aprovação expirada; gere uma nova análise e revise novamente.")
        return row, report
