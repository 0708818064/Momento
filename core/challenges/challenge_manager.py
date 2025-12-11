import random
from core.challenges.generator import ChallengeGenerator
from core.challenges.validator import ChallengeValidator
from core.crypto.challenge_layer import ChallengeLayer  # import layers
# Removed HMAC for simplicity in this refactor, focus on core change
# from core.crypto.hmac import generate_hmac, verify_hmac
from core.crypto.aes_engine import AESCipher # Assumes AESCipher takes key, maybe mode?
from core.crypto.vigenere import VigenereCipher
from core.crypto.rsa_manager import RSAManager
# Assuming other cipher engines exist similarly if needed:
# from core.crypto.des_engine import DESCipher
# from core.crypto.rc4_engine import RC4Cipher
# from core.crypto.blowfish_engine import BlowfishCipher
# from core.crypto.hash_engine import HashFunction # Example

from config.security import SECRET_KEY # Unused in this snippet?
# --- Ensure correct imports ---
from core.database import db_session
from core.challenges.models import Challenge
# --- End Ensure correct imports ---
import json
import os
import base64 # Often needed for encoding encrypted data
import hashlib # Added for hash challenge
import binascii # For error checking

class ChallengeManager:
    def __init__(self):
        self.generator = ChallengeGenerator()
        self.challenge_layer = ChallengeLayer()
        self.validator = ChallengeValidator()
        # User stats should ideally be in the database for persistence
        self.user_stats = {}  # Username: {challenge_id: {solved: bool, hints_used: int}}
        self.rsa_manager = RSAManager()
        self.public_key_pem = self.rsa_manager.get_public_key_pem()
        # Removed HMAC Key for simplicity
        # self.hmac_key = self.generator.generate_random_data(16)

    def _encrypt_file_content(self, file_path, flag, description):
        """Encrypts the flag in a file while keeping the description visible."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            if flag in content:
                encrypted_flag_placeholder = f"FLAG_ENCRYPTED_HERE[{len(flag)} bytes]"
                content = content.replace(flag, encrypted_flag_placeholder)
                with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(content)
                return True
            return False
        except Exception as e:
            print(f"Warning: Error processing file content for flag encryption: {e}")
            return False

    # --- MODIFIED create_challenge SIGNATURE ---
    def create_challenge(self, challenge_id, challenge_type, difficulty="easy",
                         description="", points=100, hints=None, files=None, flag=None,
                         key_length=None, mode=None, message_to_encrypt=None):
        """
        Creates a new challenge based on type and difficulty.
        Accepts optional crypto parameters for relevant types.
        """
        # --- MODIFIED: Use db_session.query ---
        if db_session.query(Challenge).filter_by(id=challenge_id).first():
            raise ValueError(f"Challenge ID '{challenge_id}' already exists.")
        # --- End modification ---

        if not flag:
            raise ValueError("Flag (solution) is required for challenge creation")

        challenge_details = None # Dictionary to hold details from _create methods

        # Basic type check for crypto params relevance
        crypto_types_accepting_params = ["aes", "des", "rc4", "blowfish", "caesar"] # Add others if they support these params

        # --- Pass relevant parameters down ---
        # --- CORRECTED STRUCTURE: Call helper methods ---
        if challenge_type == "caesar":
            challenge_details = self._create_caesar_challenge(
                challenge_id, difficulty, flag, description
            )
        elif challenge_type == "aes":
            challenge_details = self._create_aes_challenge(
                challenge_id, difficulty, flag, description,
                key_length, mode, message_to_encrypt
            )
        elif challenge_type == "vigenere":
            challenge_details = self._create_vigenere_challenge(
                 challenge_id, difficulty, flag, description
            )
        elif challenge_type == "rsa":
             challenge_details = self._create_rsa_challenge(
                 challenge_id, difficulty, flag, description
             )
        elif challenge_type == "xor":
             challenge_details = self._create_xor_challenge(
                 challenge_id, difficulty, flag, description, message_to_encrypt
             )
        elif challenge_type == "hash":
             challenge_details = self._create_hash_challenge(
                 challenge_id, difficulty, flag, description, message_to_encrypt
             )
        elif challenge_type == "web":
            challenge_details = self._create_web_challenge(challenge_id, difficulty, flag, description)
        elif challenge_type == "binary":
            challenge_details = self._create_binary_challenge(challenge_id, difficulty, flag, description)
        elif challenge_type == "forensics":
            challenge_details = self._create_forensics_challenge(challenge_id, difficulty, flag, description)
        elif challenge_type == "stego":
            challenge_details = self._create_stego_challenge(challenge_id, difficulty, flag, description)
        elif challenge_type == "reversing":
            challenge_details = self._create_reversing_challenge(challenge_id, difficulty, flag, description)
        elif challenge_type == "pwn":
            challenge_details = self._create_pwn_challenge(challenge_id, difficulty, flag, description)
        # --- TODO: Add other challenge types (des, rc4, blowfish) if implemented ---
        else:
            raise ValueError(f"Invalid challenge type: {challenge_type}")
        # --- End CORRECTED STRUCTURE ---

        if not challenge_details:
             raise ValueError(f"Failed to generate details for challenge type: {challenge_type}")

        # --- Apply Layers ---
        # Skip additional layers for simple cipher types that are already "encrypted"
        simple_cipher_types = ["caesar", "vigenere", "xor", "hash", "web", "binary", "forensics", "stego", "reversing", "pwn"]
        
        if challenge_type in simple_cipher_types:
            # Don't apply additional layers - the encryption is already done
            layered_encrypted_data_str = str(challenge_details.get("encrypted_message", ""))
        else:
            # Apply additional layers for complex challenges like AES, RSA
            num_layers = 1 if difficulty == "easy" else 2 if difficulty == "medium" else 3
            base_encrypted_data = challenge_details.get("encrypted_message", "")
            # Ensure base_encrypted_data is the type challenge_layer expects (likely str or bytes)
            if isinstance(base_encrypted_data, bytes):
                 # If layer expects string, decode first (e.g., base64 bytes to string)
                 try: base_encrypted_data = base_encrypted_data.decode('utf-8')
                 except UnicodeDecodeError: base_encrypted_data = base64.b64encode(base_encrypted_data).decode('ascii')

            layered_encrypted_data = self.challenge_layer.apply_layers(str(base_encrypted_data), num_layers)

            # Ensure final data is string for DB
            if isinstance(layered_encrypted_data, bytes):
                try: layered_encrypted_data_str = layered_encrypted_data.decode('utf-8')
                except UnicodeDecodeError: layered_encrypted_data_str = base64.b64encode(layered_encrypted_data).decode('ascii')
            else: layered_encrypted_data_str = str(layered_encrypted_data)

        # --- Process Files ---
        processed_files = []
        if files:
            challenge_dir = os.path.join('static', 'challenges', challenge_id)
            for filename in files:
                file_path = os.path.join(challenge_dir, filename)
                if os.path.exists(file_path):
                    self._encrypt_file_content(file_path, flag, description)
                    processed_files.append(filename)
                else:
                    print(f"Warning: File {filename} not found in {challenge_dir}.")
                    processed_files.append(f"{filename} (Not Found)")

        # --- Create database record ---
        db_hints = json.dumps(hints or challenge_details.get('hints', []))
        db_files = json.dumps(processed_files)
        db_challenge = Challenge(id=challenge_id, type=challenge_type, difficulty=difficulty,
                                 description=description or challenge_details.get('description', ''),
                                 points=int(points), hints=db_hints,
                                 encrypted_message=layered_encrypted_data_str, flag=flag,
                                 is_active=True, files=db_files)
        db_session.add(db_challenge)
        db_session.commit()

        # --- Return info for admin view ---
        admin_view_info = {"id": challenge_id, "type": challenge_type, "difficulty": difficulty,
                           "description": db_challenge.description, "points": db_challenge.points,
                           "hints": json.loads(db_hints), "flag": flag,
                           "encrypted_message": layered_encrypted_data_str,
                           "files": json.loads(db_files),
                           "key_used": challenge_details.get("key_used", "N/A"),
                           "iv_used": challenge_details.get("iv_used", "N/A"),
                           "mode_used": challenge_details.get("mode_used", "N/A"),
                           "message_source": challenge_details.get("message_source", "N/A")}
        return admin_view_info

    # --- Methods for getting/updating/deleting challenges ---
    # --- (No changes needed here from previous version with db_session.query) ---
    def get_challenge(self, challenge_id):
        """Get a challenge by ID."""
        challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
        return challenge.to_dict(exclude_flag=True) if challenge else None

    def get_all_challenges(self):
        """Get all active challenges."""
        challenges = db_session.query(Challenge).filter_by(is_active=True).all()
        return {c.id: c.to_dict(exclude_flag=True) for c in challenges}

    def update_challenge(self, challenge_id, challenge_data):
        """Update a challenge."""
        challenge = db_session.query(Challenge).filter_by(id=challenge_id).first()
        if not challenge: raise ValueError(f"Challenge ID '{challenge_id}' not found.")
        if 'flag' in challenge_data: del challenge_data['flag']
        if 'encrypted_message' in challenge_data: del challenge_data['encrypted_message']
        for key, value in challenge_data.items():
            if hasattr(challenge, key):
                if key == 'points':
                    try: value = int(value)
                    except (ValueError, TypeError): continue
                if key == 'hints' and isinstance(value, list): value = json.dumps(value)
                if key == 'files' and isinstance(value, list): value = json.dumps(value)
                setattr(challenge, key, value)
        db_session.commit()
        return challenge.to_dict(exclude_flag=True)

    def delete_challenge(self, challenge_id):
        """Delete a challenge (soft delete)."""
        challenge = db_session.query(Challenge).filter_by(id=challenge_id).first()
        if not challenge: raise ValueError(f"Challenge ID '{challenge_id}' not found.")
        challenge.is_active = False
        db_session.commit()

    def submit_flag(self, challenge_id, username, submitted_flag):
        """Submit a flag for a challenge."""
        challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
        if not challenge: return False, "Challenge not found."
        # TODO: Move user stats to DB
        if username not in self.user_stats: self.user_stats[username] = {}
        if challenge_id not in self.user_stats[username]: self.user_stats[username][challenge_id] = {"solved": False, "hints_used": 0}
        if self.user_stats[username][challenge_id]["solved"]: return True, "Challenge already solved."
        # Pass challenge object or dict to validator as needed
        if self.validator.validate_solution(challenge, submitted_flag):
             self.user_stats[username][challenge_id]["solved"] = True
             return True, "Flag is correct!"
        return False, "Incorrect flag."

    def get_user_stats(self, username):
        """Get a user's challenge statistics (from volatile memory)."""
        # TODO: Fetch this from the database instead
        return self.user_stats.get(username, {})

    def use_hint(self, challenge_id, username):
        """Use a hint for a challenge. First hint is always the encryption type."""
        challenge = db_session.query(Challenge).filter_by(id=challenge_id, is_active=True).first()
        if not challenge: return None, "Challenge not found."
        
        # TODO: Move user stats to DB
        if username not in self.user_stats: self.user_stats[username] = {}
        if challenge_id not in self.user_stats[username]: 
            self.user_stats[username][challenge_id] = {"solved": False, "hints_used": 0}
        
        hints_used = self.user_stats[username][challenge_id]["hints_used"]
        
        # Build dynamic hints list with encryption type as first hint
        dynamic_hints = []
        
        # Extract encryption type from layered format (LAYER_TYPE:KEY:DATA)
        encrypted_msg = challenge.encrypted_message or ""
        if ":" in encrypted_msg:
            layer_type = encrypted_msg.split(":", 1)[0].upper()
            if layer_type in ["AES", "VIGENERE", "RSA", "XOR"]:
                dynamic_hints.append(f"🔐 Encryption Type: {layer_type}")
            elif layer_type == "VIGENERE":
                dynamic_hints.append("🔐 Encryption Type: Vigenère Cipher (classical polyalphabetic)")
        
        # Add hint about the challenge type
        if challenge.type:
            type_hints = {
                'caesar': "This is a Caesar cipher. It's a simple shift cipher - try all 26 possible shifts!",
                'aes': "This is an AES (Advanced Encryption Standard) challenge. Look for the key!",
                'vigenere': "This is a Vigenère cipher. It's a polyalphabetic substitution cipher.",
                'rsa': "This is RSA encryption. You'll need to find the private key or factor the modulus.",
                'xor': "This is XOR encryption. Remember: XOR is its own inverse!",
                'hash': "This is a hash cracking challenge. Use rainbow tables or wordlists.",
                'web': "This is a web security challenge. Look for common vulnerabilities.",
                'binary': "This is a binary exploitation challenge. Analyze the executable.",
                'forensics': "This is a digital forensics challenge. Examine the evidence carefully.",
                'stego': "This is a steganography challenge. Data may be hidden in files.",
                'reversing': "This is a reverse engineering challenge. Disassemble and analyze.",
                'pwn': "This is a pwn challenge. Exploit the binary to get the flag."
            }
            if challenge.type.lower() in type_hints:
                dynamic_hints.append(f"💡 {type_hints[challenge.type.lower()]}")
        
        # Add stored hints from the database (might be list or JSON string)
        stored_hints = challenge.hints or []
        if isinstance(stored_hints, str):
            try: 
                stored_hints = json.loads(stored_hints)
            except json.JSONDecodeError: 
                stored_hints = []
        
        dynamic_hints.extend(stored_hints)
        
        # Check if we have hints left
        if not dynamic_hints or hints_used >= len(dynamic_hints): 
            return None, "No more hints available."
        
        hint_to_reveal = dynamic_hints[hints_used]
        self.user_stats[username][challenge_id]["hints_used"] += 1
        return hint_to_reveal, f"Hint {hints_used + 1}/{len(dynamic_hints)} revealed."

    # --- Private _create_* Methods ---
    # --- Placed at CLASS LEVEL (Correct Indentation) ---

    # --- CORRECTED VERSION: _create_aes_challenge ---
    # Assumes AESCipher.encrypt returns a Base64 encoded STRING
    def _create_aes_challenge(self, challenge_id, difficulty, flag, description,
                              key_length_param, mode_param, message_param):
        """
        Creates an AES encryption challenge.
        ASSUMES AESCipher.encrypt returns a Base64 encoded STRING.
        """
        default_key_lengths = {"easy": 16, "medium": 24, "hard": 32} # Bytes
        key_length = default_key_lengths[difficulty]
        if key_length_param and key_length_param in [128, 192, 256]:
            key_length = key_length_param // 8
            print(f"[AES Debug] Admin key length specified: {key_length*8} bits")
        else:
            print(f"[AES Debug] Default key length for {difficulty}: {key_length*8} bits")

        original_key_material = self.generator.generate_random_data(key_length)
        mode = mode_param if mode_param else "CFB8" # Default or reflect AESCipher's mode
        print(f"[AES Debug] Using encryption mode: {mode}")

        plaintext = flag; message_source = "flag"
        if message_param: plaintext = message_param; message_source = "admin_message"; print("[AES Debug] Using admin-provided message for encryption.")
        else: print("[AES Debug] No admin message provided, encrypting the flag.")
        if not isinstance(plaintext, str): plaintext = str(plaintext)

        aes_cipher = AESCipher(original_key_material)

        # --- Call encrypt and get the result (ASSUMED TO BE BASE64 STRING) ---
        encrypted_message_str_from_cipher = aes_cipher.encrypt(plaintext)

        # --- Diagnostic Check ---
        print(f"[AES Debug] Type returned by aes_cipher.encrypt: {type(encrypted_message_str_from_cipher)}")
        if not isinstance(encrypted_message_str_from_cipher, str):
             # If it's bytes, this assumption is wrong!
             print("[AES Debug] FATAL: Expected string from AESCipher.encrypt, got bytes.")
             # Attempt to fix by encoding, but the root cause needs checking
             try:
                 encrypted_message_str = base64.b64encode(encrypted_message_str_from_cipher).decode('ascii')
                 print("[AES Debug] Attempted base64 encoding of unexpected bytes.")
             except Exception as e:
                 print(f"[AES Debug] Error base64 encoding the bytes result: {e}")
                 encrypted_message_str = "Encoding Error" # Placeholder
        else:
             # If it's already a string, use it directly
             encrypted_message_str = encrypted_message_str_from_cipher
        # --- End Diagnostic Check ---

        # Get IV if possible
        iv_bytes = getattr(aes_cipher, 'iv', b'')
        iv_str = base64.b64encode(iv_bytes).decode('ascii') if iv_bytes else "N/A (Combined?)"

        hints = [f"Algorithm: AES, Mode: {mode}", f"Effective key length: {len(aes_cipher.key) * 8} bits (SHA-256 used).", "IV might be part of the Base64 output."]

        return {"id": challenge_id, "type": "aes", "description": description or f"Decrypt AES ({difficulty}, Mode: {mode}).",
                "key_used": base64.b64encode(aes_cipher.key).decode('ascii'), "iv_used": iv_str, "flag": flag,
                "encrypted_message": encrypted_message_str, # Use the final string
                "hints": hints, "mode_used": mode, "message_source": message_source}
    # --- End _create_aes_challenge ---

    def _create_caesar_challenge(self, challenge_id, difficulty, flag, description):
        """Creates a Caesar cipher challenge."""
        # Shift amount varies by difficulty
        shift_amounts = {"easy": [3, 5, 7], "medium": [11, 13, 17], "hard": [21, 23, 25]}
        shift = random.choice(shift_amounts.get(difficulty, [3]))
        
        def caesar_encrypt(text, shift_val):
            result = []
            for char in text:
                if char.isalpha():
                    base = ord('A') if char.isupper() else ord('a')
                    result.append(chr((ord(char) - base + shift_val) % 26 + base))
                else:
                    result.append(char)
            return ''.join(result)
        
        encrypted_message = caesar_encrypt(flag, shift)
        hints = [
            "This is a Caesar cipher (substitution cipher).",
            f"The alphabet is shifted by a certain number of positions.",
            f"Try ROT{shift} or brute-force all 26 possible shifts."
        ]
        
        return {
            "id": challenge_id, 
            "type": "caesar", 
            "description": description or f"Decrypt this Caesar cipher ({difficulty}).", 
            "key_used": str(shift), 
            "flag": flag, 
            "encrypted_message": encrypted_message, 
            "hints": hints, 
            "message_source": "flag"
        }

    def _create_vigenere_challenge(self, challenge_id, difficulty, flag, description):
        key_length = 3 if difficulty == "medium" else 5 if difficulty == "hard" else 3
        key = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(key_length))
        vigenere_cipher = VigenereCipher(key)
        encrypted_message = vigenere_cipher.encrypt(flag)
        hints = ["Classical cipher.", f"Key length might be {key_length}.", "Frequency analysis."]
        return {"id": challenge_id, "type": "vigenere", "description": description or f"Decrypt Vigenere ({difficulty}).", "key_used": key, "flag": flag, "encrypted_message": encrypted_message, "hints": hints, "message_source": "flag"}

    def _create_rsa_challenge(self, challenge_id, difficulty, flag, description):
        plaintext_to_encrypt = flag.encode('utf-8'); message_source = "flag"
        encrypted_message_bytes = self.rsa_manager.encrypt(plaintext_to_encrypt, self.public_key_pem)
        encrypted_message_str = base64.b64encode(encrypted_message_bytes).decode('ascii')
        hints = ["Asymmetric encryption.", "Public key provided.", "Factorization?"]
        return {"id": challenge_id, "type": "rsa", "description": description or f"Decrypt RSA ({difficulty}).", "public_key": self.public_key_pem, "flag": flag, "encrypted_message": encrypted_message_str, "hints": hints, "message_source": message_source}

    def _create_xor_challenge(self, challenge_id, difficulty, flag, description, message_param):
        key_length = 4 if difficulty == "easy" else 8 if difficulty == "medium" else len(flag)
        key = self.generator.generate_random_data(key_length)
        plaintext = flag; message_source = "flag"
        if message_param: plaintext = message_param; message_source = "admin_message"
        plaintext_bytes = str(plaintext).encode('utf-8', errors='ignore')
        encrypted_bytes = bytes([p_byte ^ key[i % len(key)] for i, p_byte in enumerate(plaintext_bytes)])
        encrypted_message_str = base64.b64encode(encrypted_bytes).decode('ascii')
        hints = ["XOR is its own inverse.", f"Key length might be {key_length} bytes."]
        return {"id": challenge_id, "type": "xor", "description": description or f"Break XOR ({difficulty}).", "key_used": base64.b64encode(key).decode('ascii'), "flag": flag, "encrypted_message": encrypted_message_str, "hints": hints, "message_source": message_source}

    def _create_hash_challenge(self, challenge_id, difficulty, flag, description, message_param):
        hash_types = {"easy": "md5", "medium": "sha256", "hard": "sha512"}
        hash_type = hash_types[difficulty]
        data_to_hash = flag; message_source = "flag"
        hasher = getattr(hashlib, hash_type)(); hasher.update(str(data_to_hash).encode('utf-8'))
        hashed_value = hasher.hexdigest()
        hints = [f"Hash is {hash_type.upper()}.", "Password lists?", "Online crackers?"]
        return {"id": challenge_id, "type": "hash", "description": description or f"Crack {hash_type.upper()} hash ({difficulty}).", "hash_type": hash_type, "encrypted_message": hashed_value, "flag": flag, "hints": hints, "message_source": message_source}

    def _create_web_challenge(self, challenge_id, difficulty, flag, description):
        vuln_types = {"easy": ["xss", "sqli_basic"], "medium": ["csrf", "sqli_blind", "xxe"], "hard": ["rce", "ssrf", "deserialization"]}
        vuln_type = random.choice(vuln_types[difficulty]); hints = [f"Look for {vuln_type.upper()}.", "Check inputs/outputs.", "Inspect source."]
        return {"id": challenge_id, "type": "web", "vuln_type": vuln_type, "description": description or f"Exploit web vulnerability ({difficulty})", "flag": flag, "hints": hints, "encrypted_message": "Find flag on target."}

    def _create_binary_challenge(self, challenge_id, difficulty, flag, description):
        vuln_types = {"easy": ["buffer_overflow", "format_string"], "medium": ["heap_overflow", "use_after_free"], "hard": ["rop_chain", "return_to_libc"]}
        vuln_type = random.choice(vuln_types[difficulty]); hints = [f"{vuln_type.replace('_', ' ')}?", "Use gdb/radare2/IDA.", "Memory layout?"]
        return {"id": challenge_id, "type": "binary", "vuln_type": vuln_type, "description": description or f"Exploit binary ({difficulty})", "flag": flag, "hints": hints, "encrypted_message": "Retrieve flag via exploit."}

    def _create_forensics_challenge(self, challenge_id, difficulty, flag, description):
        types = {"easy": ["file_recovery", "metadata"], "medium": ["network_pcap", "memory_dump"], "hard": ["disk_image", "encrypted_fs"]}
        forensics_type = random.choice(types[difficulty]); hints = [f"{forensics_type.replace('_', ' ')}?", "Use Autopsy/Volatility/Wireshark.", "Hidden data?"]
        return {"id": challenge_id, "type": "forensics", "forensics_type": forensics_type, "description": description or f"Solve forensics ({difficulty})", "flag": flag, "hints": hints, "encrypted_message": "Find flag in artifact."}

    def _create_stego_challenge(self, challenge_id, difficulty, flag, description):
        hints = ["Metadata (exiftool)?", "LSBs (zsteg, steghide)?", "Stego tools/passwords?"]
        return {"id": challenge_id, "type": "stego", "description": description or f"Find hidden flag ({difficulty})", "flag": flag, "encrypted_message": "Hidden in file", "hints": hints}

    def _create_reversing_challenge(self, challenge_id, difficulty, flag, description):
        hints = ["Disassembler/debugger?", "Interesting strings?", "Algorithm?"]
        return {"id": challenge_id, "type": "reversing", "description": description or f"Reverse engineer ({difficulty})", "flag": flag, "encrypted_message": "Hidden in binary", "hints": hints}

    def _create_pwn_challenge(self, challenge_id, difficulty, flag, description):
        hints = ["Overflows?", "Format strings?", "Bypass NX/ASLR/PIE?", "Gain control?"]
        return {"id": challenge_id, "type": "pwn", "description": description or f"Exploit binary ({difficulty})", "flag": flag, "encrypted_message": "Exploit for flag", "hints": hints}

    def _adjust_difficulty(self, challenge_id, user_id, solved):
        print(f"Placeholder: Adjusting difficulty for challenge '{challenge_id}' for user '{user_id}'. Solved: {solved}")
