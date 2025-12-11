import requests
from flask import current_app, url_for
from threading import Thread
import os

# Brevo API configuration
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# Dummy Mail class for compatibility (Flask-Mail replacement)
class BrevoMail:
    def __init__(self, app=None):
        self.app = app
        
    def init_app(self, app):
        self.app = app

mail = BrevoMail()


def send_async_email(app, email_data):
    """Send email asynchronously using Brevo API"""
    with app.app_context():
        api_key = os.getenv('BREVO_API_KEY')
        
        if not api_key:
            print("Warning: BREVO_API_KEY not configured")
            return False
            
        headers = {
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json'
        }
        
        try:
            response = requests.post(BREVO_API_URL, json=email_data, headers=headers)
            if response.status_code == 201:
                print(f"Email sent successfully to {email_data['to'][0]['email']}")
                return True
            else:
                print(f"Failed to send email: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Error sending email: {e}")
            return False


def send_email(subject, recipients, html_body):
    """Send email asynchronously using Brevo API"""
    sender_email = os.getenv('BREVO_SENDER_EMAIL', 'noreply@momento.com')
    sender_name = os.getenv('BREVO_SENDER_NAME', 'Momento')
    
    email_data = {
        'sender': {
            'name': sender_name,
            'email': sender_email
        },
        'to': [{'email': recipient} for recipient in recipients],
        'subject': subject,
        'htmlContent': html_body
    }
    
    Thread(target=send_async_email, args=(current_app._get_current_object(), email_data)).start()


def send_verification_email(user):
    """Send verification email to user
    
    Note: The user should already have an email_token generated and committed
    to the database BEFORE calling this function.
    """
    if not user.email_token:
        raise ValueError("User does not have an email verification token. Generate one first.")
    
    verify_url = url_for('auth.verify_email', token=user.email_token, _external=True)
    
    html = f'''
    <h1>Welcome to Momento!</h1>
    <p>Thank you for registering. To verify your email address, please click the link below:</p>
    <p><a href="{verify_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Verify Email</a></p>
    <p>Or copy and paste this link into your browser:</p>
    <p>{verify_url}</p>
    <p>This link will expire in 24 hours.</p>
    <p>If you did not register for Momento, please ignore this email.</p>
    '''
    
    send_email(
        'Verify Your Email - Momento',
        [user.email],
        html
    )
