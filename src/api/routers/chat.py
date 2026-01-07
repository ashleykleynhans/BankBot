"""WebSocket endpoint for real-time chat."""

import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..session import session_manager

router = APIRouter()


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket endpoint for chat conversations.

    Each connection gets its own ChatInterface with separate conversation history.

    Message Protocol:
        Client -> Server:
            {"type": "chat", "payload": {"message": "..."}}
            {"type": "ping"}

        Server -> Client:
            {"type": "connected", "payload": {"session_id": "...", "stats": {...}}}
            {"type": "chat_response", "payload": {"message": "...", "transactions": [...], "timestamp": "..."}}
            {"type": "error", "payload": {"code": "...", "message": "..."}}
            {"type": "pong"}
    """
    await websocket.accept()

    # Get shared resources from app state
    app = websocket.app
    config = app.state.config
    db = app.state.db

    # Create session for this connection
    session = session_manager.create_session(
        db=db,
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"],
    )

    try:
        # Send connection acknowledgment with stats
        stats = db.get_stats()
        await websocket.send_json(
            {
                "type": "connected",
                "payload": {
                    "session_id": session.session_id,
                    "stats": stats,
                },
            }
        )

        # Message loop
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "INVALID_JSON",
                            "message": "Invalid JSON message",
                        },
                    }
                )
                continue

            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "chat":
                payload = message.get("payload", {})
                query = payload.get("message", "").strip()

                if not query:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "payload": {
                                "code": "EMPTY_MESSAGE",
                                "message": "Message cannot be empty",
                            },
                        }
                    )
                    continue

                session.touch()

                try:
                    # Use the ChatInterface's ask method
                    response_text = session.chat_interface.ask(query)

                    # Get relevant transactions from the last query
                    transactions = session.chat_interface._last_transactions[:10]

                    await websocket.send_json(
                        {
                            "type": "chat_response",
                            "payload": {
                                "message": response_text,
                                "transactions": transactions,
                                "timestamp": datetime.now().isoformat(),
                            },
                        }
                    )
                except Exception as e:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "payload": {
                                "code": "CHAT_ERROR",
                                "message": str(e),
                            },
                        }
                    )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "UNKNOWN_TYPE",
                            "message": f"Unknown message type: {msg_type}",
                        },
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        session_manager.remove_session(session.session_id)
