import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
#app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
API_KEY = "pk_3983705aee9749499208c461bda5b9f3"
#if not os.environ.get("API_KEY"):
if not API_KEY:
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Find stocks that current user owns
    rows = db.execute("SELECT symbol, name, shares FROM portfolio WHERE users_id = :user_id ORDER BY symbol",
            user_id=session["user_id"])

    cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])[0]["cash"]

    stock_data = []     # creating an empty list
    combi_total = 0

    for row in rows:
        stock_info = {}
        stock_info["symbol"] = row["symbol"]
        stock_info["name"] = row["name"]
        stock_info["shares"] = row["shares"]
        stock_info["price"] = round(lookup(row["symbol"])["price"], 2)
        stock_info["total"] = round(stock_info["price"] * stock_info["shares"], 2)
        combi_total += stock_info["total"]

        stock_data.append(stock_info)

    balance = cash + combi_total
    balance = usd(balance)
    cash = usd(cash)

    # Calculate value of stocks using current share prices
    return render_template("/index.html", balance=balance, stock_data=stock_data, cash=cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    action = "BUY"
    if request.method == "GET":
        return render_template("/buy.html")
    else:
        buy_symbol = request.form.get("buy_symbol")
        num_shares = int(request.form.get("buy_shares"))

        # Check symbol is not blank and that symbol exists
        if not buy_symbol:
            return apology("Stock symbol is required")

        elif lookup(buy_symbol) == None:
            return apology("Stock symbol does not exist")

        # Check number of shares is a positive number
        elif num_shares <= 0:
            return apology("Number of shares must be positive and whole number")

        user_id = session["user_id"]
        stock_data = lookup(buy_symbol)
        current_price = round(stock_data["price"], 2)
        stock_symbol = stock_data["symbol"]
        stock_name = stock_data["name"]

        # Check if user has enough cash for requested share purchase
        row = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)
        current_cash = row[0]["cash"]
        share_cost = current_price * num_shares

        if current_cash - share_cost < 0:
            return apology("Not enough cash to complete transcation")
        balance = current_cash - share_cost

        # Generating timestramp for purchase
        dt = datetime.datetime.now()

        # Check if a user already owns a particular stock
        user_stock_exists = db.execute("SELECT * FROM portfolio WHERE users_id = :user_id AND symbol = :symbol",
                            user_id = user_id, symbol = stock_symbol)
        if user_stock_exists:
            # Update existing values in Portoflio table
            db.execute("""UPDATE portfolio SET shares = shares + :new_shares, price = price + :new_price, total=total + :new_share_cost
                    WHERE users_id = :user_id AND symbol = :symbol""",
                    new_shares=num_shares, new_price=current_price, new_share_cost=share_cost, user_id=user_id, symbol=stock_symbol)
        else:
            # New stock symbol for user, create new entry in Portfolio table
            db.execute("INSERT INTO portfolio (users_id, symbol, name, shares, price, total)"
                    "VALUES (:user, :symbol, :name, :shares, :price, :total)",
                    user=user_id, symbol=stock_symbol, name=stock_name, shares=num_shares,
                    price=current_price, total=share_cost)

        # Write purchase data to Transactions table
        db.execute("INSERT INTO transactions (users_id, symbol, name, shares, action, price, total, timestamp)"
                    "VALUES (:user, :symbol, :name, :shares, :action, :price, :total, :dt)",
                    user=user_id, symbol=stock_symbol, name=stock_name, shares=num_shares, action=action,
                    price=current_price, total=share_cost, dt = dt)

        # Update cash column in Users table to equal balance
        db.execute("UPDATE users SET cash = :balance WHERE id = :id", balance=balance, id=user_id)

        # return to home (portfolio) page
        flash("Brought")
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query Transactions table
    user_id = session["user_id"]
    data = []
    rows = db.execute("SELECT * FROM transactions WHERE users_id = :user_id", user_id = user_id)

    for row in rows:
        temp_data = {}
        temp_data["symbol"] = row["symbol"]
        temp_data["name"] = row["name"]
        temp_data["shares"] = row["shares"]
        temp_data["action"] = row["action"]
        temp_data["price"] = row["price"]
        temp_data["total"] = round(row["total"], 2)
        temp_data["timestamp"] = row["timestamp"]

        data.append(temp_data)

    return render_template("/history.html", data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("/quote.html")
    else:

        # Lookup quoted price of symbol
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        return render_template("/quoted.html", stock_name = stock["name"], stock_symbol = stock["symbol"], stock_price = usd(stock["price"]))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("/register.html")
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirmation")

        # Ensure username was submitted
        if not username:
            return apology("Must provide username", 403)

        # Ensure password was submitted
        elif not password:
            return apology("Must provide password", 403)

        # Checking that same password has been typed twice
        if password != confirm:
            return apology("Sorry password does not match")
        else:

            # Check if username already exists in database
            rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)
            if len(rows) == 0:
                password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
                db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username=username, password=password)
                return redirect("/")
            else:
                return apology("Username already exists")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    action = "SELL"

    # Query Portfolio table to find existing symbols
    if request.method == "GET":
        rows = db.execute("SELECT symbol FROM portfolio WHERE users_id = :user_id", user_id = user_id)
        symbols = []

        for row in rows:
            symbol = {}
            symbol["symbol"] = row["symbol"]
            symbols.append(symbol)

        return render_template("/sell.html", symbols=symbols)

    else:
        sell_symbol = request.form.get("sell_symbol")
        num_shares = int(request.form.get("sell_shares"))

        # Check symbol is not blank and that symbol exists
        if not sell_symbol:
            return apology("Stock symbol is required")

        # Check number of shares is a positive number
        elif num_shares <= 0:
            return apology("Number of shares must be positive and whole number")

        # Check number is equal to or less than number of owned shares for selected stock
        total_shares = db.execute("SELECT shares FROM portfolio WHERE users_id = :user_id AND symbol = :symbol",
                    user_id = user_id, symbol = sell_symbol)[0]["shares"]

        if num_shares <= total_shares:

            dt = datetime.datetime.now()
            stock_data = lookup(sell_symbol)
            current_price = round(stock_data["price"], 2)
            share_value = current_price * num_shares
            stock_name = stock_data["name"]

            # Deduct shares from portfolio
            db.execute("""UPDATE portfolio SET shares = shares - :num_shares, price = price - :new_price, total=total - :share_value
                    WHERE users_id = :user_id AND symbol = :symbol""",
                    num_shares=num_shares, new_price=current_price, share_value=share_value, user_id=user_id, symbol=sell_symbol)

            if num_shares == total_shares:
                # Delete stock from Portfolio
                db.execute("DELETE FROM portfolio WHERE users_id = :user_id AND symbol = :symbol",
                    user_id=user_id, symbol=sell_symbol)

            # Updating Transaction table
            db.execute("""INSERT INTO transactions (users_id, symbol, name, shares, action, price, total, timestamp)
                    VALUES (:user, :symbol, :name, :shares, :action, :price, :total, :dt);""",
                    user=user_id, symbol=sell_symbol, name=stock_name, shares=num_shares, action=action,
                    price=current_price, total=share_value, dt = dt)

            # Adding share value back to cash in Users table
            db.execute("UPDATE users SET cash = cash + :share_value WHERE id = :id",
                    share_value=share_value, id=user_id)

            # Displays Portfolio
            flash("Sold")
            return redirect("/")

        else:
            return apology("Request exceeds number of shares owned")


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Add money to portfolio"""
    user_id = session["user_id"]
    dt = datetime.datetime.now()

    if request.method == "GET":
        return render_template("/deposit.html")
    else:
        deposit = int(request.form.get("deposit"))

        # Check deposit amount is not blank
        if not deposit:
            return apology("Deposit amount required")
        if deposit <= 0:
            return apology("Deposit amount must be a positive number")

        # Add deposit to Users table
        db.execute("UPDATE users SET cash = cash + :deposit WHERE id = :id",
                    deposit=deposit, id=user_id)

        # Add  deposit to Transactions table
        db.execute("""INSERT INTO transactions (users_id, symbol, name, shares, action, price, total, timestamp)
                    VALUES (:user, "DEPOSIT", "Account Deposit", 0, "DEPO", :price, :total, :dt);""",
                    user=user_id, price=deposit, total=deposit, dt = dt)

    # Redirecting to Portfolio
    flash("Cash Added")
    return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)