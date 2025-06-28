# app.py
import os
import uuid
import subprocess
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)

# Difficulty order
DIFFICULTY_ORDER = ["basic", "intermediate", "advanced"]

def generate_problem(level="basic"):
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")


    prompt = f"Give a {level} Python programming problem only. No solution, no explanation."
    response = model.generate_content(prompt)
    return response.text.strip()

def check_solution(problem, user_code):
    model = genai.GenerativeModel("models/gemini-1.5-flash-latest")


    prompt = (
        f"Problem:\n{problem}\n\n"
        f"User's Solution:\n{user_code}\n\n"
        "Is this code correct? Answer with YES or NO. If NO, provide the correct solution and a short explanation."
    )
    response = model.generate_content(prompt)
    return response.text.strip()

def next_level(current):
    try:
        index = DIFFICULTY_ORDER.index(current)
        return DIFFICULTY_ORDER[min(index + 1, len(DIFFICULTY_ORDER) - 1)]
    except ValueError:
        return "basic"

@app.route("/")
def index():
    return render_template("index.html")

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
            ["python", filename], stderr=subprocess.STDOUT,
            timeout=5, universal_newlines=True
        )
    except subprocess.CalledProcessError as e:
        output = e.output
    except subprocess.TimeoutExpired:
        output = "⏰ Execution timed out."
    except Exception as e:
        output = f"❌ Error: {str(e)}"

    os.remove(filename)
    return jsonify({"output": output})

if __name__ == "__main__":
    app.run(debug=True)