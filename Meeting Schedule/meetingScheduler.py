import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta

import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up a folder for uploaded files (e.g., profile pictures)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Nhla@1234",
        database="meeting_scheduler",  # Replace with your database name
        auth_plugin="mysql_native_password"
    )
    return conn

# Initialize the database connection (without table creation)
def init_db():
    try:
        conn = get_db_connection()
        conn.close()
        print("Database connection verified!")
    except mysql.connector.Error as err:
        print(f"Error connecting to the database: {err}")

# Run this to verify the database connection at startup
init_db()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT role FROM users WHERE id = %s', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()

        if user['role'] == 'student':
            return redirect(url_for('schedule_meeting'))
        elif user['role'] == 'lecturer':
            return redirect(url_for('view_meetings'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']  # Capture the surname from the form
        country = request.form['country']
        cellphone = request.form['cellphone']
        student_number = request.form['student_number']
        email = request.form['email']
        password = request.form['password']  # Do not hash the password
        role = request.form['role']

        # Handle profile picture upload
        profile_picture = request.files.get('profile_picture')
        profile_picture_filename = None

        if profile_picture:
            # Secure the filename and save the file
            profile_picture_filename = os.path.join(app.config['UPLOAD_FOLDER'], profile_picture.filename)
            profile_picture.save(profile_picture_filename)

        # Insert into the database
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(''' 
                INSERT INTO users (name, surname, country, cellphone, student_number, email, password, role, profile_picture) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                (name, surname, country, cellphone, student_number, email, password, role, profile_picture_filename))
            conn.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email or student number already registered!', 'danger')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch the user details (email, password, and role)
        cursor.execute('SELECT id, email, password, role FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and user['password'] == password:  # Directly compare the password
            # Store user_id in session
            session['user_id'] = user['id']
            
            # Check the role of the user
            if user['role'] == 'Student':
                flash('Login successful! Redirecting to student dashboard.', 'success')
                return redirect(url_for('schedule_meeting'))
            elif user['role'] == 'Lecturer':
                flash('Login successful! Redirecting to lecturer dashboard.', 'success')
                return redirect(url_for('lectures_management'))
            else:
                flash('Invalid role!', 'danger')
                return redirect(url_for('login'))
        else:
            flash('Invalid email or password!', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/schedule_meeting', methods=['GET', 'POST'])
def schedule_meeting():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('SELECT role FROM users WHERE id = %s', (session['user_id'],))
    user = cursor.fetchone()
    if user['role'] != 'Student':
        flash('Access restricted to students only!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    cursor.execute('SELECT id, name FROM users WHERE role = "Lecturer"')
    lecturers = cursor.fetchall()

    if request.method == 'POST':
        lecturer_id = request.form['lecturer_id']  # ID of the selected lecturer
        date_time = datetime.strptime(request.form['date_time'], '%Y-%m-%dT%H:%M')
        meeting_description = request.form['meeting_description']  # Description from the form
        title = request.form['title']  # Title field (if applicable)

        # Expiration time set to 24 hours from creation
        expires_at = datetime.now() + timedelta(days=1)

        try:
            # Insert into pending_meetings table
            cursor.execute('''
                INSERT INTO pending_meetings (user_id, title, description, expires_at)
                VALUES (%s, %s, %s, %s)
            ''', (session['user_id'], title, meeting_description, expires_at))

            conn.commit()  # Commit the transaction to save the changes
            flash('Meeting request successfully submitted to the lecturer you selected!', 'success')
        except Exception as e:
            flash(f"An error occurred while scheduling the meeting: {e}", 'danger')
            conn.rollback()  # Rollback in case of an error

    conn.close()
    return render_template('schedule_meeting.html', lecturers=lecturers)


@app.route('/lectures_management', methods=['GET', 'POST'])
def lectures_management():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('SELECT role FROM users WHERE id = %s', (session['user_id'],))
    user = cursor.fetchone()
    if user['role'] != 'Lecturer':
        flash('Access restricted to lecturers only!', 'danger')
        conn.close()
        return redirect(url_for('index'))

    # Fetch pending meetings within 24 hours
    cursor.execute('''
        SELECT pm.id AS meeting_id, u.name AS student_name, pm.description
        FROM pending_meetings pm
        JOIN users u ON pm.user_id = u.id
        WHERE pm.expires_at > NOW() AND pm.status = 'pending'
    ''')
    meetings = cursor.fetchall()

    if request.method == 'POST':
        meeting_id = request.form['meeting_id']
        action = request.form['action']
        
        # Determine the new status based on the action
        if action == 'accept':
            new_status = 'Accepted'
            status_class = 'text-success'
        elif action == 'reject':
            new_status = 'Rejected'
            status_class = 'text-danger'
        elif action == 'delay':
            new_status = 'Delayed'
            status_class = 'text-secondary'
        else:
            new_status = 'Cancelled'  # Default action if none of the above
            status_class = 'text-muted'

        # Get the meeting details from pending meetings
        cursor.execute('SELECT * FROM pending_meetings WHERE id = %s', (meeting_id,))
        meeting = cursor.fetchone()

        if meeting:
            # Move the meeting to the meetings table
            cursor.execute('''
                INSERT INTO meetings (title, scheduled_time, description, status, user_id, role, meeting_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (meeting['title'], meeting['scheduled_time'], meeting['description'], new_status, meeting['user_id'], 'student', meeting['scheduled_time']))
            
            # Remove the meeting from pending_meetings
            cursor.execute('DELETE FROM pending_meetings WHERE id = %s', (meeting_id,))
            conn.commit()

            flash('Meeting status updated!', 'success')

    conn.close()
    return render_template('lectures_management.html', meetings=meetings)


if __name__ == '__main__':
    app.run(debug=True)
