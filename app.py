import os

import requests

from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

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
# db = SQL("sqlite:///finance.db")

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))
# db = sqlite3.connect('finance.db')

# Creating users
db.execute("CREATE TABLE IF NOT EXISTS users(id serial PRIMARY KEY NOT NULL,username VARCHAR (10) UNIQUE NOT NULL,hash VARCHAR (150) NOT NULL, cash NUMERIC NOT NULL DEFAULT 10000.00)")
db.commit()

bought = 0
sold = 0
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user = db.execute("SELECT * FROM users WHERE (id = :id)", {"id": session["user_id"]}).fetchall()

    history = "_".join((user[0]["username"], "history"))
    db.execute("CREATE TABLE IF NOT EXISTS "+history+" (id serial PRIMARY KEY NOT NULL, symbol TEXT, name TEXT, shares INTEGER, price INTEGER, Time TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS "+user[0]['username']+" (id serial PRIMARY KEY, status TEXT, symbol TEXT, name TEXT, shares INTEGER, price INTEGER, total INTEGER)")
    db.commit()

    # db.execute("INSERT OR REPLACE INTO "+user[0]['username']+" (id, symbol, total) VALUES ('1','CASH', :cash)", { "cash": user[0]["cash"]})
    db.execute("INSERT INTO "+user[0]['username']+" (id, symbol, total) VALUES ('0','CASH', :cash) ON CONFLICT (id) DO UPDATE SET total = :cash",{"cash": user[0]["cash"]} )
    db.commit()

    rows = db.execute("SELECT * FROM "+user[0]['username']+" ORDER BY id DESC").fetchall()

    total = 0
    for i in range(0, len(rows), 1):
        if rows[i]["symbol"] != 'CASH':
            stock = lookup(rows[i]["symbol"])
            newtotal = stock["price"] * rows[i]["shares"]
            theid = rows[i]["id"]
            db.execute("UPDATE "+user[0]['username']+" SET status = :status, symbol = :symbol, name = :name, price = :price, total =:newtotal WHERE (id = :theid)",
                    { "status": stock["status"], "symbol": stock["symbol"], "name": stock["name"], "price" : stock["price"], "newtotal" :newtotal, "theid": theid})
            db.commit()
        total = total + rows[i]["total"]
        # if rows[i]["price"]:
        #     # rows[i]["price"] = usd(rows[i]["price"])
        # # rows[i].update({"total" : usd(rows[i]["total"])})

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
    rows = db.execute("SELECT * FROM users WHERE (id = :id)",{"id" : session["user_id"]}).fetchall()
    if request.method == "GET":

        return render_template("buy.html", username=rows[0]["username"], scene=scene)

    else:
        symbol = lookup(request.form.get("symbol"))
        if symbol == None:
            scene = 1
            return render_template("buy.html", username=rows[0]["username"], scene=scene)

        shares = request.form.get("shares")
        if shares == "" or int(shares) < 1:
            scene=1
            return render_template("buy.html", username=rows[0]["username"], scene=scene)

        toPay = float(symbol["price"]) * int(shares)
        if rows[0]["cash"] < toPay:
            scene = 1
            return render_template("buy.html", username=rows[0]["username"], scene=scene)

        cash = float(rows[0]["cash"]) - toPay
        db.execute("UPDATE users SET cash = :cash WHERE (id = :id)", {"cash": cash, "id" : session["user_id"]})
        db.commit()

        stocks = db.execute("SELECT symbol, shares, total from "+rows[0]['username']+"").fetchall()

        exists = 0
        history = "_".join((rows[0]["username"], "history"))
        for i in range(0, len(stocks), 1):
            if stocks[i]["symbol"] and stocks[i]["symbol"] == symbol["symbol"]:
                db.execute("UPDATE "+rows[0]['username']+" SET shares = :newshares, total = :newtotal WHERE (symbol = :symbol)",
                    {"newshares": int(shares)+stocks[i]["shares"], "newtotal": (stocks[i]["shares"] + int(shares))*symbol["price"], "symbol": symbol["symbol"]})
                db.commit()
                exists = 1

        if not exists:
            db.execute("INSERT INTO "+rows[0]['username']+" (status,symbol, name, shares, price, total) VALUES (:status, :symbol, :name, :shares, :price, :total)",
                        {"status": symbol["status"], "symbol": symbol["symbol"], "name": symbol["name"], "shares": int(shares), "price": symbol["price"], "total": toPay})

        global  bought
        bought = 1
        db.execute("INSERT INTO "+history+" (symbol, name, shares, price, Time) VALUES (:symbol, :name, :shares, :price, now()::timestamp(0))",
                    {"symbol": symbol["symbol"], "name": symbol["name"], "shares": int(shares), "price": symbol["price"]})
        db.commit()
        return redirect('/')


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user = db.execute("SELECT * FROM users WHERE (id = :id)", {"id": session["user_id"]}).fetchall()
    history = "_".join((user[0]["username"], "history"))
    rows = db.execute("SELECT * FROM "+history+" ORDER BY id DESC").fetchall()

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
        username=request.form.get("username")
        rows = db.execute("SELECT * FROM users WHERE (username = :username)",
                            {"username": username}).fetchall()

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
    username = db.execute("SELECT * FROM users WHERE (id = :id)",
                          {"id": session["user_id"]}).fetchall()
    """Get stock quote."""
    if request.method == "POST":
        result = lookup(request.form.get("symbol"))
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
        
    # Query database for username
    username=request.form.get("username")
    rows = db.execute("SELECT * FROM users WHERE (username = :username)",
                            {"username": username}).fetchall()

    if len(rows) != 0 :
        return apology("this username is taken :(", 403)

    pas1 = request.form.get("password")
    pas2 = request.form.get("confirmPassword")
    if pas1 != pas2:
        # Reset passwords
        pas1 = ""
        pas2 = ""
        return apology("passwords don't match", 403)

    # Reset passwords
    pas1 = ""
    pas2 = ""

    
    password=generate_password_hash(request.form.get("password"))
    db.execute("INSERT INTO users (username, hash) VALUES(:username, :password)",
                {"username": username, "password": password})
    db.commit()


    rows = db.execute("SELECT * FROM users WHERE username = username").fetchall()

    # Remember which user has logged in
    session["user_id"] = rows[0]["id"]

    # Redirect user to home page
    return redirect("/")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user = db.execute("SELECT * FROM users WHERE (id = :id)", {"id": session["user_id"]}).fetchall()
    rows = db.execute("SELECT * FROM "+user[0]['username']).fetchall()
    if request.method == "GET":
        return render_template("sell.html", username=user[0]["username"], rows=rows)

    history = "_".join((user[0]["username"], "history"))
    for i in range(0, len(rows), 1):
        this_user = db.execute("SELECT cash FROM users WHERE (id = :id)", {"id": session["user_id"]}).fetchall()
        stock_name = rows[i]["symbol"]
        shares_num = request.form.get(rows[i]["symbol"])
        if shares_num and int(shares_num) > 0:
            shares_num = float(shares_num)
            update = lookup(stock_name)
            total = float(update["price"]) * shares_num
            db.execute("UPDATE "+user[0]['username']+" SET shares = :newshares, total = :newtotal WHERE (symbol = :symbol)",
                        { "newshares": rows[i]["shares"] - shares_num, "newtotal" : rows[i]["total"] - total ,"symbol": rows[i]["symbol"]})
            db.execute("UPDATE users SET cash = :newcash WHERE (username = :username)",
                        {"newcash": float(this_user[0]["cash"]) + total, "username": user[0]["username"]})

            db.execute("INSERT INTO "+history+" (symbol, name, shares, price, Time) VALUES (:symbol, :name, :shares, :price, now()::timestamp(0))",
                    {"symbol": update["symbol"], "name": update["name"], "shares": 0-int(shares_num), "price": update["price"]})
            db.commit()

            if int(rows[i]["shares"]) == shares_num:
                db.execute("DELETE FROM  "+user[0]['username']+" WHERE (symbol = :symbol)",
                            {"symbol": rows[i]["symbol"]})
                db.commit()

    cash = db.execute("SELECT cash FROM users WHERE (id = :id)", {"id" : session["user_id"]}).fetchall()
    db.execute("UPDATE users SET cash = :cash WHERE (id = :id)", {"cash": cash[0]["cash"], "id" : session["user_id"]})
    db.commit()
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
    