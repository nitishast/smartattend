import cv2
import numpy as np
import time
import logging
import threading
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any

from src.utils.face_recognition_utils import FaceRecognitionSystem
from src.utils.camera import CameraManager, Camera
from src.models.database import db, Student, Attendance, AttendanceSession, SecurityLog

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AttendanceProcessor:
    """
    Processes camera feeds for face recognition and attendance tracking
    """
    
    def __init__(self, 
                 camera_manager: CameraManager,
                 face_recognition_system: FaceRecognitionSystem,
                 processing_interval: float = 1.0,  # Process every 1 second
                 confidence_threshold: float = 0.65,  # Minimum confidence to mark attendance
                 store_unknown_faces: bool = True,
                 unknown_faces_dir: str = 'data/unknown_faces/'):
        """
        Initialize the attendance processor
        
        Args:
            camera_manager: Camera manager instance
            face_recognition_system: Face recognition system instance
            processing_interval: Time between processing frames (seconds)
            confidence_threshold: Minimum confidence threshold for recognition
            store_unknown_faces: Whether to store images of unknown faces
            unknown_faces_dir: Directory to store unknown faces
        """
        self.camera_manager = camera_manager
        self.face_recognition = face_recognition_system
        self.processing_interval = processing_interval
        self.confidence_threshold = confidence_threshold
        self.store_unknown_faces = store_unknown_faces
        self.unknown_faces_dir = unknown_faces_dir
        
        # Create unknown faces directory if it doesn't exist
        if store_unknown_faces and not os.path.exists(unknown_faces_dir):
            os.makedirs(unknown_faces_dir)
            
        self.is_running = False
        self.thread = None
        self.active_sessions: Dict[int, AttendanceSession] = {}  # Map of class_id -> session
        
        # Keep track of already marked students to avoid duplicate entries
        self.processed_students: Dict[int, Dict[str, float]] = {}  # session_id -> {student_id: timestamp}
        
        # Store recognition statistics
        self.stats = {
            'processed_frames': 0,
            'recognized_faces': 0,
            'unknown_faces': 0,
            'attendance_records': 0,
            'security_logs': 0
        }
        
    def start(self) -> bool:
        """Start the attendance processor"""
        if self.is_running:
            return True
            
        self.is_running = True
        self.thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.thread.start()
        
        logger.info("Attendance processor started")
        return True
        
    def stop(self) -> None:
        """Stop the attendance processor"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
            
        logger.info("Attendance processor stopped")
        
    def start_attendance_session(self, class_id: int, created_by: int) -> Optional[AttendanceSession]:
        """
        Start a new attendance session for a class
        
        Args:
            class_id: ID of the class
            created_by: ID of the user who created the session
            
        Returns:
            AttendanceSession object if successful, None otherwise
        """
        try:
            # Check if a session is already active for this class
            if class_id in self.active_sessions:
                logger.warning(f"Attendance session already active for class {class_id}")
                return self.active_sessions[class_id]
                
            # Create a new session
            now = datetime.utcnow()
            session = AttendanceSession(
                class_id=class_id,
                start_time=now,
                created_by=created_by,
                is_active=True
            )
            
            db.session.add(session)
            db.session.commit()
            
            # Add to active sessions
            self.active_sessions[class_id] = session
            self.processed_students[session.id] = {}
            
            logger.info(f"Started attendance session {session.id} for class {class_id}")
            return session
            
        except Exception as e:
            logger.error(f"Error starting attendance session: {str(e)}")
            db.session.rollback()
            return None
            
    def end_attendance_session(self, class_id: int) -> bool:
        """
        End an active attendance session
        
        Args:
            class_id: ID of the class
            
        Returns:
            Success status
        """
        try:
            if class_id not in self.active_sessions:
                logger.warning(f"No active attendance session for class {class_id}")
                return False
                
            session = self.active_sessions[class_id]
            session.end_time = datetime.utcnow()
            session.is_active = False
            
            db.session.commit()
            
            # Remove from active sessions
            del self.active_sessions[class_id]
            if session.id in self.processed_students:
                del self.processed_students[session.id]
                
            logger.info(f"Ended attendance session {session.id} for class {class_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error ending attendance session: {str(e)}")
            db.session.rollback()
            return False
    
    def _processing_loop(self) -> None:
        """Background thread for processing camera frames"""
        last_process_time = 0
        
        while self.is_running:
            try:
                # Only process at the specified interval
                current_time = time.time()
                if current_time - last_process_time < self.processing_interval:
                    time.sleep(0.1)  # Short sleep to prevent CPU hogging
                    continue
                    
                last_process_time = current_time
                
                # Get active cameras
                active_cameras = self.camera_manager.get_active_cameras()
                if not active_cameras:
                    time.sleep(0.5)  # Longer sleep if no active cameras
                    continue
                    
                # Process each camera
                for camera_name, camera in active_cameras.items():
                    self._process_camera(camera)
                    
            except Exception as e:
                logger.error(f"Error in attendance processing loop: {str(e)}")
                time.sleep(1.0)  # Sleep longer on error
    
    def _process_camera(self, camera: Camera) -> None:
        """Process frames from a single camera"""
        # Get the latest frame
        frame = camera.get_frame()
        if frame is None:
            return
            
        self.stats['processed_frames'] += 1
        
        # Detect and recognize faces
        recognition_results = self.face_recognition.recognize_face(frame)
        
        if not recognition_results:
            return
            
        # Process each detected face
        for result in recognition_results:
            student_id = result['id']
            confidence = result['confidence']
            bbox = result['bbox']
            
            if student_id is not None and confidence >= self.confidence_threshold:
                # Known face with sufficient confidence
                self.stats['recognized_faces'] += 1
                self._process_recognized_face(student_id, confidence, frame, bbox, camera.name)
            else:
                # Unknown face or low confidence
                self.stats['unknown_faces'] += 1
                self._process_unknown_face(frame, bbox, confidence, camera.name)
    
    def _process_recognized_face(self, student_id: str, confidence: float, 
                               frame: np.ndarray, bbox: Tuple[int, int, int, int], 
                               camera_location: str) -> None:
        """Process a recognized face - mark attendance or log entry"""
        try:
            # Look up the student
            student = Student.query.filter_by(student_id=student_id).first()
            if not student:
                logger.warning(f"Recognized student ID {student_id} not found in database")
                return
                
            # Check if this student is enrolled in any classes with active sessions
            student_class_ids = [c.id for c in student.classes]
            active_session_found = False
            
            # Process for each active session that includes this student
            now = datetime.utcnow()
            for class_id, session in self.active_sessions.items():
                if class_id in student_class_ids:
                    # Check if we haven't already processed this student recently
                    session_students = self.processed_students.get(session.id, {})
                    last_detection_time = session_students.get(str(student.id), 0)
                    
                    # Only process if we haven't seen this student in the last 5 minutes
                    if time.time() - last_detection_time > 300:  # 5 minutes
                        # Create attendance record
                        attendance = Attendance(
                            session_id=session.id,
                            student_id=student.id,
                            check_in_time=now,
                            status='present',
                            confidence_score=confidence,
                            verification_method='facial',
                            notes=f"Detected at {camera_location}"
                        )
                        
                        db.session.add(attendance)
                        self.stats['attendance_records'] += 1
                        active_session_found = True
                        
                        # Update processed students
                        if session.id not in self.processed_students:
                            self.processed_students[session.id] = {}
                        self.processed_students[session.id][str(student.id)] = time.time()
                        
                        logger.info(f"Marked attendance for student {student.student_id} in session {session.id}")
            
            # If no active session, log as a security entry
            if not active_session_found:
                self._log_security_event(
                    student_id=student.id,
                    event_type='entry',
                    location=camera_location,
                    confidence=confidence,
                    frame=frame,
                    bbox=bbox
                )
                
            # Optional: Update student face embeddings for progressive improvement
            if confidence > 0.8:  # Only use high-confidence detections
                # Extract face from the frame
                top, right, bottom, left = bbox
                face_image = frame[top:bottom, left:right]
                
                # Get face encoding
                face_encodings = face_recognition.face_encodings([face_image])
                if face_encodings:
                    self.face_recognition.update_embeddings(student_id, face_encodings[0])
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error processing recognized face: {str(e)}")
            db.session.rollback()
    
    def _process_unknown_face(self, frame: np.ndarray, bbox: Tuple[int, int, int, int], 
                            confidence: float, camera_location: str) -> None:
        """Process an unknown face - log security event and optionally store image"""
        try:
            # Log security event
            self._log_security_event(
                student_id=None,
                event_type='unknown_person',
                location=camera_location,
                confidence=confidence,
                frame=frame,
                bbox=bbox
            )
            
            # Store unknown face image if enabled
            if self.store_unknown_faces:
                top, right, bottom, left = bbox
                face_image = frame[top:bottom, left:right]
                
                # Create filename with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"unknown_{timestamp}_{camera_location.replace(' ', '_')}.jpg"
                filepath = os.path.join(self.unknown_faces_dir, filename)
                
                # Save image
                cv2.imwrite(filepath, face_image)
                logger.info(f"Stored unknown face image: {filepath}")
        
        except Exception as e:
            logger.error(f"Error processing unknown face: {str(e)}")
            db.session.rollback()
    
    def _log_security_event(self, student_id: Optional[int], event_type: str, 
                          location: str, confidence: float, frame: np.ndarray,
                          bbox: Tuple[int, int, int, int]) -> None:
        """Log a security event"""
        try:
            # Extract face from the frame
            top, right, bottom, left = bbox
            face_image = frame[top:bottom, left:right]
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"security_{event_type}_{timestamp}_{location.replace(' ', '_')}.jpg"
            filepath = os.path.join('data/logs/', filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Save image
            cv2.imwrite(filepath, face_image)
            
            # Create security log entry
            log_entry = SecurityLog(
                event_type=event_type,
                location=location,
                person_id=student_id,
                confidence_score=confidence,
                image_path=filepath
            )
            
            db.session.add(log_entry)
            db.session.commit()
            
            self.stats['security_logs'] += 1
            logger.info(f"Created security log: {event_type} at {location}")
            
        except Exception as e:
            logger.error(f"Error logging security event: {str(e)}")
            db.session.rollback()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self.stats.copy()
    
    def reset_stats(self) -> None:
        """Reset processing statistics"""
        for key in self.stats:
            self.stats[key] = 0