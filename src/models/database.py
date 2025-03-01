from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship

db = SQLAlchemy()

# Association table for many-to-many relationships
class_student_association = Table(
    'class_student_association',
    db.Model.metadata,
    Column('class_id', Integer, ForeignKey('class.id')),
    Column('student_id', Integer, ForeignKey('student.id'))
)

class User(db.Model):
    """Base user model for authentication"""
    __tablename__ = 'user'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), nullable=False)  # admin, teacher, staff
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True)

class Student(db.Model):
    """Student model containing personal information"""
    __tablename__ = 'student'
    
    id = Column(Integer, primary_key=True)
    student_id = Column(String(20), unique=True, nullable=False)  # School ID
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(120), unique=True)
    grade_level = Column(String(10))
    date_of_birth = Column(DateTime)
    enrollment_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    face_embeddings = relationship("FaceEmbedding", back_populates="student")
    attendances = relationship("Attendance", back_populates="student")
    classes = relationship("Class", secondary=class_student_association, back_populates="students")

class FaceEmbedding(db.Model):
    """Stores face embedding vectors for each student"""
    __tablename__ = 'face_embedding'
    
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False)
    embedding_vector = Column(String(8000), nullable=False)  # Stored as a serialized vector
    image_path = Column(String(255))  # Path to the original image (optional)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationship
    student = relationship("Student", back_populates="face_embeddings")

class Class(db.Model):
    """Class or course information"""
    __tablename__ = 'class'
    
    id = Column(Integer, primary_key=True)
    class_name = Column(String(100), nullable=False)
    class_code = Column(String(20), unique=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey('user.id'))
    schedule = Column(String(100))  # Can be enhanced with a proper schedule model
    room = Column(String(20))
    
    # Relationships
    teacher = relationship("User")
    students = relationship("Student", secondary=class_student_association, back_populates="classes")
    attendance_sessions = relationship("AttendanceSession", back_populates="class_obj")

class AttendanceSession(db.Model):
    """Represents a single attendance-taking session"""
    __tablename__ = 'attendance_session'
    
    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey('class.id'), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('user.id'))
    
    # Relationships
    class_obj = relationship("Class", back_populates="attendance_sessions")
    creator = relationship("User")
    attendances = relationship("Attendance", back_populates="session")

class Attendance(db.Model):
    """Records individual student attendance"""
    __tablename__ = 'attendance'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('attendance_session.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False)
    check_in_time = Column(DateTime)
    check_out_time = Column(DateTime)
    status = Column(String(20), default='present')  # present, absent, late, excused
    confidence_score = Column(Float)  # Confidence score of the facial recognition
    verification_method = Column(String(20), default='facial')  # facial, manual, etc.
    notes = Column(String(255))
    
    # Relationships
    session = relationship("AttendanceSession", back_populates="attendances")
    student = relationship("Student", back_populates="attendances")

class SecurityLog(db.Model):
    """Logs security-related events"""
    __tablename__ = 'security_log'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String(50), nullable=False)  # entry, exit, unknown_person
    location = Column(String(50))
    person_id = Column(Integer, ForeignKey('student.id'))  # Could be null for unknown persons
    confidence_score = Column(Float)
    image_path = Column(String(255))  # Path to the captured image
    notes = Column(String(255))
    
    # Relationship
    person = relationship("Student")