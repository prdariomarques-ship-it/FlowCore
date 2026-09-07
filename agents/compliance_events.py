"""FlowCore Compliance Domain Events and Event Bus.
Implements event-driven architecture with correlation tracking, idempotency,
and standard payloads for portfolio lifecycle transitions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Callable, Dict, List


class EventType:
    PORTFOLIO_CHANGED = "PORTFOLIO_CHANGED"
    POSITION_CHANGED = "POSITION_CHANGED"
    ALLOCATION_CHANGED = "ALLOCATION_CHANGED"
    COMPLIANCE_ALERT_CREATED = "COMPLIANCE_ALERT_CREATED"
    COMPLIANCE_ALERT_UPDATED = "COMPLIANCE_ALERT_UPDATED"
    REBALANCING_REQUIRED = "REBALANCING_REQUIRED"
    REBALANCING_PROPOSED = "REBALANCING_PROPOSED"
    REBALANCING_APPROVED = "REBALANCING_APPROVED"
    REBALANCING_REJECTED = "REBALANCING_REJECTED"
    PORTFOLIO_REENQUADRED = "PORTFOLIO_REENQUADRED"


@dataclass
class FlowCoreEvent:
    event_type: str
    client_id: str
    portfolio_id: str
    source: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "client_id": self.client_id,
            "portfolio_id": self.portfolio_id,
            "source": self.source,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
        }


class EventBus:
    """In-memory Event Bus with idempotency tracking and async subscriber support."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._subscribers = {}
            cls._instance._processed_keys = set()
            cls._instance._audit_log = []
        return cls._instance

    def clear(self):
        self._subscribers = {}
        self._processed_keys = set()
        self._audit_log = []

    def subscribe(self, event_type: str, handler: Callable[[FlowCoreEvent], None]):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(self, event: FlowCoreEvent) -> List[Any]:
        if event.idempotency_key in self._processed_keys:
            return []  # Deduplicated

        self._processed_keys.add(event.idempotency_key)
        self._audit_log.append(event.to_dict())

        results = []
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                res = handler(event)
                results.append(res)
            except Exception as e:
                results.append({"error": str(e), "handler": getattr(handler, "__name__", str(handler))})
        return results

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)


event_bus = EventBus()
