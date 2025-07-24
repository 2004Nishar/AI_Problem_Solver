import os
import sys
import uuid
import subprocess
from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
from dotenv import load_dotenv, set_key
from register import register_db
import sqlite3
import re
from datetime import timedelta

# Initialize app and generative model
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Session lifetime (30 minutes)
app.permanent_session_lifetime = timedelta(minutes=30)

# Difficulty levels
DIFFICULTY_ORDER = ["basic", "intermediate", "advanced"]

# Database connection utility
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row  # Optional: returns rows as dictionaries
    return conn
# Helper function to check password strength
def is_password_strong(password):
    if len(password) < 8:
        return False
    if not re.search(r"[A-Za-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True
# Generate problem
def generate_problem(level="basic"):
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    prompt = f"Give a {level} Python programming problem only. No solution, no explanation."
    response = model.generate_content(prompt)
    return response.text.strip()
# Check solution
def check_solution(problem, user_code):
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    prompt = f"Problem:\n{problem}\n\nUser's Solution:\n{user_code}\n\nIs this code correct? Answer with YES or NO. If NO, provide the correct solution and a short explanation."
    response = model.generate_content(prompt)
    return response.text.strip()
# Next difficulty level
def next_level(current):
    try:
        index = DIFFICULTY_ORDER.index(current)
        return DIFFICULTY_ORDER[min(index + 1, len(DIFFICULTY_ORDER) - 1)]
    except ValueError:
        return "basic"
# Routes for Flask
@app.route("/")
def index():
    return render_template("login.html")

@app.route('/register', methods=['POST'])
def register():
    data = request.json

    full_name = data.get('fullName')
    email = data.get('email')
    api_key = data.get('apiKey')
    password = data.get('password')



    if not full_name or not email or not api_key or not password:
        return jsonify({"error": "All fields are required."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    # Check password strength
    if not is_password_strong(password):
        return jsonify({"error": "Password is too weak. It must be at least 8 characters long and include numbers and special characters."}), 400

    # Hash password
    hashed_password = generate_password_hash(password)

    # Insert into database
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (full_name, email, api_key, password)
            VALUES (?, ?, ?, ?)
        ''', (full_name, email, api_key, hashed_password))
        conn.commit()
        return jsonify({"message": "Registration successful!"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists."}), 400
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user and check_password_hash(user['password'], password):
        session.permanent = True
        session['user_email'] = email
        session['user_name'] = user['full_name']

        user_api_key = user['api_key']
        set_key('.env', 'GEMINI_API_KEY', user_api_key)
        os.environ['GEMINI_API_KEY'] = user_api_key

        # ✅ Reload .env and reconfigure Gemini
        load_dotenv(override=True)
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

        return jsonify({"message": "Login successful!"}), 200
    else:
        return jsonify({"error": "Invalid email or password."}), 401

@app.route('/register', methods=['GET'])
def show_register_page():
    return render_template('register.html')

@app.route('/login', methods=['GET'])
def show_login_page():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('show_login_page'))  # Safer fallback

    return render_template("dashboard.html", 
                           email=session.get('user_email'),
                           name=session.get('user_name'))



@app.route('/logout')
def logout():
    session.pop('user_email', None)  # Remove user from session
    flash("You have been logged out.", 'info')
    return redirect(url_for('login'))

@app.route("/next-problem", methods=["POST"])
def next_problem():
    level = request.form.get("level", "basic")
    topic = request.form.get("topic", "").strip()

    if topic:
        prompt = (
            f"Generate a {level} Python programming problem based on '{topic}'. "
            f"Ensure the problem is **self-contained**: include any required variables or data like a DataFrame or list. "
            "Only return the problem, no solution or explanation."
        )
    else:
        prompt = (
            f"Generate a {level} Python programming problem. "
            "Ensure the problem is self-contained: include any required variables or data. "
            "Only return the problem, no solution or explanation."
        )

    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    response = model.generate_content(prompt)
    problem = response.text.strip()

    return jsonify({"problem": problem, "level": level})

@app.route("/solution", methods=["POST"])
def show_solution():
    problem = request.form.get("problem", "")
    if not problem:
        return jsonify({"solution": "⚠️ No problem provided."})

    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")
    prompt = f"Provide only the correct Python solution for this problem:\n\n{problem}\n\nwith explanation."
    response = model.generate_content(prompt)
    solution = response.text.strip()

    return jsonify({"solution": solution})

@app.route("/submit-solution", methods=["POST"])
def submit_solution():
    user_code = request.form.get("code")
    problem = request.form.get("problem")
    level = request.form.get("level", "basic")

    feedback = check_solution(problem, user_code)
    correct = "YES" in feedback.upper()

    result = {
        "correct": correct,
        "feedback": feedback,
        "next_level": next_level(level) if correct else level
    }
    return jsonify(result)

@app.route("/run", methods=["POST"])
def run_code():
    code = request.form.get("code")
    file_id = str(uuid.uuid4())
    filename = f"runtime/{file_id}.py"

    with open(filename, "w") as f:
        f.write(code)

    try:
        output = subprocess.check_output(
            [sys.executable, filename], 
            stderr=subprocess.STDOUT,
            timeout=5, 
            universal_newlines=True
        )
    except subprocess.CalledProcessError as e:
        output = e.output
    except subprocess.TimeoutExpired:
        output = "⏰ Execution timed out."
    except Exception as e:
        output = f"❌ Error: {str(e)}"

    os.remove(filename)
    return jsonify({"output": output})

# Validate user credentials
# Function to validate user credentials for login
def validate_user(email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[0], password):  # Use werkzeug's check_password_hash
        return True
    return False

if __name__ == "__main__":
    app.run(debug=True)
