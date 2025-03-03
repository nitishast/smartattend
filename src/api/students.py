import os
import uuid
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import numpy as np

from src.models.database import db, Student, FaceEmbedding, Class
from src.api.auth import login_required, role_required
import face_recognition

students_bp = Blueprint('students', __name__, url_prefix='/students')

def allowed_file(filename):
    """Check if file has an allowed extension"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@students_bp.route('/')
@login_required
def index():
    """List all students"""
    students = Student.query.all()
    return render_template('students/index.html', students=students)

@students_bp.route('/view/<int:student_id>')
@login_required
def view(student_id):
    """View student details"""
    student = Student.query.get_or_404(student_id)
    return render_template('students/view.html', student=student)

@students_bp.route('/add', methods=['GET', 'POST'])
@role_required(['admin', 'teacher'])
def add():
    """Add a new student"""
    if request.method == 'POST':
        # Get form data
        student_id = request.form.get('student_id')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        grade_level = request.form.get('grade_level')
        dob_str = request.form.get('date_of_birth')
        
        # Validate required fields
        if not student_id or not first_name or not last_name:
            flash('Student ID, first name, and last name are required', 'error')
            return render_template('students/add.html')
        
        # Check if student ID already exists
        if Student.query.filter_by(student_id=student_id).first():
            flash('Student ID already exists', 'error')
            return render_template('students/add.html')
        
        # Parse date of birth if provided
        dob = None
        if dob_str:
            try:
                dob = datetime.strptime(dob_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid date format for date of birth', 'error')
                return render_template('students/add.html')
        
        # Create student
        student = Student(
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            grade_level=grade_level,
            date_of_birth=dob,
            enrollment_date=datetime.utcnow()
        )
        
        # Add to selected classes
        class_ids = request.form.getlist('classes')
        if class_ids:
            classes = Class.query.filter(Class.id.in_(class_ids)).all()
            student.classes.extend(classes)
        
        db.session.add(student)
        db.session.commit()
        
        flash(f'Student {first_name} {last_name} added successfully', 'success')
        
        # Check if face images were uploaded
        if 'face_images' in request.files:
            return redirect(url_for('students.enroll_face', student_id=student.id))
        
        return redirect(url_for('students.index'))
    
    # Get all classes for the form
    classes = Class.query.all()
    return render_template('students/add.html', classes=classes)

@students_bp.route('/edit/<int:student_id>', methods=['GET', 'POST'])
@role_required(['admin', 'teacher'])
def edit(student_id):
    """Edit student details"""
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        # Update student data
        student.first_name = request.form.get('first_name')
        student.last_name = request.form.get('last_name')
        student.email = request.form.get('email')
        student.grade_level = request.form.get('grade_level')
        
        dob_str = request.form.get('date_of_birth')
        if dob_str:
            try:
                student.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid date format for date of birth', 'error')
                return render_template('students/edit.html', student=student)
        
        # Update classes
        class_ids = request.form.getlist('classes')
        if class_ids:
            classes = Class.query.filter(Class.id.in_(class_ids)).all()
            student.classes = classes
        else:
            student.classes = []
        
        db.session.commit()
        flash('Student information updated successfully', 'success')
        return redirect(url_for('students.view', student_id=student.id))
    
    # Get all classes for the form
    classes = Class.query.all()
    return render_template('students/edit.html', student=student, classes=classes)

@students_bp.route('/delete/<int:student_id>', methods=['POST'])
@role_required(['admin'])
def delete(student_id):
    """Delete a student"""
    student = Student.query.get_or_404(student_id)
    
    # Delete associated face embeddings
    for embedding in student.face_embeddings:
        # Delete enrollment image file
        if embedding.image_path and os.path.exists(embedding.image_path):
            try:
                os.remove(embedding.image_path)
            except OSError as e:
                current_app.logger.error(f"Error deleting file {embedding.image_path}: {e}")
                
        db.session.delete(embedding)
    
    # Remove student's enrollment directory
    enrollment_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], '../enrollments', str(student.id))
    if os.path.exists(enrollment_dir):
        try:
            for filename in os.listdir(enrollment_dir):
                file_path = os.path.join(enrollment_dir, filename)
                os.remove(file_path)
            os.rmdir(enrollment_dir)  # Remove the empty directory
        except OSError as e:
            current_app.logger.error(f"Error deleting directory {enrollment_dir}: {e}")

    # Delete the student
    db.session.delete(student)
    db.session.commit()
    
    # Remove student from face recognition system
    face_recognition = current_app.config['FACE_RECOGNITION']
    removed_count = face_recognition.remove_student(student.student_id)
    current_app.logger.info(f"Removed {removed_count} face embeddings for student {student.student_id}")
    
    flash(f'Student {student.first_name} {student.last_name} deleted successfully', 'success')
    return redirect(url_for('students.index'))

@students_bp.route('/enroll_face/<int:student_id>', methods=['GET', 'POST'])
@role_required(['admin', 'teacher'])
def enroll_face(student_id):
    """Enroll face images for a student"""
    student = Student.query.get_or_404(student_id)
    face_recognition = current_app.config['FACE_RECOGNITION']
    
    if request.method == 'POST':
        uploaded_files = request.files.getlist('face_images')
        
        # Validate at least one image is uploaded
        if not uploaded_files or uploaded_files[0].filename == '':
            flash('No files selected', 'error')
            return render_template('students/enroll_face.html', student=student)
        
        image_paths = []
        for file in uploaded_files:
            if file and allowed_file(file.filename):
                # Generate a unique filename
                filename = secure_filename(file.filename)
                file_ext = os.path.splitext(filename)[1]
                unique_filename = str(uuid.uuid4()) + file_ext
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                
                file.save(filepath)
                image_paths.append(filepath)
            else:
                flash('Invalid file type. Allowed extensions: png, jpg, jpeg', 'error')
                return render_template('students/enroll_face.html', student=student)
        
        # Enroll the face
        success, encodings = face_recognition.enroll_face(student.student_id, image_paths)
        
        if success:
            # Create database entries for face embeddings
            for i, encoding in enumerate(encodings):
                # Find the corresponding saved image (use index based on upload order)
                if i < len(image_paths):
                    image_path = image_paths[i]
                
                    new_embedding = FaceEmbedding(
                        student_id=student.id,
                        embedding_vector=str(encoding.tolist()),
                        image_path=image_path,  # Store relative path
                    )
                    db.session.add(new_embedding)
            db.session.commit()
            
            flash(f'Face enrolled successfully for {student.first_name} {student.last_name}', 'success')
            return redirect(url_for('students.view', student_id=student.id))
        else:
            flash('Face enrollment failed. Make sure the images clearly show the student\'s face.', 'error')
            
            # Clean up uploaded files
            for path in image_paths:
                if os.path.exists(path):
                    os.remove(path)
            return render_template('students/enroll_face.html', student=student)

    return render_template('students/enroll_face.html', student=student)

@students_bp.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# API Endpoints
@students_bp.route('/api/students', methods=['GET'])
@login_required
def api_get_students():
    """Get all students (for API access)"""
    students = Student.query.all()
    return jsonify([{'id': s.id, 'student_id': s.student_id, 'first_name': s.first_name, 'last_name': s.last_name} for s in students])

@students_bp.route('/api/students/<int:student_id>', methods=['GET'])
@login_required
def api_get_student(student_id):
    """Get a specific student (for API access)"""
    student = Student.query.get_or_404(student_id)
    return jsonify({'id': student.id, 'student_id': student.student_id, 'first_name': student.first_name, 'last_name': student.last_name})