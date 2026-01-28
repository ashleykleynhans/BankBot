"""Session management for WebSocket chat connections."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ..chat import ChatInterface
from ..database import Database
from ..llm_backend import LLMBackend


@dataclass
class ChatSession:
    """Represents a single WebSocket chat session."""

    session_id: str
    chat_interface: ChatInterface
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


class SessionManager:
    """Manages chat sessions for WebSocket connections."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def create_session(
        self, db: Database, backend: LLMBackend
    ) -> ChatSession:
        """Create a new chat session with its own ChatInterface."""
        session_id = str(uuid.uuid4())
        chat_interface = ChatInterface(db=db, backend=backend)
        session = ChatSession(session_id=session_id, chat_interface=chat_interface)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """Remove a session when WebSocket disconnects."""
        self._sessions.pop(session_id, None)

    def cleanup_stale_sessions(self, max_age_minutes: int = 60) -> int:
        """Remove sessions inactive for longer than max_age_minutes.

        Returns:
            Number of sessions removed.
        """
        now = datetime.now()
        stale = [
            sid
            for sid, session in self._sessions.items()
            if (now - session.last_activity).total_seconds() > max_age_minutes * 60
        ]
        for sid in stale:
            self._sessions.pop(sid, None)
        return len(stale)

    @property
    def active_sessions(self) -> int:
        """Return count of active sessions."""
        return len(self._sessions)


# Global session manager instance
session_manager = SessionManager()
