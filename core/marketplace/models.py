from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    Enum,
    Boolean,
    Text,               # ← Use Text instead of JSON for full SQLite compatibility
    text,
)
from sqlalchemy.orm import relationship
from core.database import Base
from core.auth.models import User
import enum
from datetime import datetime
import json
# Correct place for SelectField
from wtforms import StringField, TextAreaField, FloatField, IntegerField, SelectField, FileField, SubmitField


# ------------------- Enums -------------------
class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentMethod(enum.Enum):
    STRIPE = "stripe"
    CRYPTO = "crypto"
    MPESA = "mpesa"


class DeliveryStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# ------------------- Buyer -------------------
class Buyer(Base):
    __tablename__ = 'buyers'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(80), ForeignKey('users.username'), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    stripe_customer_id = Column(String(100), unique=True)

    # JSON stored as Text → 100% SQLite compatible
    solved_challenges = Column(Text, nullable=False, default='[]', server_default=text("'[]'"))
    is_verified = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="buyer_profile")
    payments = relationship("Payment", back_populates="buyer")

    # ---------------- Methods ----------------
    def has_valid_payment_method(self):
        return bool(self.stripe_customer_id)

    def can_view_products(self):
        return self.is_verified >= 3

    def get_solved_challenges(self):
        if not self.solved_challenges:
            return []
        try:
            return json.loads(self.solved_challenges)
        except json.JSONDecodeError:
            return []

    def add_solved_challenge(self, challenge_id):
        solved = self.get_solved_challenges()
        if challenge_id not in solved:
            solved.append(challenge_id)
            self.solved_challenges = json.dumps(solved)
            self.is_verified = len(solved)


# ------------------- Seller -------------------
class Seller(Base):
    __tablename__ = 'sellers'

    id = Column(Integer, primary_key=True)
    user_id = Column(String(80), ForeignKey('users.username'), nullable=False, unique=True)
    business_name = Column(String(100), nullable=False)
    description = Column(String(500))

    # Same pattern — Text + JSON string
    solved_challenges = Column(Text, nullable=False, default='[]', server_default=text("'[]'"))
    is_verified = Column(Integer, default=0, nullable=False)
    hard_challenges_completed = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="seller_profile")
    products = relationship("Product", back_populates="seller", cascade="all, delete-orphan")

    # ---------------- Methods ----------------
    def can_sell(self):
        return self.is_verified >= 5

    def get_solved_challenges(self):
        if not self.solved_challenges:
            return []
        try:
            return json.loads(self.solved_challenges)
        except json.JSONDecodeError:
            return []

    def add_solved_challenge(self, challenge_id, is_hard=False):
        solved = self.get_solved_challenges()
        if challenge_id not in solved:
            solved.append(challenge_id)
            self.solved_challenges = json.dumps(solved)
            self.is_verified = len(solved)
            if is_hard:
                self.hard_challenges_completed += 1


# ------------------- Product -------------------
class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey('sellers.id'), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(String(2000))
    price = Column(Float, nullable=False)
    image_path = Column(String(500))
    stock = Column(Integer, default=0, nullable=False)
    
    # ←←← ONLY THIS LINE BELONGS HERE
    category = Column(String(100), nullable=False, default='Other')

    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False, server_default=text('true'))

    # Relationships
    seller = relationship("Seller", back_populates="products")
    payments = relationship("Payment", back_populates="product")


# ------------------- Payment -------------------
class Payment(Base):
    __tablename__ = 'payments'

    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey('buyers.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(Enum(PaymentMethod))
    transaction_id = Column(String(200))
    checkout_request_id = Column(String(200))  # For M-Pesa STK Push tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    buyer = relationship("Buyer", back_populates="payments")
    product = relationship("Product", back_populates="payments")
    order = relationship("Order", back_populates="payment", uselist=False)


# ------------------- Order -------------------
class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey('buyers.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    payment_id = Column(Integer, ForeignKey('payments.id'), nullable=True)
    
    # Order details
    quantity = Column(Integer, default=1, nullable=False)
    total_amount = Column(Float, nullable=False)
    
    # Delivery info
    delivery_status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING)
    delivery_address = Column(Text, nullable=True)
    phone_number = Column(String(20), nullable=False)
    
    # M-Pesa specific
    mpesa_receipt_number = Column(String(50), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)
    
    # Relationships
    buyer = relationship("Buyer", backref="orders")
    product = relationship("Product", backref="orders")
    payment = relationship("Payment", back_populates="order")