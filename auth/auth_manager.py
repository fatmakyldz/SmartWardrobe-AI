import json
import os
from utils.validators import is_valid_email
from utils.hasher import hash_password, check_password

USERS_FILE = "data/users.json"

class AuthManager:

    def __init__(self):
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, "w") as f:
                json.dump([], f)

    def load_users(self):
        with open(USERS_FILE, "r") as f:
            return json.load(f)

    def save_users(self, users):
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=4)

    def is_username_taken(self, username):
        users = self.load_users()
        return any(user["username"] == username for user in users)

    def is_email_taken(self, email):
        users = self.load_users()
        return any(user["email"] == email for user in users)

    def register_user(self, username, email, password, confirm_password):
        if not username or not email or not password or not confirm_password:
            return False, "🚨 Please fill in all fields."
        
        if self.is_username_taken(username):
            return False, "⚠️ This username is already taken."

        if self.is_email_taken(email):
            return False, "📧 This email is already registered."

        if not is_valid_email(email):
            return False, "❌ Invalid email format."

        if password != confirm_password:
            return False, "🔐 Passwords do not match."

        hashed_pw = hash_password(password)
        new_user = {
            "username": username,
            "email": email,
            "password": hashed_pw
        }

        users = self.load_users()
        users.append(new_user)
        self.save_users(users)

        return True, "✅ Registration successful!"

    def login_user(self, email, password):
        users = self.load_users()
        for user in users:
            if user["email"] == email:
                if check_password(password, user["password"]):
                    return True, f"✅ Welcome back, {user['username']}!", user["username"]
                else:
                    return False, "🔐 Incorrect password.", None
        return False, "❌ Email not found.", None
