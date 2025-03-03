# src/api/attendance.py
from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for, current_app
from src.models.database import db, Class, AttendanceSession, Attendance, Student
from src.api.auth import login_required, role_required
from datetime import datetime

attendance_bp = Blueprint('attendance', __name__, url_prefix='/attendance')

@attendance_bp.route('/sessions')
@login_required
def sessions():
    """List attendance sessions (for teachers, their classes)"""
    if current_app.config.get('user') and current_app.config['user'].role == 'teacher':
        # Show sessions created by the teacher
        sessions = AttendanceSession.query.filter_by(created_by=current_app.config['user'].id).order_by(AttendanceSession.start_time.desc()).all()
    else:  # Default for non-teachers/admins, can be refined
        sessions = AttendanceSession.query.order_by(AttendanceSession.start_time.desc()).all()
    return render_template('attendance/sessions.html', sessions=sessions)


@attendance_bp.route('/sessions/start', methods=['GET', 'POST'])
@role_required(['teacher'])
def start_session():
    """Start a new attendance session (teacher-only)"""
    if request.method == 'POST':
        class_id = request.form.get('class_id')

        # Validate
        if not class_id:
            flash('Class ID is required', 'error')
            return redirect(url_for('attendance.start_session'))

        # Start the session using the attendance processor
        attendance_processor = current_app.config['ATTENDANCE_PROCESSOR']
        session = attendance_processor.start_attendance_session(int(class_id), current_app.config['user'].id)

        if session:
            flash(f'Attendance session started for class {class_id}', 'success')
            return redirect(url_for('attendance.sessions'))
        else:
            flash('Failed to start attendance session', 'error')
            return redirect(url_for('attendance.start_session'))

    # Get classes taught by the current teacher
    classes = Class.query.filter_by(teacher_id=current_app.config['user'].id).all()
    return render_template('attendance/start_session.html', classes=classes)


@attendance_bp.route('/sessions/end/<int:class_id>', methods=['POST'])
@role_required(['teacher'])
def end_session(class_id):
    """End an active attendance session (teacher-only)"""
    attendance_processor = current_app.config['ATTENDANCE_PROCESSOR']
    success = attendance_processor.end_attendance_session(class_id)

    if success:
        flash(f'Attendance session ended for class {class_id}', 'success')
    else:
        flash('Failed to end attendance session', 'error')

    return redirect(url_for('attendance.sessions'))



@attendance_bp.route('/sessions/view/<int:session_id>')
@login_required
def view_session(session_id):
    """View details of a specific attendance session"""
    session = AttendanceSession.query.get_or_404(session_id)

    # Check authorization (teacher can only view their sessions, admin can view all)
    if current_app.config.get('user') and current_app.config['user'].role == 'teacher' and session.created_by != current_app.config['user'].id:
        flash('You do not have permission to view this session', 'error')
        return redirect(url_for('attendance.sessions'))


    attendance_records = Attendance.query.filter_by(session_id=session_id).all()
    return render_template('attendance/view_session.html', session=session, attendance_records=attendance_records)

@attendance_bp.route('/sessions/edit/<int:attendance_id>', methods=['POST'])
@role_required(['teacher', 'admin'])
def edit_attendance(attendance_id):
    """Edit individual attendance records (e.g., change status)"""
    attendance = Attendance.query.get_or_404(attendance_id)
    session = AttendanceSession.query.get_or_404(attendance.session_id)

    # Authorization check: Only the teacher who created the session or an admin
    if not (current_app.config.get('user') and (current_app.config['user'].role == 'admin' or session.created_by == current_app.config['user'].id)):
        return jsonify({'error': 'Unauthorized'}), 403

    new_status = request.form.get('status')
    notes = request.form.get('notes')

    if new_status:
        attendance.status = new_status
    if notes is not None:
        attendance.notes = notes

    db.session.commit()
    flash('Attendance record updated', 'success')

    return redirect(url_for('attendance.view_session', session_id=attendance.session_id))


@attendance_bp.route('/my_attendance')
@login_required
def my_attendance():
    """View personal attendance records (for students)"""
    # Assuming the logged-in user is a student (you might need a different mechanism)
    if 'user_id' not in current_app.config or current_app.config['user'].role != 'student':
        flash('You must be logged in as a student to view your attendance.', 'error')
        return redirect(url_for('index'))

    student = Student.query.filter_by(student_id = current_app.config['user'].username ).first()
    if not student:
          flash('Student details not found', 'error')
          return redirect(url_for('index'))

    attendance_records = Attendance.query.filter_by(student_id=student.id).join(AttendanceSession).order_by(AttendanceSession.date.desc()).all()

    return render_template('attendance/my_attendance.html', attendance_records=attendance_records, student=student)


# API Endpoints
@attendance_bp.route('/api/sessions', methods=['GET'])
@login_required
def api_get_sessions():
    """Get all attendance sessions (for API access)"""
    sessions = AttendanceSession.query.all()
    return jsonify([{'id': s.id, 'class_id': s.class_id, 'start_time': s.start_time, 'end_time': s.end_time, 'is_active': s.is_active} for s in sessions])

@attendance_bp.route('/api/sessions/<int:session_id>', methods=['GET'])
@login_required
def api_get_session(session_id):
    """Get details of a specific session (for API access)"""
    session = AttendanceSession.query.get_or_404(session_id)
    return jsonify({'id': session.id, 'class_id': session.class_id, 'start_time': session.start_time, 'end_time': session.end_time, 'is_active': session.is_active})

@attendance_bp.route('/api/sessions/<int:session_id>/attendance', methods=['GET'])
@login_required
def api_get_session_attendance(session_id):
    """Get attendance records for a specific session (for API access)"""
    attendance_records = Attendance.query.filter_by(session_id=session_id).all()
    return jsonify([{'id': a.id, 'student_id': a.student_id, 'check_in_time': a.check_in_time, 'status': a.status} for a in attendance_records])