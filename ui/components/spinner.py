"""
Reusable loading spinner / progress components for long-running operations.

Provides:
- `LoadingSpinner`: Context manager wrapping Streamlit's st.spinner() with elapsed time
- `ProgressOverlay`: Full-screen overlay with progress bar (for operations > 5s)
- `with_loading_spinner`: Decorator for simple function-level spinners
"""

import streamlit as st
import time
import logging
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)


class LoadingSpinner:
    """
    Context manager that shows a spinner with elapsed time for long operations.
    
    Usage:
        with LoadingSpinner("Downloading TLE data..."):
            download_tles()
    
    For operations > 5 seconds, automatically switches to a progress overlay.
    """

    def __init__(self, message: str = "Loading...", timeout_threshold: int = 5):
        self.message = message
        self.timeout_threshold = timeout_threshold
        self.start_time = None
        self.overlay = None

    def __enter__(self):
        self.start_time = time.time()
        self.placeholder = st.empty()
        self.placeholder.info(f"⏳ {self.message}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        if elapsed > self.timeout_threshold:
            logger.info("Operation completed in %.1f seconds: %s", elapsed, self.message)
        self.placeholder.empty()
        if exc_type is not None:
            st.error(f"❌ {self.message} — Error: {exc_val}")
        return False

    def update_message(self, new_message: str):
        """Update the spinner message mid-operation."""
        self.message = new_message
        self.placeholder.info(f"⏳ {new_message}")


class ProgressOverlay:
    """
    Full-screen overlay with animated progress bar and elapsed time.
    
    Usage:
        overlay = ProgressOverlay()
        overlay.show("Processing satellites...", 30)
        overlay.update(50, "Halfway there...")
        overlay.hide()
    """

    def __init__(self):
        self.container = st.empty()
        self.start_time = None

    def show(self, message: str = "Processing...", initial_progress: int = 0):
        """Display the overlay with initial message."""
        self.start_time = datetime.now()
        self._render(initial_progress, message)

    def update(self, progress: int, message: str):
        """Update progress (0-100) and message."""
        self._render(progress, message)

    def hide(self):
        """Remove the overlay."""
        self.container.empty()

    def _render(self, progress: int, message: str):
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        html = f"""
        <style>
        .progress-overlay {{
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.7); backdrop-filter: blur(4px);
            z-index: 9999; display: flex; justify-content: center; align-items: center;
            font-family: system-ui, -apple-system, sans-serif;
        }}
        .progress-card {{
            background: #1e1e2e; border-radius: 16px; padding: 24px 32px;
            min-width: 300px; text-align: center;
            border: 1px solid #2ecc71; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}
        .progress-message {{ color: white; margin-bottom: 16px; font-size: 16px; }}
        .progress-bar-container {{
            width: 100%; height: 8px; background: #333; border-radius: 4px; overflow: hidden;
            margin: 16px 0;
        }}
        .progress-bar {{
            height: 100%; background: #2ecc71; width: {progress}%;
            transition: width 0.2s ease; border-radius: 4px;
        }}
        .progress-widget {{
            display: inline-block; width: 20px; height: 20px;
            border: 2px solid #2ecc71; border-top-color: transparent;
            border-radius: 50%; animation: spin 0.8s linear infinite;
            margin-right: 8px; vertical-align: middle;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .progress-time {{ font-size: 12px; color: #aaa; margin-top: 12px; }}
        </style>
        <div class="progress-overlay">
            <div class="progress-card">
                <div class="progress-message">
                    <span class="progress-widget"></span> {message}
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar"></div>
                </div>
                <div class="progress-time">⏱️ {elapsed:.0f} sec</div>
            </div>
        </div>
        """
        self.container.markdown(html, unsafe_allow_html=True)


def with_loading_spinner(message: str = "Loading..."):
    """
    Decorator that wraps a function with a loading spinner.
    
    Usage:
        @with_loading_spinner("Fetching TLE data...")
        def fetch_tles():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with LoadingSpinner(message):
                return func(*args, **kwargs)
        return wrapper
    return decorator
