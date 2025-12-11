from core.database import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, LargeBinary
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from datetime import datetime, timedelta
import secrets

class User(Base, UserMixin):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # Increased for scrypt hashes
    email = Column(String(120), unique=True, nullable=True)
    email_verified = Column(Boolean, default=False)
    email_token = Column(String(100), unique=True)
    email_token_expiry = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Password reset fields
    reset_token = Column(String(100))
    reset_token_expiry = Column(DateTime)
    
    # WebAuthn/Biometric login fields
    webauthn_credential_id = Column(String(255), nullable=True)
    webauthn_public_key = Column(LargeBinary, nullable=True)
    webauthn_sign_count = Column(Integer, default=0)

    # Relationships
    buyer_profile = relationship("Buyer", back_populates="user", uselist=False)
    seller_profile = relationship("Seller", back_populates="user", uselist=False)
    
    def get_id(self):
        return str(self.username)
    
    def generate_email_token(self):
        """Generate a new email verification token"""
        self.email_token = secrets.token_urlsafe(32)
        self.email_token_expiry = datetime.utcnow() + timedelta(hours=24)
        return self.email_token
    
    def has_webauthn_credential(self):
        """Check if user has a registered WebAuthn credential"""
        return self.webauthn_credential_id is not None
