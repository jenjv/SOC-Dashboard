
from sqlalchemy import Column, Integer, String, Numeric, Text
from database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "techstore_app"}
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, default=0, nullable=False)
