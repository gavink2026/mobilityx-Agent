# --- Only run this cell once (background launch) ---
import subprocess
import time
from pyngrok import ngrok

# Set auth token (REQUIRED now for ngrok)
ngrok.set_auth_token(os.getenv("NGROK_AUTH_TOKEN"))

# Start Streamlit in background
subprocess.Popen(["streamlit", "run", "app.py", "--server.enableCORS", "false", "--server.port", "8501"])

# Wait 3–5 seconds for Streamlit to boot
time.sleep(5)

# Connect ngrok to Streamlit
public_url = ngrok.connect(8501)
print("🔗 Public URL:", public_url)
