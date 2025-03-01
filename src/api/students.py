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
    student = Student.query.get_or_