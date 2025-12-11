from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from core.auth.models import User
from core.database import db_session, Base
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

messages_bp = Blueprint('messages', __name__, url_prefix='/messages')


# Message Model
class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)
    
    sender = relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    recipient = relationship('User', foreign_keys=[recipient_id], backref='received_messages')


@messages_bp.route('/')
@login_required
def inbox():
    """Show list of conversations"""
    from sqlalchemy import or_, and_
    
    # Get all messages involving current user
    all_messages = Message.query.filter(
        or_(
            Message.sender_id == current_user.id,
            Message.recipient_id == current_user.id
        )
    ).order_by(Message.created_at.desc()).all()
    
    # Build unique conversation list
    seen_users = set()
    conversations = []
    
    for msg in all_messages:
        # Determine the other user in the conversation
        if msg.sender_id == current_user.id:
            other_user_id = msg.recipient_id
        else:
            other_user_id = msg.sender_id
        
        if other_user_id not in seen_users:
            seen_users.add(other_user_id)
            other_user = User.query.get(other_user_id)
            
            if other_user:
                # Count unread messages from this user
                unread_count = Message.query.filter(
                    Message.sender_id == other_user_id,
                    Message.recipient_id == current_user.id,
                    Message.read == False
                ).count()
                
                conversations.append({
                    'user': other_user,
                    'last_message': msg,
                    'unread_count': unread_count
                })
    
    return render_template('messages/inbox.html', conversations=conversations)


@messages_bp.route('/chat/<username>')
@login_required
def chat(username):
    """Show chat with a specific user"""
    other_user = User.query.filter_by(username=username).first()
    if not other_user:
        abort(404)
    
    if other_user.id == current_user.id:
        flash('You cannot message yourself.', 'error')
        return redirect(url_for('messages.inbox'))
    
    # Get messages between the two users
    from sqlalchemy import or_, and_
    messages = Message.query.filter(
        or_(
            and_(Message.sender_id == current_user.id, Message.recipient_id == other_user.id),
            and_(Message.sender_id == other_user.id, Message.recipient_id == current_user.id)
        )
    ).order_by(Message.created_at.asc()).all()
    
    # Mark messages as read
    for msg in messages:
        if msg.recipient_id == current_user.id and not msg.read:
            msg.read = True
    db_session.commit()
    
    return render_template('messages/chat.html', other_user=other_user, messages=messages)


@messages_bp.route('/send/<username>', methods=['POST'])
@login_required
def send_message(username):
    """Send a message to a user"""
    other_user = User.query.filter_by(username=username).first()
    if not other_user:
        abort(404)
    
    content = request.form.get('content', '').strip()
    if not content:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('messages.chat', username=username))
    
    message = Message(
        sender_id=current_user.id,
        recipient_id=other_user.id,
        content=content
    )
    db_session.add(message)
    db_session.commit()
    
    # If AJAX request, return JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'content': message.content,
                'created_at': message.created_at.strftime('%I:%M %p'),
                'sender': current_user.username
            }
        })
    
    return redirect(url_for('messages.chat', username=username))


@messages_bp.route('/new')
@login_required
def new_conversation():
    """Start a new conversation - select a user"""
    # Get all users except current user
    users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template('messages/new.html', users=users)


@messages_bp.route('/unread-count')
@login_required
def unread_count():
    """Get count of unread messages (for notifications)"""
    count = Message.query.filter(
        Message.recipient_id == current_user.id,
        Message.read == False
    ).count()
    return jsonify({'count': count})
