from flask import Flask, jsonify
from bluetooth_manager import BluetoothManager
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

PRIVATE_KEY = os.environ.get('PRIVATE_KEY')
SESAME5_ADDRESS = os.environ.get('SESAME5_ADDRESS')

if not PRIVATE_KEY or not SESAME5_ADDRESS:
    raise ValueError("PRIVATE_KEY and SESAME5_ADDRESS must be set in the environment or .env file")

manager = BluetoothManager(PRIVATE_KEY, SESAME5_ADDRESS)
manager.connect()

@app.route('/open', methods=['POST'])
def open_lock():
    if not manager.is_connected():
        return jsonify({"status": "error", "message": "Device not connected."}), 503
    try:
        manager.send_unlock()
        return jsonify({"status": "success", "message": "Unlock command sent."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/close', methods=['POST'])
def close_lock():
    if not manager.is_connected():
        return jsonify({"status": "error", "message": "Device not connected."}), 503
    try:
        manager.send_lock()
        return jsonify({"status": "success", "message": "Lock command sent."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    if not manager.is_connected():
        return jsonify({"status": "error", "message": "Device not connected."}), 503
    try:
        mech_status = manager.get_Status()
        if mech_status is None:
            return jsonify({"status": "error", "message": "Status not available yet."}), 503
        return jsonify(mech_status.__dict__), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)