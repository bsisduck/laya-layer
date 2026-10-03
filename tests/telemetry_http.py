"""Repository-native ephemeral HTTP lab; binds only a dynamically allocated loopback port."""

import socket
from contextlib import contextmanager
from threading import Event, Thread

import uvicorn


@contextmanager
def live_server(app, *, port=0):
    ready = Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets)
            ready.set()

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = Server(
        uvicorn.Config(app, access_log=False, log_level="critical", timeout_graceful_shutdown=1)
    )
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        assert ready.wait(10), "Local HTTP lab failed to start"
        yield origin
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive(), "Local HTTP lab failed to stop"
