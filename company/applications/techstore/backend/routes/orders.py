
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models import User, Product, Order, OrderItem
from schemas.orders import OrderCreate

logger = logging.getLogger("techstore")

router = APIRouter(
    prefix="/api/orders",
    tags=["orders"]
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db)
):
    try:
        # Check that the customer exists.
        user = db.query(User).filter(
            User.id == order_data.user_id
        ).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Combine duplicate product entries.
        quantities = defaultdict(int)

        for item in order_data.items:
            quantities[item.product_id] += item.quantity

        # Lock the requested product records.
        products = db.scalars(
            select(Product)
            .where(Product.id.in_(list(quantities.keys())))
            .with_for_update()
        ).all()

        product_lookup = {
            product.id: product for product in products
        }

        # Confirm all products exist.
        for product_id in quantities:
            if product_id not in product_lookup:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product {product_id} not found"
                )

        # Check stock and calculate the order total.
        order_total = 0

        for product_id, quantity in quantities.items():
            product = product_lookup[product_id]

            if product.stock < quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {product.name}"
                )

            order_total += product.price * quantity

        # Create the order.
        new_order = Order(
            user_id=user.id,
            total=order_total,
            status="pending"
        )

        db.add(new_order)
        db.flush()

        # Create order items and update inventory.
        for product_id, quantity in quantities.items():
            product = product_lookup[product_id]

            new_item = OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price
            )

            product.stock -= quantity
            db.add(new_item)

        db.commit()
        db.refresh(new_order)

        logger.info(
            "Order placed: order_id=%s user_id=%s total=%s",
            new_order.id,
            user.id,
            new_order.total
        )

        return {
            "message": "Order placed successfully",
            "order_id": new_order.id,
            "user_id": new_order.user_id,
            "total": str(new_order.total),
            "status": new_order.status
        }

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating order")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create order"
        )


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    items = db.query(OrderItem).filter(
        OrderItem.order_id == order_id
    ).all()

    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "total": str(order.total),
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price)
            }
            for item in items
        ]
    }
