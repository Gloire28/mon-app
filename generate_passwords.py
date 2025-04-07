# generate_passwords.py
from werkzeug.security import generate_password_hash

users = ['Juste', 'Kevine', 'Joseph', 'Gamal', 'Eme', 'Spero', 'Gloir']
for user in users:
    password = "password123" 
    hashed_password = generate_password_hash(password)
    print(f"{user}: {hashed_password}")