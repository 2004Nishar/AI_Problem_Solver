import sqlite3
from werkzeug.security import generate_password_hash

# Database setup: Create database and tables if they don't exist
def register_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    api_key TEXT NOT NULL,
                    password TEXT NOT NULL);
                ''')
    conn.commit()
    conn.close()


register_db()