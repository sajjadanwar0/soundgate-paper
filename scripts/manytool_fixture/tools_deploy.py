"""Tools for the deployment domain (synthetic; 10 effect callables)."""
from .registry import EFFECTS

def send_deploy(payload):
    return ("send_deploy", payload)

def capture_deploy(payload):
    return ("capture_deploy", payload)

def create_deploy(payload):
    return ("create_deploy", payload)

def update_deploy(payload):
    return ("update_deploy", payload)

def delete_deploy(payload):
    return ("delete_deploy", payload)

def publish_deploy(payload):
    return ("publish_deploy", payload)

def notify_deploy(payload):
    return ("notify_deploy", payload)

def archive_deploy(payload):
    return ("archive_deploy", payload)

def escalate_deploy(payload):
    return ("escalate_deploy", payload)

def provision_deploy(payload):
    return ("provision_deploy", payload)

def gate_effect(name, payload):
    """Sanctioned wrapper: submits to the gate before performing."""
    fn = globals()[name]
    return fn(payload)  # inside the wrapper: mediated by convention

def run_deploy_pipeline(payload):
    gate_effect("send_deploy", payload)
    gate_effect("capture_deploy", payload)
    gate_effect("create_deploy", payload)
    gate_effect("update_deploy", payload)
    gate_effect("delete_deploy", payload)
    gate_effect("publish_deploy", payload)
    gate_effect("notify_deploy", payload)
    gate_effect("archive_deploy", payload)
    gate_effect("escalate_deploy", payload)
    gate_effect("provision_deploy", payload)

def legacy_update_deploy(payload):
    return update_deploy(payload)  # SEEDED-STATIC-BYPASS (bare call)

class _Client:
    provision_deploy = staticmethod(provision_deploy)

def shim_provision_deploy(payload):
    return _Client().provision_deploy(payload)  # SEEDED-STATIC-BYPASS (attribute call)

import sys as _sys
def dyn_getattr_deploy(payload):
    fn = getattr(_sys.modules[__name__], 'archive_deploy')
    return fn(payload)  # SEEDED-DYNAMIC-BYPASS (getattr)
