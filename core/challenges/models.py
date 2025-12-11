from core.database import Base, db_session
from sqlalchemy import Column, Integer, String, Boolean, JSON, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime


class MinigameProgress(Base):
    """Track user progress in challenge minigames."""
    __tablename__ = 'minigame_progress'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    challenge_id = Column(String(50), ForeignKey('challenges.id'), nullable=False)
    minigame_type = Column(String(20), nullable=False)  # wheel, quiz, memory, slider, scramble
    part_index = Column(Integer, nullable=False)  # Which part of the key (0-4)
    revealed_part = Column(String(50), nullable=False)  # The actual key characters revealed
    completed_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MinigameProgress(user_id={self.user_id}, challenge_id='{self.challenge_id}', type='{self.minigame_type}')>"

    @classmethod
    def get_user_progress(cls, user_id, challenge_id):
        """Get all completed minigames for a user on a challenge."""
        return db_session.query(cls).filter_by(
            user_id=user_id,
            challenge_id=challenge_id
        ).all()

    @classmethod
    def has_completed(cls, user_id, challenge_id, minigame_type):
        """Check if user has completed a specific minigame for a challenge."""
        return db_session.query(cls).filter_by(
            user_id=user_id,
            challenge_id=challenge_id,
            minigame_type=minigame_type
        ).first() is not None

    @classmethod
    def mark_completed(cls, user_id, challenge_id, minigame_type, part_index, revealed_part):
        """Mark a minigame as completed and store the revealed key part."""
        progress = cls(
            user_id=user_id,
            challenge_id=challenge_id,
            minigame_type=minigame_type,
            part_index=part_index,
            revealed_part=revealed_part
        )
        db_session.add(progress)
        db_session.commit()
        return progress

class Challenge(Base):
    __tablename__ = 'challenges'

    id = Column(String(50), primary_key=True)
    type = Column(String(20), nullable=False)
    difficulty = Column(String(10), nullable=False)
    description = Column(Text, nullable=False)
    points = Column(String(10), nullable=False)
    hints = Column(JSON, nullable=False)
    encrypted_message = Column(Text, nullable=False)
    flag = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    files = Column(JSON, nullable=True)

    def to_dict(self , exclude_flag = False):
        """Convert challenge to dictionary format."""
        return {
            'id': self.id,
            'type': self.type,
            'difficulty': self.difficulty,
            'description': self.description,
            'points': self.points,
            'hints': self.hints,
            'encrypted_message': self.encrypted_message,
            'flag': self.flag,
            'is_active': self.is_active,
            'files': self.files or []
        }

    def __repr__(self):
        return f"<Challenge(id='{self.id}', type='{self.type}', difficulty='{self.difficulty}')>" 
