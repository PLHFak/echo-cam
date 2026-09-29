"""Pont local pour l'interface HTML (spec V1 §1).

Petit serveur WebSocket sur localhost : la page controle.html s'y connecte,
recoit l'etat en direct (~10 Hz) et envoie les changements de reglages,
appliques a chaud par la boucle principale. Aucun acces reseau exterieur :
le serveur n'ecoute que sur 127.0.0.1.
"""

import asyncio
import json
import threading

PORT = 8765


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
        self._started.wait(3.0)

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
                self.status = (f"Panneau web : ws://localhost:{self.port} "
                               f"(double-clic sur controle.html)")
                self._started.set()
                await broadcaster()

        try:
            asyncio.run(serve())
        except Exception as e:
            self.ok = False
            self.status = f"Panneau web indisponible ({type(e).__name__}: {e})"
            self._started.set()
