from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
import os

# Database configuration - supports both PostgreSQL and SQLite
# PostgreSQL: postgresql://user:password@host:port/database
# SQLite fallback: sqlite:///instance/marketplace.db

DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Handle Heroku-style postgres:// URLs (convert to postgresql://)
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
else:
    # Fallback to SQLite for local development
    DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance')
    os.makedirs(DB_DIR, exist_ok=True)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(DB_DIR, "marketplace.db")}'

# Create engine with appropriate settings
if SQLALCHEMY_DATABASE_URI.startswith('postgresql'):
    # PostgreSQL settings
    engine = create_engine(
        SQLALCHEMY_DATABASE_URI,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Enable connection health checks
        pool_recycle=300,    # Recycle connections after 5 minutes
    )
else:
    # SQLite settings
    engine = create_engine(SQLALCHEMY_DATABASE_URI)

# Create a session factory
session_factory = sessionmaker(bind=engine)
db_session = scoped_session(session_factory)

# Base class for all models
Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    """Initialize the database with all models."""
    # Import all models here to ensure they are registered with Base
    from core.marketplace.models import User, Product, Seller, Buyer, Payment
    from core.challenges.models import Challenge
    from routes.messages import Message
    
    # Create all tables
    Base.metadata.create_all(engine)

def close_db():
    """Close the database session."""
    db_session.remove()
