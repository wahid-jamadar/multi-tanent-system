"""Event queue abstraction.

JSON persistence is the compatibility implementation. Production deployments
should replace this boundary with Redis Streams, Kafka, or another durable
ordered event log.
"""


class InMemoryEventQueue:
    def __init__(self):
        self._events = []

    def publish(self, event):
        self._events.append(event)

    def drain(self):
        events = list(self._events)
        self._events.clear()
        return events

