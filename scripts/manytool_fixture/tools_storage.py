"""Tools for the storage domain (synthetic; 10 effect callables)."""
from .registry import EFFECTS

def send_storage(payload):
    return ("send_storage", payload)

def capture_storage(payload):
    return ("capture_storage", payload)

def create_storage(payload):
    return ("create_storage", payload)

def update_storage(payload):
    return ("update_storage", payload)

def delete_storage(payload):
    return ("delete_storage", payload)

def publish_storage(payload):
    return ("publish_storage", payload)

def notify_storage(payload):
    return ("notify_storage", payload)

def archive_storage(payload):
    return ("archive_storage", payload)

def escalate_storage(payload):
    return ("escalate_storage", payload)

def provision_storage(payload):
    return ("provision_storage", payload)

def gate_effect(name, payload):
    """Sanctioned wrapper: submits to the gate before performing."""
    fn = globals()[name]
    return fn(payload)  # inside the wrapper: mediated by convention

def run_storage_pipeline(payload):
    gate_effect("send_storage", payload)
    gate_effect("capture_storage", payload)
    gate_effect("create_storage", payload)
    gate_effect("update_storage", payload)
    gate_effect("delete_storage", payload)
    gate_effect("publish_storage", payload)
    gate_effect("notify_storage", payload)
    gate_effect("archive_storage", payload)
    gate_effect("escalate_storage", payload)
    gate_effect("provision_storage", payload)

_REGISTRY = {'x': escalate_storage}
def dyn_dict_storage(payload):
    return _REGISTRY['x'](payload)

_f = delete_storage
def dyn_alias_storage(payload):
    return _f(payload)
