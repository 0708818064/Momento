"""
Minigames module for revealing encryption keys through interactive games.
"""
import random
import string
import json
from datetime import datetime
from core.challenges.models import MinigameProgress

# Quiz question bank for crypto/security topics
QUIZ_QUESTIONS = [
    {
        "question": "What does AES stand for?",
        "options": ["Advanced Encryption Standard", "Automatic Encryption System", "Applied Electronic Security", "Abstract Encoding Scheme"],
        "answer": 0
    },
    {
        "question": "Which encryption is asymmetric?",
        "options": ["AES", "DES", "RSA", "XOR"],
        "answer": 2
    },
    {
        "question": "What is the purpose of an IV in encryption?",
        "options": ["Speed up encryption", "Add randomness", "Compress data", "Verify integrity"],
        "answer": 1
    },
    {
        "question": "Which hash function is considered insecure?",
        "options": ["SHA-256", "SHA-512", "MD5", "SHA-3"],
        "answer": 2
    },
    {
        "question": "What does XOR mean?",
        "options": ["Extra Operational Register", "Exclusive OR", "Extended Output Result", "External Operation Request"],
        "answer": 1
    },
    {
        "question": "What key size does AES-256 use?",
        "options": ["128 bits", "192 bits", "256 bits", "512 bits"],
        "answer": 2
    },
    {
        "question": "What is a Caesar cipher?",
        "options": ["Substitution cipher", "Block cipher", "Stream cipher", "Hash function"],
        "answer": 0
    },
    {
        "question": "What does SSL stand for?",
        "options": ["Secure Sockets Layer", "System Security Lock", "Safe Socket Link", "Secure System Login"],
        "answer": 0
    },
    {
        "question": "What is a rainbow table used for?",
        "options": ["Color encryption", "Password cracking", "Data compression", "Network routing"],
        "answer": 1
    },
    {
        "question": "What is the purpose of salt in hashing?",
        "options": ["Speed up hashing", "Prevent rainbow table attacks", "Compress data", "Encrypt the hash"],
        "answer": 1
    }
]

# Word scramble terms
SCRAMBLE_WORDS = [
    ("ENCRYPTION", "Process of encoding data"),
    ("DECRYPTION", "Process of decoding data"),
    ("ALGORITHM", "Set of rules for calculations"),
    ("CIPHERTEXT", "Encrypted message"),
    ("PLAINTEXT", "Unencrypted message"),
    ("SYMMETRIC", "Same key for encrypt/decrypt"),
    ("ASYMMETRIC", "Different keys for encrypt/decrypt"),
    ("HASHING", "One-way function"),
    ("SECURITY", "Protection from threats"),
    ("CRYPTOGRAPHY", "Science of secret writing")
]


class KeyRevealManager:
    """Manages key splitting and minigame-based revelation using database persistence."""
    
    def __init__(self):
        self.minigame_types = ['wheel', 'quiz', 'memory', 'slider', 'scramble']
    
    def split_key(self, key: str, num_parts: int = 5) -> list:
        """
        Split a key into multiple parts for minigame revelation.
        Each part is assigned to a different minigame type.
        """
        if not key:
            return []
        
        # Ensure key is string
        key = str(key)
        
        # Calculate part sizes
        key_length = len(key)
        base_size = key_length // num_parts
        remainder = key_length % num_parts
        
        parts = []
        start = 0
        
        for i in range(num_parts):
            # Add 1 to size for first 'remainder' parts
            size = base_size + (1 if i < remainder else 0)
            if size > 0:
                parts.append({
                    'index': i,
                    'value': key[start:start + size],
                    'game_type': self.minigame_types[i % len(self.minigame_types)],
                    'revealed': False
                })
                start += size
        
        return parts
    
    def get_user_progress(self, user_id: int, challenge_id: str) -> dict:
        """Get user's minigame progress for a challenge from database."""
        progress_records = MinigameProgress.get_user_progress(user_id, challenge_id)
        
        result = {}
        for record in progress_records:
            result[record.minigame_type] = {
                'completed': True,
                'revealed_part': record.revealed_part,
                'completed_at': record.completed_at.isoformat() if record.completed_at else None
            }
        return result
    
    def mark_game_completed(self, user_id: int, challenge_id: str, game_type: str, revealed_part: str, part_index: int = 0):
        """Mark a minigame as completed and store the revealed part in database."""
        # Check if already completed to avoid duplicates
        if not MinigameProgress.has_completed(user_id, challenge_id, game_type):
            MinigameProgress.mark_completed(
                user_id=user_id,
                challenge_id=challenge_id,
                minigame_type=game_type,
                part_index=part_index,
                revealed_part=revealed_part
            )
    
    def get_revealed_key(self, user_id: int, challenge_id: str, key_parts: list) -> str:
        """
        Get the full revealed key based on completed minigames.
        Returns masked string with * for unrevealed parts.
        """
        progress = self.get_user_progress(user_id, challenge_id)
        result = ""
        
        for part in key_parts:
            game_type = part['game_type']
            if game_type in progress and progress[game_type].get('completed'):
                result += part['value']
            else:
                result += '*' * len(part['value'])
        
        return result
    
    # --- Wheel Spin Game ---
    def generate_wheel_segments(self, key_part: str) -> list:
        """Generate wheel segments with the correct key characters hidden among decoys."""
        segments = []
        correct_chars = list(key_part)
        
        # Create segments - real characters plus decoys
        all_chars = string.ascii_uppercase + string.digits
        decoy_count = max(8 - len(correct_chars), 4)
        
        # Add correct characters
        for char in correct_chars:
            segments.append({'char': char.upper(), 'is_correct': True})
        
        # Add decoy characters
        for _ in range(decoy_count):
            decoy = random.choice(all_chars)
            segments.append({'char': decoy, 'is_correct': False})
        
        random.shuffle(segments)
        return segments
    
    # --- Quiz Game ---
    def get_quiz_questions(self, count: int = 3) -> list:
        """Get random quiz questions."""
        selected = random.sample(QUIZ_QUESTIONS, min(count, len(QUIZ_QUESTIONS)))
        # Shuffle options for each question
        for q in selected:
            q = q.copy()
        return selected
    
    def verify_quiz_answers(self, questions: list, answers: list) -> tuple:
        """Verify quiz answers. Returns (correct_count, total)."""
        correct = 0
        for i, q in enumerate(questions):
            if i < len(answers) and answers[i] == q['answer']:
                correct += 1
        return correct, len(questions)
    
    # --- Memory Game ---
    def generate_memory_cards(self, key_part: str) -> list:
        """Generate memory game cards with pairs."""
        cards = []
        chars = list(key_part.upper())
        
        # Create pairs for each character
        for i, char in enumerate(chars):
            cards.append({'id': f'{i}a', 'value': char, 'pair_id': i})
            cards.append({'id': f'{i}b', 'value': char, 'pair_id': i})
        
        # Add some decoy pairs
        decoys = random.sample(string.ascii_uppercase, min(3, 26 - len(chars)))
        for i, char in enumerate(decoys):
            idx = len(chars) + i
            cards.append({'id': f'{idx}a', 'value': char, 'pair_id': idx, 'is_decoy': True})
            cards.append({'id': f'{idx}b', 'value': char, 'pair_id': idx, 'is_decoy': True})
        
        random.shuffle(cards)
        return cards
    
    # --- Slider Puzzle ---
    def generate_slider_puzzle(self, key_part: str) -> dict:
        """Generate a 3x3 slider puzzle."""
        # Create a solvable puzzle state
        solution = list(range(1, 9)) + [0]  # 1-8 and empty (0)
        
        # Shuffle to create puzzle (ensure solvable)
        puzzle = solution.copy()
        for _ in range(100):
            empty_idx = puzzle.index(0)
            # Find valid moves
            moves = []
            if empty_idx >= 3: moves.append(empty_idx - 3)  # Up
            if empty_idx < 6: moves.append(empty_idx + 3)   # Down
            if empty_idx % 3 > 0: moves.append(empty_idx - 1)  # Left
            if empty_idx % 3 < 2: moves.append(empty_idx + 1)  # Right
            
            swap_idx = random.choice(moves)
            puzzle[empty_idx], puzzle[swap_idx] = puzzle[swap_idx], puzzle[empty_idx]
        
        return {
            'puzzle': puzzle,
            'solution': solution,
            'key_part': key_part
        }
    
    def verify_slider_solution(self, puzzle_state: list) -> bool:
        """Verify if slider puzzle is solved."""
        solution = list(range(1, 9)) + [0]
        return puzzle_state == solution
    
    # --- Word Scramble ---
    def generate_scramble(self) -> dict:
        """Generate a word scramble puzzle."""
        word, hint = random.choice(SCRAMBLE_WORDS)
        scrambled = list(word)
        random.shuffle(scrambled)
        
        # Make sure it's actually scrambled
        while ''.join(scrambled) == word:
            random.shuffle(scrambled)
        
        return {
            'scrambled': ''.join(scrambled),
            'word': word,
            'hint': hint
        }
    
    def verify_scramble(self, submitted: str, correct: str) -> bool:
        """Verify word scramble answer."""
        return submitted.upper().strip() == correct.upper()


# Singleton instance
key_reveal_manager = KeyRevealManager()
