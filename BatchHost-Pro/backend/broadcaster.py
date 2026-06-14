"""WebSocket broadcaster abstraction used by server.py."""


class SocketBroadcaster:
    def __init__(self, socketio, logger):
        self.socketio = socketio
        self.logger = logger

    def emit(self, event, payload):
        self.logger.info("WEBSOCKET emit event=%s payload=%s", event, payload)
        self.socketio.emit(event, payload)

