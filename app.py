# app.py

from flask import Flask, jsonify
from bluetooth_manager import BluetoothManager
import threading
import time
import os

app = Flask(__name__)

# 設定値
PRIVATE_KEY = os.environ['PRIVATE_KEY']
SESAME5_ADDRESS = os.environ['SESAME5_ADDRESS'] 

manager = BluetoothManager(PRIVATE_KEY, SESAME5_ADDRESS)
manager.connect()
# manager.start_notification_loop()

@app.route('/open', methods=['POST'])
def open_lock():
    try:
        manager.send_unlock()
        return jsonify({"status": "success", "message": "Lock opened."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/close', methods=['POST'])
def close_lock():
    try:
        manager.send_lock()
        return jsonify({"status": "success", "message": "Lock closed."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    try:
        status = manager.get_Status()
        if status == None:
            return jsonify({"status": "error", "message": str("Not initialized")}), 500
        return jsonify(status), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    # Flaskサーバーをホストとポートを指定して起動
    app.run(host='0.0.0.0', port=5000)
