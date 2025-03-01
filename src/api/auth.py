from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta
from functools import wraps

from src.models.database import db, User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Role-based authorization
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))
            
            user = User.query.get(session['user_id'])
            if not user or user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Update last login timestamp
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Set session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            flash(f'Welcome back, {user.username}!', 'success')
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@role_required(['admin'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Validate input
        if not username or not email or not password or not role:
            flash('All fields are required', 'error')
            return render_template('auth/register.html')
        
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('auth/register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('auth/register.html')
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            created_at=datetime.utcnow(),
            is_active=True
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash(f'User {username} created successfully', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('auth/register.html')

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        # Update email
        if email and email != user.email:
            if User.query.filter_by(email=email).first():
                flash('Email already exists', 'error')
            else:
                user.email = email
                flash('Email updated successfully', 'success')
        
        # Update password
        if current_password and new_password:
            if check_password_hash(user.password_hash, current_password):
                user.password_hash = generate_password_hash(new_password)
                flash('Password updated successfully', 'success')
            else:
                flash('Current password is incorrect', 'error')
        
        db.session.commit()
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html', user=user)

# API endpoints
@auth_bp.route('/api/token', methods=['POST'])
def get_token():
    """Get JWT token for API authentication"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate token
    token = jwt.encode({
        'user_id': user.id,
        'username': user.username,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, current_app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user_id': user.id,
        'username': user.username,
        'role': user.role
    })

# Initialize admin user if none exists
@auth_bp.before_app_first_request
def create_admin_user():
    if User.query.count() == 0:
        admin_user = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin'),  # Change in production!
            role='admin',
            created_at=datetime.utcnow(),
            is_active=True
        )
        
        db.session.add(admin_user)
        db.session.commit()
        current_app.logger.info('Created initial admin user (username: admin, password: admin)')