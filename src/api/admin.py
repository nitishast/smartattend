# src/api/admin.py
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from src.models.database import db, User, Student, Class, AttendanceSession, SecurityLog
from src.api.auth import login_required, role_required
from sqlalchemy import func, distinct
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@role_required(['admin'])
def dashboard():
    """Admin dashboard with system overview"""
    # Basic statistics
    total_students = Student.query.count()
    total_users = User.query.count()
    total_classes = Class.query.count()

    # Active attendance sessions
    active_sessions = AttendanceSession.query.filter_by(is_active=True).count()

    # Recent attendance (last 7 days)
    recent_attendance = db.session.query(
        func.date(AttendanceSession.date).label('date'),
        func.count(distinct(Attendance.student_id)).label('student_count')
    ).join(Attendance, Attendance.session_id == AttendanceSession.id).filter(
        AttendanceSession.date >= datetime.utcnow() - timedelta(days=7)
    ).group_by(func.date(AttendanceSession.date)).order_by(func.date(AttendanceSession.date)).all()

    # Recent security logs (last 7 days)
    recent_security_logs = SecurityLog.query.filter(
        SecurityLog.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).order_by(SecurityLog.timestamp.desc()).limit(10).all()
    
    # Format data for charts
    attendance_labels = [entry.date.strftime('%Y-%m-%d') for entry in recent_attendance]
    attendance_data = [entry.student_count for entry in recent_attendance]

    return render_template('admin/dashboard.html',
                           total_students=total_students,
                           total_users=total_users,
                           total_classes=total_classes,
                           active_sessions=active_sessions,
                           recent_security_logs=recent_security_logs,
                           attendance_labels=attendance_labels,
                           attendance_data=attendance_data)

@admin_bp.route('/users')
@role_required(['admin'])
def users():
    """Manage users (list, edit, delete)"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@role_required(['admin'])
def edit_user(user_id):
    """Edit user details (admin-only)"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user.username = request.form.get('username')
        user.email = request.form.get('email')
        user.role = request.form.get('role')
        user.is_active = request.form.get('is_active') == 'true'

        if 'password' in request.form and request.form.get('password'):
             user.password_hash = generate_password_hash(request.form.get('password'))

        db.session.commit()
        flash(f'User {user.username} updated successfully', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/edit_user.html', user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@role_required(['admin'])
def delete_user(user_id):
    """Delete a user (admin-only)"""
    user = User.query.get_or_404(user_id)

    if user.role == 'admin' and User.query.filter_by(role='admin').count() == 1:
        flash('Cannot delete the last admin user', 'error')
        return redirect(url_for('admin.users'))

    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted successfully', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/classes')
@role_required(['admin'])
def classes():
    """Manage classes (list, add, edit, delete)"""
    classes = Class.query.all()
    users = User.query.filter_by(role='teacher').all()  # Fetch only teachers
    return render_template('admin/classes.html', classes=classes, users=users)

@admin_bp.route('/classes/add', methods=['POST'])
@role_required(['admin'])
def add_class():
    """Add a new class"""
    class_name = request.form.get('class_name')
    class_code = request.form.get('class_code')
    teacher_id = request.form.get('teacher_id')
    schedule = request.form.get('schedule')
    room = request.form.get('room')

    # Validate input (add more validation as needed)
    if not class_name or not class_code:
        flash('Class name and code are required', 'error')
        return redirect(url_for('admin.classes'))

    # Check if class code already exists
    if Class.query.filter_by(class_code=class_code).first():
        flash('Class code already exists', 'error')
        return redirect(url_for('admin.classes'))

    # Create new class
    new_class = Class(
        class_name=class_name,
        class_code=class_code,
        teacher_id=teacher_id,
        schedule=schedule,
        room=room
    )

    db.session.add(new_class)
    db.session.commit()

    flash(f'Class {class_name} created successfully', 'success')
    return redirect(url_for('admin.classes'))

@admin_bp.route('/classes/edit/<int:class_id>', methods=['GET', 'POST'])
@role_required(['admin'])
def edit_class(class_id):
    """Edit class details"""
    class_obj = Class.query.get_or_404(class_id)
    teachers = User.query.filter_by(role='teacher').all()

    if request.method == 'POST':
        class_obj.class_name = request.form.get('class_name')
        class_obj.class_code = request.form.get('class_code')
        class_obj.teacher_id = request.form.get('teacher_id')
        class_obj.schedule = request.form.get('schedule')
        class_obj.room = request.form.get('room')

        db.session.commit()
        flash(f'Class {class_obj.class_name} updated successfully', 'success')
        return redirect(url_for('admin.classes'))

    return render_template('admin/edit_class.html', class_obj=class_obj, users=teachers)

@admin_bp.route('/classes/delete/<int:class_id>', methods=['POST'])
@role_required(['admin'])
def delete_class(class_id):
    """Delete a class"""
    class_obj = Class.query.get_or_404(class_id)

    db.session.delete(class_obj)
    db.session.commit()
    flash(f'Class {class_obj.class_name} deleted successfully', 'success')
    return redirect(url_for('admin.classes'))

@admin_bp.route('/security_logs')
@role_required(['admin'])
def security_logs():
    """View security logs"""
    logs = SecurityLog.query.order_by(SecurityLog.timestamp.desc()).all()
    return render_template('admin/security_logs.html', logs=logs)

@admin_bp.route('/attendance_sessions')
@role_required(['admin'])
def attendance_sessions():
    """View all attendance sessions"""
    sessions = AttendanceSession.query.order_by(AttendanceSession.start_time.desc()).all()
    return render_template('admin/attendance_sessions.html', sessions=sessions)

@admin_bp.route('/attendance_sessions/<int:session_id>')
@role_required(['admin'])
def view_attendance_session(session_id):
    session = AttendanceSession.query.get_or_404(session_id)
    attendance_records = Attendance.query.filter_by(session_id=session_id).all()
    return render_template('admin/view_attendance_session.html', session=session, attendance_records=attendance_records)


@admin_bp.route('/system_status')
@role_required(['admin'])
def system_status():
    """Display system status and diagnostics"""

    # Camera status
    camera_manager = current_app.config['CAMERA_MANAGER']
    cameras = camera_manager.get_all_cameras()

    # Attendance processor status
    attendance_processor = current_app.config['ATTENDANCE_PROCESSOR']
    processor_status = {
        'is_running': attendance_processor.is_running,
        'stats': attendance_processor.get_stats()
    }

    # Face recognition system status
    face_recognition = current_app.config['FACE_RECOGNITION']
    recognition_status = {
        'known_faces': len(face_recognition.known_face_ids),
        'detection_method': face_recognition.detection_method,
    }

    return render_template('admin/system_status.html',
                           cameras=cameras,
                           processor_status=processor_status,
                           recognition_status=recognition_status)