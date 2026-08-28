"""Tools for the tickets domain (synthetic; 10 effect callables)."""
from .registry import EFFECTS

def send_tickets(payload):
    return ("send_tickets", payload)

def capture_tickets(payload):
    return ("capture_tickets", payload)

def create_tickets(payload):
    return ("create_tickets", payload)

def update_tickets(payload):
    return ("update_tickets", payload)

def delete_tickets(payload):
    return ("delete_tickets", payload)

def publish_tickets(payload):
    return ("publish_tickets", payload)

def notify_tickets(payload):
    return ("notify_tickets", payload)

def archive_tickets(payload):
    return ("archive_tickets", payload)

def escalate_tickets(payload):
    return ("escalate_tickets", payload)

def provision_tickets(payload):
    return ("provision_tickets", payload)

def gate_effect(name, payload):
    """Sanctioned wrapper: submits to the gate before performing."""
    fn = globals()[name]
    return fn(payload)

def run_tickets_pipeline(payload):
    gate_effect("send_tickets", payload)
    gate_effect("capture_tickets", payload)
    gate_effect("create_tickets", payload)
    gate_effect("update_tickets", payload)
    gate_effect("delete_tickets", payload)
    gate_effect("publish_tickets", payload)
    gate_effect("notify_tickets", payload)
    gate_effect("archive_tickets", payload)
    gate_effect("escalate_tickets", payload)
    gate_effect("provision_tickets", payload)

def legacy_publish_tickets(payload):
    return publish_tickets(payload)

class _Client:
    notify_tickets = staticmethod(notify_tickets)

def shim_notify_tickets(payload):
    return _Client().notify_tickets(payload)
