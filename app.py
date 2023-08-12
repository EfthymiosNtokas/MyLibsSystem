from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import mariadb
from datetime import timedelta
import random
import string
import os
import subprocess
from markupsafe import escape
app = Flask(__name__)

# Flask-Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = 'mylibsdatabase@gmail.com'
app.config['MAIL_PASSWORD'] = 'rhmzuzufyobuwlmf'

mail = Mail(app)

# DB-related
conn = mariadb.connect(
         host='127.0.0.1',
         port= 3306,
         user='root',
         password='',
         database='myLibs',
         autocommit=True)

cur = conn.cursor()

UPLOAD_FOLDER = 'upload'

try: 
    # Check if the directory exists
    if not os.path.exists('./upload'):
        # If it doesn't exist, create it
        os.makedirs('./upload')
except:
    print('Could not create upload directory')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def exec_query(q, commit=False, fetchone=False, handle_error=True): 
    if not handle_error: 
        cur.execute(q)
    else: 
        try: cur.execute(q)
        except mariadb.Error as e: 
            print(f"Error: {e}") 
    if commit: 
        conn.commit()
        return {}
    if fetchone:
        res = cur.fetchone()
        if res:
            column_names = [i[0] for i in cur.description]
            return dict(zip(column_names, res))
        else: 
            return None
    else:
        res = cur.fetchall()
        column_names = [i[0] for i in cur.description]
        return [dict(zip(column_names, r)) for r in res]

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Used to detect if user has not been punctual with borrows
# Returns: False if owes, True if not
def not_naughty(user_id):
    q = f"SELECT * FROM borrow b WHERE b.user_id = {user_id} AND b.end_date < NOW() AND b.return_date IS NULL"
    u = exec_query(q)
    return (u == [], "Borrows overdue") 

#utility function
def reserve_eligibility(user_id, isbn, school_id):
    q = f'''SELECT u.user_type, u.is_active 
            FROM user u 
            WHERE u.user_id = {user_id} AND school_id = {school_id} AND u.user_type IN ('TEACHER', 'STUDENT') '''
    user = exec_query(q, fetchone=True)
    if user is None:
        return False, "Member with given username does not exist in your school"
    
    # Afterwards, check if user is active
    if not user['is_active']:
        return False, "Member with given username is inactive"

    # First, check if 2 reservations/week limit is respected
    q = f'''SELECT r.ISBN 
            FROM reservation r 
            WHERE r.user_id = {user_id} AND DATEDIFF(NOW(), r.begin_date) <= 7'''
    l = exec_query(q)

    user_type = user['user_type']
    if user_type == 'STUDENT': 
        bl = 2
    else: 
        bl = 1

    if len(l) >= bl:
        return (False, "Reservation limit reached")
    
    isbns = [i['ISBN'] for i in l] # now u contains list of ISBNs reserved in the last week
    if isbn in isbns:
        return (False, "Book already reserved") # Assumption made that all end date is at least 7 days later, so all books returned 
                                                # are problematic
    
    # Also, check if user has already borrowed the book that he wants to reserve
    q = f'''SELECT b.user_id, i.item_id FROM borrow b 
            INNER JOIN item i ON b.item_id = i.item_id 
            WHERE i.ISBN='{isbn}' AND b.user_id = {user_id} AND b.return_date IS NULL'''
    borrowed_books = exec_query(q)
    if borrowed_books != []:
        return False, "Member has already borrowed book"
    
    # Last, Check if user has already reserved book this week
    q = f'''SELECT r.user_id, r.ISBN 
            FROM reservation r 
            WHERE r.ISBN='{isbn}' AND r.user_id = {user_id}'''
    reserved_books = exec_query(q)
    if reserved_books != []:
        return False, "Member has already reserved book this week"

        
    return not_naughty(user_id)

def borrow_eligibility(user_id, isbn, school_id):
    # First, check that user is actually a member (and get member_id in the process)
    q = f'''SELECT u.user_type, u.school_id, u.is_active 
            FROM user u
            WHERE u.user_id = {user_id} AND u.school_id = {school_id} 
            AND u.user_type IN ('TEACHER', 'STUDENT')'''
    u = exec_query(q, fetchone=True)

    if u is None:
        return False, 0, "Member with given username does not exist in your school"

    # Afterwards, check if user is active
    if not u['is_active']:
        return False, 0, "Member with given username is inactive"

    # Then, check if borrow limit has been reached
    q = f"SELECT * FROM borrow WHERE user_id = {user_id} AND DATEDIFF(NOW(), begin_date) <= 7"
    l = exec_query(q)

    user_type = u['user_type']
    if user_type == 'STUDENT': 
        bl = 2
    else: 
        bl = 1

    if len(l) >= bl:
        return False, 0, "Borrow limit reached"
    
    # Check if books are overdue
    n, err = not_naughty(user_id)
    if n == False:
        return False, 0, err
    
    # Check if user has already borrowed book AND OWNS IT RIGHT NOW
    q = f'''SELECT b.user_id, i.item_id FROM borrow b 
            INNER JOIN item i ON b.item_id = i.item_id 
            WHERE i.ISBN='{isbn}' AND b.user_id = {user_id} AND b.return_date IS NULL'''
    borrowed_books = exec_query(q)

    if borrowed_books != []:
        return False, 0, "Member has already borrowed book"

    # Get reservations to see user's priority (basically how many books should exist in order for user to be able to borrow book)
    q = f'''SELECT u.user_id FROM reservation r 
            INNER JOIN user u ON r.user_id = u.user_id 
            WHERE u.school_id = '{school_id}' AND r.ISBN = '{isbn}' 
            ORDER BY r.begin_date'''
    rsrvs = exec_query(q)

    # We initially assume that user hasn't reserved book
    priority = len(rsrvs) + 1
    for i in range(0, len(rsrvs)):
        if rsrvs[i]['user_id'] == user_id:
            priority = i + 1
            break

    # Get number of available copies based items returned
    q = f'''SELECT available_copies FROM school_book
            WHERE school_id = {school_id} AND ISBN = {isbn}'''
    ac = exec_query(q, fetchone=True)
    ac = ac['available_copies']
    
    if priority > ac:
        return False, priority - len(rsrvs), "User too low in priority"
    
    return True, priority - len(rsrvs), "No errors were detected"

# Session-related 
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/' # Private key for sessions.
app.permanent_session_lifetime = timedelta(minutes=120) # Set duration for session authentication token

# Session decorator, to be used in all pages requiring login
def session_check(fun):
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return render_template('error.html', error_message='Login required') 
        return fun(*args, **kwargs)
    
    decorated_function.__name__ = fun.__name__
    return decorated_function

# Session decorator, to be used in all pages requiring login depending on user_type
def access_check(user_type):
    def decorator_function(fun):
        def decorated_function(*args, **kwargs):
            if session['user_type'] not in user_type:
                return render_template('error.html', error_message='Access Denied')
            return fun(*args, **kwargs)
        
        decorated_function.__name__ = fun.__name__
        return decorated_function
    
    return decorator_function

admin_check = access_check(['ADMIN'])
manager_check = access_check(['MANAGER'])
member_check = access_check(['TEACHER', 'STUDENT'])
member_check = access_check(['TEACHER', 'STUDENT'])



def member_check(fun):
    def decorated_function(*args, **kwargs):
        if session['user_type'] not in ['TEACHER', 'STUDENT']:
            return render_template('error.html', error_message='Accesss Denied') 
        return fun(*args, **kwargs)
    
    decorated_function.__name__ = fun.__name__
    return decorated_function

@app.route('/manage_db', methods=['GET', 'POST'])
@session_check
@admin_check
def manage_db():
    if request.method == 'GET':
        return render_template('manage_db.html')
    else:
        action = request.form['action']

        if action == 'backup':
            # Generate a random filename for the backup
            backup_filename = 'myLibs-backup.sql'
            backup_path = os.path.join(app.root_path, backup_filename)
            
            #linux
            fd = open(backup_path, 'w')
            password = ""
            subprocess.Popen(['mysqldump', '-u', "root", f"--password={password}", "myLibs"], stdout=fd).wait()
            return send_file(backup_path, as_attachment=True)

        elif action == 'restore':
            file = request.files['restore_from_file']
            if file.filename == '':
                return render_template('error.html', error_message='No file selected')
            filename = secure_filename(file.filename)

            restore_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(restore_path)        
            cur.execute('drop database if exists myLibs')
            cur.execute('create database myLibs')
            cur.execute('USE myLibs')
            fd = open(restore_path, 'r')
            password = ""
            subprocess.Popen(['mysql', '-u', "root", f"--password={password}", "myLibs"], stdin=fd).wait()
            
            os.remove(restore_path)
            q = f'''
                    SELECT * FROM user WHERE user_id = {session["user_id"]}
                '''
            u = exec_query(q, fetchone=True)
            session['username']=u['username']          


        return render_template('manage_db.html')

@app.route("/register", methods=['GET','POST'])
def register():
    if request.method == 'GET':
        # get the schools and put them in a presentable list for the user to see
        q = 'SELECT school_name from school'
        res = exec_query(q)
        schools = []
        for r in res: 
            schools.append((r['school_name']))
        
        return render_template('register.html', schools=schools)
    else: #all fields are necessary no empty value will be given
        #read the request
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        first_name = request.form['firstname']
        last_name = request.form['lastname']
        date_of_birth = request.form['dateofbirth']
        school = request.form['school']
        usertype = request.form['usertype']
        usertype=usertype.upper()
        
       
        #insert request into database
        #first find the school_id
        q = f"SELECT school_id from school where school_name = '{school}'"
        school = exec_query(q, fetchone=True)
        school_id = school['school_id']

        q = f"SELECT * FROM user u WHERE u.username = '{username}'"
        user = exec_query(q, fetchone=True)
        if user is not None: 
            flash('Username already exists', category='error')
            return redirect(url_for('register'))

        q = f"SELECT * FROM user u WHERE u.email = '{email}'"
        user = exec_query(q, fetchone=True)
        if user: 
            flash('Email address already exists', category='error')
            return redirect(url_for('register'))

        q = f'''INSERT INTO request (username, user_password, email, first_name, last_name, date_of_birth, user_type, school_id) VALUES
                ('{username}', '{password}', '{email}', '{first_name}', '{last_name}', '{date_of_birth}', '{usertype}', {school_id})'''
        
        exec_query(q, commit=True)        
       
        return render_template('register_redirect.html')


@app.route("/login", methods=['GET', 'POST'])
def login():
    
    if request.method == 'GET':
        if 'username' not in session: #if logged in then redircet him to index
            return render_template('login.html')
        else:
            return redirect(url_for('index'))

    elif request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        
        username = request.form['username']
        password = request.form['password']

        # Check if account exists using MySQL
        q = f"SELECT * FROM user WHERE username = '{username}' AND user_password = '{password}'"
        account = exec_query(q, fetchone=True)
        # Fetch one record and return result 

        if account:
            # Check if user is inactive
            if account['user_type'] in ['TEACHER', 'STUDENT', 'MANAGER']:
                if account['is_active'] == 0:
                    return render_template('inactive_user.html')

            session.permanent = True
            session['username'] = username
            session['user_type'] = account['user_type']
            session['user_id'] = account['user_id']
            session.modified = True

            return redirect(url_for('index'))
        else:
            return render_template('error.html', error_message='Login Error')

@app.route("/index", methods=["GET"])
@session_check
def index():
    user_type = session['user_type']
    username = session['username']
    user_id = session['user_id']

    # At this point, we should be a valid user. Serve different result based on user type
    if user_type == 'ADMIN':
        
        return render_template('index_admin.html', username = username)
    
    else: 
        q = f"SELECT u.school_id FROM user u WHERE u.user_id = {user_id}"
        session['school_id'] = exec_query(q, fetchone=True)['school_id']
        if user_type == 'MANAGER': 
            return render_template('index_manager.html', username = username)
        else: 
            return render_template('index_member.html', username = username)
        
@app.route("/books", methods=["GET", "POST"])
@session_check
def books():
    ut = session['user_type']
    user_id = session['user_id']

    school_id = ""
    # Redirect if admin
    if ut == 'ADMIN':
        return redirect(url_for('index'))

    # Find info for filters
    q = '''SELECT a.author_id AS author_id, CONCAT(a.first_name, ' ', a.last_name) AS author_name, 
            COUNT(*) AS nbooks FROM author a 
            INNER JOIN book_author ba ON a.author_id = ba.author_id 
            GROUP BY ba.author_id
            ORDER BY author_name'''
    authors = exec_query(q)

    q = '''SELECT c.category_id AS category_id, c.category AS category, 
            COUNT(*) as nbooks FROM category c 
            INNER JOIN book_category bc ON c.category_id = bc.category_id 
            GROUP BY bc.category_id
            ORDER BY category'''
    categories = exec_query(q)

    # Apply filters
    author_filter = None if 'author_filter' not in request.form else request.form.getlist('author_filter')
    category_filter = None if 'category_filter' not in request.form else request.form.getlist('category_filter')
    title_filter = None if 'title_filter' not in request.form else request.form['title_filter']
    copies_lb_filter = None if 'copies_lb_filter' not in request.form else request.form['copies_lb_filter']
    copies_ub_filter = None if 'copies_ub_filter' not in request.form else request.form['copies_ub_filter']
    school_filter = None if 'school_filter' not in request.form else request.form['school_filter']

    # Query 3_2_1 / Query 3_3_1
    q = '''SELECT fb.title, fb.ISBN, fb.cover, sb.total_copies AS 'copies', sb.available_copies as 'available copies',
            GROUP_CONCAT(DISTINCT fb.author_full_name SEPARATOR ', ') AS 'authors',
            GROUP_CONCAT(DISTINCT fb.category SEPARATOR ', ') AS 'categories'
            FROM (SELECT b.title, b.ISBN, b.cover, CONCAT(a.first_name, ' ', a.last_name) as author_full_name, c.category 
            FROM (SELECT b.title, b.ISBN, b.cover FROM book b
            LEFT JOIN book_author ba ON b.ISBN = ba.ISBN LEFT JOIN author a ON ba.author_id = a.author_id 
            LEFT JOIN book_category bc ON b.ISBN = bc.ISBN LEFT JOIN category c ON bc.category_id = c.category_id '''

    args = []
    if author_filter:
        aqs = []
        for a in author_filter:
            aqs.append("a.author_id = "+a)
        args.append(" ("+' OR '.join(aqs)+")")

    if category_filter:
        cqs = []
        for c in category_filter:
            cqs.append("c.category_id = "+c)
        args.append(" ("+' OR '.join(cqs)+")")
        
    if title_filter:
        args.append(" (b.title LIKE '%"+title_filter+"%')")
    

    if author_filter or category_filter or title_filter:
        q += " WHERE" + " AND ".join(args)
    
    s = ''
    if school_filter:
        s += " AND sb.total_copies > 0"

    if copies_lb_filter:
        s += f" AND sb.total_copies >= {copies_lb_filter}"

    if copies_ub_filter:
        s += f" AND sb.total_copies <= {copies_ub_filter}"


    q += f''') as b LEFT JOIN book_author ba ON b.ISBN = ba.ISBN LEFT JOIN author a ON ba.author_id = a.author_id 
            LEFT JOIN book_category bc ON b.ISBN = bc.ISBN LEFT JOIN category c ON bc.category_id = c.category_id) as fb LEFT JOIN school_book sb ON fb.ISBN = sb.ISBN
            WHERE sb.school_id = {session['school_id']} {s} 
            GROUP BY fb.ISBN'''

    # Get books based on filters
    books = exec_query(q)

    return render_template('book_browser.html', books=books, authors=authors, categories=categories)

@app.route("/add_item/<isbn>")
@session_check
@manager_check
def add_item(isbn):
    q = f"INSERT INTO item(school_id, ISBN) VALUES ({session['school_id']}, '{isbn}')"
    exec_query(q, commit=True)
    return redirect(f'/book/{isbn}')

@app.route("/remove_item/<item_id>")
@session_check
@manager_check
def remove_item(item_id):
    
    isbn = request.args['isbn']
    q = f"DELETE FROM item WHERE item_id = {item_id}"
    exec_query(q, commit=True)
    return redirect(f'/book/{isbn}')

@app.route("/image/<img_file>", methods=["GET", "POST"])
@session_check
def image(img_file):
    if request.method == "GET":
        try:
            return send_file("./upload/"+img_file, mimetype='image/jpg')
        except:
            return redirect(url_for('index'))

@app.route("/book/<isbn>", methods=["GET", "POST"])
@session_check
def book(isbn):
    q = f'''SELECT b.title, b.ISBN, b.publisher, b.pages, b.summary, b.cover, b.book_language, b.keyword, 
            CONCAT(a.first_name, ' ', a.last_name) AS author_name, c.category FROM book b 
            LEFT JOIN book_author ba ON b.ISBN=ba.ISBN LEFT JOIN author a ON ba.author_id = a.author_id 
            LEFT JOIN book_category bc ON b.ISBN = bc.ISBN LEFT JOIN category c ON bc.category_id = c.category_id 
            WHERE b.ISBN='{isbn}' '''
    bk = exec_query(q)
    if bk == []:
        return render_template('error.html', error_message="Book not in database")

    title = bk[0]['title']
    isbn = bk[0]['ISBN']
    publisher = bk[0]['publisher']
    pages = bk[0]['pages']
    summary = bk[0]['summary']
    cover = bk[0]['cover']
    book_language = bk[0]['book_language']
    keywords = bk[0]['keyword']

    

    authors = {d['author_name'] for d in bk}
    categories = {d['category'] for d in bk}
    
    q = f'''SELECT u.username AS username, r.rating, r.review_body AS review FROM book b 
            INNER JOIN review r on b.ISBN=r.ISBN INNER JOIN user u ON u.user_id=r.user_id 
            WHERE r.approved=1 AND b.ISBN='{isbn}' '''
    reviews = exec_query(q)

    q = f'''SELECT AVG(rating) AS average FROM review WHERE ISBN = '{isbn}' AND approved = 1'''
    
    average = exec_query(q,fetchone=True)['average']
    

    rsrvs = None
    items = None
    if session['user_type'] == 'MANAGER':
        q = f'''SELECT u.username, r.begin_date, r.end_date FROM reservation r 
                INNER JOIN user u ON u.user_id = r.user_id INNER JOIN book b ON b.ISBN = r.ISBN 
                WHERE u.school_id = {session['school_id']} AND b.ISBN='{isbn}' ORDER BY r.begin_date'''
        rsrvs = exec_query(q)

        q = f'''SELECT i.item_id, u.username, b.end_date FROM item i LEFT JOIN 
                (SELECT * FROM borrow WHERE return_date IS NULL) b ON i.item_id = b.item_id 
                LEFT JOIN user u ON u.user_id = b.user_id 
                WHERE i.school_id = {session['school_id']} AND i.ISBN = '{isbn}' AND b.return_date IS NULL'''
        items = exec_query(q)

    return render_template('book.html', title=title, isbn=isbn, publisher=publisher, pages=pages, summary=summary, cover=cover, book_language=book_language, keywords=keywords, reviews=reviews, authors=authors, categories=categories, reservations=rsrvs, items=items, average=average)

@app.route("/reserve/<isbn>", methods=["GET", "POST"])
@session_check
def reserve(isbn):
    user = ""
    user_id = 0
    if session['user_type'] in ['TEACHER', 'STUDENT']:
        user = session['username']
        user_id = session['user_id']
    else:
        username = request.form['username']
        q = f"SELECT user_id FROM user u WHERE u.username = '{username}'"
        u = exec_query(q, fetchone=True)

        if u == None:
            return render_template('reserve.html', isbn=isbn, reserved=False, err="Member with given username does not exist in your school")

        user_id = u['user_id']

    reserved, err = reserve_eligibility(user_id, isbn, session['school_id'])
    if reserved:
        # Query 3_3_1
        q = f"INSERT INTO reservation(user_id, ISBN, begin_date, end_date) VALUES ({str(user_id)}, '{isbn}', NOW(), ADDDATE(NOW(), 7))"
        exec_query(q, commit=True)
    return render_template('reserve.html', isbn=isbn, reserved=reserved, err=err)

@app.route("/reservations", methods=["GET", "POST"])
@session_check
def reservations():
    user_type = session['user_type']
    user_id = session['user_id']
    if (user_type == 'ADMIN'):
        return redirect(url_for('index'))
    
    if (user_type in ['TEACHER', 'STUDENT']):
        q = f'''SELECT b.title, b.ISBN, r.begin_date, r.end_date FROM reservation r 
                INNER JOIN book b ON b.ISBN=r.ISBN 
                WHERE r.user_id = {user_id} ORDER BY r.begin_date DESC'''
        rsrvs = exec_query(q)
        
        for r in rsrvs: 
            isbn = r['ISBN']
            b, _, _ = borrow_eligibility(user_id, isbn, session['school_id'])
            
            if b:
                b = 'Yes'
            else:
                b = 'No'
            r['borrow_available'] = b
        
        

    if(user_type == 'MANAGER'):
        q = f'''SELECT u.first_name, u.last_name, u.username, b.title, b.ISBN, r.begin_date, r.end_date FROM reservation r 
                INNER JOIN book b ON b.ISBN=r.ISBN INNER JOIN user u ON u.user_id=r.user_id 
                WHERE u.school_id = {session['school_id']} ORDER BY r.begin_date DESC'''
        rsrvs = exec_query(q)

    
    if request.method == 'GET':
        return render_template('reservations.html', reservations=rsrvs)
    elif request.method == 'POST':
        if(user_type in ['TEACHER', 'STUDENT']):
            for rs in rsrvs:
                if 'cancel_'+rs['ISBN'] in request.form:
                    q = f"DELETE FROM reservation WHERE isbn='{rs['ISBN']}'"
                    exec_query(q, commit=True)
        else:
            first_name_filter = None if 'first_name_filter' not in request.form else request.form['first_name_filter']
            last_name_filter = None if 'last_name_filter' not in request.form else request.form['last_name_filter']

            q = f'''SELECT u.first_name, u.last_name, u.username, b.title, b.ISBN, r.begin_date, r.end_date FROM reservation r 
                    INNER JOIN book b ON b.ISBN=r.ISBN INNER JOIN user u ON u.user_id=r.user_id 
                    WHERE u.school_id={session['school_id']}'''

           
            args = []
            
            if first_name_filter or last_name_filter:
                q += " AND"
            if first_name_filter:
                args.append(" u.first_name LIKE '%"+str(first_name_filter)+"%'")

            if last_name_filter:
                args.append(" u.last_name LIKE '%"+str(last_name_filter)+"%'")
            
            q+= ' AND '.join(args)
            

            # Get reservations based on filters
            rsrvs = exec_query(q)

            return render_template('reservations.html', reservations=rsrvs)


        return redirect(url_for('reservations'))
        
@app.route("/borrow", methods=["GET", "POST"])
@session_check
@manager_check
def borrow():
    manager_id = session['user_id']
    borrow_data = [k for k in request.form if "borrow_" in k]
    if borrow_data == []:
        return render_template('borrow.html', borrowed=False, err="No item selected", priority=0)
    borrow_data = borrow_data[0] # Now borrow_data is of the form borrow_itemid_isbn
    borrow_data = borrow_data.split('_')
    item_id = borrow_data[1]
    isbn = borrow_data[2]

    username = request.form['username']

    q = f'''SELECT u.user_id, u.school_id FROM user u 
            WHERE u.username = '{username}' '''
    u = exec_query(q, fetchone=True)

    if u == None:
        return render_template('borrow.html', borrowed=False, err="Member with given username does not exist in your school", priority=0)
    
    user_id = u['user_id']

    b, priority, err = borrow_eligibility(user_id, isbn, session['school_id'])
    
    if b:
        q = f'''INSERT INTO borrow(user_id, manager_id, item_id, begin_date, end_date) 
                VALUES ({u['user_id']}, {manager_id}, {item_id}, NOW(), ADDDATE(NOW(), 7))'''
        exec_query(q, commit=True)

    return render_template('borrow.html', borrowed=b, err=err, username=username, priority=priority, item_id=item_id, isbn=isbn)
        
@app.route("/borrows", methods=["GET", "POST"])
@session_check
def borrows():
    user_type = session['user_type']
    user_id = session['user_id']
    if (user_type == 'ADMIN'):
        return redirect(url_for('index'))

    if request.method == 'GET':
        borrows = []
        if (user_type in ['TEACHER', 'STUDENT']):
            q = f'''SELECT bk.title, bk.ISBN, b.begin_date, b.end_date, b.return_date, DATEDIFF(NOW(), b.end_date) as 'overdue' 
                    FROM borrow b INNER JOIN item i ON b.item_id = i.item_id 
                    INNER JOIN book bk ON bk.ISBN=i.ISBN WHERE b.user_id = {user_id} ORDER BY b.begin_date DESC'''
        else:
            q = f'''SELECT u.username, u.first_name, u.last_name, i.item_id, bk.title, bk.ISBN, b.begin_date, b.end_date, b.return_date, 
                    DATEDIFF(NOW(), b.end_date) as 'overdue' FROM borrow b INNER JOIN user u ON b.user_id = u.user_id 
                    INNER JOIN item i ON b.item_id = i.item_id INNER JOIN book bk ON bk.ISBN=i.ISBN 
                    WHERE u.school_id = {session['school_id']} ORDER BY b.begin_date DESC'''
        
        borrows = exec_query(q)
        return render_template('borrows.html', borrows=borrows)   
    
    elif request.method == 'POST':
        returned_item = [k for k in request.form if "return_" in k]
        
        if returned_item != []: # We returned a book
            returned_item = returned_item[0]
            returned_item = returned_item.split('_')[1] # Now returned_item contains the item_id of the returned item

            q = f"UPDATE borrow SET return_date=NOW() WHERE item_id={returned_item}"
            exec_query(q, commit=True)

            q = f'''SELECT u.username, u.first_name, u.last_name, i.item_id, bk.title, bk.ISBN, b.begin_date, b.end_date, b.return_date, 
                    DATEDIFF(NOW(), b.end_date) as 'overdue' FROM borrow b INNER JOIN user u ON b.user_id = u.user_id 
                    INNER JOIN item i ON b.item_id = i.item_id INNER JOIN book bk ON bk.ISBN=i.ISBN'''
            borrows = exec_query(q)

            return redirect(url_for('borrows'))
        else: # We applied filters
            first_name_filter = None if 'first_name_filter' not in request.form else request.form['first_name_filter']
            last_name_filter = None if 'last_name_filter' not in request.form else request.form['last_name_filter']
            overdue_filter = None if 'overdue_filter' not in request.form else request.form.getlist('overdue_filter')
            days_overdue_min_filter = None if 'days_overdue_min_filter' not in request.form else request.form['days_overdue_min_filter']
            days_overdue_max_filter = None if 'days_overdue_max_filter' not in request.form else request.form['days_overdue_max_filter']
            
            q = ""
            args = []
            if (user_type in ['TEACHER', 'STUDENT']):
                q = f'''SELECT bk.title, bk.ISBN, b.begin_date, b.end_date, b.return_date, DATEDIFF(NOW(), b.end_date) as 'overdue' 
                        FROM borrow b INNER JOIN item i ON b.item_id = i.item_id 
                        INNER JOIN book bk ON bk.ISBN=i.ISBN WHERE '''
                
                args = [f'''b.user_id = {user_id}''']
            else:
                # Query 3_2_2
                q = f'''SELECT u.username, u.first_name, u.last_name, i.item_id, bk.title, bk.ISBN, b.begin_date, b.end_date, b.return_date, 
                        DATEDIFF(NOW(), b.end_date) as 'overdue' FROM borrow b INNER JOIN user u ON b.user_id = u.user_id 
                        INNER JOIN item i ON b.item_id = i.item_id INNER JOIN book bk ON bk.ISBN=i.ISBN 
                        WHERE '''
                
                args = [f'''u.school_id = {session['school_id']}''']

            if first_name_filter:
                args.append(" u.first_name LIKE '%"+str(first_name_filter)+"%'")

            if last_name_filter:
                args.append(" u.last_name LIKE '%"+str(last_name_filter)+"%'")

            if overdue_filter or days_overdue_min_filter or days_overdue_max_filter:
                args.append(" b.return_date IS NULL")

            if overdue_filter:
                args.append(" b.end_date < NOW()")

            if days_overdue_min_filter:
                args.append(f" DATEDIFF(NOW(), b.end_date) >= {days_overdue_min_filter}")

            if days_overdue_max_filter:
                args.append(f" DATEDIFF(NOW(), b.end_date) <= {days_overdue_max_filter}")

            q+= ' AND '.join(args)

            # Get borrows based on filters
            
            borrows = exec_query(q)

            return render_template('borrows.html', borrows=borrows)

@app.route("/borrowed_books", methods=['GET'])
@session_check
def borrowed_books():
    if session['user_type'] not in ['TEACHER', 'STUDENT']:
        return redirect(url_for('index'))
    
    user_id = session['user_id']

    # Query 3_3_2
    q = f'''SELECT DISTINCT b.title, b.ISBN FROM book b INNER JOIN item i ON b.ISBN = i.ISBN
            INNER JOIN borrow br ON br.item_id = i.item_id WHERE br.user_id = {user_id}'''
    
    books = exec_query(q)
    
    return render_template("borrowed_books.html", books=books)

@app.route("/add_book", methods=['GET','POST'])
@session_check
@manager_check
def add_book():
        
    if request.method == 'GET':
        return render_template('add_book.html')
    elif request.method == 'POST':
        isbn = request.form['isbn']
        title = request.form['title']
        publisher = request.form['publisher']
        pages = request.form['pages']
        language = request.form['language']
        keywords = request.form['keywords']
        summary = request.form['summary']
        copies = request.form['copies']
        cover = request.files['cover']
        author_first_names = request.form.getlist('author_first_names')
        author_last_names = request.form.getlist('author_last_names')
        category_names = request.form.getlist('category_names')

        # First, check that the ISBN value provided is valid
        if not (isbn.isnumeric() and len(isbn) == 13):
            return render_template('add_book_redirect.html', err="Invalid ISBN. Expected 13-digit number")

        checksum = 0
        for i in range(0, 13):
            checksum += int(isbn[i]) * (1 if i%2 == 0 else 3)

        
        if not (checksum%10 == 0): return render_template('add_book_redirect.html', err="Invalid ISBN. Non-zero checksum")

        # Check that book doesn't already exist
        q = f"SELECT * FROM book WHERE ISBN = {isbn}"
        res = exec_query(q, fetchone=True)
        if res:
            return render_template('add_book_redirect.html', err="Book already exists")

        # Check if title length is too big
        if len(title) > 80:
            return render_template('add_book_redirect.html', err="Title too long, expected length at most 80 characters")

        # Check if publisher length is too big
        if len(publisher) > 80:
            return render_template('add_book_redirect.html', err="Publisher name too long, expected length at most 80 characters")

        # Check that pages are actually a number
        if not pages.isnumeric():
            return render_template('add_book_redirect.html', err="Pages must be a number")
        
        # Check that summary is <= 2000 characters
        if len(summary) > 2000:
            return render_template('add_book_redirect.html', err="Summary too long, expected length at most 2000 characters")
            

        # Check if keywords length is too big
        if len(keywords) > 80:
            return render_template('add_book_redirect.html', err="Keywords name too long, expected length at most 100 characters")
        
        # Check if language length is too big
        if len(language) > 80:
            return render_template('add_book_redirect.html', err="Language name too long, expected length at most 50 characters")

        # Check that number of items in school is positive integer
        if not copies:
            copies = 0
        else: 
            copies = int(copies)

        if copies < 0:
            return render_template('add_book_redirect.html', err="Invalid number of copies")

        cover_title = "NULL"
        if 'cover' in request.files and cover.filename != '':
            # If the user does not select a file, the browser submits an
            # empty file without a filename.
            if cover and allowed_file(cover.filename):
                cover_title = 'img_'+request.form['isbn']+'.jpg'
                cover.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_title))
        
        if cover_title == "NULL":
            q = f'''INSERT INTO book(ISBN, title, publisher, pages, summary, cover, book_language, keyword) VALUES \
                ('{isbn}', '{title}', '{publisher}', {pages}, '{summary}', {cover_title}, '{language}', '{keywords}')'''
            exec_query(q, commit=True)
        else:
            q = f'''INSERT INTO book(ISBN, title, publisher, pages, summary, cover, book_language, keyword) VALUES \
              ('{isbn}', '{title}', '{publisher}', {pages}, '{summary}', '/image/{cover_title}', '{language}', '{keywords}')'''
            exec_query(q, commit=True)

        if copies > 0:
            q = "INSERT INTO item(school_id, ISBN) VALUES"
            for i in range(0, copies):
                q += f" ({session['school_id']}, {isbn}),"

            exec_query(q[:-1], commit=True)

        # Here we will deal with book author pairs

        # First make sure all authors are distinct
        author_names = [(author_first_names[i], author_last_names[i]) for i in range(len(author_first_names))]
        author_names = list(dict.fromkeys(author_names))

        # Then make sure to only keep non-empty author names
        author_names = [(a[0], a[1]) for a in author_names if a[0] != "" and a[1] != ""]

        # Only proceed if authors were added
        if author_names != []:
            # Run check to see which authors are not in the database and need to be added
            
            # Get names of given authors that are already in the database
            q = "SELECT * FROM author WHERE "
            args = []
            for a in author_names:
                args.append(f"(first_name = '{a[0]}' AND last_name = '{a[1]}')")

            q += ' OR '.join(args)
            existing_authors = exec_query(q)
            existing_author_names = [(e['first_name'], e['last_name']) for e in existing_authors]

            # Add new authors in the database
            args = []
            for a in author_names:
                if a not in existing_author_names:
                    args.append(f"('{a[0]}', '{a[1]}')")

            if args != []:
                q = "INSERT INTO author(first_name, last_name) VALUES "+", ".join(args)
                exec_query(q, commit=True)

            # Now add the book_author relations
            q = "INSERT INTO book_author(ISBN, author_id) VALUES "
            args = []
            for a in author_names:
                args.append(f"('{isbn}', (SELECT author_id FROM author WHERE first_name = '{a[0]}' AND last_name = '{a[1]}'))")

            q += ', '.join(args)
            exec_query(q, commit=True)

        # Do the same thing for categories
        # First make sure all categories are distinct
        categories = list(dict.fromkeys(category_names))

        # Then make sure to only keep non-empty author names
        categories = [c for c in categories if c != ""]

        # Only proceed if categories were added
        if categories != []:
            # Run check to see which categories are not in the database and need to be added
            
            # Get names of given categories that are already in the database
            q = "SELECT * FROM category WHERE "
            args = []
            for c in categories:
                args.append(f"category = '{c}'")

            q += ' OR '.join(args)
            existing_categories = exec_query(q)
            existing_categories = [e['category'] for e in existing_categories]

            # Add new categories in the database
            args = []
            for c in category_names:
                if c not in existing_categories:
                    args.append(f"('{c}')")

            if args != []:
                q = "INSERT INTO category(category) VALUES "+", ".join(args)
                exec_query(q, commit=True)

            # Now add the book_category relations
            q = "INSERT INTO book_category(ISBN, category_id) VALUES "
            args = []
            for c in categories:
                args.append(f"('{isbn}', (SELECT category_id FROM category c WHERE c.category = '{c}'))")

            q += ', '.join(args)
            exec_query(q, commit=True)

        return redirect(url_for('books'))
    
@app.route("/edit_book/<isbn>", methods=['GET','POST'])
@session_check
@manager_check
def edit_book(isbn):

    if request.method == 'GET':
        q = f'''SELECT b.title, b.publisher, b.pages, b.book_language, b.keyword, b.summary, sb.total_copies FROM book b 
                INNER JOIN school_book sb ON b.ISBN = sb.ISBN
                WHERE b.ISBN = '{isbn}' AND sb.school_id = {session['school_id']}'''
        book = exec_query(q, fetchone=True)
        if not book:
            return render_template("edit_book_redirect.html", err="Book not found in database")

        title = book['title']
        publisher = book['publisher']
        pages = book['pages']
        language = book['book_language']
        keywords = book['keyword']
        summary = book['summary']
        copies = book['total_copies']

        q = f'''SELECT a.first_name, a.last_name FROM author a 
                INNER JOIN book_author ba ON a.author_id = ba.author_id 
                WHERE ba.ISBN = '{isbn}' '''
        authors = exec_query(q)

        q = f'''SELECT c.category FROM category c 
                INNER JOIN book_category bc ON c.category_id = bc.category_id 
                WHERE bc.ISBN = '{isbn}' '''
        categories = exec_query(q)


        return render_template('edit_book.html', isbn=isbn, title=title, publisher=publisher, pages=pages, language=language, keywords=keywords, summary=summary, copies=copies, authors=authors, categories=categories)
    
    elif request.method == 'POST':
        title = request.form['title']
        publisher = request.form['publisher']
        pages = request.form['pages']
        language = request.form['language']
        keywords = request.form['keywords']
        summary = request.form['summary']
        cover = request.files['cover']
        author_first_names = request.form.getlist('author_first_names')
        author_last_names = request.form.getlist('author_last_names')
        category_names = request.form.getlist('category_names')

        # Check if title length is too big
        if len(title) > 80:
            return render_template('edit_book_redirect.html', err="Title too long, expected length at most 80 characters")

        # Check if publisher length is too big
        if len(publisher) > 80:
            return render_template('edit_book_redirect.html', err="Publisher name too long, expected length at most 80 characters")

        # Check that pages are actually a number
        if not pages.isnumeric():
            return render_template('edit_book_redirect.html', err="Pages must be a number")
        
        # Check that summary is <= 2000 characters
        if len(summary) > 2000:
            return render_template('edit_book_redirect.html', err="Summary too long, expected length at most 2000 characters")
            

        # Check if keywords length is too big
        if len(keywords) > 80:
            return render_template('edit_book_redirect.html', err="Keywords name too long, expected length at most 100 characters")
        
        # Check if language length is too big
        if len(language) > 80:
            return render_template('add_book_redirect.html', err="Language name too long, expected length at most 50 characters")

        cover_title = "NULL"
        if 'cover' in request.files and cover.filename != '':
            # If the user does not select a file, the browser submits an
            # empty file without a filename.
            if cover and allowed_file(cover.filename):
                cover_title = 'img_'+isbn+'.jpg'
                cover.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_title))
        
        
        if cover_title == "NULL":
            q = f'''UPDATE book SET title = '{title}', publisher = '{publisher}', pages = {pages}, summary = '{summary}',
                         book_language = '{language}', keyword='{keywords}' WHERE ISBN = '{isbn}' '''
        else:
            q = f'''UPDATE book SET title = '{title}', publisher = '{publisher}', pages = {pages}, summary = '{summary}',
                        cover = '/image/{cover_title}', book_language = '{language}', keyword='{keywords}' WHERE ISBN = '{isbn}' '''
            
        exec_query(q, commit=True)

        # Here we will deal with book author pairs

        # First make sure all authors are distinct
        author_names = [(author_first_names[i], author_last_names[i]) for i in range(len(author_first_names))]
        author_names = list(dict.fromkeys(author_names))

        # Then make sure to only keep non-empty author names
        author_names = [(a[0], a[1]) for a in author_names if a[0] != "" and a[1] != ""]

        # If authors were added, add them into the database

        # Only proceed if authors were added
        if author_names != []:
            # Run check to see which authors are not in the database and need to be added
            
            # Get names of given authors that are already in the database
            q = "SELECT * FROM author WHERE "
            args = []
            for a in author_names:
                args.append(f"(first_name = '{a[0]}' AND last_name = '{a[1]}')")

            q += ' OR '.join(args)
            existing_authors = exec_query(q)
            existing_author_names = [(e['first_name'], e['last_name']) for e in existing_authors]

            # Add new authors in the database
            args = []
            for a in author_names:
                if a not in existing_author_names:
                    args.append(f"('{a[0]}', '{a[1]}')")

            if args != []:
                q = "INSERT INTO author(first_name, last_name) VALUES "+", ".join(args)
                exec_query(q, commit=True)

        # Now add the book_author relations
        # First delete all existing ones
        q = f"DELETE FROM book_author WHERE ISBN={isbn}"
        exec_query(q, commit=True)

        # Now add all the new ones
        if author_names != []:
            q = "INSERT INTO book_author(ISBN, author_id) VALUES "
            args = []
            for a in author_names:
                args.append(f"('{isbn}', (SELECT author_id FROM author WHERE first_name = '{a[0]}' AND last_name = '{a[1]}'))")

            q += ', '.join(args)
            
            exec_query(q, commit=True)

        # Do the same thing for categories
        # First make sure all categories are distinct
        categories = list(dict.fromkeys(category_names))

        # Then make sure to only keep non-empty categories
        categories = [c for c in categories if c != ""]

        # Only proceed if categories were added
        if categories != []:
            # Run check to see which categories are not in the database and need to be added
            
            # Get names of given categories that are already in the database
            q = "SELECT * FROM category WHERE "
            args = []
            for c in categories:
                args.append(f"category = '{c}'")

            q += ' OR '.join(args)
            existing_categories = exec_query(q)
            existing_categories = [e['category'] for e in existing_categories]

            # Add new categories in the database
            args = []
            for c in category_names:
                if c not in existing_categories:
                    args.append(f"('{c}')")

            if args != []:
                q = "INSERT INTO category(category) VALUES "+", ".join(args)
                exec_query(q, commit=True)

        # Now add the book_category relations
        # First delete all existing ones
        q = f"DELETE FROM book_category WHERE ISBN={isbn}"
        exec_query(q, commit=True)

        if categories != []:
            # Now add the book_category relations
            q = "INSERT INTO book_category(ISBN, category_id) VALUES "
            args = []
            for c in categories:
                args.append(f"('{isbn}', (SELECT category_id FROM category c WHERE c.category = '{c}'))")

            q += ', '.join(args)
            exec_query(q, commit=True)

        return redirect(url_for('books'))

@app.route("/add_school_library", methods=['GET','POST'])
@session_check
@admin_check
def add_school_library():
    if request.method == 'GET':
        return render_template('add_school_library.html')
    else:
        #read the request
        school_name = request.form['school_name']
        school_address = request.form['school_address']
        city = request.form['city']
        phone = request.form['phone']
        email = request.form['email']
        principal_first_name = request.form['principal_first_name']
        principal_last_name = request.form['principal_last_name']

        #check for empty fields (phone, email)
        if (email == ''): 
            email = 'NULL'
        if (phone == ''): 
            phone = 'NULL'

        #insert school_library into database
        q = f'''INSERT INTO school (school_name, school_address, city, phone, email, principal_first_name, principal_last_name) VALUES 
                ('{school_name}', '{school_address}', '{city}', '{phone}', '{email}', '{principal_first_name}', '{principal_last_name}')'''
        exec_query(q, commit=True)
       
        return render_template('add_school_library_redirect.html')


@app.route("/requests", methods=['GET','POST'])
@session_check
def requests(): 
    user_type = session['user_type']
    if (user_type == 'ADMIN'):
        q = '''SELECT r.username, r.user_password, r.email, CONCAT(r.first_name, ' ', r.last_name) AS name, r.date_of_birth, 
                s.school_name FROM request r INNER JOIN school s ON r.school_id = s.school_id 
                WHERE r.user_type = 'MANAGER' AND r.is_active = 1'''
    
    if (user_type in ['TEACHER', 'STUDENT']):
        return redirect(url_for('index'))
    
    if (user_type == 'MANAGER'):
        q = f'''SELECT r.username, r.user_password, r.email, CONCAT(r.first_name, ' ', r.last_name) AS name, r.date_of_birth, 
                r.user_type FROM request r WHERE r.school_id = {session['school_id']} AND r.is_active = 1 AND r.user_type != 'MANAGER' '''
    
    reqs = exec_query(q)

    if(request.method == 'GET'): 
        if (user_type == 'ADMIN'):
            return render_template('manager_requests.html', requests=reqs)
        #otherwise we are in manager
        return render_template('member_requests.html', requests=reqs)
    else:
        for req in reqs:
            req_email = str(req['email'])
            if 'accept_' + req_email in request.form:
                # Accept the request
                q = f"UPDATE request SET is_active = 0 WHERE email = '{req_email}'"
                exec_query(q, commit=True)
                

                if(session['user_type']=='ADMIN'):
                    typeuser='MANAGER'
                else:
                    typeuser=req['user_type'] 
                #check if email in there
                q = f"SELECT * FROM user WHERE email = '{req['email']}'"
                if(exec_query(q, fetchone=True) != None):
                    q = f"UPDATE request SET is_active = 0 WHERE email = '{req['email']}'"
                    exec_query(q, commit=True)
                    return redirect(url_for('requests'))
                
                
                q = f'''SELECT r.first_name, r.last_name, r.date_of_birth, r.school_id FROM request r 
                        WHERE r.email = '{req_email}' '''
                m = exec_query(q)
                

                q = f'''INSERT INTO user(email, username, user_password, user_type, first_name, last_name, date_of_birth, school_id) VALUES
                        ('{req['email']}', '{req['username']}', '{req['user_password']}', '{typeuser}', '{m[0]['first_name']}', '{m[0]['last_name']}', '{m[0]['date_of_birth']}', {m[0]['school_id']})'''
                
                    
                exec_query(q, commit=True)
                
                # Send an email notification
                try: 
                    msg = Message('Registration accepted', sender='mylibsdatabase@gmail.com', recipients=[req['email']])
                    msg.body = f"Your registration was accepted. You can now login to myLibs.\n"
                    mail.send(msg)
                except:
                    print("Mail has not sented!")

                # Print member card
                q = f"SELECT school_name FROM school WHERE school_id = {m[0]['school_id']}"
                school_name = exec_query(q, fetchone=True)['school_name']
                if session['user_type'] == 'MANAGER': 
                    return render_template('member_card.html', first_name = m[0]['first_name'], 
                                            last_name = m[0]['last_name'], email = req['email'], 
                                            date_of_birth=m[0]['date_of_birth'], school_name = school_name, 
                                            member_type = req['user_type'])
        



            elif 'reject_' + req_email in request.form:
                # Reject the request
                q = f"UPDATE request SET is_active = 0 WHERE email = '{req_email}'" #we dont delete them (in case of mistake)
                exec_query(q, commit=True)
        return redirect(url_for('requests'))   
    
@app.route("/reviews_all", methods=['GET','POST'])
@session_check
@manager_check
def reviews_all():
    user_type = session['user_type']

    school_id = ""
    # Redirect if admin
    if user_type != 'MANAGER':
        return redirect(url_for('index'))

    q = '''SELECT c.category_id AS category_id, c.category AS category FROM category c'''
    categories = exec_query(q)

    # Apply filters
    username_filter = None if 'username_filter' not in request.form else request.form['username_filter']
    category_filter = None if 'category_filter' not in request.form else request.form.getlist('category_filter')
    borrowed_filter = None if 'borrowed_filter' not in request.form else request.form.getlist('borrowed_filter')

    q = f'''SELECT DISTINCT u.username AS username, b.title AS title, r.rating, r.review_body AS review FROM review r 
            INNER JOIN user u ON u.user_id=r.user_id INNER JOIN book b ON r.ISBN = b.ISBN'''

    args = ""
    if category_filter:
        q += " INNER JOIN book_category bc ON b.ISBN = bc.ISBN INNER JOIN category c ON bc.category_id = c.category_id"
        cqs = []
        for c in category_filter:
            cqs.append("c.category_id = "+c)
        args = " ("+' OR '.join(cqs)+")"

    if borrowed_filter:
        q += " INNER JOIN item i ON b.ISBN = i.ISBN INNER JOIN borrow br ON (i.item_id = br.item_id AND u.user_id = br.user_id)"

    q += " WHERE r.approved = 1"

    if username_filter:
        q += f" AND u.username LIKE '%{username_filter}%'"

    if category_filter:
        q += " AND" + args

    reviews = exec_query(q)

    q = '''SELECT c.category_id AS category_id, c.category AS category FROM category c'''
    categories = exec_query(q)

    # Repeat to calculate average
    # Query 3_2_3
    q = f'''SELECT IFNULL(AVG(r.rating), 0) AS average FROM review r 
            INNER JOIN user u ON u.user_id=r.user_id INNER JOIN book b ON r.ISBN = b.ISBN'''

    if borrowed_filter:
        q += " INNER JOIN item i ON b.ISBN = i.ISBN INNER JOIN borrow br ON (i.item_id = br.item_id AND u.user_id = br.user_id)"

    args = ""
    if category_filter:
        q += " INNER JOIN book_category bc ON b.ISBN = bc.ISBN INNER JOIN category c ON bc.category_id = c.category_id"
        cqs = []
        for c in category_filter:
            cqs.append("c.category_id = "+c)
        args = " ("+' OR '.join(cqs)+")"

    q += " WHERE r.approved = 1"

    if username_filter:
        q += f" AND u.username LIKE '%{username_filter}%'"

    if category_filter:
        q += " AND" + args

    average = exec_query(q, fetchone=True)['average']

    return render_template('reviews_all.html', reviews=reviews, categories=categories, average=average)

@app.route("/reviews", methods=['GET','POST'])
@session_check        
@manager_check
def reviews():
    revs=[]
    #ISBN, USERNAME, FULL NAME, RATING, REVIEW_BODY, SAME SCHOOL
    

    q = f'''SELECT r.review_id AS review_id, r.ISBN AS isbn, u.username AS username, u.user_type AS usertype, 
            CONCAT(u.first_name, ' ', u.last_name) AS name, r.rating AS rating, r.review_body AS review_body FROM review r 
            INNER JOIN user u ON r.user_id=u.user_id 
            WHERE r.approved = 0 AND u.school_id = {session['school_id']}'''

    revs = exec_query(q)
    if(request.method == 'GET'): 
        return render_template('reviews.html', reviews=revs)
    else:
        for rev in revs:
            rev_id = str(rev['review_id'])
            if 'accept_' + rev_id in request.form:
                q = f"UPDATE review SET approved = 1 WHERE review_id = {rev_id}"
                exec_query(q, commit=True)
            elif 'reject_' + rev_id in request.form:
                q = f"'DELETE from review WHERE review_id = {rev_id}"
                exec_query(q, commit=True)
        return redirect(url_for('reviews')) 

@app.route("/review", methods=["GET", "POST"])
@session_check
def review():
    
    isbn = request.form['isbn']
    rating = request.form['rating']
    review_body = request.form['review_body']
    if session['user_type'] == 'STUDENT':
        try:
            query = "INSERT INTO review (user_id, ISBN, rating, review_body) VALUES (?, ?, ?, ?)"
            values = (session['user_id'], isbn, rating, review_body)
            cur.execute(query, values)
            conn.commit() 
        except:
            print("error")
        
        
    else:
        try:
            query = "INSERT INTO review (user_id, ISBN, rating, review_body, approved) VALUES (?, ?, ?, ?, ?)"
            values = (session['user_id'], isbn, rating, review_body, 1)
            cur.execute(query, values)
            conn.commit()
        except:
            print("error")
    
    return redirect('/book/'+str(isbn))

@app.route("/profile", methods=["GET", "POST"])
@session_check
def profile():
    if(request.method == 'GET'):
        if(session['user_type'] != 'ADMIN'):
            q = f'''SELECT u.username, u.email, u.first_name, u.last_name, u.date_of_birth, s.school_name 
                    FROM user u 
                    INNER JOIN school s ON u.school_id=s.school_id 
                    WHERE u.user_id = {session['user_id']}'''

        else:
            q = f'''SELECT u.username, u.email, u.first_name, u.last_name, u.date_of_birth 
                    FROM user u 
                    WHERE u.user_id = {session['user_id']}'''
            
        res = exec_query(q, fetchone=True)

        return render_template('profile.html', x = res)
    elif request.method == 'POST':
        # If "See member card" button was pressed, render member card
        if session['user_type'] in ['TEACHER', 'STUDENT'] and 'member_card' in request.form:
            q = f'''SELECT u.first_name, u.last_name, u.email, u.date_of_birth, s.school_name, u.user_type FROM user u
                    INNER JOIN school s ON u.school_id = s.school_id
                    WHERE u.user_id = {session['user_id']}'''
            u = exec_query(q, fetchone=True)

            if u == None:
                return render_template('error.html', error_message="Something must have gone horribly wrong to enter here")

            return render_template('member_card.html', first_name = u['first_name'], 
                                            last_name = u['last_name'], email = u['email'], 
                                            date_of_birth=u['date_of_birth'], school_name = u['school_name'], 
                                            member_type = u['user_type'])

        if session['user_type'] in ['ADMIN', 'MANAGER', 'TEACHER']:
            username = request.form['username']
            email = request.form['email']
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            date_of_birth = request.form['date_of_birth']
            
            #username
            try:
                q = f"UPDATE user SET username= '{username}' WHERE user_id={session['user_id']}"
                exec_query(q, commit=True, handle_error=False)
                session['username']=username            
            except:
                return render_template('profile_redirect.html', err='Username already exists')
            #email
            try:
                q = f"UPDATE user SET email= '{email}' WHERE user_id={session['user_id']}"
                exec_query(q, commit=True, handle_error=False)         
            except:
                return render_template('profile_redirect.html', err='Email already in use')
            #names and birth
            try:
                q = f'''UPDATE user SET first_name= '{first_name}', last_name= '{last_name}', date_of_birth='{date_of_birth}'
                        WHERE user_id={session['user_id']}'''
                
                exec_query(q, commit=True, handle_error=False)
            except:
                return render_template('profile_redirect.html', err='Unexpected')    
                
        cur_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if(cur_password != '' or new_password != '' or confirm_password != ''):
            q = f"SELECT user_password FROM user WHERE user_id = {session['user_id']}"
            if(cur_password != exec_query(q, fetchone=True)['user_password']):
                return render_template('profile_redirect.html', err='Incorrect Current Password')
            if(len(new_password) <= 2):
                return render_template('profile_redirect.html', err='Password Must be at least 3 chars long')
            if(new_password!= confirm_password):
                return render_template('profile_redirect.html', err='New passwords do not match')
            
            try:
                q = f"UPDATE user SET user_password= '{new_password}' WHERE user_id={session['user_id']}"
                
                exec_query(q, commit=True, handle_error=False)
            except:
                return render_template('profile_redirect.html', err='Unexpected')         

        return redirect(url_for('profile'))
        
@app.route('/profiles', methods=["GET", "POST"])
@session_check
@access_check(['MANAGER', 'ADMIN'])
def profiles():
    # Apply filters
    first_name_filter = None if 'first_name_filter' not in request.form else request.form['first_name_filter']
    last_name_filter = None if 'last_name_filter' not in request.form else request.form['last_name_filter']
    username_filter = None if 'username_filter' not in request.form else request.form['username_filter']
    
    if(session['user_type']=='MANAGER'):
        q = f'''SELECT u.first_name as FirstName, u.last_name as LastName, u.username as username, u.is_active as Active, 
                u.user_type as UserType FROM user u 
                WHERE u.school_id = {session['school_id']} AND u.user_type IN ('TEACHER', 'STUDENT') '''
    else:
        q = f'''SELECT u.first_name as FirstName, u.last_name as LastName, u.username as username, u.is_active as Active, 
                u.user_type as UserType FROM user u 
                WHERE u.user_type = 'MANAGER' ''' 


    args = []
    
    if first_name_filter or last_name_filter or username_filter:
        q += " AND"
    if first_name_filter:
        args.append(" u.first_name LIKE '%"+str(first_name_filter)+"%'")

    if last_name_filter:
        args.append(" u.last_name LIKE '%"+str(last_name_filter)+"%'")

    if username_filter:
        args.append(" u.username LIKE '%"+str(username_filter)+"%'")
            
    q+= ' AND '.join(args)
    
    
    profiles = exec_query(q)
    

    return render_template('profile_browser.html', profiles=profiles)


@app.route("/profileof/<username>", methods=["GET", "POST"])
@session_check
@access_check(['MANAGER','ADMIN'])
def profileof(username):
    q = '''SELECT * FROM category'''

    categories = exec_query(q)

    if(request.method == 'GET'):
        if(session['user_type']=='MANAGER'):

            q = f'''SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, u.date_of_birth, u.user_type, s.school_name, 
                u.is_active FROM user u INNER JOIN school s ON u.school_id=s.school_id 
                WHERE u.username = '{username}' AND s.school_id = {session['school_id']}'''
        
            x = exec_query(q)

            session['member_user_id']=x[0]['user_id']
            
        else:
            
            q = f'''SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, u.date_of_birth, u.user_type, s.school_name, u.is_active FROM user u INNER JOIN school s ON u.school_id=s.school_id  WHERE u.username = '{username}' '''
            
            x = exec_query(q)
        

        return render_template('profileof.html', x=x[0], categories=categories)
    elif request.method == 'POST':
        if(session['user_type']=='MANAGER'):
            # First check if post request was because we want to delete user
            if 'delete_user' in request.form:
                try:
                    q = f'''DELETE FROM user WHERE username = '{username}' '''
                    exec_query(q, commit=True, handle_error=False)
                except:
                    return render_template('profile_delete_redirect.html', err="User had borrows/reservations/reviews")
                
                return redirect(url_for('profiles'))
            
            
            username = request.form['username']
            email = request.form['email']
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            date_of_birth = request.form['date_of_birth']
            active = request.form['yesNoInput']
            if(active == 'yes'): active =1
            else: active=0
            membertype = request.form['membertype']

            try:
                q = f"UPDATE user SET username= '{username}' WHERE user_id={session['member_user_id']}"
                exec_query(q, commit=True, handle_error=False)
            except:
                return render_template('profile_redirect.html', err='Username already exists')
            #email
            try:
                q = f"UPDATE user SET email= '{email}' WHERE user_id={session['member_user_id']}"
                exec_query(q, commit=True, handle_error=False)         
            except:
                return render_template('profile_redirect.html', err='Email already in use')
            #names and birth and active and membertype
            try:
                q = f'''UPDATE user SET first_name= '{first_name}', last_name= '{last_name}', date_of_birth='{date_of_birth}', is_active = {active}, user_type = '{membertype}'
                        WHERE user_id={session['member_user_id']}'''
                
                exec_query(q, commit=True, handle_error=False)
            except:
                return render_template('profile_of_redirect.html', err='Unexpected')
        else:
            active = request.form['yesNoInput']
            if(active == 'yes'): active =1
            else: active=0
            try:
                q = f'''UPDATE user SET is_active = {active}
                        WHERE username='{username}' '''
                
                exec_query(q, commit=True, handle_error=False)
            except:
                return render_template('profile_of_redirect.html', err='Unexpected')
            

    return redirect(f"/profileof/{username}")


@app.route('/stats')
@session_check
@admin_check
def stats():
   return render_template('stats.html')

@app.route('/query_3_1_1', methods=['GET', 'POST'])
@session_check
@admin_check
def query_3_1_1():
    if request.method == 'GET':
        return render_template('query_3_1_1.html')
    if request.method == 'POST': 
        year = request.form.get('year')
        month = request.form.get('month')
        s = ''
        if month != 'Whole Year':
            s = f"AND MONTH(b.begin_date) = {month}"
        #Query 3_1_1
        q = f'''SELECT s.school_name, COUNT(b.borrow_id) AS total_borrowed
                FROM school s
                LEFT JOIN (SELECT * FROM user WHERE user_type IN ('TEACHER', 'STUDENT')) u ON s.school_id = u.school_id
                LEFT JOIN borrow b ON u.user_id = b.user_id AND YEAR(b.begin_date) = {year} {s}
                GROUP BY s.school_id;
'''
        loan_stat = exec_query(q)
        return jsonify(loan_stat)

@app.route('/query_3_1_2', methods=['GET', 'POST'])
@session_check
@admin_check
def query_3_1_2():
    if request.method == 'GET':
        q = "SELECT category FROM category"
        categories = exec_query(q)
        category_names = [c['category'] for c in categories]
        return render_template('query_3_1_2.html', categories=category_names)
    
    if request.method == 'POST': 
        category = request.form.get('category')

        q = f'''SELECT DISTINCT CONCAT(a.first_name, ' ', a.last_name) AS 'author_name'
                FROM author a
                INNER JOIN book_author ba ON a.author_id=ba.author_id
                INNER JOIN book b ON b.ISBN=ba.ISBN
                INNER JOIN book_category bc ON bc.ISBN=b.ISBN
                INNER JOIN category c ON bc.category_id=c.category_id
                WHERE c.category='{category}' '''  

        authors = exec_query(q)
        #Query 3_1_2
        q = f'''SELECT DISTINCT CONCAT(t.first_name, ' ', t.last_name) AS teacher_name
                FROM (SELECT * FROM user WHERE user_type='TEACHER') t
                INNER JOIN borrow br ON t.user_id=br.user_id
                INNER JOIN item i ON i.item_id = br.item_id
                INNER JOIN book b ON b.ISBN=i.ISBN
                INNER JOIN book_category bc ON bc.ISBN=b.ISBN
                INNER JOIN category c ON bc.category_id=c.category_id
                WHERE br.begin_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR) AND category='{category}' '''  

        teachers = exec_query(q)

        result = {
            'authors': authors,
            'teachers': teachers
        }

        return jsonify(result)


@app.route('/query_3_1_5', methods=['GET', 'POST'])
@session_check
@admin_check
def query_3_1_5():
    if request.method == 'GET':
        return render_template('query_3_1_5.html')
    if request.method == 'POST': 
        year = request.form.get('year')
        #Query 3_1_5
        q = f'''SELECT GROUP_CONCAT(q.manager_name SEPARATOR ', ') AS manager_names, q.book_count AS total_borrows
                FROM (SELECT CONCAT(m.first_name, ' ', m.last_name) AS manager_name, COUNT(*) as book_count
                FROM user m INNER JOIN borrow b ON m.user_id = b.manager_id
                INNER JOIN item i ON b.item_id = i.item_id
                WHERE YEAR(b.begin_date) = {year}
                GROUP BY m.user_id
                HAVING COUNT(*) > 20
                ORDER BY COUNT(*)) q
                GROUP BY q.book_count
                HAVING COUNT(*) > 1
                ORDER BY q.book_count DESC;
            '''
        loan_stat = exec_query(q)
        return jsonify(loan_stat)

@app.route('/button_queries', methods=['GET', 'POST'])
@session_check
@admin_check
def button_queries():
    if request.method == 'GET':
        return render_template('button_queries.html')
    if request.method == 'POST': 
        selected_query = request.form.get('query')
        
        if selected_query == 'query_3_1_3':
            #Query 3_1_3
            q = ''' SELECT GROUP_CONCAT(q.teacher_name SEPARATOR ', ') AS teacher_names, q.total_borrowed FROM
                    (SELECT CONCAT(m.first_name, ' ', m.last_name) AS teacher_name, COUNT(*) AS total_borrowed
                    FROM user AS m
                    JOIN borrow AS b ON m.user_id = b.user_id
                    JOIN item AS i ON b.item_id = i.item_id
                    JOIN book AS bk ON i.ISBN = bk.ISBN
                    WHERE m.user_type = 'TEACHER' AND m.date_of_birth > DATE_SUB(CURDATE(), INTERVAL 40 YEAR)
                    GROUP BY m.user_id
                    ORDER BY total_borrowed DESC) q
                    GROUP BY q.total_borrowed
                    ORDER BY total_borrowed DESC
                    LIMIT 1
                '''
            result = exec_query(q)

        elif selected_query == 'query_3_1_4':
            #Query 3_1_4
            q = ''' SELECT CONCAT(a.first_name, ' ', a.last_name) AS author_name
                    FROM author a
                    WHERE a.author_id NOT IN (
                        SELECT DISTINCT aa.author_id
                        FROM author aa
                        INNER JOIN book_author ba ON aa.author_id = ba.author_id
                        INNER JOIN item i ON ba.ISBN = i.ISBN
                        INNER JOIN borrow br ON i.item_id = br.item_id)'''
            result = exec_query(q)

        elif selected_query == 'query_3_1_6':
            #Query 3_1_6
            q = ''' SELECT CONCAT(c1.category, ' - ', c2.category) AS category_pair, COUNT(*) AS borrowed_count 
                    FROM book_category bc1 
                    INNER JOIN book_category bc2 ON bc1.ISBN = bc2.ISBN AND bc1.category_id < bc2.category_id
                    INNER JOIN item i ON i.ISBN = bc1.ISBN
                    INNER JOIN borrow b ON b.item_id = i.item_id
                    INNER JOIN category c1 ON bc1.category_id = c1.category_id 
                    INNER JOIN category c2 ON bc2.category_id = c2.category_id 
                    GROUP BY c1.category, c2.category 
                    ORDER BY borrowed_count 
                    DESC LIMIT 3
                '''
            result = exec_query(q)

        elif selected_query == 'query_3_1_7':
            #Query 3_1_7
            q = ''' SELECT CONCAT(a.first_name, ' ', a.last_name) AS author_name, COUNT(*) AS book_count
                    FROM author a
                    INNER JOIN book_author ba ON ba.author_id = a.author_id
                    GROUP BY a.author_id
                    HAVING COUNT(*) <= (SELECT MAX(book_count) - 5 
                                       FROM (SELECT COUNT(*) AS book_count FROM book_author GROUP BY author_id) subquery)
                    ORDER BY book_count DESC
                '''
            result = exec_query(q)

        else:
            result = "No query selected"

        return render_template('button_queries.html', selected_query = selected_query, result = result)

@app.route('/schools', methods=["GET", "POST"])
@session_check
@access_check(['ADMIN'])
def schools():
    # Apply filters
    school_name_filter = None if 'school_name_filter' not in request.form else request.form['school_name_filter']
    
    q = f'''SELECT s.school_id as school_id, s.school_name as Name, s.school_address as Address, s.city as City, s.phone as Phone, s.email as Email, s.principal_first_name as PrincipalFirstName, s.principal_last_name as PrincipalLastName,  GROUP_CONCAT(CONCAT(u.first_name, ' ', u.last_name) SEPARATOR ', ') AS ManagerNames 
            FROM school s LEFT JOIN (SELECT * FROM user WHERE user_type='MANAGER') u
            ON s.school_id = u.school_id '''
    


    args = []
    
    if school_name_filter:
        q += "AND"
        q+=" s.school_name LIKE '%"+str(school_name_filter)+"%'"

    q+= " GROUP BY s.school_id"
    
    schools = exec_query(q)
    

    return render_template('school_browser.html', schools=schools)


@app.route("/school/<school_id>", methods=["GET", "POST"])
@session_check
@access_check(['ADMIN'])
def school(school_id):
    if(request.method == 'GET'):
        
        q = f'''SELECT s.school_id as school_id, s.school_name, s.school_address, s.city, s.phone, s.email, s.principal_first_name, s.principal_last_name FROM school s WHERE s.school_id= {school_id} '''

        
        x = exec_query(q)            

        return render_template('school.html', x=x[0])
    elif request.method == 'POST':
        
        school_name = request.form['school_name']
        school_address = request.form['school_address']
        city = request.form['city']
        phone = request.form['phone']
        email = request.form['email']
        principal_first_name = request.form['principal_first_name']
        principal_last_name = request.form['principal_last_name']
        

        try:
            q = f"UPDATE school SET school_name= '{school_name}' WHERE school_id={school_id}"
            exec_query(q, commit=True, handle_error=False)
        except:
            return render_template('school_redirect.html', err='School Name already exists')
        #phone
        try:
            q = f"UPDATE school SET phone= '{phone}' WHERE school_id={school_id}"
            exec_query(q, commit=True, handle_error=False)
        except:
            return render_template('school_redirect.html', err='School Phone already exists')
        #address, city, email, prin_fir_name, prin_las_name
        try:
            q = f"UPDATE school SET school_address= '{school_address}', city= '{city}', email= '{email}', principal_first_name= '{principal_first_name}', principal_last_name= '{principal_last_name}' WHERE school_id={school_id}"
            exec_query(q, commit=True, handle_error=False)
        except:
            return render_template('school_redirect.html', err='Unexpected')
       
    return redirect(f"/school/{school_id}")

@app.route('/logout')
@session_check
def logout():
    # remove the username from the session if it's there
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
def root():
    return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(error):
    return render_template('error404.html')
