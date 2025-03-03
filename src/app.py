import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import logging
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv  # Import load_dotenv

from src.models.database import db, User, Student, Class, Attendance, AttendanceSession, FaceEmbedding, SecurityLog
from src.utils.face_recognition_utils import FaceRecognitionSystem
from src.utils.camera import CameraManager
from src.utils.attendance_processor import AttendanceProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Load configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev_key_change_in_production'),
        # DATABASE_URL is now loaded from .env, so no need for a default here
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Updated paths, relative to app.py (which is inside src/)
        UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), '../data/uploads'),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload
    )
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
    # Initialize face recognition system
    face_recognition = FaceRecognitionSystem(
        # Updated paths, relative to app.py
        model_path=os.path.join(os.path.dirname(__file__), '../data/face_encodings.pkl'),
        enrollment_dir=os.path.join(os.path.dirname(__file__), '../data/enrollments/'),
        detection_method='hog',  # Use 'cnn' for better accuracy if GPU available
        distance_threshold=0.6
    )
    
    # Initialize camera manager
    camera_manager = CameraManager()
    
    # Initialize attendance processor
    attendance_processor = AttendanceProcessor(
        camera_manager=camera_manager,
        face_recognition_system=face_recognition,
        processing_interval=1.0,
        confidence_threshold=0.65,
        store_unknown_faces=True,
        # Updated path, relative to app.py
        unknown_faces_dir=os.path.join(os.path.dirname(__file__), '../data/unknown_faces/')
    )
    
    # Make components available to views
    @app.before_request
    def before_request():
        app.config['FACE_RECOGNITION'] = face_recognition
        app.config['CAMERA_MANAGER'] = camera_manager
        app.config['ATTENDANCE_PROCESSOR'] = attendance_processor
    
    # Register blueprints
    from src.api.auth import auth_bp
    from src.api.students import students_bp
    from src.api.attendance import attendance_bp
    from src.api.cameras import cameras_bp
    from src.api.admin import admin_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(cameras_bp)
    app.register_blueprint(admin_bp)
    
    # Start attendance processor
    attendance_processor.start()
    
    # Home route
    @app.route('/')
    def index():
        return render_template('index.html')
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500
    
    # Save face embeddings when app shuts down
    @app.teardown_appcontext
    def teardown_app(exception=None):
        face_recognition.save_encodings(
            # Updated path, relative to app.py
            os.path.join(os.path.dirname(__file__), '../data/face_encodings.pkl')
        )
        attendance_processor.stop()
        camera_manager.stop_all()
    
    return app

if __name__ == '__main__':
    app = create_app()
    # Use Flask's built-in server with automatic reloading
    app.run(debug=True, host='0.0.0.0', port=5000)  # Or use flask run --debug