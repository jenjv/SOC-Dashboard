from sqlalchemy import Column, Integer, ForeignKey, Numeric
from database import Base


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": "techstore_app"}

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("techstore_app.orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("techstore_app.products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
