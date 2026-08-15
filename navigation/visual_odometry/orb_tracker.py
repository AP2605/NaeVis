"""
ORB Feature Tracker Module (P3 Module).
=======================================
Handles feature detection, descriptor extraction, and feature matching
using OpenCV ORB (Oriented FAST and Rotated BRIEF) with Lowe's Ratio Test.
"""

from typing import Tuple, List, Optional
import numpy as np
import cv2


class ORBTracker:
    """
    Extracts and matches ORB keypoints and 256-bit binary descriptors between frames.
    """

    def __init__(
        self,
        n_features: int = 2000,
        scale_factor: float = 1.2,
        n_levels: int = 8,
        ratio_threshold: float = 0.80,
        fast_threshold: int = 12
    ):
        self.n_features = n_features
        self.scale_factor = scale_factor
        self.n_levels = n_levels
        self.ratio_threshold = ratio_threshold

        # Initialize ORB detector
        self.orb = cv2.ORB_create(
            nfeatures=n_features,
            scaleFactor=scale_factor,
            nlevels=n_levels,
            edgeThreshold=15,
            firstLevel=0,
            WTA_K=2,
            scoreType=cv2.ORB_HARRIS_SCORE,
            patchSize=31,
            fastThreshold=fast_threshold
        )

        # Hamming distance matcher for binary ORB descriptors
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def detect_and_compute(self, frame: np.ndarray) -> Tuple[List[cv2.KeyPoint], Optional[np.ndarray]]:
        """
        Detects keypoints and computes 256-bit binary descriptors for a given frame.

        Args:
            frame: Input image (BGR or Grayscale).

        Returns:
            Tuple of (list_of_keypoints, descriptors_array).
        """
        if frame is None:
            return [], None

        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        return keypoints, descriptors

    def match(
        self,
        des_prev: Optional[np.ndarray],
        des_curr: Optional[np.ndarray],
        kp_prev: List[cv2.KeyPoint],
        kp_curr: List[cv2.KeyPoint]
    ) -> Tuple[np.ndarray, np.ndarray, List[cv2.DMatch]]:
        """
        Matches descriptors between previous and current frames using k-NN (k=2)
        and applies Lowe's ratio test to filter ambiguous correspondences.

        Returns:
            pts_prev: np.ndarray of shape (N, 2) in previous frame pixel coords.
            pts_curr: np.ndarray of shape (N, 2) in current frame pixel coords.
            good_matches: List of filtered cv2.DMatch objects.
        """
        if des_prev is None or des_curr is None or len(des_prev) < 8 or len(des_curr) < 8:
            return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32), []

        # k-NN match with k=2
        raw_matches = self.matcher.knnMatch(des_prev, des_curr, k=2)

        good_matches = []
        for match_pair in raw_matches:
            if len(match_pair) == 2:
                m, n = match_pair
                # Lowe's ratio test for binary descriptors
                if m.distance < self.ratio_threshold * n.distance:
                    good_matches.append(m)

        if len(good_matches) < 8:
            return np.empty((0, 2), dtype=np.float32), np.empty((0, 2), dtype=np.float32), []

        pts_prev = np.float32([kp_prev[m.queryIdx].pt for m in good_matches])
        pts_curr = np.float32([kp_curr[m.trainIdx].pt for m in good_matches])

        return pts_prev, pts_curr, good_matches

    def draw_matches(
        self,
        img_prev: np.ndarray,
        kp_prev: List[cv2.KeyPoint],
        img_curr: np.ndarray,
        kp_curr: List[cv2.KeyPoint],
        matches: List[cv2.DMatch],
        max_draw: int = 50
    ) -> np.ndarray:
        """Draws visual correspondences between two frames for debugging."""
        display_matches = matches[:max_draw]
        return cv2.drawMatches(
            img_prev, kp_prev,
            img_curr, kp_curr,
            display_matches, None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
        )


if __name__ == "__main__":
    print("=== Testing ORBTracker ===")
    from navigation.utils.mock_generator import MockDataGenerator

    gen = MockDataGenerator(trajectory_type="circular", duration=1.0, camera_hz=30)
    frames = []

    for sensor_type, packet in gen.stream_dataset():
        if sensor_type == "camera":
            frames.append(packet["frame"])
            if len(frames) >= 2:
                break

    assert len(frames) >= 2, "Need at least 2 frames for testing"

    tracker = ORBTracker(n_features=2000, fast_threshold=12, ratio_threshold=0.80)
    kp1, des1 = tracker.detect_and_compute(frames[0])
    kp2, des2 = tracker.detect_and_compute(frames[1])

    print(f"Frame 1: Detected {len(kp1)} keypoints, descriptors shape: {des1.shape}")
    print(f"Frame 2: Detected {len(kp2)} keypoints, descriptors shape: {des2.shape}")

    pts1, pts2, good_matches = tracker.match(des1, des2, kp1, kp2)
    print(f"Lowe's Ratio Test: Matched {len(good_matches)} good feature correspondences.")

    assert len(good_matches) >= 20, f"Expected at least 20 good matches, got {len(good_matches)}"
    print("ORBTracker verification PASSED successfully!")
