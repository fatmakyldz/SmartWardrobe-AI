import hashlib

def hash_password(password):
    # Şifreyi SHA-256 ile şifreler
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(input_password, stored_hash):
    # Girilen şifreyi hash'leyip kayıtlı hash ile karşılaştır
    return hash_password(input_password) == stored_hash
