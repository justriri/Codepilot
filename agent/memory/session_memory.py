"""
Session memory: the complete history of one AI coding agent run.

Unlike long-term memory, session memory is temporary.

It tracks everything that happens while an AI coding agent works:
- project context
- disposable environment
- commands executed
- files changed
- errors discovered
- fixes attempted
- tests performed
- screenshots/recordings generated
- verification results

Important knowledge can later be promoted into long-term memory.
"""

import threading
import time

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SessionEvent:
    """
    A single event during an agent run.
    """

    timestamp: float
    kind: str
    summary: str
    detail: dict = field(default_factory=dict)



@dataclass
class AgentSession:
    """
    Represents one complete AI coding agent execution.
    """

    session_id: str

    project_name: Optional[str] = None

    started_at: float = field(
        default_factory=time.time
    )

    status: str = "running"

    environment_id: Optional[str] = None

    events: List[SessionEvent] = field(
        default_factory=list
    )

    files_changed: List[str] = field(
        default_factory=list
    )

    commands_executed: List[str] = field(
        default_factory=list
    )

    verification_result: Optional[str] = None

    evidence: Dict = field(
        default_factory=dict
    )



class SessionMemory:

    def __init__(self):
        self._sessions: Dict[str, AgentSession] = {}

        self._lock = threading.Lock()



    def create_session(
        self,
        session_id: str,
        project_name: Optional[str] = None
    ):

        with self._lock:

            self._sessions[session_id] = AgentSession(
                session_id=session_id,
                project_name=project_name
            )



    def record(
        self,
        session_id: str,
        kind: str,
        summary: str,
        detail: Optional[dict] = None
    ):

        if not session_id:
            return


        with self._lock:

            if session_id not in self._sessions:
                self._sessions[session_id] = AgentSession(
                    session_id=session_id
                )


            self._sessions[session_id].events.append(
                SessionEvent(
                    timestamp=time.time(),
                    kind=kind,
                    summary=summary,
                    detail=detail or {}
                )
            )



    def update_environment(
        self,
        session_id: str,
        environment_id: str
    ):

        with self._lock:

            session = self._sessions.get(session_id)

            if session:
                session.environment_id = environment_id



    def add_file_change(
        self,
        session_id: str,
        file_path: str
    ):

        with self._lock:

            session = self._sessions.get(session_id)

            if session and file_path not in session.files_changed:
                session.files_changed.append(file_path)



    def add_command(
        self,
        session_id: str,
        command: str
    ):

        with self._lock:

            session = self._sessions.get(session_id)

            if session:
                session.commands_executed.append(command)



    def add_evidence(
        self,
        session_id: str,
        evidence_type: str,
        value: str
    ):

        with self._lock:

            session = self._sessions.get(session_id)

            if session:

                session.evidence.setdefault(
                    evidence_type,
                    []
                ).append(value)



    def complete_session(
        self,
        session_id: str,
        result: str
    ):

        with self._lock:

            session = self._sessions.get(session_id)

            if session:

                session.status = "completed"

                session.verification_result = result



    def get_session(
        self,
        session_id: str
    ) -> Optional[AgentSession]:

        with self._lock:
            return self._sessions.get(session_id)



    def get_events(
        self,
        session_id: str
    ) -> List[SessionEvent]:

        session = self.get_session(session_id)

        if not session:
            return []

        return list(session.events)



    def get_recent_context(
        self,
        session_id: str,
        limit: int = 10
    ) -> str:

        events = self.get_events(session_id)[-limit:]

        if not events:
            return ""


        lines = [
            f"- ({event.kind}) {event.summary}"
            for event in events
        ]


        return (
            "Previous agent actions in this session:\n"
            + "\n".join(lines)
        )



    def clear(
        self,
        session_id: str
    ):

        with self._lock:
            self._sessions.pop(session_id, None)



    def session_count(self):

        with self._lock:
            return len(self._sessions)