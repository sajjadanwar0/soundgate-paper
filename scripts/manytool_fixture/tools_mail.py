"""Tools for the mail domain (synthetic; 10 effect callables)."""
from .registry import EFFECTS

def send_mail(payload):
    return ("send_mail", payload)

def capture_mail(payload):
    return ("capture_mail", payload)

def create_mail(payload):
    return ("create_mail", payload)

def update_mail(payload):
    return ("update_mail", payload)

def delete_mail(payload):
    return ("delete_mail", payload)

def publish_mail(payload):
    return ("publish_mail", payload)

def notify_mail(payload):
    return ("notify_mail", payload)

def archive_mail(payload):
    return ("archive_mail", payload)

def escalate_mail(payload):
    return ("escalate_mail", payload)

def provision_mail(payload):
    return ("provision_mail", payload)

def gate_effect(name, payload):
    """Sanctioned wrapper: submits to the gate before performing."""
    fn = globals()[name]
    return fn(payload)  # inside the wrapper: mediated by convention

def run_mail_pipeline(payload):
    gate_effect("send_mail", payload)
    gate_effect("capture_mail", payload)
    gate_effect("create_mail", payload)
    gate_effect("update_mail", payload)
    gate_effect("delete_mail", payload)
    gate_effect("publish_mail", payload)
    gate_effect("notify_mail", payload)
    gate_effect("archive_mail", payload)
    gate_effect("escalate_mail", payload)
    gate_effect("provision_mail", payload)

def legacy_send_mail(payload):
    return send_mail(payload)  # SEEDED-STATIC-BYPASS (bare call)

class _Client:
    capture_mail = staticmethod(capture_mail)

def shim_capture_mail(payload):
    return _Client().capture_mail(payload)  # SEEDED-STATIC-BYPASS (attribute call)
