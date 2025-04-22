from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging
from datetime import datetime
import requests
import base64
import json
from threading import Thread
import time

# Flask app setup with detailed logging
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///beba.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'super-secure-key-123')  # Use env var in production
db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# M-Pesa Configuration (Daraja API)
MPESA_CONSUMER_KEY = 'your-consumer-key'  # From Safaricom Developer Portal
MPESA_CONSUMER_SECRET = 'your-consumer-secret'
MPESA_SHORTCODE = 'your-shortcode'  # Paybill or Till Number
MPESA_PASSKEY = 'your-passkey'  # From Safaricom
MPESA_CALLBACK_URL = 'https://yourdomain.com/mpesa/callback'  # Publicly accessible callback URL

def get_mpesa_access_token():
    """Fetch M-Pesa access token with error handling."""
    try:
        api_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
        headers = {'Authorization': f'Basic {auth}'}
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("M-Pesa access token retrieved successfully")
        return response.json()['access_token']
    except requests.RequestException as e:
        logger.error(f"Failed to get M-Pesa access token: {str(e)}")
        raise Exception(f"M-Pesa token retrieval failed: {str(e)}")

def initiate_mpesa_payment(phone_number, amount, description):
    """Initiate STK Push payment with detailed logging."""
    try:
        if not phone_number.startswith('254'):
            phone_number = f"254{phone_number[1:]}"
        access_token = get_mpesa_access_token()
        url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        payload = {
            "BusinessShortCode": MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": str(amount),
            "PartyA": phone_number,
            "PartyB": MPESA_SHORTCODE,
            "PhoneNumber": phone_number,
            "CallBackURL": MPESA_CALLBACK_URL,
            "AccountReference": description[:12],
            "TransactionDesc": description
        }
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info(f"M-Pesa payment initiated: {phone_number} - {amount} Ksh - {description}")
        return response.json()
    except requests.RequestException as e:
        logger.error(f"M-Pesa payment initiation failed: {str(e)}")
        return {"ResponseCode": "1", "ResponseDescription": f"Error: {str(e)}"}

@app.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    """Handle M-Pesa callback asynchronously."""
    data = request.get_json()
    logger.info(f"M-Pesa callback received: {json.dumps(data)}")
    if data['Body']['stkCallback']['ResultCode'] == 0:
        checkout_id = data['Body']['stkCallback']['CheckoutRequestID']
        def update_payment_status():
            with app.app_context():
                booking = Booking.query.filter_by(payment_checkout_id=checkout_id).first()
                if booking:
                    booking.payment_status = 'completed'
                    db.session.commit()
                    socketio.emit('payment_confirmed', {'booking_id': booking.id})
                    logger.info(f"Booking payment confirmed: {booking.id}")
                listing = Listing.query.filter_by(payment_checkout_id=checkout_id).first()
                if listing:
                    listing.payment_status = 'completed'
                    db.session.commit()
                    socketio.emit(f'{listing.type}s_added', {'listing_id': listing.id})
                    logger.info(f"Listing payment confirmed: {listing.id}")
                job = TransportJob.query.filter_by(payment_checkout_id=checkout_id).first()
                if job:
                    job.payment_status = 'completed'
                    db.session.commit()
                    socketio.emit('transport_job_added', {'job_id': job.id})
                    logger.info(f"Transport job payment confirmed: {job.id}")
        Thread(target=update_payment_status).start()
        return jsonify({'message': 'Callback processed'}), 200
    else:
        logger.warning(f"M-Pesa payment failed: {data['Body']['stkCallback']['ResultDesc']}")
        return jsonify({'message': 'Payment failed'}), 200

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    id_number = db.Column(db.String(20), unique=True, nullable=False)
    kra_pin = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_driver = db.Column(db.Boolean, default=False)

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_reg = db.Column(db.String(20), unique=True, nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    tons = db.Column(db.Integer)
    image = db.Column(db.String(200))
    booked = db.Column(db.Boolean, default=False)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    pickup = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    payment_checkout_id = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    details = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    payment_checkout_id = db.Column(db.String(50))

class TransportJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pickup_location = db.Column(db.String(100), nullable=False)
    destination = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    payment_checkout_id = db.Column(db.String(50))
    status = db.Column(db.String(20), default='available')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Insurance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    policy_number = db.Column(db.String(50), unique=True, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)

# Authentication Routes
@app.route('/signup', methods=['POST'])
def signup():
    """User signup with detailed validation."""
    data = request.get_json()
    logger.info(f"Signup attempt: {data['email']}")
    if not all(k in data for k in ('full_name', 'phone', 'id_number', 'kra_pin', 'email', 'password')):
        return jsonify({'error': 'Missing required fields'}), 400
    if User.query.filter_by(email=data['email']).first() or User.query.filter_by(phone=data['phone']).first():
        logger.warning(f"Duplicate signup attempt: {data['email']}")
        return jsonify({'error': 'User already exists'}), 400
    hashed_password = generate_password_hash(data['password'])
    new_user = User(
        full_name=data['full_name'], phone=data['phone'], id_number=data['id_number'],
        kra_pin=data['kra_pin'], email=data['email'], password_hash=hashed_password,
        is_driver=data.get('is_driver', False)
    )
    db.session.add(new_user)
    db.session.commit()
    logger.info(f"User created: {new_user.email}")
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    """User login with JWT token generation."""
    data = request.get_json()
    logger.info(f"Login attempt: {data['email']}")
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password_hash, data['password']):
        access_token = create_access_token(identity=user.id)
        logger.info(f"Login successful: {user.email}")
        return jsonify({'access_token': access_token, 'is_driver': user.is_driver}), 200
    logger.warning(f"Login failed: {data['email']}")
    return jsonify({'error': 'Invalid credentials'}), 401

# Vehicle Routes
@app.route('/vehicles', methods=['POST'])
@jwt_required()
def add_vehicle():
    """Add a vehicle listing (free)."""
    user_id = get_jwt_identity()
    data = request.form
    logger.info(f"Adding vehicle for user {user_id}")
    if 'vehicle_reg' not in data or 'vehicle_type' not in data:
        return jsonify({'error': 'Missing vehicle details'}), 400
    file = request.files.get('image')
    image_path = None
    if file:
        image_path = os.path.join('uploads', file.filename)
        file.save(image_path)
        logger.info(f"Vehicle image uploaded: {image_path}")
    new_vehicle = Vehicle(
        user_id=user_id, vehicle_reg=data['vehicle_reg'], vehicle_type=data['vehicle_type'],
        tons=data.get('tons'), image=image_path
    )
    db.session.add(new_vehicle)
    db.session.commit()
    socketio.emit('vehicle_added', {'vehicle_id': new_vehicle.id, 'vehicle_reg': new_vehicle.vehicle_reg})
    logger.info(f"Vehicle added: {new_vehicle.vehicle_reg}")
    return jsonify({'message': 'Vehicle added successfully (free)'}), 201

@app.route('/vehicles', methods=['GET'])
@jwt_required()
def get_vehicles():
    """Fetch user's vehicles."""
    user_id = get_jwt_identity()
    logger.info(f"Fetching vehicles for user {user_id}")
    vehicles = Vehicle.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'id': v.id, 'vehicle_reg': v.vehicle_reg, 'vehicle_type': v.vehicle_type,
        'tons': v.tons, 'image': v.image, 'booked': v.booked
    } for v in vehicles]), 200

@app.route('/listings/vehicles', methods=['GET'])
@jwt_required()
def get_available_vehicles():
    """Fetch available vehicles for booking."""
    logger.info("Fetching available vehicles")
    vehicles = Vehicle.query.filter_by(booked=False).all()
    return jsonify([{
        'id': v.id, 'vehicle_reg': v.vehicle_reg, 'vehicle_type': v.vehicle_type,
        'tons': v.tons, 'image': v.image
    } for v in vehicles]), 200

@app.route('/book_vehicle/<int:vehicle_id>', methods=['POST'])
@jwt_required()
def book_vehicle(vehicle_id):
    """Book a vehicle with M-Pesa payment (Ksh 100)."""
    user_id = get_jwt_identity()
    data = request.get_json()
    logger.info(f"Booking vehicle {vehicle_id} for user {user_id}")
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    if vehicle.booked:
        logger.warning(f"Vehicle {vehicle_id} already booked")
        return jsonify({'error': 'Vehicle already booked'}), 400
    
    user = User.query.get(user_id)
    phone = user.phone if user.phone.startswith('254') else f"254{user.phone[1:]}"
    payment_response = initiate_mpesa_payment(phone, 100, f"Beba Vehicle Booking - {vehicle.vehicle_reg}")
    if payment_response.get('ResponseCode') != '0':
        logger.error(f"Payment initiation failed for booking: {payment_response}")
        return jsonify({'error': 'Payment initiation failed', 'details': payment_response}), 400
    
    booking = Booking(
        user_id=user_id, vehicle_id=vehicle_id, pickup=data['pickup'],
        destination=data['destination'], budget=data['budget'],
        payment_checkout_id=payment_response['CheckoutRequestID']
    )
    db.session.add(booking)
    db.session.commit()
    logger.info(f"Booking initiated: {booking.id}, awaiting payment")
    return jsonify({'message': 'Payment initiated. Please complete Ksh 100 on your phone.', 'checkout_id': payment_response['CheckoutRequestID']}), 202

# Listing Routes
@app.route('/listings/<type>', methods=['POST'])
@jwt_required()
def add_listing(type):
    """Add a listing with M-Pesa payment (Ksh 100)."""
    user_id = get_jwt_identity()
    if type not in ['rentals', 'shamba', 'apartments']:
        logger.warning(f"Invalid listing type: {type}")
        return jsonify({'error': 'Invalid listing type'}), 400
    
    data = request.form
    logger.info(f"Adding {type} listing for user {user_id}")
    files = request.files.getlist('images')
    image_paths = [os.path.join('uploads', f.filename) for f in files if f.save(os.path.join('uploads', f.filename))]

    user = User.query.get(user_id)
    phone = user.phone if user.phone.startswith('254') else f"254{user.phone[1:]}"
    payment_response = initiate_mpesa_payment(phone, 100, f"Beba {type.capitalize()} Listing")
    if payment_response.get('ResponseCode') != '0':
        logger.error(f"Payment initiation failed for {type} listing: {payment_response}")
        return jsonify({'error': 'Payment initiation failed', 'details': payment_response}), 400
    
    listing = Listing(
        user_id=user_id, type=type[:-1], location=data['location'], lat=data.get('lat'), lng=data.get('lng'),
        details=data['details'], price=data['price'], payment_checkout_id=payment_response['CheckoutRequestID']
    )
    if type == 'shamba':
        title_deed = request.files.get('title_deed')
        if title_deed:
            listing.title_deed = os.path.join('uploads', title_deed.filename)
            title_deed.save(listing.title_deed)
            logger.info(f"Title deed uploaded for shamba: {listing.title_deed}")
    db.session.add(listing)
    db.session.commit()
    logger.info(f"{type} listing initiated: {listing.id}, awaiting payment")
    return jsonify({'message': 'Payment initiated. Please complete Ksh 100 on your phone.', 'checkout_id': payment_response['CheckoutRequestID']}), 202

@app.route('/listings/<type>', methods=['GET'])
@jwt_required()
def get_listings(type):
    """Fetch user's completed listings."""
    user_id = get_jwt_identity()
    logger.info(f"Fetching {type} listings for user {user_id}")
    listings = Listing.query.filter_by(user_id=user_id, type=type[:-1], payment_status='completed').all()
    return jsonify([{
        'id': l.id, 'location': l.location, 'lat': l.lat, 'lng': l.lng,
        'details': l.details, 'price': l.price
    } for l in listings]), 200

# Transport Job Routes
@app.route('/transport_jobs', methods=['POST'])
@jwt_required()
def add_transport_job():
    """Post a transport job with M-Pesa payment (Ksh 100)."""
    user_id = get_jwt_identity()
    data = request.get_json()
    logger.info(f"Posting transport job for user {user_id}")
    user = User.query.get(user_id)
    phone = user.phone if user.phone.startswith('254') else f"254{user.phone[1:]}"
    payment_response = initiate_mpesa_payment(phone, 100, f"Beba Transport Job - {data['pickup_location']} to {data['destination']}")
    if payment_response.get('ResponseCode') != '0':
        logger.error(f"Payment initiation failed for transport job: {payment_response}")
        return jsonify({'error': 'Payment initiation failed', 'details': payment_response}), 400
    
    job = TransportJob(
        user_id=user_id, pickup_location=data['pickup_location'],
        destination=data['destination'], description=data['description'],
        budget=data['budget'], payment_checkout_id=payment_response['CheckoutRequestID']
    )
    db.session.add(job)
    db.session.commit()
    logger.info(f"Transport job initiated: {job.id}, awaiting payment")
    return jsonify({'message': 'Payment initiated. Please complete Ksh 100 on your phone.', 'checkout_id': payment_response['CheckoutRequestID']}), 202

@app.route('/transport_jobs', methods=['GET'])
@jwt_required()
def get_transport_jobs():
    """Search available transport jobs by location and destination."""
    pickup = request.args.get('pickup_location', '')
    destination = request.args.get('destination', '')
    logger.info(f"Searching transport jobs: pickup={pickup}, destination={destination}")
    jobs = TransportJob.query.filter(
        TransportJob.status == 'available',
        TransportJob.payment_status == 'completed',
        TransportJob.pickup_location.ilike(f'%{pickup}%'),
        TransportJob.destination.ilike(f'%{destination}%')
    ).all()
    return jsonify([{
        'id': j.id, 'pickup_location': j.pickup_location, 'destination': j.destination,
        'description': j.description, 'budget': j.budget, 'timestamp': j.timestamp.isoformat()
    } for j in jobs]), 200

# Insurance Route
@app.route('/insurance', methods=['POST'])
@jwt_required()
def add_insurance():
    """Add insurance (free)."""
    user_id = get_jwt_identity()
    data = request.get_json()
    logger.info(f"Adding insurance for user {user_id}")
    insurance = Insurance(
        user_id=user_id, vehicle_id=data['vehicle_id'], policy_number=data['policy_number'],
        expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d')
    )
    db.session.add(insurance)
    db.session.commit()
    logger.info(f"Insurance added: {insurance.policy_number}")
    return jsonify({'message': 'Insurance added successfully (free)'}), 201

# Run the app
if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    logger.info("Initializing database and starting server")
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
