from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'unicornguardian'

if __name__ == "__main__":
    # Koyeb typically assigns the port via the PORT environment variable
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
