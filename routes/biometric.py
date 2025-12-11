from flask import Blueprint, jsonify, request, render_template, session, url_for
from flask_login import login_required, current_user, login_user
from core.auth.models import User
from core.database import db_session
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AuthenticatorAttachment,
    PublicKeyCredentialDescriptor,
)
import json

biometric_bp = Blueprint('biometric', __name__, url_prefix='/biometric')

# WebAuthn Configuration - update these for production
RP_ID = "localhost"
RP_NAME = "Momento"
ORIGIN = "http://localhost:5000"


@biometric_bp.route('/setup')
@login_required
def setup():
    """Show biometric setup page"""
    has_credential = current_user.has_webauthn_credential()
    return render_template('auth/biometric_setup.html', has_credential=has_credential)


@biometric_bp.route('/register-options', methods=['GET'])
@login_required
def register_options():
    """Generate WebAuthn registration options"""
    user = current_user
    
    # Generate registration options
    # Note: Not specifying authenticator_attachment allows both platform (biometric)
    # and cross-platform (USB security key) authenticators
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    
    # Store the challenge in session for verification
    session['webauthn_challenge'] = bytes_to_base64url(options.challenge)
    
    return jsonify(json.loads(options_to_json(options)))


@biometric_bp.route('/register', methods=['POST'])
@login_required
def register():
    """Complete WebAuthn registration"""
    try:
        credential_data = request.get_json()
        
        # Get the stored challenge
        expected_challenge = base64url_to_bytes(session.get('webauthn_challenge', ''))
        
        if not expected_challenge:
            return jsonify({'error': 'No challenge found. Please try again.'}), 400
        
        # Verify the registration response
        verification = verify_registration_response(
            credential=credential_data,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
        )
        
        # Store the credential
        current_user.webauthn_credential_id = bytes_to_base64url(verification.credential_id)
        current_user.webauthn_public_key = verification.credential_public_key
        current_user.webauthn_sign_count = verification.sign_count
        db_session.commit()
        
        # Clear the challenge
        session.pop('webauthn_challenge', None)
        
        return jsonify({'success': True, 'message': 'Passkey registered successfully!'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@biometric_bp.route('/login-options', methods=['POST'])
def login_options():
    """Generate WebAuthn authentication options"""
    data = request.get_json() or {}
    username = data.get('username', '')
    
    # Find user with WebAuthn credential
    user = None
    allow_credentials = []
    
    if username:
        user = User.query.filter_by(username=username).first()
        if user and user.webauthn_credential_id:
            allow_credentials = [
                PublicKeyCredentialDescriptor(
                    id=base64url_to_bytes(user.webauthn_credential_id)
                )
            ]
    
    if not allow_credentials:
        return jsonify({'error': 'No passkey found for this user.'}), 400
    
    # Generate authentication options
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    
    # Store challenge and username for verification
    session['webauthn_challenge'] = bytes_to_base64url(options.challenge)
    session['webauthn_username'] = username
    
    return jsonify(json.loads(options_to_json(options)))


@biometric_bp.route('/login', methods=['POST'])
def login():
    """Complete WebAuthn authentication"""
    try:
        credential_data = request.get_json()
        
        # Get the stored challenge and username
        expected_challenge = base64url_to_bytes(session.get('webauthn_challenge', ''))
        username = session.get('webauthn_username', '')
        
        if not expected_challenge or not username:
            return jsonify({'error': 'Session expired. Please try again.'}), 400
        
        # Get user
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.webauthn_credential_id:
            return jsonify({'error': 'User not found or no passkey registered.'}), 400
        
        # Verify the authentication response
        verification = verify_authentication_response(
            credential=credential_data,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=user.webauthn_public_key,
            credential_current_sign_count=user.webauthn_sign_count,
        )
        
        # Update sign count
        user.webauthn_sign_count = verification.new_sign_count
        db_session.commit()
        
        # Clear session data
        session.pop('webauthn_challenge', None)
        session.pop('webauthn_username', None)
        
        # Log the user in
        login_user(user)
        
        return jsonify({
            'success': True,
            'message': 'Login successful!',
            'redirect': url_for('index')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@biometric_bp.route('/remove', methods=['POST'])
@login_required
def remove():
    """Remove WebAuthn credential"""
    current_user.webauthn_credential_id = None
    current_user.webauthn_public_key = None
    current_user.webauthn_sign_count = 0
    db_session.commit()
    
    return jsonify({'success': True, 'message': 'Passkey removed successfully.'})
