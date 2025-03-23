import cv2
import numpy as np

def stitch_images(images):
    # Initialize ORB detector
    orb = cv2.ORB_create()

    # Detect keypoints and descriptors
    keypoints = []
    descriptors = []
    for img in images:
        kp, des = orb.detectAndCompute(img, None)
        keypoints.append(kp)
        descriptors.append(des)

    # Match descriptors using BFMatcher
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(descriptors[0], descriptors[1])

    # Sort matches by distance
    matches = sorted(matches, key=lambda x: x.distance)

    # Extract location of good matches
    points1 = np.zeros((len(matches), 2), dtype=np.float32)
    points2 = np.zeros((len(matches), 2), dtype=np.float32)

    for i, match in enumerate(matches):
        points1[i, :] = keypoints[0][match.queryIdx].pt
        points2[i, :] = keypoints[1][match.trainIdx].pt

    # Find homography
    H, _ = cv2.findHomography(points2, points1, cv2.RANSAC, 5.0)

    # Warp the second image
    height, width, _ = images[0].shape
    result = cv2.warpPerspective(images[1], H, (width * 2, height))
    result[0:height, 0:width] = images[0]

    return result

def auto_focus(image):
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Calculate Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Apply sharpening if the image is blurry (low Laplacian variance)
    if laplacian_var < 100:  # Adjust threshold as needed
        sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened_image = cv2.filter2D(image, -1, sharpen_kernel)
        return sharpened_image
    else:
        return image  # Return the original image if it's already sharp