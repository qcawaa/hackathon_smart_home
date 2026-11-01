from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bootstrap import wiring

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    queue = wiring.bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        wiring.bus.unsubscribe(queue)