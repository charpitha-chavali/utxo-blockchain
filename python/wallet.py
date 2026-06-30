"""
wallet.py
---------
Handles key generation, addresses, and signing for the UTXO blockchain.

Every wallet has:
  - a private key (kept secret, used to sign transactions)
  - a public key (derived from private key)
  - an address (a hash of the public key -- this is what people send coins to)

Using real elliptic-curve cryptography (SECP256k1, same curve as Bitcoin)
means nobody can spend coins from your address unless they have your
private key. This is the core defense against "someone forges a
transaction that spends my money".
"""

import hashlib
import json
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_pubkey_to_address(pubkey_hex: str) -> str:
    """Derive a short 'address' from a public key (like Bitcoin does)."""
    sha = hashlib.sha256(pubkey_hex.encode()).digest()
    ripemd = hashlib.new('ripemd160', sha).hexdigest()
    return "UX" + ripemd  # 'UX' prefix just to make addresses recognizable


class Wallet:
    def __init__(self, name: str):
        self.name = name
        self._sk = SigningKey.generate(curve=SECP256k1)
        self._vk = self._sk.get_verifying_key()
        self.public_key = self._vk.to_string().hex()
        self.address = hash_pubkey_to_address(self.public_key)

    def sign(self, message: str) -> str:
        """Sign a message (e.g. a transaction hash) with the private key."""
        return self._sk.sign(message.encode()).hex()

    @staticmethod
    def verify(public_key_hex: str, message: str, signature_hex: str) -> bool:
        """Verify a signature was produced by the holder of public_key_hex."""
        try:
            vk = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
            return vk.verify(bytes.fromhex(signature_hex), message.encode())
        except (BadSignatureError, ValueError, Exception):
            return False
