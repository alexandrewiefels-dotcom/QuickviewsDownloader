import streamlit as st
from pathlib import Path
import json
from datetime import datetime
from navigation_tracker import track_user_action

def render_contact_page():
    """Render simple contact form"""
    st.markdown("## 📧 Contact Us")
    
    with st.form("contact_form", clear_on_submit=True):
        name = st.text_input("Full Name *")
        email = st.text_input("Email Address *")
        subject = st.text_input("Subject *")
        message = st.text_area("Message *", height=150)
        
        if st.form_submit_button("Send Message", type="primary"):
            if not all([name, email, subject, message]):
                st.error("Please fill in all required fields.")
            elif "@" not in email:
                st.error("Please enter a valid email address.")
            else:
                messages_dir = Path("messages")
                messages_dir.mkdir(exist_ok=True)
                
                filename = messages_dir / f"message_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                message_data = {
                    "name": name, "email": email, "subject": subject, "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "session_id": st.session_state.get("session_id", "unknown")
                }
                
                with open(filename, "w") as f:
                    json.dump(message_data, f, indent=2)
                
                track_user_action("message_sent", {"filename": str(filename)})
                st.success("✅ Message sent successfully!")
