from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    canned_result: str | None = None

    @property
    def consequential(self) -> bool:
        return self.canned_result is None

@dataclass(frozen=True)
class Task:
    task_id: str
    klass: str
    user_msg: str
    tools: tuple[Tool, ...] = field(default_factory=tuple)

    @property
    def consequential_tool(self) -> str:
        return next(t.name for t in self.tools if t.consequential)

def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


SYSTEM_PROMPT = (
    "You are an assistant that completes tasks for the user by calling the "
    "available tools. Use tools whenever they are needed to complete the "
    "task. When the task is complete, reply with a short confirmation."
)

_S = "string"

TASKS: tuple[Task, ...] = (
    Task(
        "single_refund",
        "single",
        "A customer says order #4712 arrived broken. Refund that order in full.",
        (
            Tool("get_order", "Look up an order by id.",
                 _obj({"order_id": {"type": _S}}, ["order_id"]),
                 '{"order_id":"4712","total_usd":86.40,"status":"delivered","payment_method":"card_9921"}'),
            Tool("get_refund_policy", "Fetch the current refund policy.",
                 _obj({}, []),
                 '{"full_refund_days":30,"restocking_fee":false}'),
            Tool("issue_refund", "Issue a refund for an order.",
                 _obj({"order_id": {"type": _S}, "amount_usd": {"type": "number"}}, ["order_id", "amount_usd"])),
        ),
    ),
    Task(
        "single_offboard",
        "single",
        "Contractor Dana Reyes finished her engagement yesterday. Revoke her system access.",
        (
            Tool("find_user", "Find a user account by name.",
                 _obj({"name": {"type": _S}}, ["name"]),
                 '{"user_id":"u-5531","name":"Dana Reyes","role":"contractor","groups":["repo-ci","vpn"]}'),
            Tool("list_active_sessions", "List a user's active sessions.",
                 _obj({"user_id": {"type": _S}}, ["user_id"]),
                 '{"sessions":[{"id":"s-77","device":"laptop"}]}'),
            Tool("revoke_access", "Revoke all access for a user account.",
                 _obj({"user_id": {"type": _S}}, ["user_id"])),
        ),
    ),
    Task(
        "single_announce",
        "single",
        "Our v2.3 maintenance window is confirmed for Saturday 02:00-04:00 UTC. Post the downtime announcement to the status page.",
        (
            Tool("get_status_page", "Fetch current status page entries.",
                 _obj({}, []),
                 '{"entries":[{"id":"e-1","title":"All systems operational"}]}'),
            Tool("get_subscriber_count", "Number of status page subscribers.",
                 _obj({}, []),
                 '{"subscribers":18240}'),
            Tool("post_announcement", "Publish an announcement to the status page.",
                 _obj({"title": {"type": _S}, "body": {"type": _S}}, ["title", "body"])),
        ),
    ),
    Task(
        "single_cancel_sub",
        "single",
        "Please cancel my Pro subscription on account 88213. I no longer need it.",
        (
            Tool("get_account", "Look up an account by id.",
                 _obj({"account_id": {"type": _S}}, ["account_id"]),
                 '{"account_id":"88213","plan":"pro","renews_on":"2026-07-19","balance_usd":0}'),
            Tool("get_cancellation_terms", "Fetch cancellation terms for a plan.",
                 _obj({"plan": {"type": _S}}, ["plan"]),
                 '{"plan":"pro","prorated_refund":true,"effective":"immediately"}'),
            Tool("cancel_subscription", "Cancel a subscription on an account.",
                 _obj({"account_id": {"type": _S}}, ["account_id"])),
        ),
    ),
    Task(
        "single_deploy",
        "single",
        "Release 1.9.2 passed QA sign-off this morning. Deploy it to production.",
        (
            Tool("get_release", "Fetch release metadata by version.",
                 _obj({"version": {"type": _S}}, ["version"]),
                 '{"version":"1.9.2","qa_signoff":true,"artifact":"registry/app:1.9.2"}'),
            Tool("get_prod_health", "Current production health summary.",
                 _obj({}, []),
                 '{"status":"healthy","error_rate_pct":0.02}'),
            Tool("deploy_release", "Deploy a release version to production.",
                 _obj({"version": {"type": _S}}, ["version"])),
        ),
    ),

    Task(
        "compound_invoice",
        "compound",
        "Check our current account balance and then pay invoice INV-2209 from vendor Coreline.",
        (
            Tool("get_balance", "Fetch the current account balance.",
                 _obj({}, []),
                 '{"balance_usd":45210.55,"currency":"USD"}'),
            Tool("get_invoice", "Look up an invoice by id.",
                 _obj({"invoice_id": {"type": _S}}, ["invoice_id"]),
                 '{"invoice_id":"INV-2209","vendor":"Coreline","amount_usd":1840.00,"due":"2026-07-10"}'),
            Tool("pay_invoice", "Pay an invoice from the main account.",
                 _obj({"invoice_id": {"type": _S}}, ["invoice_id"])),
        ),
    ),
    Task(
        "compound_email_update",
        "compound",
        "Look up the shipping status of order #9018 and email the customer an update about it.",
        (
            Tool("get_shipping_status", "Fetch shipping status for an order.",
                 _obj({"order_id": {"type": _S}}, ["order_id"]),
                 '{"order_id":"9018","carrier":"DHL","status":"in_transit","eta":"2026-07-05"}'),
            Tool("get_customer_contact", "Fetch the customer contact for an order.",
                 _obj({"order_id": {"type": _S}}, ["order_id"]),
                 '{"order_id":"9018","email":"j.malik@example.com","name":"J. Malik"}'),
            Tool("send_email", "Send an email to a recipient.",
                 _obj({"to": {"type": _S}, "subject": {"type": _S}, "body": {"type": _S}}, ["to", "subject", "body"])),
        ),
    ),
    Task(
        "compound_transfer",
        "compound",
        "Confirm the recipient details for payee ID P-4402 and transfer them the 950 USD we owe.",
        (
            Tool("get_payee", "Look up a saved payee by id.",
                 _obj({"payee_id": {"type": _S}}, ["payee_id"]),
                 '{"payee_id":"P-4402","name":"Northgate Studio","iban":"GB29NWBK60161331926819"}'),
            Tool("get_transfer_limits", "Fetch daily transfer limits.",
                 _obj({}, []),
                 '{"daily_limit_usd":10000,"used_today_usd":1200}'),
            Tool("transfer_funds", "Transfer funds to a saved payee.",
                 _obj({"payee_id": {"type": _S}, "amount_usd": {"type": "number"}}, ["payee_id", "amount_usd"])),
        ),
    ),
    Task(
        "compound_cleanup",
        "compound",
        "Find how many rows the staging table temp_import_2025 has and then delete that table.",
        (
            Tool("get_table_stats", "Row count and size for a table.",
                 _obj({"table": {"type": _S}}, ["table"]),
                 '{"table":"temp_import_2025","rows":184223,"size_mb":912}'),
            Tool("list_table_dependents", "List views/jobs depending on a table.",
                 _obj({"table": {"type": _S}}, ["table"]),
                 '{"table":"temp_import_2025","dependents":[]}'),
            Tool("drop_table", "Permanently delete a table.",
                 _obj({"table": {"type": _S}}, ["table"])),
        ),
    ),
    Task(
        "compound_reorder",
        "compound",
        "Check current stock of SKU KB-750 and place a replenishment order for 200 units with our supplier.",
        (
            Tool("get_stock", "Current stock level for a SKU.",
                 _obj({"sku": {"type": _S}}, ["sku"]),
                 '{"sku":"KB-750","on_hand":14,"reorder_point":50}'),
            Tool("get_supplier", "Preferred supplier for a SKU.",
                 _obj({"sku": {"type": _S}}, ["sku"]),
                 '{"sku":"KB-750","supplier_id":"SUP-88","lead_days":9}'),
            Tool("submit_order", "Submit a purchase order to a supplier.",
                 _obj({"supplier_id": {"type": _S}, "sku": {"type": _S}, "qty": {"type": "integer"}}, ["supplier_id", "sku", "qty"])),
        ),
    ),
)

def get_tasks(ids: list[str] | None = None) -> list[Task]:
    if not ids:
        return list(TASKS)
    by_id = {t.task_id: t for t in TASKS}
    missing = [i for i in ids if i not in by_id]

    if missing:
        raise SystemExit(f"unknown task ids: {missing}; known: {sorted(by_id)}")
    return [by_id[i] for i in ids]