"""Site door: HTTP/WebSocket contract, validation, routing and static web assets."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, catalog_entry, load_configs
from .domain import MissionRequest, PlatformError
from .service import MissionManager


def create_app(manager: MissionManager | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        bridge = None
        if manager is None:
            # Lazy import keeps contract tests independent of a running ROS system.
            from .ros_adapter import RosBridge
            configs = load_configs()
            bridge = RosBridge(configs)
            app.state.manager = MissionManager(configs, bridge.adapters)
        else:
            app.state.manager = manager
        yield
        await app.state.manager.close()
        if bridge:
            bridge.close()

    app = FastAPI(title="IAC Robot Platform", version="1.0.0", lifespan=lifespan,
                  description="One mission API across official ROS 2 stacks. Local mock hardware demonstration.")

    @app.exception_handler(PlatformError)
    async def platform_error(_, error):
        return JSONResponse(status_code=error.status, content={"detail": error.detail})

    @app.get("/api/robots")
    async def robots():
        return {"robots": [catalog_entry(c) for c in app.state.manager.configs.values()]}

    @app.get("/api/state")
    async def state():
        return app.state.manager.snapshot()

    @app.get("/api/health")
    async def health():
        states = app.state.manager.snapshot()["robots"]
        ready = all(s["connected"] for s in states)
        return {"status": "ready" if ready else "degraded", "mode": "mock_hardware", "ros_connected": ready}

    @app.post("/api/missions", status_code=202)
    async def submit(request: MissionRequest):
        return app.state.manager.submit(request)

    @app.post("/api/robots/{robot}/stop")
    async def stop(robot: str):
        return app.state.manager.stop(robot)

    @app.websocket("/api/events")
    async def events(socket: WebSocket):
        # Local demonstration: refuse cross-origin browser connections; no authentication claim.
        origin = socket.headers.get("origin")
        allowed = {f"http://localhost:{port}" for port in (8000, 5173)} | {f"http://127.0.0.1:{port}" for port in (8000, 5173)}
        if origin and origin not in allowed:
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            while True:
                await socket.send_json({"type": "snapshot", **app.state.manager.snapshot()})
                # Receive also notices disconnects when no more snapshots can be sent.
                try:
                    await asyncio.wait_for(socket.receive_text(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass

    app.mount("/assets", StaticFiles(directory=str(ROOT / "assets"), check_dir=False), name="assets")
    if (ROOT / "frontend" / "dist").exists():
        app.mount("/", StaticFiles(directory=str(ROOT / "frontend" / "dist"), html=True), name="web")
    return app


app = create_app()
