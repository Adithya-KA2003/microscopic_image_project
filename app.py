from flask import Flask, request, jsonify, send_file
import cv2
import numpy as np
import os
from werkzeug.utils import secure_filename
from image_processing import stitch_images,auto_focus

app = Flask(__name__)

# Define paths
UPLOAD_FOLDER = 'input'
OUTPUT_FOLDER = 'output'
ZOOM_FOLDER = os.path.join(OUTPUT_FOLDER, 'zoom_output')
AUTOFOCUS_FOLDER = os.path.join(OUTPUT_FOLDER, 'autofocus_output')

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, ZOOM_FOLDER, AUTOFOCUS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Allowed image formats
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return """
    <h1>Welcome to the Microscope Image Processing API</h1>
    <p>Available Endpoints:</p>
    <ul>
        <li><b>POST /images/upload</b>: Upload microscope images.</li>
        <li><b>GET /images/stitch</b>: Stitch images into one.</li>
        <li><b>POST /roi</b>: Extract a Region of Interest (ROI).</li>
        <li><b>POST /zoom</b>: Zoom ROI (10X or 20X).</li>
        <li><b>GET /auto_focus</b>: Apply auto-focus.</li>
    </ul>
    """

# Image sharpening function with adaptive sharpening strength
def img_sharpen(image, strength=1.5):
    blurred = cv2.GaussianBlur(image, (0, 0), strength)
    sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    return sharpened

# Improved ROI extraction for better zooming clarity
def roi_extraction(image, x, y, width, height):
    h, w = image.shape[:2]
    if x < 0 or y < 0 or x + width > w or y + height > h:
        return None
    return image[y:y+height, x:x+width]

# Improved digital zoom with adaptive sharpening & better interpolation
def digital_zoom(image, zoom_factor):
    """
    Zoom into a specific area of the image (e.g., center) and magnify it.
    :param image: Input image (ROI).
    :param zoom_factor: Zoom level (e.g., 10 or 20).
    :return: Zoomed image.
    """
    # Get the dimensions of the input image
    height, width = image.shape[:2]

    # Define the area to zoom into (e.g., center of the image)
    zoom_area_width = width // zoom_factor
    zoom_area_height = height // zoom_factor

    # Calculate the coordinates of the zoom area
    x1 = (width - zoom_area_width) // 2
    y1 = (height - zoom_area_height) // 2
    x2 = x1 + zoom_area_width
    y2 = y1 + zoom_area_height

    # Extract the zoom area
    zoom_area = image[y1:y2, x1:x2]

    # Resize the zoom area to the original dimensions using high-quality interpolation
    zoomed_image = cv2.resize(zoom_area, (width, height), interpolation=cv2.INTER_LANCZOS4)

    return zoomed_image

# Upload images
@app.route('/images/upload', methods=['POST'])
def upload_images():
    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "No files provided"}), 400

    filenames = []
    for file in files:
        if file.filename == '' or not allowed_file(file.filename):
            continue
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        filenames.append(filename)

    return jsonify({"message": "Files uploaded successfully", "filenames": filenames}), 200

# Stitch images using ORB feature detection
@app.route('/images/stitch', methods=['GET'])
def stitch_images_endpoint():
    images = []
    for filename in sorted(os.listdir(app.config['UPLOAD_FOLDER'])):
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        img = cv2.imread(img_path)
        if img is not None:
            images.append(img)

    if len(images) < 2:
        return jsonify({"error": "Need at least two images for stitching"}), 400

    stitched_image = stitch_images(images)
    if stitched_image is None:
        return jsonify({"error": "Stitching failed"}), 500

    output_path = os.path.join(app.config['OUTPUT_FOLDER'], 'stitched_output.jpg')
    cv2.imwrite(output_path, stitched_image)

    return send_file(output_path, mimetype='image/jpeg')

# Extract ROI
@app.route('/roi', methods=['POST'])
def roi_selection_endpoint():
    data = request.json
    if not data or 'x' not in data or 'y' not in data or 'width' not in data or 'height' not in data:
        return jsonify({"error": "Invalid ROI coordinates"}), 400

    x, y, width, height = data['x'], data['y'], data['width'], data['height']

    stitched_image_path = os.path.join(app.config['OUTPUT_FOLDER'], 'stitched_output.jpg')
    image = cv2.imread(stitched_image_path)
    if image is None:
        return jsonify({"error": "Stitched image not found"}), 404

    roi = roi_extraction(image, x, y, width, height)
    if roi is None:
        return jsonify({"error": "Invalid ROI coordinates"}), 400

    roi_path = os.path.join(app.config['OUTPUT_FOLDER'], 'roi_output.jpg')
    cv2.imwrite(roi_path, roi)

    return send_file(roi_path, mimetype='image/jpeg')

# Zoom ROI (10X & 20X)
@app.route('/zoom', methods=['POST'])
def zoom_endpoint():
    roi_image_path = os.path.join(app.config['OUTPUT_FOLDER'], 'roi_output.jpg')
    roi_image = cv2.imread(roi_image_path)

    if roi_image is None:
        return jsonify({"error": "ROI image not found"}), 404

    zoom_output_folder = os.path.join(app.config['OUTPUT_FOLDER'], 'zoom_output')
    os.makedirs(zoom_output_folder, exist_ok=True)

    zoom_factors = [10, 20]
    output_files = {}

    for zoom_factor in zoom_factors:
        # Apply digital zoom to the ROI
        zoomed_image = digital_zoom(roi_image, zoom_factor)

        # Save the zoomed image
        output_path = os.path.join(zoom_output_folder, f'zoomed_output_{zoom_factor}x.jpg')
        cv2.imwrite(output_path, zoomed_image)

        # Add file URL
        output_files[f"zoom_{zoom_factor}x"] = f"/zoom/{zoom_factor}x"

    return jsonify(output_files)

# Serve Zoomed Images
@app.route('/zoom/<int:factor>x', methods=['GET'])
def get_zoomed_image(factor):
    zoomed_image_path = os.path.join(ZOOM_FOLDER, f'zoomed_output_{factor}x.jpg')
    
    if not os.path.exists(zoomed_image_path):
        return jsonify({"error": f"Zoomed image {factor}x not found"}), 404
    
    return send_file(zoomed_image_path, mimetype='image/jpeg')

# Apply Auto-Focus using Laplacian variance
@app.route('/auto_focus', methods=['GET'])
def auto_focus_endpoint():
    output_files = {}

    for zoom_factor in [10, 20]:
        zoomed_path = os.path.join(ZOOM_FOLDER, f'zoomed_output_{zoom_factor}x.jpg')
        zoomed_image = cv2.imread(zoomed_path)

        if zoomed_image is None:
            return jsonify({"error": f"Zoomed image {zoom_factor}x not found"}), 404

        focused_image = auto_focus(zoomed_image)
        output_path = os.path.join(AUTOFOCUS_FOLDER, f'autofocused_{zoom_factor}x.jpg')
        cv2.imwrite(output_path, focused_image)

        # Add file URL
        output_files[f"autofocused_{zoom_factor}x"] = f"/auto_focus/{zoom_factor}x"

    return jsonify(output_files)

# Serve Auto-Focused Images
@app.route('/auto_focus/<int:factor>x', methods=['GET'])
def get_autofocused_image(factor):
    autofocus_image_path = os.path.join(AUTOFOCUS_FOLDER, f'autofocused_{factor}x.jpg')
    
    if not os.path.exists(autofocus_image_path):
        return jsonify({"error": f"Auto-focused image {factor}x not found"}), 404
    
    return send_file(autofocus_image_path, mimetype='image/jpeg')

if __name__ == '__main__':
    app.run(debug=True)