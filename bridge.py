"""Pont local pour l'interface HTML (spec V1 §1).

Petit serveur WebSocket sur localhost : la page controle.html s'y connecte,
recoit l'etat en direct (~10 Hz) et envoie les changements de reglages,
appliques a chaud par la boucle principale. Aucun acces reseau exterieur :
le serveur n'ecoute que sur 127.0.0.1.
"""

import asyncio
import http.server
import json
import os
import threading

PORT = 8765
PORT_HTTP = 8766      # la page controle.html est servie par l'app elle-meme :
                      # elle correspond donc toujours a la version qui tourne


class Bridge:
    """publish(etat) cote app ; poll() rend les commandes recues (dicts)."""

    def __init__(self, port=PORT):
        self.port = port
        self.ok = False
        self.status = "Panneau web : demarrage..."
        self._lock = threading.Lock()
        self._state = {}
        self._cmds = []
        self._clients = set()
        self._started = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        threading.Thread(target=self._run_http, daemon=True).start()
        self._started.wait(3.0)

    # --- mini serveur HTTP : sert controle.html (version toujours a jour) ---
    def _run_http(self):
        dossier = os.path.dirname(os.path.abspath(__file__))

        class Page(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    with open(os.path.join(dossier, "controle.html"), "rb") as f:
                        corps = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(corps)))
                    self.end_headers()
                    self.wfile.write(corps)
                except Exception:
                    self.send_response(500)
                    self.end_headers()

            def log_message(self, *a):
                pass

        try:
            http.server.ThreadingHTTPServer(
                ("127.0.0.1", PORT_HTTP), Page).serve_forever()
        except Exception:
            pass                        # port pris : la page file:// marche aussi

    def publish(self, state):
        with self._lock:
            self._state = state

    def poll(self):
        with self._lock:
            cmds, self._cmds = self._cmds, []
        return cmds

    # --- serveur (thread + boucle asyncio dediee) ---
    def _run(self):
        try:
            import websockets
        except Exception as e:
            self.status = f"Panneau web indisponible ({type(e).__name__})"
            self._started.set()
            return

        async def handler(ws):
            self._clients.add(ws)
            try:
                async for msg in ws:
                    try:
                        cmd = json.loads(msg)
                    except ValueError:
                        continue
                    if isinstance(cmd, dict):
                        with self._lock:
                            self._cmds.append(cmd)
            finally:
                self._clients.discard(ws)

        async def broadcaster():
            while True:
                await asyncio.sleep(0.1)
                if not self._clients:
                    continue
                with self._lock:
                    payload = json.dumps(self._state, ensure_ascii=False)
                for ws in list(self._clients):
                    try:
                        await ws.send(payload)
                    except Exception:
                        self._clients.discard(ws)

        async def serve():
            async with websockets.serve(handler, "127.0.0.1", self.port):
                self.ok = True
                self.status = (f"Panneau web : http://localhost:{PORT_HTTP} "
                               f"(double-clic sur panneau.bat)")
                self._started.set()
                await broadcaster()

        try:
            asyncio.run(serve())
        except Exception as e:
            self.ok = False
            self.status = f"Panneau web indisponible ({type(e).__name__}: {e})"
            self._started.set()
