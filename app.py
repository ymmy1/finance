import os

from cs50 import SQL
# import sqlite3
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
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")
# db = sqlite3.connect('finance.db')

bought = 0
sold = 0
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])

    history = " ".join((user[0]["username"], "history"))
    db.execute("CREATE TABLE IF NOT EXISTS :history ('id' INTEGER PRIMARY KEY NOT NULL, 'Symbol' TEXT, 'Name' TEXT, 'Shares' INTEGER, 'Price' INTEGER, 'Time' TEXT)", history=history)

    db.execute("CREATE TABLE IF NOT EXISTS :username ('id' INTEGER PRIMARY KEY NOT NULL, 'Status' TEXT, 'Symbol' TEXT, 'Name' TEXT, 'Shares' INTEGER, 'Price' INTEGER, 'TOTAL' INTEGER)", username = user[0]["username"])
    rows = db.execute("SELECT * FROM :id ORDER BY id DESC", id=user[0]["username"])
    db.execute("INSERT OR REPLACE INTO :username (id, Symbol, TOTAL) VALUES ('1','CASH', :cash)", username=user[0]["username"],cash=user[0]["cash"])


    if not rows:
        rows = db.execute("SELECT * FROM :id ORDER BY id DESC", id=user[0]["username"])
        rows[0].update({"TOTAL" : usd(rows[0]["TOTAL"])})
        return render_template("index.html", username=user[0]["username"], total=usd(user[0]["cash"]), rows_len=int(len(rows)), rows=rows)
    total = 0
    for i in range(0, len(rows), 1):
        if rows[i]["Symbol"] != 'CASH':
            stock = lookup(rows[i]["Symbol"])
            newtotal = stock["price"] * rows[i]["Shares"]
            theid = rows[i]["id"]
            db.execute("UPDATE :username SET Status = :status, Symbol = :symbol, Name = :name, Price = :price, TOTAL =:newtotal WHERE id =:theid",
                    username=user[0]["username"], status=stock["status"], symbol=stock["symbol"], name=stock["name"], price=stock["price"], newtotal=newtotal, theid=theid)

        total = total + rows[i]["TOTAL"]
        if rows[i]["Price"]:
            rows[i].update({"Price" : usd(rows[i]["Price"])})
        rows[i].update({"TOTAL" : usd(rows[i]["TOTAL"])})

    total = usd(total)
    global  bought
    bstatus = bought
    bought = 0
    global  sold
    sstatus = sold
    sold = 0
    return render_template("index.html", username=user[0]["username"], total=total, rows_len=int(len(rows)), rows=rows, bought=bstatus, sold=sstatus)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    scene = 0
    row = db.execute("SELECT * FROM users WHERE id = :id",
                    id = session["user_id"])
    if request.method == "GET":

        return render_template("buy.html", username=row[0]["username"], scene=scene)

    else:
        symbol = lookup(request.form.get("symbol"))
        if symbol == None:

            scene = 1
            return render_template("buy.html", username=row[0]["username"], scene=scene)
        shares = request.form.get("shares")
        if shares == "" or int(shares) < 1:
            scene=1
            return render_template("buy.html", username=row[0]["username"], scene=scene)
        toPay = symbol["price"] * int(shares)
        if row[0]["cash"] < toPay:
            scene = 1
            return render_template("buy.html", username=row[0]["username"], scene=scene)
        cash = row[0]["cash"] - toPay
        db.execute("CREATE TABLE IF NOT EXISTS :username ('id' INTEGER PRIMARY KEY NOT NULL, 'Status' TEXT, 'Symbol' TEXT, 'Name' TEXT, 'Shares' INTEGER, 'Price' INTEGER, 'TOTAL' INTEGER)", username = row[0]["username"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=cash, id = session["user_id"])
        db.execute("INSERT OR REPLACE INTO :username (id, Symbol, TOTAL) VALUES ('1','CASH', :cash)", username=row[0]["username"],cash=cash)

        stocks = db.execute("SELECT Symbol, Shares, TOTAL from :username", username=row[0]["username"])

        exists = 0
        history = " ".join((row[0]["username"], "history"))
        for i in range(0, len(stocks), 1):
            if stocks[i]["Symbol"] and stocks[i]["Symbol"] == symbol["symbol"]:
                db.execute("UPDATE :username SET Shares = :newshares, TOTAL = :newtotal WHERE Symbol = :symbol",
                    username=row[0]["username"], newshares= int(shares)+stocks[i]["Shares"], newtotal=(stocks[i]["Shares"] + int(shares))*symbol["price"], symbol=symbol["symbol"])
                exists = 1

        if not exists:
            db.execute("INSERT INTO :username (Status,Symbol, Name, Shares, Price, TOTAL) VALUES (:status, :symbol, :name, :shares, :price, :total)",
                        username=row[0]["username"], status=symbol["status"], symbol=symbol["symbol"], name=symbol["name"], shares=int(shares), price=symbol["price"], total=toPay)

        global  bought
        bought = 1
        db.execute("INSERT INTO :history (Symbol, Name, Shares, Price, Time) VALUES (:symbol, :name, :shares, :price, datetime('now','localtime'))",
                    history=history, symbol=symbol["symbol"], name=symbol["name"], shares=int(shares), price=symbol["price"])
        return redirect('/')


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
    history = " ".join((user[0]["username"], "history"))
    rows = db.execute("SELECT * FROM :history ORDER BY id DESC", history=history)

    return render_template("history.html", username=user[0]["username"], rows=rows)


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
    post = 0
    username = db.execute("SELECT * FROM users WHERE id = :id",
                          id = session["user_id"])
    """Get stock quote."""
    if request.method == "POST":
        result = lookup(request.form.get("Symbol"))
        if result == None:
            post = 2
            return render_template("quote.html", username=username[0]["username"], post=post)
        name = result["name"]
        symbol = result["symbol"]
        price = result["price"]
        post = 1
        return render_template("quote.html", username=username[0]["username"], post=post, name=name, symbol=symbol, price=price)


    return render_template("quote.html", username=username[0]["username"], post=post)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        if len(rows) != 0 :
            return apology("this username is taken :(", 403)

        pas1 = request.form.get("password")
        pas2 = request.form.get("confirmPassword")
        if pas1 != pas2:
            pas1 = ""
            pas2 = ""
            return apology("passwords don't match", 403)

        pas1 = ""
        pas2 = ""
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                    username=request.form.get("username"),
                    password=generate_password_hash(request.form.get("password")))

        row = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = row[0]["id"]

        # Redirect user to home page
        return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
    rows = db.execute("SELECT * FROM :username", username=user[0]["username"])
    if request.method == "GET":
        return render_template("sell.html", username=user[0]["username"], rows=rows)

    history = " ".join((user[0]["username"], "history"))
    for i in range(0, len(rows), 1):
        this_user = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
        stock_name = rows[i]["Symbol"]
        shares_num = request.form.get(rows[i]["Symbol"])
        if shares_num and int(shares_num) > 0:
            shares_num = int(shares_num)
            update = lookup(stock_name)
            total = update["price"] * shares_num
            db.execute("UPDATE :username SET Shares = :newshares WHERE Symbol = :symbol",
                        username=user[0]["username"], newshares= rows[i]["Shares"] - shares_num, symbol=rows[i]["Symbol"])
            db.execute("UPDATE users SET cash = :newcash WHERE username = :username",
                        newcash=this_user[0]["cash"] + total, username=user[0]["username"])

            db.execute("INSERT INTO :history (Symbol, Name, Shares, Price, Time) VALUES (:symbol, :name, :shares, :price, datetime('now','localtime'))",
                    history=history, symbol=update["symbol"], name=update["name"], shares=0-int(shares_num), price=update["price"])

            if int(rows[i]["Shares"]) == shares_num:
                db.execute("DELETE FROM :username WHERE Symbol = :symbol",
                            username=user[0]["username"], symbol=rows[i]["Symbol"])
    cash = db.execute("SELECT cash FROM users WHERE id = :id", id = session["user_id"])
    db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash=cash[0]["cash"], id = session["user_id"])
    db.execute("INSERT OR REPLACE INTO :username (id, Symbol, TOTAL) VALUES ('1','CASH', :cash)", username=user[0]["username"], cash=cash[0]["cash"])

    global  sold
    sold = 1

    return redirect("/")





def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
    