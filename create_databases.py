import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = "flights.db"
ADMIN_DB = "admin.db"
USERS_DB = "users.db"
FLIGHT_INFO_PATH = "flights_info.txt"

def initialize_flights_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS bookings")
    c.execute("DROP TABLE IF EXISTS flights")

    c.execute('''CREATE TABLE flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flight_no TEXT UNIQUE NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        departure DATETIME NOT NULL,
        arrival DATETIME NOT NULL,
        price REAL NOT NULL,
        seats INTEGER NOT NULL,
        airline TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flight_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        booking_ref TEXT UNIQUE NOT NULL,
        payment_amount REAL NOT NULL,
        status TEXT DEFAULT 'confirmed',
        seat_number TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(flight_id) REFERENCES flights(id) ON DELETE CASCADE)''')

    cities = ['Bangalore', 'London', 'Paris', 'Tokyo', 'Dubai', 'Delhi', 'New York', 'Bangkok', 'Malasiya', 'Melbourne', 'Moscow', 'Jerusalem', 'Madrid', 'Rome', 'Amsterdam', 'Riyadh', 'Singapore', 'AbuDhabi', 'Wellington', 'Budapest']
    airlines = ['CloudSky', 'Global Airways', 'AirNova', 'AirIndia']

    start_date = datetime(2025,12,1,0,0,0)
    total_flights = 365
    flight_log = []

    for i in range(total_flights):
        origin = cities[i % len(cities)]
        destination = cities[(i + 1) % len(cities)]
        departure = start_date + timedelta(days=i)
        arrival = departure + timedelta(hours=8)
        flight_no = f"CS{1000 + i}"
        price = 150 + (i % 100)
        seats = 100
        airline = airlines[i % len(airlines)]

        c.execute('''INSERT INTO flights 
            (flight_no, origin, destination, departure, arrival, price, seats, airline)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (flight_no, origin, destination,
            departure.strftime('%Y-%m-%d %H:%M:%S'),
            arrival.strftime('%Y-%m-%d %H:%M:%S'),
            price, seats, airline))

        flight_log.append(f"{flight_no} | {origin} -> {destination} | Departure: {departure.strftime('%d-%m-%Y %H:%M')} | Arrival: {arrival.strftime('%d-%m-%Y %H:%M')} | Price: ${price} | Airline: {airline}")

    with open(FLIGHT_INFO_PATH, "w") as f:
        f.write("\n".join(flight_log))

    conn.commit()
    conn.close()

def initialize_admin_db():
    conn = sqlite3.connect(ADMIN_DB)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS admin_logs")
    c.execute("DROP TABLE IF EXISTS payments")

    c.execute('''CREATE TABLE payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_ref TEXT UNIQUE NOT NULL,
        amount REAL NOT NULL,
        card_last4 TEXT NOT NULL,
        payment_method TEXT DEFAULT 'credit_card',
        status TEXT DEFAULT 'completed',
        payment_date DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_username TEXT NOT NULL,
        action TEXT NOT NULL,
        ip_address TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''INSERT INTO admin_logs 
        (admin_username, action, ip_address)
        VALUES (?, ?, ?)''',
        ('system', 'Database initialized', '127.0.0.1'))

    conn.commit()
    conn.close()

def initialize_users_db():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS users")

    c.execute('''CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        passport TEXT UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Sample user
    c.execute('''INSERT OR IGNORE INTO users 
        (username, password_hash, full_name, email, phone, passport)
        VALUES (?, ?, ?, ?, ?, ?)''',
        ('john_doe',
         generate_password_hash('Travel@123'),
         'John Doe',
         'john.doe@example.com',
         '+1 (555) 123-4567',
         'P12345678'))

    conn.commit()
    conn.close()

def main():
    print("Initializing databases...")
    initialize_flights_db()
    initialize_admin_db()
    initialize_users_db()
    print("""
    Databases created successfully!
    - flights.db: Contains flight and bookings info
    - admin.db: Contains admin and payments info
    - users.db: Contains registered users
    - flights_info.txt: Lists all flight records for reference
    """)

if __name__ == '__main__':
    main()
