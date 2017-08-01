from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *
import time

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    
    #query user's portfolio
    rowsPF = db.execute("SELECT * FROM portfolio WHERE id = :id", id = session["user_id"])
    
    #lookup each stock's info
    total = 0
    stocks = []
        
    for row in rowsPF:
        obj = {}
        obj["stock"] = row["stock"]
        obj["shares"] = row["shares"]
        info = lookup(row["stock"])
        price = info["price"]
        obj["price"] = price
        sub_total = row["shares"] * price
        obj["sub_total"] = usd(sub_total)
        stocks.append(obj)
        total += sub_total
    
    #retrieve user's cash balance    
    rowsUser = db.execute("SELECT * FROM users WHERE id = :id", id = session["user_id"])
    
    equity = rowsUser[0]["cash"] + total

    return render_template("index.html", user=rowsUser[0]["username"], stocks=stocks, total=usd(total), cash=usd(rowsUser[0]["cash"]), equity=usd(equity))

@app.route("/acount", methods=["GET", "POST"])
@login_required
def account():
    """Add cash to balance."""
    
    #if POST method
    if request.method == "POST":
        
        #query the user's data
        id = session["user_id"]
        rowsUser = db.execute("SELECT * FROM users where id=:id", id = id)
        
        #update the user's cash balance
        cash = int(request.form.get("cash"))
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash = rowsUser[0]["cash"] + cash, id=id)
        
        # thanks to https://www.tutorialspoint.com/python3/python_date_time.htm   for the time code snippet
        localtime = time.asctime( time.localtime(time.time()) )
        
        #update transaction history table        
        db.execute("INSERT INTO transactions (id, buy_sell, price, time) VALUES(:id, :buy_sell, :price, :time)",
            id = id, buy_sell = "Cash", price = cash, time = localtime)

        return redirect(url_for("index"))
            
    # if GET method
    else:
        rowsUser = db.execute("SELECT * FROM users where id=:id", id = session["user_id"])
        return render_template("add_cash.html", balance=usd(rowsUser[0]["cash"]))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    
    # if POST method
    if request.method == "POST":
        
        #check if the stock exists
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("symbol is not valid or could not retrieve data")
        
        shares = int(request.form.get("shares"))
        purchase = stock["price"] * shares

        #check if the user has sufficient funds
        id = session["user_id"]
        rowsUser = db.execute("SELECT * FROM users WHERE id = :id", id = id )
        
        cash = rowsUser[0]["cash"]
        if cash < purchase:
            return apology("insufficient funds for transaction")
            
        localtime = time.asctime( time.localtime(time.time()) )
        
        #update transaction history table        
        db.execute("INSERT INTO transactions (id, stock, buy_sell, shares, price, time) VALUES(:id, :stock, :buy_sell, :shares, :price, :time)",
            id = id, stock = stock["symbol"], buy_sell = "Buy", shares = shares, price = stock["price"], time = localtime)
        
        # if user already owns this stock, update the record
        rowsPF = db.execute("SELECT * FROM portfolio WHERE id = :id AND stock = :symbol", id = id, symbol = stock["symbol"])
        #rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rowsPF) > 0:
            db.execute("UPDATE portfolio SET shares = :shares WHERE id = :id AND stock = :stock", 
                shares = rowsPF[0]["shares"] + shares, id = id, stock = stock["symbol"])
        
        # otherwise insert new stock to portfolio table
        else:
            db.execute("INSERT INTO portfolio (id, stock, shares) VALUES(:id, :stock, :shares)",
                id = id, stock = stock["symbol"], shares = shares)
                
        #update the cash position
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = cash - purchase, id = id)
        
        # render the successful result
        return render_template("bought.html", name=stock["name"], symbol=stock["symbol"], price=stock["price"],
            shares=shares, total=usd(stock["price"]*shares), buy_sell="Buy", time = localtime)
        
    # if GET method    
    else: 
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    
    #query user's transactions table
    rowsT = db.execute("SELECT * FROM transactions WHERE id = :id", id = session["user_id"])
    
    return render_template("history.html", stocks=rowsT)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    # if POST method
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))
        
        # check for error in symbol
        if quote == None:    #None is equivalent to Null in other languages
            return apology("symbol is not valid or could not retrieve data")
        
        # render a new page
        return render_template("quoted.html", name=quote["name"], price=usd(quote["price"]), symbol=quote["symbol"])
    
    # if GET method    
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    # forget any user_id
    session.clear()
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")
        
        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure both passwrds match
        elif request.form.get("password") != request.form.get("retyped"):
            return apology("passwords must match")
        
        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        
        # ensure username does not already exist
        if len(rows) > 0:
            return apology("that username already exists!")
            
        # encrypt password into hash
        hashed = pwd_context.hash(request.form.get("password"))
        
        # insert the user info into database
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
            username=request.form.get("username"), hash=hashed)
        
        # re-query database for id
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        
        # remember which user has logged in
        session["user_id"] = rows[0]["id"]
        
        localtime = time.asctime( time.localtime(time.time()) )
        
        #update transaction history table        
        db.execute("INSERT INTO transactions (id, buy_sell, price, time) VALUES(:id, :buy_sell, :price, :time)",
            id = session["user_id"], buy_sell = "Account Opening Bonus", price = 10000, time = localtime)
        
        # redirect user to home page
        return redirect(url_for("index"))
    
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")
        

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    
    # if POST method
    if request.method == "POST":
        
        #check if the stock exists
        stock = lookup(request.form.get("symbol"))
        if stock == None:
            return apology("symbol is not valid or could not retrieve data")
            
        #check if user owns the stock
        id = session["user_id"]
        rowsPF = db.execute("SELECT * FROM portfolio WHERE id = :id AND stock = :stock", id = id, stock=stock["symbol"])
        if len(rowsPF) == 0:
            return apology("you do not own this stock")
            
            
        shares = int(request.form.get("shares"))
        sale = stock["price"] * shares

        #retrieve user's cash balance
        rowsUser = db.execute("SELECT * FROM users WHERE id = :id", id = id )
        cash = rowsUser[0]["cash"]
        
        #check the user has greater than or equal number of shares available to sell
        if rowsPF[0]["shares"] < shares:
            return apology("you are trying to sell more shares than you own")
        
            
        localtime = time.asctime( time.localtime(time.time()) )
        
        #update transaction history table        
        db.execute("INSERT INTO transactions (id, stock, buy_sell, shares, price, time) VALUES(:id, :stock, :buy_sell, :shares, :price, :time)",
            id = id, stock = stock["symbol"], buy_sell = "Sell", shares = shares, price = stock["price"], time = localtime)
        
        # update the portfolio
        db.execute("UPDATE portfolio SET shares = :shares WHERE id = :id AND stock = :stock", 
            shares = rowsPF[0]["shares"] - shares, id = id, stock = stock["symbol"])
        
        #update the cash position
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = cash + sale, id = id)
        
        # render the successful result
        return render_template("sold.html", name=stock["name"], symbol=stock["symbol"], price=stock["price"],
            shares=shares, total=usd(stock["price"]*shares), buy_sell="Sell", time = localtime)
        
    # if GET method    
    else: 
        return render_template("sell.html")
