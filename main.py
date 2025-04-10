from flask import Flask,render_template, request, redirect, url_for, session, send_file
from flask_mysqldb import MySQL
import mysql.connector
import io
import time

app=Flask(__name__)
app.secret_key = 'your_secret_key_here'

MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASSWORD = ''
MYSQL_DB = 'hospital'

conn = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DB
)

@app.route('/')
def home():
    if 'email' in session:
        email = session['email']
        user_info = None
        account_type = None

        cursor = conn.cursor()
        
        # First check doctors table
        cursor.execute("SELECT username, email, telephone, dob FROM doctors WHERE email = %s", (email,))
        result = cursor.fetchone()
        
        if result:
            account_type = 'doctor'
            user_info = {
                'username': result[0],
                'email': result[1],
                'telephone': result[2],
                'dob': result[3]
            }
        else:
            # If not found in doctors, check users table
            cursor.execute("SELECT username, email, telephone, dob FROM users WHERE email = %s", (email,))
            result = cursor.fetchone()
            
            if result:
                account_type = 'user'
                user_info = {
                    'username': result[0],
                    'email': result[1],
                    'telephone': result[2],
                    'dob': result[3]
                }

        # Fetch list of doctors (for users only)
        doctors = []
        if account_type == 'user':
            cursor.execute("SELECT username FROM doctors")
            doctors = [row[0] for row in cursor.fetchall()]

        cursor.close()

        if user_info and account_type == 'user':
            return render_template('home.html', user_info=user_info, email=email, account_type=account_type, doctors=doctors)
        elif user_info and account_type == 'doctor':
            return render_template('doctor_home.html', user_info=user_info, email=email, account_type=account_type)
        else:
            return render_template('error.html', message="User not found in either doctors or users database")
    else:
        return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        account_type = request.form['account_type']
        username = request.form['username']
        email = request.form['email']
        telephone = request.form['phone']
        dob = request.form['dob']
        pwd = request.form['password']
        cpwd = request.form['confirm-password']

        if pwd != cpwd:
            return render_template('register.html', error="Passwords do not match.")

        cursor = conn.cursor()
        try:
            if account_type == 'user':
                cursor.execute("""
                    INSERT INTO users (username, email, telephone, password, dob) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (username, email, telephone, pwd, dob))
            elif account_type == 'doctor':
                cursor.execute("""
                    INSERT INTO doctors (username, email, telephone, password, dob) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (username, email, telephone, pwd, dob))
            else:
                return render_template('register.html', error="Invalid account type selected.")

            conn.commit()
        except Exception as e:
            print("Registration error:", e)
            conn.rollback()
            return render_template('register.html', error="Registration failed.")
        finally:
            cursor.close()

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        account_type = request.form['account_type']
        email = request.form['email']
        pwd = request.form['password']

        if not account_type:
            return render_template('login.html', error='Please select account type.')

        cursor = conn.cursor()
        try:
            # Choose table based on account type
            if account_type == 'user':
                cursor.execute("SELECT email, password FROM users WHERE email = %s", (email,))
            elif account_type == 'doctor':
                cursor.execute("SELECT email, password FROM doctors WHERE email = %s", (email,))
            else:
                return render_template('login.html', error='Invalid account type selected.')

            user = cursor.fetchone()
        except Exception as e:
            print("Login error:", e)
            return render_template('login.html', error='Login failed. Please try again.')
        finally:
            cursor.close()

        # Validate user
        if user and pwd == user[1]:
            session['email'] = user[0]
            session['role'] = account_type
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error='Invalid email or password')

    return render_template('login.html')

@app.route('/logout', methods =['GET','POST'])
def logout():
    session.pop('email', None)
    return redirect(url_for('login'))

@app.route('/appointments')
def appointments():
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    account_type = session.get('role')  # Get the account type from the session (set during login)

    cursor = conn.cursor()
    
    # Fetch user info to get the username
    if account_type == 'doctor':
        cursor.execute("SELECT username FROM doctors WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT username FROM users WHERE email = %s", (email,))
    
    username_result = cursor.fetchone()
    if not username_result:
        cursor.close()
        return render_template('error.html', message="User not found")

    username = username_result[0]

    # Fetch appointments based on account type
    if account_type == 'user':
        # For users, fetch appointments where they are the patient
        cursor.execute("""
            SELECT id, patient_name, doctor_name, date, time, reason 
            FROM appointments 
            WHERE patient_name = %s
        """, (username,))
    elif account_type == 'doctor':
        # For doctors, fetch appointments where they are the doctor
        cursor.execute("""
            SELECT id, patient_name, doctor_name, date, time, reason 
            FROM appointments 
            WHERE doctor_name = %s
        """, (username,))
    else:
        cursor.close()
        return render_template('error.html', message="Invalid account type")

    appointments = cursor.fetchall()
    cursor.close()

    appt_list = [
        {
            'id': appt[0],
            'patient_name': appt[1],
            'doctor_name': appt[2],
            'date': appt[3],
            'time': appt[4],
            'reason': appt[5]
        } for appt in appointments
    ]
    
    user_info = get_user_info(email)
    return render_template('appointments.html', appointments=appt_list, user_info=user_info, account_type=account_type)

@app.route('/make_appointment', methods=['POST'])
def make_appointment():
    patient_name = request.form['patient_name']
    doctor_name = request.form['doctor_name']
    date = request.form['date']
    time = request.form['time']
    reason = request.form['reason']

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO appointments (patient_name, doctor_name, date, time, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (patient_name, doctor_name, date, time, reason))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return render_template('error.html', message=f"Failed to make appointment: {str(e)}")
    finally:
        cursor.close()
    
    return redirect(url_for('appointments'))

@app.route('/cancel_appointment/<int:appt_id>', methods=['POST'])
def cancel_appointment(appt_id):
    if 'email' in session:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM appointments WHERE id = %s", (appt_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            return render_template('error.html', message=f"Failed to cancel appointment: {str(e)}")
        finally:
            cursor.close()
        return redirect(url_for('appointments'))
    else:
        return redirect(url_for('login'))

@app.route('/update_appointment/<int:appt_id>', methods=['GET', 'POST'])
def update_appointment(appt_id):
    if 'email' not in session:
        return redirect(url_for('login'))

    cursor = conn.cursor()
    
    if request.method == 'GET':
        # Fetch the appointment details
        cursor.execute("""
            SELECT patient_name, doctor_name, date, time, reason 
            FROM appointments 
            WHERE id = %s
        """, (appt_id,))
        appt = cursor.fetchone()
        cursor.close()
        
        if appt:
            appt_data = {
                'patient_name': appt[0],
                'doctor_name': appt[1],
                'date': appt[2],
                'time': appt[3],
                'reason': appt[4]
            }
            return render_template('update_appointment.html', appt_id=appt_id, appt_data=appt_data)
        else:
            return render_template('error.html', message="Appointment not found")

    elif request.method == 'POST':
        # Update the appointment
        patient_name = request.form['patient_name']
        doctor_name = request.form['doctor_name']
        date = request.form['date']
        time = request.form['time']
        reason = request.form['reason']

        try:
            cursor.execute("""
                UPDATE appointments 
                SET patient_name = %s, doctor_name = %s, date = %s, time = %s, reason = %s 
                WHERE id = %s
            """, (patient_name, doctor_name, date, time, reason, appt_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            return render_template('error.html', message=f"Failed to update appointment: {str(e)}")
        finally:
            cursor.close()
        
        return redirect(url_for('appointments'))

def get_user_info(email):
    cursor = conn.cursor()
    cursor.execute("SELECT username, email, telephone, dob FROM users WHERE email = %s", (email,))
    result = cursor.fetchone()
    cursor.close()
    if result:
        return {
            'username': result[0],
            'email': result[1],
            'telephone': result[2],
            'dob': result[3]
        }
    return None

if __name__ == '__main__':
    app.run(debug=True)