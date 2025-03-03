# src/api/cameras.py
from flask import Blueprint, request, jsonify, render_template, current_app, Response
from src.utils.camera import Camera
from src.api.auth import login_required, role_required
import cv2
import numpy as np

cameras_bp = Blueprint('cameras', __name__, url_prefix='/cameras')

@cameras_bp.route('/')
@role_required(['admin', 'teacher'])
def list_cameras():
    """List all cameras"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    cameras = camera_manager.get_all_cameras()
    return render_template('cameras/list.html', cameras=cameras)

@cameras_bp.route('/add', methods=['GET', 'POST'])
@role_required(['admin'])
def add_camera():
    """Add a new camera"""
    if request.method == 'POST':
        camera_id = int(request.form.get('camera_id'))
        name = request.form.get('name')
        resolution_str = request.form.get('resolution', '640x480')  # Default resolution
        fps = int(request.form.get('fps', 30))  # Default FPS
        auto_start = request.form.get('auto_start') == 'true'

        try:
            width, height = map(int, resolution_str.split('x'))
            resolution = (width, height)
        except ValueError:
            return jsonify({'error': 'Invalid resolution format. Use WIDTHxHEIGHT'}), 400
        
        camera_manager = current_app.config['CAMERA_MANAGER']
        success = camera_manager.add_camera(camera_id, name, resolution, fps, auto_start)

        if success:
            return jsonify({'message': f'Camera {name} added successfully'}), 201
        else:
            return jsonify({'error': f'Failed to add camera {name}'}), 500

    return render_template('cameras/add.html')  # Corrected path

@cameras_bp.route('/remove/<string:name>', methods=['POST'])
@role_required(['admin'])
def remove_camera(name):
    """Remove a camera"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    success = camera_manager.remove_camera(name)

    if success:
        return jsonify({'message': f'Camera {name} removed successfully'}), 200
    else:
        return jsonify({'error': f'Failed to remove camera {name}'}), 404

@cameras_bp.route('/start/<string:name>', methods=['POST'])
@role_required(['admin', 'teacher'])
def start_camera(name):
    """Start a specific camera"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    camera = camera_manager.get_camera(name)
    if camera:
        if camera.start():
            return jsonify({'message': f'Camera {name} started'}), 200
        else:
            return jsonify({'error': f'Failed to start camera {name}'}), 500
    return jsonify({'error': f'Camera {name} not found'}), 404

@cameras_bp.route('/stop/<string:name>', methods=['POST'])
@role_required(['admin', 'teacher'])
def stop_camera(name):
    """Stop a specific camera"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    camera = camera_manager.get_camera(name)
    if camera:
        camera.stop()
        return jsonify({'message': f'Camera {name} stopped'}), 200
    return jsonify({'error': f'Camera {name} not found'}), 404

@cameras_bp.route('/view/<string:name>')
@login_required
def view_camera(name):
    """View a live camera feed"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    camera = camera_manager.get_camera(name)
    if not camera:
        return render_template('errors/404.html'), 404

    return render_template('cameras/view.html', camera=camera)  # Pass camera object


def generate_frames(camera_name):
    """Generator function for streaming camera frames"""
    camera_manager = current_app.config['CAMERA_MANAGER']
    camera = camera_manager.get_camera(camera_name)

    if not camera:
        return

    while True:
        frame = camera.get_frame()
        if frame is not None:
             # Draw bounding box around detected faces.
            face_recognition_system =  current_app.config.get('FACE_RECOGNITION')
            if face_recognition_system is not None:
                recognition_results = face_recognition_system.recognize_face(frame)
                for result in recognition_results:
                    top, right, bottom, left = result['bbox']
                    color = (0, 255, 0) if result['id'] is not None else (0, 0, 255) # Green for known, red for unknown
                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@cameras_bp.route('/video_feed/<string:name>')
@login_required
def video_feed(name):
    """Stream camera feed using multipart/x-mixed-replace"""
    return Response(generate_frames(name),
                    mimetype='multipart/x-mixed-replace; boundary=frame')