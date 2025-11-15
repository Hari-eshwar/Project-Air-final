import os
import random
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.config['DATABASE'] = 'flights.db'
app.config['ADMIN_DB'] = 'admin.db'
app.config['USERS_DB'] = 'users.db'
CORS(app)

MAX_BOOKING_DAYS = 365
FRONTEND_DATE_FORMAT = '%d-%m-%Y'
ADMINS = {
    "Harishwar S": generate_password_hash("Harishwar@"),
    "Suhas J": generate_password_hash("Suhas@123")
}

def get_db_connection():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def get_admin_connection():
    conn = sqlite3.connect(app.config['ADMIN_DB'])
    conn.row_factory = sqlite3.Row
    return conn

def get_user_connection():
    conn = sqlite3.connect(app.config['USERS_DB'])
    conn.row_factory = sqlite3.Row
    return conn

def validate_date(date_str):
    try:
        try:
            date = datetime.strptime(date_str, '%d-%m-%Y').date()
        except ValueError:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        if date < today:
            return False, "Date cannot be in the past"
        if date > today + timedelta(days=MAX_BOOKING_DAYS):
            return False, f"Maximum booking window is {MAX_BOOKING_DAYS} days"
        return True, ""
    except ValueError:
        return False, "Invalid date format"

@app.context_processor
def inject_user():
    user = None
    bookings = []
    if session.get('user_id'):
        try:
            with get_user_connection() as uconn:
                user_row = uconn.execute(
                    "SELECT id, username, full_name, email, phone, passport, created_at FROM users WHERE id = ?",
                    (session['user_id'],)
                ).fetchone()
                if user_row:
                    user = dict(user_row)
            with get_db_connection() as conn:
                user_bookings = conn.execute('''
                    SELECT b.id as booking_id, b.booking_ref, b.seat_number, b.payment_amount, b.created_at,
                           f.flight_no, f.origin, f.destination, f.departure
                    FROM bookings b
                    JOIN flights f ON f.id = b.flight_id
                    WHERE b.user_id = ?
                    ORDER BY b.created_at DESC
                    LIMIT 10
                ''', (session['user_id'],)).fetchall()
                bookings = [dict(r) for r in user_bookings]
        except Exception as e:
            print("Error injecting user:", e)
    return dict(current_user=user, current_user_bookings=bookings)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    today = datetime.now().strftime(FRONTEND_DATE_FORMAT)
    max_date = (datetime.now() + timedelta(days=MAX_BOOKING_DAYS)).strftime(FRONTEND_DATE_FORMAT)
    with get_db_connection() as conn:
        cities = conn.execute("SELECT DISTINCT origin FROM flights UNION SELECT DISTINCT destination FROM flights").fetchall()
        flights = conn.execute("SELECT * FROM flights ORDER BY departure").fetchall()
    return render_template(
        'home.html',
        min_date=today,
        max_date=max_date,
        cities=[city['origin'] for city in cities],
        flights=flights
    )

@app.route('/book-seat', methods=['POST'])
def book_seat():
    seat = request.form.get('selected_seat')
    flash(f'Seat {seat} selected. Continue to booking.', 'success')
    session['selected_seat'] = seat
    return redirect(url_for('home'))

@app.route('/search', methods=['POST'])
def search_results():
    origin = request.form.get('origin', '').strip()
    dest = request.form.get('destination', '').strip()
    date_str = request.form.get('date')
    try:
        passengers = int(request.form.get('passengers', '1'))
    except ValueError:
        flash("Invalid number of passengers", "error")
        return redirect(url_for('home'))
    valid, msg = validate_date(date_str)
    if not valid:
        flash(msg, 'error')
        return redirect(url_for('home'))
    try:
        try:
            search_date = datetime.strptime(date_str, '%d-%m-%Y').date()
        except ValueError:
            search_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format", "error")
        return redirect(url_for('home'))
    with get_db_connection() as conn:
        search_date_db = search_date.strftime('%Y-%m-%d')
        flights = conn.execute('''
            SELECT * FROM flights
            WHERE LOWER(origin) = LOWER(?) AND LOWER(destination) = LOWER(?)
            AND DATE(departure) = ?
            AND seats >= ?
            ORDER BY departure
        ''', (origin.strip(), dest.strip(), search_date_db, passengers)).fetchall()
    if not flights:
        flash("No flights found for your search. Try changing date or cities.", "info")
        return redirect(url_for('home'))
    return render_template('search_results.html', flights=flights, search_date=date_str,
                           origin=origin, destination=dest, passengers=passengers)

@app.route('/book/<int:flight_id>', methods=['GET', 'POST'])
def book(flight_id):
    if request.method == 'POST':
        # --- DEBUG! print all input values to debug POST ---
        print("BOOKING POST:", {k: v for k, v in request.form.items()})
        try:
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            passport = request.form.get('passport')
            card_number = request.form.get('card_number', '').strip()
            seat_number = request.form.get('selected_seat', '')

            # Check all form fields, *including* seat selection!
            if not all([full_name, email, phone, passport, card_number, seat_number]):
                flash("All fields including seat selection are required.", "error")
                return redirect(url_for('book', flight_id=flight_id))

            if len(card_number) < 4:
                flash('Invalid card number.', 'error')
                return redirect(url_for('book', flight_id=flight_id))
            last4 = card_number[-4:]

            with get_db_connection() as conn, get_admin_connection() as admin_conn, get_user_connection() as user_conn:
                flight = conn.execute('SELECT * FROM flights WHERE id = ?', (flight_id,)).fetchone()
                if not flight or flight['seats'] < 1:
                    flash('Sorry, this flight is no longer available.', 'error')
                    return redirect(url_for('home'))
                taken_seats = conn.execute(
                    'SELECT seat_number FROM bookings WHERE flight_id = ? AND seat_number = ?',
                    (flight_id, seat_number)
                ).fetchone()
                if taken_seats:
                    flash(f"Seat {seat_number} is already booked. Please choose another.", 'error')
                    return redirect(url_for('book', flight_id=flight_id))
                if session.get('user_id'):
                    user_id = session['user_id']
                else:
                    existing_user = user_conn.execute(
                        'SELECT id FROM users WHERE email = ? OR passport = ?', (email, passport)
                    ).fetchone()
                    if existing_user:
                        user_id = existing_user['id']
                    else:
                        cur_user = user_conn.execute('''INSERT INTO users
                            (username, password_hash, full_name, email, phone, passport)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (email, generate_password_hash(str(random.randint(1000, 9999))),
                             full_name, email, phone, passport))
                        user_conn.commit()
                        user_id = cur_user.lastrowid
                cur_booking = conn.execute('''INSERT INTO bookings
                    (flight_id, user_id, booking_ref, payment_amount, seat_number)
                    VALUES (?, ?, ?, ?, ?)''',
                    (flight_id, user_id, f"BK{datetime.now().strftime('%Y%m%d')}{random.randint(1000,9999)}",
                     flight['price'], seat_number))
                conn.commit()
                booking_id = cur_booking.lastrowid
                booking_row = conn.execute(
                    'SELECT id, booking_ref FROM bookings WHERE id = ?', (booking_id,)
                ).fetchone()
                booking_ref = booking_row['booking_ref']
                admin_conn.execute('''INSERT INTO payments (booking_ref, amount, card_last4)
                                       VALUES (?, ?, ?)''',
                                    (booking_ref, flight['price'], last4))
                admin_conn.commit()
                conn.execute('UPDATE flights SET seats = seats - 1 WHERE id = ?', (flight_id,))
                conn.commit()
                # Generate ticket PDF
                ticket_path = f"tickets/{booking_ref}.pdf"
                os.makedirs("tickets", exist_ok=True)
                c = canvas.Canvas(ticket_path, pagesize=letter)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 750, "PASSENGER NAME")
                c.setFont("Helvetica", 14)
                c.drawString(100, 730, full_name)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 700, "FLIGHT")
                c.setFont("Helvetica", 14)
                c.drawString(100, 680, flight['flight_no'])
                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 650, "SEAT")
                c.setFont("Helvetica", 14)
                c.drawString(100, 630, seat_number)
                c.setFont("Helvetica-Bold", 16)
                c.drawString(100, 600, f"{flight['origin']} → {flight['destination']}")
                c.setFont("Helvetica", 10)
                c.drawString(100, 400, f"Booking Ref: {booking_ref}")
                c.save()
                booking_for_template = {
                    'id': booking_id,
                    'booking_ref': booking_ref,
                    'flight_no': flight['flight_no'],
                    'date': flight['departure'],
                    'seat': seat_number
                }
                user_for_template = None
                try:
                    with get_user_connection() as uconn:
                        urow = uconn.execute(
                            "SELECT id, username, full_name, email, phone, passport FROM users WHERE id = ?",
                            (user_id,)
                        ).fetchone()
                        if urow:
                            user_for_template = dict(urow)
                except Exception:
                    pass
                return render_template('booking_confirmation.html',
                                       booking=booking_for_template,
                                       user=user_for_template)
        except Exception as e:
            print(f"Error during booking: {str(e)}")
            flash('An error occurred during booking. Please try again.', 'error')
            return redirect(url_for('book', flight_id=flight_id))

    with get_db_connection() as conn:
        flight = conn.execute('SELECT * FROM flights WHERE id = ?', (flight_id,)).fetchone()
        booked = conn.execute(
            'SELECT seat_number FROM bookings WHERE flight_id = ? AND seat_number IS NOT NULL',
            (flight_id,)
        ).fetchall()
        booked_seats = [row['seat_number'] for row in booked]
    return render_template('booking_form.html', flight=flight,
                           booked_seats=booked_seats,
                           selected_seat=session.get('selected_seat'))

@app.route('/tickets/<filename>')
def get_ticket(filename):
    return send_from_directory('tickets', filename)

@app.route('/download_ticket/<int:booking_id>')
def download_ticket(booking_id):
    try:
        with get_db_connection() as conn:
            b = conn.execute('SELECT booking_ref FROM bookings WHERE id = ?', (booking_id,)).fetchone()
            if not b:
                flash("Booking not found.", "error")
                return redirect(url_for('home'))
            filename = f"{b['booking_ref']}.pdf"
            filepath = os.path.join('tickets', filename)
            if not os.path.exists(filepath):
                flash("Ticket file not found.", "error")
                return redirect(url_for('home'))
            return send_from_directory('tickets', filename, as_attachment=True)
    except Exception as e:
        print("Error serving ticket:", e)
        flash("An error occurred while fetching the ticket.", "error")
        return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        passport = request.form.get('passport', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if not all([username, full_name, email, password, password2]):
            flash("Please fill in all required fields.", "error")
            return redirect(url_for('register'))
        if password != password2:
            flash("Passwords do not match.", "error")
            return redirect(url_for('register'))
        with get_user_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM users WHERE username = ? OR email = ? OR passport = ?",
                (username, email, passport)
            ).fetchone()
            if existing:
                flash("An account with these details already exists. Try logging in.", "error")
                return redirect(url_for('register'))
            pw_hash = generate_password_hash(password)
            cur = conn.execute('''INSERT INTO users
                (username, password_hash, full_name, email, phone, passport)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (username, pw_hash, full_name, email, phone, passport))
            conn.commit()
            session['user_id'] = cur.lastrowid
            flash("Registration successful. You are now logged in.", "success")
            return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_username = request.form.get('email_or_username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember')
        with get_user_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ? OR username = ?",
                (email_or_username, email_or_username)
            ).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                if remember:
                    session.permanent = True
                    app.permanent_session_lifetime = timedelta(days=30)
                flash("Logged in successfully.", "success")
                return redirect(url_for('home'))
            else:
                flash("Invalid login credentials.", "error")
                return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        if username in ADMINS and check_password_hash(ADMINS[username], password):
            session['admin'] = username
            flash('Login successful', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'error')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    with get_db_connection() as conn, get_admin_connection() as admin_conn, get_user_connection() as user_conn:
        stats = {
            'flights': conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0],
            'bookings': conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
            'users': user_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            'revenue': admin_conn.execute("SELECT SUM(amount) FROM payments").fetchone()[0] or 0
        }
        recent_bookings = admin_conn.execute(
            'SELECT * FROM payments ORDER BY payment_date DESC LIMIT 5'
        ).fetchall()
    return render_template('admin_dashboard.html', stats=stats, bookings=recent_bookings, admin=session.get('admin'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('tickets', exist_ok=True)
    app.run(host="0.0.0.0", port=port, debug=True)
