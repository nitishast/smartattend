import os
import cv2
import numpy as np
import utils.face_recognition_utils as face_recognition_utils
import pickle
from datetime import datetime
import logging
from typing import List, Tuple, Dict, Optional, Union

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FaceRecognitionSystem:
    def __init__(self, model_path: str = None, enrollment_dir: str = 'data/enrollments/', 
                 detection_method: str = 'hog', distance_threshold: float = 0.6):
        """
        Initialize the face recognition system
        
        Args:
            model_path: Path to load pre-computed embeddings
            enrollment_dir: Directory where enrollment images are stored
            detection_method: 'hog' (faster) or 'cnn' (more accurate)
            distance_threshold: Threshold for face matching (lower is stricter)
        """
        self.known_face_encodings = []
        self.known_face_ids = []
        self.detection_method = detection_method
        self.distance_threshold = distance_threshold
        self.enrollment_dir = enrollment_dir
        
        # Create enrollment directory if it doesn't exist
        if not os.path.exists(enrollment_dir):
            os.makedirs(enrollment_dir)
        
        # Load pre-computed embeddings if available
        if model_path and os.path.exists(model_path):
            self.load_encodings(model_path)
            logger.info(f"Loaded {len(self.known_face_ids)} face encodings from {model_path}")
    
    def load_encodings(self, model_path: str) -> bool:
        """Load pre-computed face encodings from a file"""
        try:
            with open(model_path, 'rb') as f:
                data = pickle.load(f)
                self.known_face_encodings = data.get('encodings', [])
                self.known_face_ids = data.get('ids', [])
            return True
        except Exception as e:
            logger.error(f"Error loading encodings: {str(e)}")
            return False
    
    def save_encodings(self, output_path: str) -> bool:
        """Save current face encodings to a file"""
        try:
            data = {
                'encodings': self.known_face_encodings,
                'ids': self.known_face_ids,
                'timestamp': datetime.now().isoformat()
            }
            with open(output_path, 'wb') as f:
                pickle.dump(data, f)
            return True
        except Exception as e:
            logger.error(f"Error saving encodings: {str(e)}")
            return False
    
    def enroll_face(self, student_id: str, image_paths: List[str]) -> Tuple[bool, List[np.ndarray]]:
        """
        Enroll a new face for a student
        
        Args:
            student_id: Unique identifier for the student
            image_paths: List of paths to the student's face images
            
        Returns:
            Tuple of (success, list of encodings)
        """
        encodings = []
        
        for image_path in image_paths:
            try:
                # Load image
                image = face_recognition_utils.load_image_file(image_path)
                
                # Detect faces
                face_locations = face_recognition_utils.face_locations(image, model=self.detection_method)
                
                if len(face_locations) != 1:
                    logger.warning(f"Expected 1 face, found {len(face_locations)} in {image_path}")
                    continue
                
                # Get face encodings
                face_encoding = face_recognition_utils.face_encodings(image, face_locations)[0]
                encodings.append(face_encoding)
                
                # Add to known faces
                self.known_face_encodings.append(face_encoding)
                self.known_face_ids.append(student_id)
                
                # Save the image to enrollment directory
                student_dir = os.path.join(self.enrollment_dir, str(student_id))
                if not os.path.exists(student_dir):
                    os.makedirs(student_dir)
                
                # Copy the image
                img_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(image_path)}"
                img_save_path = os.path.join(student_dir, img_filename)
                cv2.imwrite(img_save_path, cv2.imread(image_path))
                
            except Exception as e:
                logger.error(f"Error enrolling face from {image_path}: {str(e)}")
        
        success = len(encodings) > 0
        return success, encodings
    
    def recognize_face(self, image: Union[str, np.ndarray]) -> List[Dict]:
        """
        Recognize faces in an image
        
        Args:
            image: Path to image or numpy array containing the image
            
        Returns:
            List of dicts with keys 'id', 'confidence', 'bbox'
        """
        if isinstance(image, str):
            # Load image from path
            image = face_recognition_utils.load_image_file(image)
        
        # Detect faces
        face_locations = face_recognition_utils.face_locations(image, model=self.detection_method)
        
        if not face_locations:
            return []
        
        # Get face encodings
        face_encodings = face_recognition_utils.face_encodings(image, face_locations)
        
        results = []
        for i, face_encoding in enumerate(face_encodings):
            # Compare with known faces
            if not self.known_face_encodings:
                results.append({
                    'id': None,
                    'confidence': 0.0,
                    'bbox': face_locations[i]
                })
                continue
                
            # Calculate face distances (lower is better match)
            face_distances = face_recognition_utils.face_distance(self.known_face_encodings, face_encoding)
            
            # Get best match
            best_match_index = np.argmin(face_distances)
            best_match_distance = face_distances[best_match_index]
            
            # Convert distance to confidence (0-1)
            confidence = 1.0 - best_match_distance
            
            if confidence >= (1.0 - self.distance_threshold):
                student_id = self.known_face_ids[best_match_index]
            else:
                student_id = None  # Unknown face
            
            results.append({
                'id': student_id,
                'confidence': float(confidence),
                'bbox': face_locations[i]
            })
        
        return results
    
    def update_embeddings(self, student_id: str, new_embedding: np.ndarray, max_embeddings: int = 10) -> bool:
        """
        Update the embeddings for a student (for progressive enrollment)
        
        Args:
            student_id: Unique identifier for the student
            new_embedding: New face embedding to add
            max_embeddings: Maximum number of embeddings to keep per student
            
        Returns:
            Success status
        """
        # Count existing embeddings for this student
        existing_indices = [i for i, s_id in enumerate(self.known_face_ids) if s_id == student_id]
        
        if len(existing_indices) >= max_embeddings:
            # Remove the oldest embedding
            oldest_index = existing_indices[0]
            self.known_face_encodings.pop(oldest_index)
            self.known_face_ids.pop(oldest_index)
            
            # Recalculate indices after removal
            existing_indices = [i for i, s_id in enumerate(self.known_face_ids) if s_id == student_id]
        
        # Add new embedding
        self.known_face_encodings.append(new_embedding)
        self.known_face_ids.append(student_id)
        
        return True
    
    def remove_student(self, student_id: str) -> int:
        """
        Remove all embeddings for a student
        
        Args:
            student_id: Unique identifier for the student
            
        Returns:
            Number of embeddings removed
        """
        indices_to_remove = [i for i, s_id in enumerate(self.known_face_ids) if s_id == student_id]
        
        # Remove from the end to avoid index shifting issues
        for index in sorted(indices_to_remove, reverse=True):
            self.known_face_encodings.pop(index)
            self.known_face_ids.pop(index)
        
        # Remove enrollment directory for the student
        student_dir = os.path.join(self.enrollment_dir, str(student_id))
        if os.path.exists(student_dir):
            for file in os.listdir(student_dir):
                os.remove(os.path.join(student_dir, file))
            os.rmdir(student_dir)
        
        return len(indices_to_remove)