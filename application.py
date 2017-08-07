from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *
import time
import sqlite3

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

# configure SQLite database
conn = sqlite3.connect('finance.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()





@app.route("/")
@login_required
def index():
    
    #query user's portfolio
    # https://docs.python.org/3/library/sqlite3.html
    c.execute('SELECT * FROM portfolio WHERE id = ?', (session["user_id"],))
    rowsPF = c.fetchall()
    
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
    c.execute('SELECT * FROM users WHERE id = ?', (session["user_id"],))
    user = c.fetchone()
    
    equity = user["cash"] + total
    
    return render_template("index.html", user=user["username"], stocks=stocks, total=usd(total), cash=usd(user["cash"]), equity=usd(equity))







@app.route("/account")
@login_required
def account():
    """Display account management options."""
    
    c.execute('SELECT * FROM users WHERE id = ?', (session["user_id"],))
    user = c.fetchone()
    return render_template("account.html", user=user['username'], balance=usd(user['cash']))







@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Add funds to cash balance."""
    
    id = session["user_id"]

    #query the user's data
    c.execute("SELECT * FROM users WHERE id = ?", (id,))
    user = c.fetchone()
    
    #if POST method
    if request.method == "POST":
        
        # check for correct integer input
        userInput =  request.form.get("deposit")
        if not userInput.isdigit():
            return apology("Please enter only positive numbers")
        
        #update the user's cash balance
        deposit =  int(userInput)
        c.execute('UPDATE users SET cash = ? WHERE id = ?', (user["cash"] + deposit, id))

        #update transaction history table        
        c.execute("INSERT INTO transactions (id, buy_sell, price, time) VALUES(?,?,?,?)", (id, 'Deposit', deposit, currentTime()))
        
        #commit any changes to db
        conn.commit()
            
        return redirect(url_for("index"))
            
    # if GET method
    else:
        return render_template("deposit.html", balance=usd(user["cash"]))








@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    """Withdraw funds."""
    
    id = session["user_id"]

    #query the user's data
    c.execute("SELECT * FROM users WHERE id = ?", (id,))
    user = c.fetchone()
    
    #if POST method
    if request.method == "POST":
        
        # check for correct integer input
        userInput =  request.form.get("deposit")
        if not userInput.isdigit():
            return apology("Please enter only positive numbers")

        #update the user's cash balance
        withdraw =  int(userInput)
        c.execute('UPDATE users SET cash = ? WHERE id = ?', (user["cash"] - withdraw, id))

        #update transaction history table        
        c.execute("INSERT INTO transactions (id, buy_sell, price, time) VALUES(?,?,?,?)", (id, 'Withdraw', -withdraw, currentTime()))
        
        #commit any changes to db
        conn.commit()
            
        return redirect(url_for("index"))
            
    # if GET method
    else:
        return render_template("withdraw.html", balance=usd(user["cash"]))







@app.route("/userChange", methods=['GET', 'POST'])
@login_required
def userChange():
    
    if request.method == 'POST':
        
        # ensure old username was submitted
        if not request.form.get("oldName"):
            return apology("must provide old username")
            
        # ensure new username was submitted
        if not request.form.get("newName"):
            return apology("must provide a new username")

        # ensure old username matches db
        c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
        user = c.fetchone()
        if user['username'] != request.form.get('oldName'):
            return apology('old username does not match')

        # ensure password is correct
        if not pwd_context.verify(request.form.get("password"), user["hash"]):
            return apology("invalid username and/or password")
        
        #update db
        c.execute('UPDATE users SET username = ? WHERE id = ?', (request.form.get('newName'), session['user_id']))
        conn.commit()
        
        # redirect user to home page
        return redirect(url_for("index"))
        
    else:
        return render_template('userChange.html')







@app.route("/passChange", methods=['GET', 'POST'])
@login_required
def passChange():
    
    if request.method == 'POST':
        
        # ensure old password was submitted
        if not request.form.get("oldPass"):
            return apology("must provide old Password")
            
        # ensure new password was submitted
        if not request.form.get("newPass"):
            return apology("must provide a new Password")
            
        # confirm new password matches twice
        if request.form.get("newPass") != request.form.get("confirmPass"):
            return apology("new password must match")

        # ensure old password matches db
        c.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
        user = c.fetchone()
        if not pwd_context.verify(request.form.get("oldPass"), user["hash"]):
            return apology('old password does not match database')

        # encrypt password into hash
        hashed = pwd_context.hash(request.form.get("newPass"))
        
        #update db
        c.execute('UPDATE users SET hash = ? WHERE id = ?', (hashed, session['user_id']))
        conn.commit()
        
        # redirect user to home page
        return redirect(url_for("index"))
        
    else:
        return render_template('passChange.html')








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
        
        # check for correct integer input for number of shares
        userInput =  request.form.get("shares")
        if not userInput.isdigit():
            return apology("Please enter only positive numbers")
        
        shares = int(userInput)
        purchase = stock["price"] * shares
        
        #check if the user has sufficient funds
        id = session["user_id"]
        c.execute("SELECT * FROM users WHERE id = ?", (id,))
        user = c.fetchone()
        
        cash = user["cash"]
        if cash < purchase:
            return apology("insufficient funds for transaction")
            
        #update transaction history table        
        c.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?)", (id, stock["symbol"], "Buy", shares, stock["price"], currentTime()))
        
        # if user already owns this stock, update the record
        c.execute("SELECT * FROM portfolio WHERE id = ? AND stock = ?", (id, stock["symbol"], ) )
        owned = c.fetchone()
        
        if owned:
            #db.execute("UPDATE portfolio SET shares = :shares WHERE id = :id AND stock = :stock", 
            #    shares = rowsPF[0]["shares"] + shares, id = id, stock = stock["symbol"])
            c.execute('UPDATE portfolio SET SHARES = ? WHERE id = ? AND stock = ?', (owned["shares"] + shares, id, stock["symbol"]))
        
        # otherwise insert new stock to portfolio table
        else:
            #db.execute("INSERT INTO portfolio (id, stock, shares) VALUES(:id, :stock, :shares)",
            #    id = id, stock = stock["symbol"], shares = shares)
            c.execute("INSERT INTO portfolio VALUES(?,?,?)", (id, stock["symbol"], shares))
                
        #update the cash position
        c.execute('UPDATE users SET cash = ? WHERE id = ?', (cash - purchase, id))
        
        conn.commit()
        
        # render the successful result
        return render_template("bought.html", name=stock["name"], symbol=stock["symbol"], price=stock["price"],
            shares=shares, total=usd(stock["price"]*shares), buy_sell="Buy", time = currentTime())
        
    # if GET method    
    else: 
        return render_template("buy.html")







@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    
    #query user's transactions table
    c.execute("SELECT * FROM transactions WHERE id = ?", (session["user_id"],))
    rowsT = c.fetchall()
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
        c.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
        user = c.fetchone()

        # ensure username exists and password is correct
        if not user or not pwd_context.verify(request.form.get("password"), user["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = user["id"]

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
        c.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
        user = c.fetchone()
        
        # ensure username does not already exist
        if user:
            return apology("that username already exists!")
            
        # encrypt password into hash
        hashed = pwd_context.hash(request.form.get("password"))
        
        # insert the user info into database, id is autoincremented by sqlite
        c.execute("INSERT INTO users (username, hash) VALUES(?,?)", (request.form.get("username"), hashed))
        
        # re-query database for id
        c.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
        row = c.fetchone()
        
        # remember which user has logged in
        session["user_id"] = row["id"]
        
        #update transaction history table        
        c.execute('INSERT INTO transactions (id, buy_sell, price, time) VALUES(?,?,?,?)', (session['user_id'], "Account Opening Bonus", 10000, currentTime()))
        
        # redirect user to home page
        conn.commit()
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
        c.execute("SELECT * FROM portfolio WHERE id = ? AND stock = ?", (id, stock["symbol"],))
        owned = c.fetchone()
        
        if not owned:
            return apology("you do not own this stock")
            
        # check for correct integer input for number of shares
        userInput =  request.form.get("shares")
        if not userInput.isdigit():
            return apology("Please enter only positive numbers")
            
        shares = int(userInput)
        sale = stock["price"] * shares

        #retrieve user's cash balance
        c.execute("SELECT * FROM users WHERE id = ?", (id,))
        user = c.fetchone()
        cash = user["cash"]
        
        #check the user has greater than or equal number of shares available to sell
        if owned["shares"] < shares:
            return apology("you are trying to sell more shares than you own")
        
            
        #update transaction history table        
        c.execute("INSERT INTO transactions VALUES(?,?,?,?,?,?)", (id, stock['symbol'], 'Sell', shares, stock['price'], currentTime()))
        
        # update the portfolio
        c.execute('UPDATE portfolio SET shares = ? WHERE id = ? AND stock = ?', (owned["shares"] - shares, id, stock["symbol"]))
        
        #update the cash position
        #db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = cash + sale, id = id)
        c.execute('UPDATE users SET cash = ? WHERE id = ?', (cash + sale, id))
        
        # render the successful result
        conn.commit()
        return render_template("sold.html", name=stock["name"], symbol=stock["symbol"], price=stock["price"],
            shares=shares, total=usd(stock["price"]*shares), buy_sell="Sell", time = currentTime())
        
    # if GET method    
    else: 
        return render_template("sell.html")







    
    