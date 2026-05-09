# ui/components/spinner.py
import streamlit as st

def show_spinner(message):
    """Display a custom spinner with moving satellite animation"""
    spinner_html = f"""
    <div style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.85); color: white; padding: 25px 35px; 
                border-radius: 15px; z-index: 1000; text-align: center;
                border: 1px solid #2ecc71; box-shadow: 0 0 20px rgba(46,204,113,0.3);
                backdrop-filter: blur(8px);">
        <div style="font-size: 48px; margin-bottom: 15px; animation: satelliteMove 1.5s ease-in-out infinite;">
            🛰️
        </div>
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 8px;">{message}</div>
        <div style="font-size: 12px; color: #aaa;">Processing satellite data...</div>
        <div style="margin-top: 12px;">
            <div style="display: inline-block; width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; margin: 0 3px; animation: pulse 1s ease-in-out infinite;"></div>
            <div style="display: inline-block; width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; margin: 0 3px; animation: pulse 1s ease-in-out 0.2s infinite;"></div>
            <div style="display: inline-block; width: 8px; height: 8px; background: #2ecc71; border-radius: 50%; margin: 0 3px; animation: pulse 1s ease-in-out 0.4s infinite;"></div>
        </div>
    </div>
    <style>
    @keyframes satelliteMove {{
        0% {{ transform: translateX(-20px) rotate(-10deg); }}
        50% {{ transform: translateX(20px) rotate(10deg); }}
        100% {{ transform: translateX(-20px) rotate(-10deg); }}
    }}
    @keyframes pulse {{
        0%, 100% {{ opacity: 0.3; transform: scale(0.8); }}
        50% {{ opacity: 1; transform: scale(1.2); }}
    }}
    </style>
    """
    return st.markdown(spinner_html, unsafe_allow_html=True)

def hide_spinner():
    """Hide the spinner by clearing the placeholder"""
    st.empty()
