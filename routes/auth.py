from flask import Blueprint, flash, redirect, url_for, render_template, request
from core.auth.models import User
from core.database import db_session
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from core.email.service import mail, send_verification_email
from flask_mail import Message
import secrets

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        
        # Validate password confirmation
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        # Check if username exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('auth/register.html')
        
        # Check if email exists
        if email and User.query.filter_by(email=email).first():
            flash('Email already registered. Please login instead.', 'error')
            return redirect(url_for('auth.login'))
        
        # Create user with email verification required
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            is_active=True,
            is_admin=False,
            email_verified=False,
            created_at=datetime.utcnow()
        )
        
        # Generate email verification token
        user.generate_email_token()
        
        db_session.add(user)
        db_session.commit()
        
        # Send verification email
        try:
            send_verification_email(user)
            flash('Registration successful! Please check your email to verify your account.', 'success')
        except Exception as e:
            flash('Registration successful but we could not send verification email. Please request a new one.', 'warning')
        
        return redirect(url_for('auth.verify_pending', email=email))
    
    return render_template('auth/register.html')

@auth_bp.route('/verify-pending')
def verify_pending():
    """Show verification pending page"""
    email = request.args.get('email', '')
    return render_template('auth/verify_pending.html', email=email)

@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email"""
    email = request.form.get('email')
    
    if not email:
        flash('Please provide your email address.', 'error')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    
    if user and not user.email_verified:
        # Generate new token
        user.generate_email_token()
        db_session.commit()
        
        try:
            send_verification_email(user)
            flash('Verification email sent! Please check your inbox.', 'success')
        except Exception as e:
            flash('Failed to send verification email. Please try again later.', 'error')
    else:
        # Don't reveal if user exists or is already verified
        flash('If the email exists and is unverified, a verification link has been sent.', 'info')
    
    return redirect(url_for('auth.verify_pending', email=email))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    admin_login = request.args.get('admin', '0') == '1'
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin_login = request.form.get('admin_login') == '1'
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Check email verification
            if not user.email_verified and not user.is_admin:
                flash('Please verify your email before logging in. Check your inbox for the verification link.', 'warning')
                return redirect(url_for('auth.verify_pending', email=user.email))
            
            if admin_login and not user.is_admin:
                flash('Access denied. Admin privileges required.', 'error')
                return render_template('auth/login.html', admin_login=True)
                
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'error')
                return render_template('auth/login.html', admin_login=admin_login)
                
            login_user(user)
            flash('Logged in successfully!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin.admin_dashboard'))
            return redirect(url_for('index'))
            
        flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html', admin_login=admin_login)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@auth_bp.route('/verify/<token>')
def verify_email(token):
    user = User.query.filter_by(email_token=token).first()
    
    if not user:
        flash('Invalid verification link', 'error')
        return redirect(url_for('index'))
    
    if user.email_token_expiry < datetime.utcnow():
        flash('Verification link has expired. Please request a new one.', 'error')
        return redirect(url_for('index'))
    
    user.email_verified = True
    user.email_token = None
    user.email_token_expiry = None
    db_session.commit()
    
    flash('Email verified successfully!', 'success')
    return redirect(url_for('marketplace.index'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate password reset token
            user.reset_token = secrets.token_urlsafe(32)
            user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
            db_session.commit()
            
            # Send password reset email
            send_password_reset_email(user)
            
        # Always show success message to prevent email enumeration
        flash('If an account exists with that email, you will receive a password reset link.', 'info')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expiry < datetime.utcnow():
        flash('Invalid or expired password reset link', 'error')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/reset_password.html', token=token)
            
        user.password_hash = generate_password_hash(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db_session.commit()
        
        flash('Your password has been reset successfully!', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', token=token)

def send_password_reset_email(user):
    msg = Message('Reset your password',
                 recipients=[user.email])
    msg.html = render_template('email/reset_password.html',
                             reset_url=url_for('auth.reset_password',
                                             token=user.reset_token,
                                             _external=True))
    mail.send(msg)
