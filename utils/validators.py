import re

def is_valid_email(email):
    # Basit ve yaygın kullanılan e-posta regex'i
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
    return re.match(pattern, email) is not None
