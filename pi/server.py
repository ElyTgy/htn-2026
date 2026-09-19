"""Serves the caption page and streams face data to it.

  /                 the page (web/)
  /ws               WebSocket: one JSON "frame" message per processed camera frame (rate limited)
  /config           small JSON blob the page reads at startup
  /stt-token        short-lived credential for the chosen transcription provider (keys stay in .env)
  /video            MJPEG debug feed of what the camera sees
"""
import asyncio
import json
import os
import socket
import ssl
import threading

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from config import CERT_DIR, ROOT, WEB_DIR


@web.middleware
async def no_cache(request, handler):
    # The page is edited often during setup; never let a browser run a stale copy of it.
    resp = await handler(request)
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


class CaptionServer:
    def __init__(self, cfg, backend, backend_name):
        self.cfg = cfg
        self.backend = backend
        self.backend_name = backend_name
        self.clients: set[web.WebSocketResponse] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.app = web.Application(middlewares=[no_cache])
        self.app.add_routes([
            web.get("/", self.index),
            web.get("/ws", self.ws),
            web.get("/config", self.config),
            web.get("/stt-token", self.stt_token),
            web.get("/video", self.video),
            web.post("/log", self.log),
            web.static("/", WEB_DIR),
        ])
        self.app.on_startup.append(self._on_startup)

    async def _on_startup(self, app):
        self.loop = asyncio.get_running_loop()

    # Called from the vision thread.
    def publish(self, message: dict):
        if self.loop is None or not self.clients:
            return
        data = json.dumps(message, separators=(",", ":"))
        self.loop.call_soon_threadsafe(self._broadcast, data)

    def _broadcast(self, data: str):
        for ws in list(self.clients):
            if ws.closed:
                self.clients.discard(ws)
            else:
                asyncio.ensure_future(self._send(ws, data))

    async def _send(self, ws, data):
        try:
            await ws.send_str(data)
        except (ConnectionError, RuntimeError):
            self.clients.discard(ws)

    async def index(self, request):
        return web.FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})

    async def ws(self, request):
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            self.clients.discard(ws)
        return ws

    async def config(self, request):
        return web.json_response({
            "backend": self.backend_name,
            "defaultStt": self.cfg.default_stt,
            "hasVideo": self.backend.latest_frame() is not None or self.backend_name != "fake",
            "aspect": self.cfg.width / self.cfg.height,
        })

    async def stt_token(self, request):
        provider = request.query.get("provider", self.cfg.default_stt)
        handler = TOKEN_HANDLERS.get(provider)
        if handler is None:
            return web.json_response({"error": f"no token handler for provider '{provider}'"}, status=404)
        try:
            return web.json_response(await handler(request.query))
        except TokenError as e:
            return web.json_response({"error": str(e)}, status=500)

    async def log(self, request):
        # The page reports its status and errors here, so they show up in this terminal.
        # On the Beam Pro there is no easy way to see the browser console otherwise.
        text = (await request.text())[:500].replace("\n", " ")
        print(f"\n[page] {text}")
        return web.Response(status=204)

    async def video(self, request):
        import cv2  # only needed for the debug feed

        resp = web.StreamResponse(headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store",
        })
        await resp.prepare(request)
        try:
            while True:
                frame = self.backend.latest_frame()
                if frame is not None:
                    small = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
                    ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                                           [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if ok:
                        await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
                await asyncio.sleep(1 / 15)
        except (ConnectionError, asyncio.CancelledError):
            pass
        return resp

    def start_in_thread(self, https: bool):
        """Run the web server on its own thread and event loop; returns once it is listening.

        Plain http is always served on cfg.port. If certs/ exists (scripts/make_cert.sh), https is
        served as well on cfg.https_port: browsers only allow the microphone on https or localhost.
        """
        cert, key = CERT_DIR / "cert.pem", CERT_DIR / "key.pem"
        ssl_ctx = None
        if cert.exists() and key.exists():
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(cert, key)
        elif https:
            raise SystemExit("no certificate found; run scripts/make_cert.sh first")

        ready = threading.Event()
        failure = []

        async def serve():
            runner = web.AppRunner(self.app)
            await runner.setup()
            try:
                await web.TCPSite(runner, self.cfg.host, self.cfg.port).start()
                if ssl_ctx:
                    await web.TCPSite(runner, self.cfg.host, self.cfg.https_port, ssl_context=ssl_ctx).start()
            except OSError as e:
                failure.append(e)
                ready.set()
                return
            ready.set()
            await asyncio.Event().wait()  # serve until the process exits

        threading.Thread(target=lambda: asyncio.run(serve()), daemon=True).start()
        ready.wait()
        if failure:
            raise SystemExit(f"could not start the web server: {failure[0]}")
        name = socket.gethostname().removesuffix(".local")
        print(f"caption page (this machine): http://localhost:{self.cfg.port}/")
        if ssl_ctx:
            print(f"caption page (other devices, mic works): https://{name}.local:{self.cfg.https_port}/")
        else:
            print(f"caption page (other devices): http://{name}.local:{self.cfg.port}/  "
                  "(no mic there until you run scripts/make_cert.sh and restart)")


# ---- transcription provider credentials -------------------------------------------------
# One handler per provider. Each returns whatever its matching web/stt/<provider>.js expects.
# To add a provider: write a handler, register it below, add web/stt/<name>.js.

class TokenError(Exception):
    pass


async def deepgram_token(query):
    load_dotenv(ROOT / ".env", override=True)  # re-read so a key added while running is picked up
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key:
        raise TokenError("DEEPGRAM_API_KEY is not set (copy .env.example to .env and fill it in)")
    if query.get("scheme") == "token":  # the page asks for this if a short-lived token was refused
        print("warning: sending the Deepgram API key to the page (short-lived token was refused)")
        return {"scheme": "token", "credential": key}
    # Prefer a 30-second token so the real key never reaches the browser.
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.post("https://api.deepgram.com/v1/auth/grant",
                              headers={"Authorization": f"Token {key}"}) as r:
                if r.status == 200:
                    body = await r.json()
                    return {"scheme": "bearer", "credential": body["access_token"]}
                detail = await r.text()
    except aiohttp.ClientError as e:
        raise TokenError(f"could not reach Deepgram: {e}")
    # Keys without Member permission can't mint tokens. Fall back to the key itself:
    # fine on a private hotspot for a demo, not for anything public.
    print(f"warning: Deepgram token grant failed ({detail[:120]}); sending the API key to the page instead")
    return {"scheme": "token", "credential": key}


TOKEN_HANDLERS = {
    "deepgram": deepgram_token,
}
