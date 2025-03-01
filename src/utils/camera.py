import cv2
import time
import logging
import threading
import numpy as np
from typing import Tuple, List, Optional, Dict, Callable

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Camera:
    """Camera interface for capturing faces"""
    
    def __init__(self, camera_id: int = 0, resolution: Tuple[int, int] = (640, 480),
                 fps: int = 30, name: str = "Camera"):
        """
        Initialize camera interface
        
        Args:
            camera_id: Camera device ID (usually 0 for built-in webcam)
            resolution: Desired resolution (width, height)
            fps: Frames per second
            name: Camera name/location identifier
        """
        self.camera_id = camera_id
        self.resolution = resolution
        self.fps = fps
        self.name = name
        self.cap = None
        self.is_running = False
        self.thread = None
        self.current_frame = None
        self.last_frame_time = 0
        self.frame_lock = threading.Lock()
        
    def start(self) -> bool:
        """Start the camera capture"""
        if self.is_running:
            return True
            
        try:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera {self.camera_id}")
                return False
                
            # Set resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Start capture thread
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            
            logger.info(f"Camera {self.name} (ID: {self.camera_id}) started")
            return True
            
        except Exception as e:
            logger.error(f"Error starting camera {self.camera_id}: {str(e)}")
            self.is_running = False
            if self.cap:
                self.cap.release()
                self.cap = None
            return False
            
    def stop(self) -> None:
        """Stop the camera capture"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
            
        if self.cap:
            self.cap.release()
            self.cap = None
            
        logger.info(f"Camera {self.name} stopped")
            
    def _capture_loop(self) -> None:
        """Background thread for continuous frame capture"""
        while self.is_running and self.cap:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning(f"Failed to grab frame from camera {self.name}")
                    time.sleep(0.1)
                    continue
                    
                with self.frame_lock:
                    self.current_frame = frame
                    self.last_frame_time = time.time()
                    
            except Exception as e:
                logger.error(f"Error in camera capture loop: {str(e)}")
                time.sleep(0.1)
                
    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest frame from the camera"""
        with self.frame_lock:
            if self.current_frame is None:
                return None
            return self.current_frame.copy()
            
    def get_frame_with_timestamp(self) -> Tuple[Optional[np.ndarray], float]:
        """Get the latest frame with its timestamp"""
        with self.frame_lock:
            if self.current_frame is None:
                return None, 0
            return self.current_frame.copy(), self.last_frame_time
            
    def capture_still(self) -> Optional[np.ndarray]:
        """Capture a single still image"""
        # Get the latest frame
        frame = self.get_frame()
        if frame is None:
            return None
            
        return frame
        
    def is_active(self) -> bool:
        """Check if the camera is active and providing frames"""
        if not self.is_running or self.cap is None:
            return False
            
        # Check if we've received a frame recently
        with self.frame_lock:
            if self.current_frame is None:
                return False
            # Consider the camera inactive if no frame in the last 3 seconds
            if time.time() - self.last_frame_time > 3.0:
                return False
                
        return True

class CameraManager:
    """Manages multiple cameras for the system"""
    
    def __init__(self):
        self.cameras: Dict[str, Camera] = {}
        
    def add_camera(self, camera_id: int, name: str, resolution: Tuple[int, int] = (640, 480),
                  fps: int = 30, auto_start: bool = True) -> bool:
        """Add a new camera to the manager"""
        if name in self.cameras:
            logger.warning(f"Camera with name '{name}' already exists")
            return False
            
        camera = Camera(camera_id=camera_id, resolution=resolution, fps=fps, name=name)
        self.cameras[name] = camera
        
        if auto_start:
            return camera.start()
        return True
        
    def remove_camera(self, name: str) -> bool:
        """Remove a camera from the manager"""
        if name not in self.cameras:
            return False
            
        camera = self.cameras[name]
        camera.stop()
        del self.cameras[name]
        return True
        
    def get_camera(self, name: str) -> Optional[Camera]:
        """Get a camera by name"""
        return self.cameras.get(name)
        
    def get_all_cameras(self) -> Dict[str, Camera]:
        """Get all cameras"""
        return self.cameras
        
    def start_all(self) -> None:
        """Start all cameras"""
        for name, camera in self.cameras.items():
            camera.start()
            
    def stop_all(self) -> None:
        """Stop all cameras"""
        for name, camera in self.cameras.items():
            camera.stop()
            
    def get_active_cameras(self) -> Dict[str, Camera]:
        """Get all active cameras"""
        return {name: camera for name, camera in self.cameras.items() if camera.is_active()}