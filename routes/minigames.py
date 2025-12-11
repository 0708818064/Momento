"""
Minigames routes for key revelation through interactive games.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from core.challenges.minigames import key_reveal_manager
from core.challenges.challenge_manager import ChallengeManager
from core.database import db_session
from core.challenges.models import Challenge
import json

minigames_bp = Blueprint('minigames', __name__, url_prefix='/minigames')

# Shared challenge manager instance
challenge_manager = ChallengeManager()


@minigames_bp.route('/')
@login_required
def minigames_index():
    """Show list of challenges with available minigames."""
    challenges = db_session.query(Challenge).filter_by(is_active=True).all()
    return render_template('minigames/index.html', challenges=challenges)


def get_challenge_key(challenge_id: str) -> str:
    """Get the key for a challenge (from layered encrypted data)."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        return None
    
    # Extract key from layered format: LAYER_TYPE:KEY:ENCRYPTED_DATA
    encrypted_msg = challenge.encrypted_message
    if ':' in encrypted_msg:
        parts = encrypted_msg.split(':', 2)
        if len(parts) >= 2:
            return parts[1]  # The key is the second part
    
    # Fallback - use first 16 chars of encrypted message as "key"
    return encrypted_msg[:16] if encrypted_msg else "UNKNOWNKEY123456"


@minigames_bp.route('/challenge/<challenge_id>')
@login_required
def minigames_hub(challenge_id):
    """Show all available minigames for a challenge."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    # Get the key and split it
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    # Get user's progress
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    
    # Mark which games are completed
    for part in key_parts:
        game_type = part['game_type']
        if game_type in progress and progress[game_type].get('completed'):
            part['revealed'] = True
            part['value'] = progress[game_type].get('revealed_part', part['value'])
    
    # Calculate revealed key
    revealed_key = key_reveal_manager.get_revealed_key(current_user.id, challenge_id, key_parts)
    
    return render_template('minigames/hub.html',
                         challenge=challenge,
                         key_parts=key_parts,
                         revealed_key=revealed_key,
                         progress=progress)


@minigames_bp.route('/challenge/<challenge_id>/wheel')
@login_required
def wheel_spin(challenge_id):
    """Wheel spin minigame."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    # Find the wheel game part
    wheel_part = next((p for p in key_parts if p['game_type'] == 'wheel'), None)
    if not wheel_part:
        flash("Wheel game not available for this challenge.", "warning")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    # Check if already completed
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    if 'wheel' in progress and progress['wheel'].get('completed'):
        flash(f"Already completed! Key part: {wheel_part['value']}", "success")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    # Generate wheel segments
    segments = key_reveal_manager.generate_wheel_segments(wheel_part['value'])
    
    # Store the key part in session for verification
    session[f'wheel_{challenge_id}'] = wheel_part['value']
    
    return render_template('minigames/wheel_spin.html',
                         challenge=challenge,
                         segments=segments,
                         key_part_length=len(wheel_part['value']))


@minigames_bp.route('/challenge/<challenge_id>/wheel/complete', methods=['POST'])
@login_required
def wheel_complete(challenge_id):
    """Complete wheel spin game."""
    key_part = session.get(f'wheel_{challenge_id}')
    if not key_part:
        return jsonify({'success': False, 'message': 'Invalid session'})
    
    # Mark as completed
    key_reveal_manager.mark_game_completed(
        current_user.id, challenge_id, 'wheel', key_part
    )
    
    # Clear session
    session.pop(f'wheel_{challenge_id}', None)
    
    return jsonify({
        'success': True,
        'revealed_part': key_part,
        'message': f'Key part revealed: {key_part}'
    })


@minigames_bp.route('/challenge/<challenge_id>/quiz')
@login_required  
def quiz_game(challenge_id):
    """Quiz minigame."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    # Find the quiz game part
    quiz_part = next((p for p in key_parts if p['game_type'] == 'quiz'), None)
    if not quiz_part:
        flash("Quiz game not available for this challenge.", "warning")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    # Check if already completed
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    if 'quiz' in progress and progress['quiz'].get('completed'):
        flash(f"Already completed! Key part: {quiz_part['value']}", "success")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    # Get quiz questions
    questions = key_reveal_manager.get_quiz_questions(3)
    
    # Store for verification
    session[f'quiz_{challenge_id}'] = {
        'questions': questions,
        'key_part': quiz_part['value']
    }
    
    return render_template('minigames/quiz.html',
                         challenge=challenge,
                         questions=questions)


@minigames_bp.route('/challenge/<challenge_id>/quiz/submit', methods=['POST'])
@login_required
def quiz_submit(challenge_id):
    """Submit quiz answers."""
    quiz_data = session.get(f'quiz_{challenge_id}')
    if not quiz_data:
        return jsonify({'success': False, 'message': 'Invalid session'})
    
    answers = request.json.get('answers', [])
    questions = quiz_data['questions']
    key_part = quiz_data['key_part']
    
    correct, total = key_reveal_manager.verify_quiz_answers(questions, answers)
    
    # Need at least 2/3 correct
    if correct >= 2:
        key_reveal_manager.mark_game_completed(
            current_user.id, challenge_id, 'quiz', key_part
        )
        session.pop(f'quiz_{challenge_id}', None)
        return jsonify({
            'success': True,
            'correct': correct,
            'total': total,
            'revealed_part': key_part,
            'message': f'Correct! Key part: {key_part}'
        })
    else:
        return jsonify({
            'success': False,
            'correct': correct,
            'total': total,
            'message': f'You got {correct}/{total}. Need at least 2 correct!'
        })


@minigames_bp.route('/challenge/<challenge_id>/memory')
@login_required
def memory_game(challenge_id):
    """Memory match minigame."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    memory_part = next((p for p in key_parts if p['game_type'] == 'memory'), None)
    if not memory_part:
        flash("Memory game not available.", "warning")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    if 'memory' in progress and progress['memory'].get('completed'):
        flash(f"Already completed! Key part: {memory_part['value']}", "success")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    cards = key_reveal_manager.generate_memory_cards(memory_part['value'])
    session[f'memory_{challenge_id}'] = memory_part['value']
    
    return render_template('minigames/memory.html',
                         challenge=challenge,
                         cards=cards)


@minigames_bp.route('/challenge/<challenge_id>/memory/complete', methods=['POST'])
@login_required
def memory_complete(challenge_id):
    """Complete memory game."""
    key_part = session.get(f'memory_{challenge_id}')
    if not key_part:
        return jsonify({'success': False, 'message': 'Invalid session'})
    
    key_reveal_manager.mark_game_completed(
        current_user.id, challenge_id, 'memory', key_part
    )
    session.pop(f'memory_{challenge_id}', None)
    
    return jsonify({
        'success': True,
        'revealed_part': key_part,
        'message': f'Key part revealed: {key_part}'
    })


@minigames_bp.route('/challenge/<challenge_id>/slider')
@login_required
def slider_puzzle(challenge_id):
    """Slider puzzle minigame."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    slider_part = next((p for p in key_parts if p['game_type'] == 'slider'), None)
    if not slider_part:
        flash("Slider game not available.", "warning")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    if 'slider' in progress and progress['slider'].get('completed'):
        flash(f"Already completed! Key part: {slider_part['value']}", "success")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    puzzle_data = key_reveal_manager.generate_slider_puzzle(slider_part['value'])
    session[f'slider_{challenge_id}'] = slider_part['value']
    
    return render_template('minigames/slider.html',
                         challenge=challenge,
                         puzzle=puzzle_data['puzzle'])


@minigames_bp.route('/challenge/<challenge_id>/slider/complete', methods=['POST'])
@login_required
def slider_complete(challenge_id):
    """Complete slider puzzle."""
    key_part = session.get(f'slider_{challenge_id}')
    if not key_part:
        return jsonify({'success': False, 'message': 'Invalid session'})
    
    puzzle_state = request.json.get('state', [])
    if key_reveal_manager.verify_slider_solution(puzzle_state):
        key_reveal_manager.mark_game_completed(
            current_user.id, challenge_id, 'slider', key_part
        )
        session.pop(f'slider_{challenge_id}', None)
        return jsonify({
            'success': True,
            'revealed_part': key_part,
            'message': f'Key part revealed: {key_part}'
        })
    else:
        return jsonify({'success': False, 'message': 'Puzzle not solved yet!'})


@minigames_bp.route('/challenge/<challenge_id>/scramble')
@login_required
def scramble_game(challenge_id):
    """Word scramble minigame."""
    challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
    if not challenge:
        flash("Challenge not found.", "error")
        return redirect(url_for('list_challenges'))
    
    key = get_challenge_key(challenge_id)
    key_parts = key_reveal_manager.split_key(key)
    
    scramble_part = next((p for p in key_parts if p['game_type'] == 'scramble'), None)
    if not scramble_part:
        flash("Scramble game not available.", "warning")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    progress = key_reveal_manager.get_user_progress(current_user.id, challenge_id)
    if 'scramble' in progress and progress['scramble'].get('completed'):
        flash(f"Already completed! Key part: {scramble_part['value']}", "success")
        return redirect(url_for('minigames.minigames_hub', challenge_id=challenge_id))
    
    scramble_data = key_reveal_manager.generate_scramble()
    session[f'scramble_{challenge_id}'] = {
        'word': scramble_data['word'],
        'key_part': scramble_part['value']
    }
    
    return render_template('minigames/scramble.html',
                         challenge=challenge,
                         scrambled=scramble_data['scrambled'],
                         hint=scramble_data['hint'])


@minigames_bp.route('/challenge/<challenge_id>/scramble/submit', methods=['POST'])
@login_required
def scramble_submit(challenge_id):
    """Submit scramble answer."""
    scramble_data = session.get(f'scramble_{challenge_id}')
    if not scramble_data:
        return jsonify({'success': False, 'message': 'Invalid session'})
    
    answer = request.json.get('answer', '')
    if key_reveal_manager.verify_scramble(answer, scramble_data['word']):
        key_part = scramble_data['key_part']
        key_reveal_manager.mark_game_completed(
            current_user.id, challenge_id, 'scramble', key_part
        )
        session.pop(f'scramble_{challenge_id}', None)
        return jsonify({
            'success': True,
            'revealed_part': key_part,
            'word': scramble_data['word'],
            'message': f'Correct! Key part: {key_part}'
        })
    else:
        return jsonify({'success': False, 'message': 'Incorrect! Try again.'})
