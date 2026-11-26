"""T3.5 : graphe déterministe à sept agents remplaçables, checkpoints PostgreSQL."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import uuid4

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from saam.audit.events import pipeline_completed
from saam.cases import CaseService, InvalidTransition, Job
from saam.traceability import (
    AnchoringError,
    Artifact,
    ArtifactFile,
    TraceabilityTool,
    UploadStaging,
    json_file,
)

STAGES = (
    "ingestion",
    "preparation",
    "features",
    "prediction",
    "validation",
    "explanation",
    "finalization",
)
TYPES = dict(
    zip(
        STAGES,
        (
            "original",
            "processed",
            "features",
            "prediction",
            "validation",
            "explanation",
            "final_result",
        ),
        strict=True,
    )
)


class WorkerInterrupted(BaseException):
    """Arrêt/lease perdu : laisser le job et le checkpoint pour une reprise."""


class CaseState(TypedDict, total=False):
    case_id: str
    job_id: str
    artifacts: dict[str, str]
    artifact_time: str
    last_artifact_id: str | None
    status: str
    decision: str
    errors: list[str]


@dataclass(frozen=True)
class AgentOutput:
    files: tuple[ArtifactFile, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    decision: str | None = None


Agent = Callable[[str, CaseState, dict[str, tuple[str, bytes]]], AgentOutput]


def fake_agent(
    step: str, state: CaseState, files: dict[str, tuple[str, bytes]]
) -> AgentOutput:
    """Tranche fine, sans modèle clinique ni LLM ; aucun Accepté par défaut."""
    if step == "ingestion":
        return AgentOutput(
            tuple(
                ArtifactFile(name, media_type, data)
                for name, (media_type, data) in files.items()
            ),
            {"simulation": True},
        )
    payload: dict[str, Any] = {"stage": step, "simulation": True}
    decision = "revision_requise" if step == "validation" else None
    if step == "finalization":
        decision = state.get("decision", "revision_requise")
        payload |= {
            "decision": decision,
            "message": "Pipeline factice — pas un diagnostic médical.",
        }
    return AgentOutput(
        (json_file(TYPES[step] + ".json", payload),),
        {"simulation": True},
        decision,
    )


class GraphRunner:
    def __init__(
        self,
        cases: CaseService,
        uploads: UploadStaging,
        tools: Mapping[str, TraceabilityTool],
        *,
        agents: Mapping[str, Agent] | None = None,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self.cases, self.uploads, self.tools = cases, uploads, dict(tools)
        if set(self.tools) != set(STAGES):
            raise ValueError("Les sept identités d'agent sont obligatoires.")
        self.agents = dict(agents or {})
        self.heartbeat_interval = heartbeat_interval
        self.current_job: Job | None = None
        self.interrupted = threading.Event()
        self.stop: threading.Event | None = None
        self.connection = psycopg.connect(
            cases.database_url,
            autocommit=True,
            row_factory=dict_row,
            prepare_threshold=0,
            options="-c search_path=langgraph,public",
        )
        self.checkpointer = PostgresSaver(self.connection)
        try:
            self.connection.execute(
                "SELECT pg_advisory_lock(hashtextextended('saam-checkpoint-setup',0))"
            )
            try:
                self.checkpointer.setup()
            finally:
                self.connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended('saam-checkpoint-setup',0))"
                )
        except BaseException:
            self.connection.close()
            raise
        builder = StateGraph(CaseState)
        builder.add_node("allocate", self.allocate)
        builder.add_edge(START, "allocate")
        builder.add_edge("allocate", "ingestion")
        for step in STAGES:

            def node(state: CaseState, step: str = step) -> CaseState:
                return self.process(state, step)

            builder.add_node(step, node)
            if step == "finalization":
                builder.add_edge(step, END)
            else:
                following = STAGES[STAGES.index(step) + 1]

                def route(state: CaseState, following: str = following) -> str:
                    if state.get("status") == "erreur_ancrage":
                        return END
                    return (
                        "finalization"
                        if state.get("decision") == "rejete"
                        else following
                    )

                builder.add_conditional_edges(
                    step, route, [following, "finalization", END]
                )
        self.graph = builder.compile(checkpointer=self.checkpointer)

    @classmethod
    def from_environment(cls) -> GraphRunner:
        cases = CaseService(os.environ.get("DATABASE_URL_WORKER", ""))
        tools: dict[str, TraceabilityTool] = {}
        try:
            for step in STAGES:
                tools[step] = TraceabilityTool.from_environment(
                    step, on_failure=cases.fail_case
                )
            return cls(cases, UploadStaging.from_environment(), tools)
        except BaseException:
            for tool in tools.values():
                close = getattr(tool.ledger, "close", None)
                if close:
                    close()
            raise

    def close(self) -> None:
        self.connection.close()
        for tool in self.tools.values():
            close = getattr(tool.ledger, "close", None)
            if close:
                close()

    def allocate(self, state: CaseState) -> CaseState:
        return {
            "artifacts": {step: str(uuid4()) for step in STAGES},
            "artifact_time": datetime.now(UTC).isoformat(),
            "last_artifact_id": None,
            "decision": "revision_requise",
            "errors": [],
        }

    def log(
        self,
        state: CaseState,
        step: str,
        status: str,
        input_id: str | None,
        output_id: str | None,
        started: datetime,
        duration: int,
    ) -> None:
        with self.cases.connect() as db:
            # A crash can happen after the journal commit and before the node's
            # checkpoint. Replaying that node must keep one journal entry.
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,2))",
                (state["job_id"],),
            )
            if db.execute(
                "SELECT 1 FROM agent_logs WHERE job_id=%s AND step=%s LIMIT 1",
                (state["job_id"], step),
            ).fetchone():
                return
            db.execute(
                "INSERT INTO agent_logs (case_id,job_id,agent,step,status,input_artifact_ids,output_artifact_id,message,details,started_at,duration_ms) VALUES (%s,%s,%s,%s,%s,%s::uuid[],%s,%s,%s,%s,%s)",
                (
                    state["case_id"],
                    state["job_id"],
                    step,
                    step,
                    status,
                    [input_id] if input_id else [],
                    output_id,
                    {
                        "succes": "Étape terminée.",
                        "echec": "Étape interrompue.",
                        "ignore": "Étape non exécutée.",
                    }[status],
                    Jsonb({"simulation": True}),
                    started,
                    max(0, duration),
                ),
            )

    def skips(self, state: CaseState, step: str) -> None:
        for skipped in STAGES[STAGES.index(step) + 1 : -1]:
            self.log(
                state,
                skipped,
                "ignore",
                state.get("last_artifact_id"),
                None,
                datetime.now(UTC),
                0,
            )

    def process(self, state: CaseState, step: str) -> CaseState:
        job = self.current_job
        if job and (
            state.get("case_id") != job.case_id or state.get("job_id") != job.id
        ):
            raise WorkerInterrupted("Checkpoint d'un autre job.")
        if (
            job is None
            or self.interrupted.is_set()
            or (self.stop and self.stop.is_set())
            or not self.cases.heartbeat(job)
        ):
            raise WorkerInterrupted("Worker interrompu.")
        try:
            self.cases.update_progress(job, step)
        except InvalidTransition:
            raise WorkerInterrupted("Lease perdu.") from None
        updated = cast(CaseState, dict(state))
        updated["errors"] = list(state.get("errors", []))
        parent = state.get("last_artifact_id")
        started, clock = datetime.now(UTC), time.perf_counter()
        failed = False
        try:
            if step == "ingestion":
                _, files = self.uploads.read(state["case_id"])
            elif parent:
                manifest = self.tools[step].read_manifest(parent)
                files = {
                    f["name"]: (
                        f["media_type"],
                        self.tools[step].read(parent, f["name"]),
                    )
                    for f in manifest["files"]
                }
            else:
                files = {}
            output = self.agents.get(step, fake_agent)(step, updated, files)
            if output.decision is not None and output.decision not in {
                "accepte",
                "revision_requise",
                "rejete",
            }:
                raise ValueError("Décision d'agent invalide.")
        except AnchoringError:
            self.cases.fail_case(state["case_id"], job=job)
            updated["status"] = "erreur_ancrage"
            self.log(
                updated,
                step,
                "echec",
                parent,
                None,
                started,
                int((time.perf_counter() - clock) * 1000),
            )
            return updated
        except Exception:
            failed = True
            updated["errors"].append(step + ":AGENT_FAILURE")
            updated["decision"] = "rejete"
            output = AgentOutput(
                metadata={"simulation": True, "input_unavailable": True}
            )
            if step not in {"ingestion", "finalization"}:
                self.log(
                    updated,
                    step,
                    "echec",
                    parent,
                    None,
                    started,
                    int((time.perf_counter() - clock) * 1000),
                )
                self.skips(updated, step)
                return updated
        if output.decision == "rejete":
            updated["decision"] = "rejete"
            updated["errors"].append(step + ":REJECTED")
        elif output.decision and not updated["errors"]:
            updated["decision"] = output.decision
        if step == "finalization":
            decision = (
                "rejete"
                if updated["errors"]
                else updated.get("decision", "revision_requise")
            )
            updated["decision"] = decision
            payload = {
                "decision": decision,
                "simulation": True,
                "reason_codes": updated["errors"],
                "message": "Pipeline factice — pas un diagnostic médical.",
            }
            output = AgentOutput(
                (json_file("final_result.json", payload),),
                {"simulation": True},
            )
        if (
            self.interrupted.is_set()
            or (self.stop and self.stop.is_set())
            or not self.cases.heartbeat(job)
        ):
            raise WorkerInterrupted("Lease perdu.")
        artifact = Artifact(
            state["artifacts"][step],
            state["case_id"],
            TYPES[step],
            step,
            datetime.fromisoformat(state["artifact_time"]),
            parent_id=parent,
            files=output.files,
            metadata=output.metadata,
        )
        try:
            self.tools[step].record(artifact)
        except AnchoringError:
            self.cases.fail_case(state["case_id"], job=job)
            updated["status"] = "erreur_ancrage"
            self.log(
                updated,
                step,
                "echec",
                parent,
                None,
                started,
                int((time.perf_counter() - clock) * 1000),
            )
            return updated
        if (
            self.interrupted.is_set()
            or (self.stop and self.stop.is_set())
            or not self.cases.heartbeat(job)
        ):
            raise WorkerInterrupted("Lease perdu.")
        updated["last_artifact_id"] = artifact.id
        self.log(
            updated,
            step,
            "echec" if failed else "succes",
            parent,
            artifact.id,
            started,
            int((time.perf_counter() - clock) * 1000),
        )
        if step == "finalization":
            try:
                self.cases.complete_case(
                    state["case_id"],
                    updated["decision"],
                    job=job,
                    on_complete=lambda db, duration: pipeline_completed(
                        db, job.case_id, updated["decision"], duration
                    ),
                )
            except InvalidTransition:
                raise WorkerInterrupted("Lease perdu.") from None
            updated["status"] = "termine"
        elif updated["decision"] == "rejete":
            self.skips(updated, step)
        return updated

    def run(
        self,
        job: Job,
        *,
        stop: threading.Event | None = None,
        report: Callable[[bool], None] | None = None,
    ) -> CaseState:
        case = self.cases.get_case(job.case_id)
        if case["status"] == "termine":
            if self.cases.heartbeat(job):
                self.cases.finish_job(job, True)
            return {
                "case_id": job.case_id,
                "status": "termine",
                "decision": case["decision"],
            }
        self.current_job, self.stop = job, stop
        templates = self.tools
        self.tools = {
            step: TraceabilityTool(
                tool.database_url,
                tool.store,
                tool.ledger,
                on_failure=lambda cid: self.cases.fail_case(cid, job=job),
                sleep=tool.sleep,
            )
            for step, tool in templates.items()
        }
        self.interrupted.clear()
        completed = threading.Event()

        def beat() -> None:
            while not completed.wait(self.heartbeat_interval):
                try:
                    owned = self.cases.heartbeat(job)
                    if not owned:
                        self.interrupted.set()
                    if report:
                        report(owned)
                except (psycopg.Error, OSError):
                    self.interrupted.set()
                    if report:
                        report(False)

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        config: RunnableConfig = {"configurable": {"thread_id": job.id}}
        try:
            snapshot = self.graph.get_state(config)
            initial: CaseState | None = (
                None
                if snapshot.values
                else {"case_id": job.case_id, "job_id": job.id, "status": "en_cours"}
            )
            result = cast(
                CaseState, self.graph.invoke(initial, config, durability="sync")
            )
            # Stop the heartbeat before releasing the lease, otherwise its last
            # tick can misreport a normally completed job as a lost lease.
            completed.set()
            thread.join(timeout=10)
            self.cases.finish_job(job, result.get("status") == "termine")
            return result
        finally:
            completed.set()
            thread.join(timeout=10)
            self.current_job = None
            self.tools = templates
