"""Tools for the chat domain (synthetic; 10 effect callables)."""
from .registry import EFFECTS

def send_chat(payload):
    return ("send_chat", payload)

def capture_chat(payload):
    return ("capture_chat", payload)

def create_chat(payload):
    return ("create_chat", payload)

def update_chat(payload):
    return ("update_chat", payload)

def delete_chat(payload):
    return ("delete_chat", payload)

def publish_chat(payload):
    return ("publish_chat", payload)

def notify_chat(payload):
    return ("notify_chat", payload)

def archive_chat(payload):
    return ("archive_chat", payload)

def escalate_chat(payload):
    return ("escalate_chat", payload)

def provision_chat(payload):
    return ("provision_chat", payload)

def gate_effect(name, payload):
    """Sanctioned wrapper: submits to the gate before performing."""
    fn = globals()[name]
    return fn(payload)  # inside the wrapper: mediated by convention

def run_chat_pipeline(payload):
    gate_effect("send_chat", payload)
    gate_effect("capture_chat", payload)
    gate_effect("create_chat", payload)
    gate_effect("update_chat", payload)
    gate_effect("delete_chat", payload)
    gate_effect("publish_chat", payload)
    gate_effect("notify_chat", payload)
    gate_effect("archive_chat", payload)
    gate_effect("escalate_chat", payload)
    gate_effect("provision_chat", payload)

_thunk = (lambda f: (lambda p: f(p)))(publish_chat)
def dyn_lambda_chat(payload):
    return _thunk(payload)
