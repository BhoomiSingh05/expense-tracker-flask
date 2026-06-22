"""
Expense Tracker - Single-file Flask backend.
Only 3 files in this project: app.py (Python), index.html (HTML), style.css (CSS).
"""

import sqlite3
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DB = "expense_tracker.db"
CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Other"
]


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            expense_date TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()


def get_chart_data(user_id):
    """Fetch category-wise totals for the pie chart."""
    conn = get_db()

    rows = conn.execute(
        """
        SELECT category,
               SUM(amount) as total
        FROM expenses
        WHERE user_id=?
        GROUP BY category
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    labels = [row["category"] for row in rows]
    values = [row["total"] for row in rows]

    return labels, values


@app.route("/", methods=["GET"])
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    expenses = conn.execute(
        """
        SELECT *
        FROM expenses
        WHERE user_id=?
        ORDER BY expense_date DESC, id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    total = sum(e["amount"] for e in expenses)

    conn.close()

    chart_labels, chart_values = get_chart_data(session["user_id"])

    return render_template(
        "index.html",
        page="dashboard",
        expenses=expenses,
        total=total,
        categories=CATEGORIES,
        today=date.today().isoformat(),
        chart_labels=chart_labels,
        chart_values=chart_values
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return redirect(url_for("register"))

        conn = get_db()

        existing = conn.execute(
            "SELECT id FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if existing:
            flash("Username already taken.")
            conn.close()
            return redirect(url_for("register"))

        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password))
        )

        conn.commit()
        conn.close()

        flash("Registration successful. Please log in.")
        return redirect(url_for("login"))

    return render_template("index.html", page="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("home"))

        flash("Invalid username or password.")
        return redirect(url_for("login"))

    return render_template("index.html", page="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/add", methods=["POST"])
def add_expense():

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        amount = float(request.form["amount"])

        if amount <= 0:
            raise ValueError

    except (ValueError, KeyError):
        flash("Please enter a valid positive amount.")
        return redirect(url_for("home"))

    category = request.form.get("category", "")

    if category not in CATEGORIES:
        flash("Please select a valid category.")
        return redirect(url_for("home"))

    description = request.form.get("description", "").strip()
    expense_date = request.form.get("expense_date") or date.today().isoformat()

    conn = get_db()

    conn.execute(
        """
        INSERT INTO expenses
        (user_id, amount, category, description, expense_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            amount,
            category,
            description,
            expense_date
        )
    )

    conn.commit()
    conn.close()

    flash("Expense added.")
    return redirect(url_for("home"))


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    conn.execute(
        "DELETE FROM expenses WHERE id=? AND user_id=?",
        (expense_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    flash("Expense deleted.")
    return redirect(url_for("home"))


# ==========================
# EDIT EXPENSE
# ==========================

@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    expense = conn.execute(
        """
        SELECT *
        FROM expenses
        WHERE id=? AND user_id=?
        """,
        (expense_id, session["user_id"])
    ).fetchone()

    if not expense:
        conn.close()
        flash("Expense not found.")
        return redirect(url_for("home"))

    if request.method == "POST":

        try:
            amount = float(request.form["amount"])

            if amount <= 0:
                raise ValueError

        except (ValueError, KeyError):
            conn.close()
            flash("Invalid amount.")
            return redirect(
                url_for("edit_expense", expense_id=expense_id)
            )

        category = request.form.get("category", "")

        if category not in CATEGORIES:
            conn.close()
            flash("Please select a valid category.")
            return redirect(
                url_for("edit_expense", expense_id=expense_id)
            )

        description = request.form.get("description", "").strip()
        expense_date = request.form.get("expense_date") or expense["expense_date"]

        conn.execute(
            """
            UPDATE expenses
            SET amount=?,
                category=?,
                description=?,
                expense_date=?
            WHERE id=? AND user_id=?
            """,
            (
                amount,
                category,
                description,
                expense_date,
                expense_id,
                session["user_id"]
            )
        )

        conn.commit()
        conn.close()

        flash("Expense updated successfully.")
        return redirect(url_for("home"))

    conn.close()

    return render_template(
        "index.html",
        page="edit",
        expense=expense,
        categories=CATEGORIES
    )


# ==========================
# PIE CHART DATA API
# ==========================

@app.route("/chart-data")
def chart_data():

    if "user_id" not in session:
        return jsonify({})

    labels, values = get_chart_data(session["user_id"])

    return jsonify({"labels": labels, "values": values})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
