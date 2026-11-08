"""Orders and the activation tracker."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..orders import service
from ..privacy import audit

router = APIRouter(tags=["orders"])


class OrderIn(BaseModel):
    session_id: str
    items: dict[str, int] | None = Field(None, description="optional edited bundle {product_id: qty}; defaults to the session's recommendation")


@router.post("/orders", status_code=201)
def place_order(body: OrderIn) -> dict:
    """Create the order from the session's (engine-validated) bundle. Needs a PASS KYC on the session."""
    try:
        order = service.create(body.session_id, body.items)
    except service.OrderError as e:
        raise HTTPException(e.status_code, e.detail) from None
    audit.log("owner", "order.placed", f"{body.session_id} {order['order_id']}")
    return order


@router.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = service.get(order_id)
    if not order:
        raise HTTPException(404, "unknown order")
    return order


@router.post("/orders/{order_id}/advance")
def advance_order(order_id: str) -> dict:
    """Demo helper: move the order to its next stage."""
    order = service.advance(order_id)
    if not order:
        raise HTTPException(404, "unknown order")
    audit.log("system", "order.advanced", f"{order_id} -> {order['status']}")
    return order


@router.get("/sessions/{session_id}/order")
def session_order(session_id: str) -> dict:
    order = service.for_session(session_id)
    if not order:
        raise HTTPException(404, "no order for this session")
    return order
