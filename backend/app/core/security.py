"""Senhas e tokens de sessão — stdlib apenas (PDF/PBKDF2), sem dependência extra."""

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 200_000


def hash_password(senha: str) -> str:
    """Retorna hash no formato `pbkdf2_sha256$iterations$salt_hex$digest_hex`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", senha.encode(), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(senha: str, senha_hash: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = senha_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode(),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(computed, expected)


def gerar_token_sessao() -> str:
    """Token opaco de sessão entregue ao cliente (nonce desconectado do hash)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash que fica armazenado em `usuario_sessao.token_hash` (não guardamos o token)."""
    return hashlib.sha256(token.encode()).hexdigest()