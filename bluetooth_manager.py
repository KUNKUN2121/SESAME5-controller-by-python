from bluepy import btle
from Crypto.Hash import CMAC
from Crypto.Cipher import AES
import queue
import time
import threading
from mech_status import parse_mech_status, MechStatus

class NotifyDelegate(btle.DefaultDelegate):
    def __init__(self, random_code):
        super().__init__()
        self._buffer = bytes()
        self._encrypt_counter = 0
        self._decrypt_counter = 0
        self._random_code = random_code
        self._token = None
        self.current_mech_status = None

    def handleNotification(self, cHandle, data):
        if not data:
            return

        if (data[0] & 1) != 0:
            self._buffer = bytes()
            # print("Buffer reset.")

        self._buffer += data[1:]
        header_type = data[0] >> 1

        if header_type == 0:
            # print("Continuation of data.")
            return

        if header_type == 2:
            try:
                decrypted_data = self.decrypt(self._buffer)
                # print(f"Decrypted Data: {decrypted_data.hex()}")
            except Exception as e:
                print(f"Decryption failed: {e}")
                return
        else:
            decrypted_data = self._buffer
            # print(f"Received Data: {decrypted_data.hex()}")

        if len(decrypted_data) < 2:
            print("Invalid data length.")
            return

        op_code = decrypted_data[0]
        self._last_item_code = decrypted_data[1]

        # print(f"Op Code: {op_code}, Item Code: {self._last_item_code}")
        
        if self._last_item_code == 0x0E:
            self._random_code = decrypted_data[2:6]
            # print(f"Random Code Updated: {self._random_code.hex()}")
            
        if op_code == 0x08 and self._last_item_code == 81:
            try:
                status_data = decrypted_data[2:]
                mech_status = parse_mech_status(status_data)
                print(f"Mech Status: {mech_status}")
                
                self.current_mech_status = mech_status
                
            except Exception as e:
                print(f"Failed to parse mech status: {e}")
            

    def send(self, peri, send_data, is_encrypt):
        if is_encrypt:
            if not self._token:
                print("Error: Token is not set.")
                return
            send_data = self.encrypt(send_data)

        remain = len(send_data)
        offset = 0
        while remain > 0:
            header = 0
            if offset == 0:
                header += 1

            if remain <= 19:
                buffer = send_data[offset:]
                remain = 0
                if is_encrypt:
                    header += 4
                else:
                    header += 2
            else:
                buffer = send_data[offset:offset+19]
                offset += 19
                remain -= 19

            buffer = bytes([header]) + buffer
            peri.writeCharacteristic(0x000d, buffer, False)

    def encrypt(self, data):
        iv = self._encrypt_counter.to_bytes(9, "little") + self._random_code
        cobj = AES.new(self._token, AES.MODE_CCM, nonce=iv, mac_len=4)
        self._encrypt_counter += 1
        cobj.update(bytes([0]))
        enc_data, tag = cobj.encrypt_and_digest(data)
        tag4 = tag[:4]
        return enc_data + tag4

    def decrypt(self, data):
        iv = self._decrypt_counter.to_bytes(9, "little") + self._random_code
        cobj = AES.new(self._token, AES.MODE_CCM, nonce=iv, mac_len=4)
        self._decrypt_counter += 1
        decode_data = cobj.decrypt(data[:-4])
        return decode_data


class BluetoothManager:
    def __init__(self, private_key, device_address):
        self.private_key = private_key
        self.device_address = device_address
        self.peri = None
        self.notify_delegate = None
        self.token = None
        self.initial_random_code = b'\x01\x02\x03\x04'
        self.lock = threading.Lock()
        self.connected = False
        self.reconnect_delay = 5  # Start with a 5-second delay
        self.command_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self.command_worker, daemon=True)
        self.worker_thread.start()

    def command_worker(self):
        while True:
            if not self.is_connected():
                print(f"Device not connected. Trying to connect in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                try:
                    self._connect()
                    print("Connection successful.")
                    self.reconnect_delay = 5  # Reset delay to 5 seconds after a successful connection
                except Exception as e:
                    print(f"Connection attempt failed: {e}")
                    self.reconnect_delay = 60  # If it fails, set the next attempt to 60 seconds
                continue

            try:
                try:
                    command, args = self.command_queue.get(timeout=1.0)
                    command(*args)
                    self.command_queue.task_done()
                except queue.Empty:
                    pass

                if self.peri:
                    self.peri.waitForNotifications(1.0)

            except (btle.BTLEDisconnectError, btle.BTLEInternalError) as e:
                print(f"Connection lost: {e}. Will start reconnection attempts.")
                self._cleanup_connection()
                self.reconnect_delay = 5  # For the first attempt after losing connection, wait 5 seconds
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                self._cleanup_connection()
                self.reconnect_delay = 5

    def _cleanup_connection(self):
        with self.lock:
            self.connected = False
            if self.peri:
                try:
                    self.peri.disconnect()
                except Exception:
                    pass
                finally:
                    self.peri = None

    def enqueue_command(self, command, *args):
        self.command_queue.put((command, args))

    def connect(self):
        if not self.is_connected():
             print("Initial connection attempt triggered.")

    def _connect(self):
        with self.lock:
            if self.connected:
                return

        try:
            print("Connecting to peripheral...")
            self.peri = btle.Peripheral()
            self.peri.connect(self.device_address, btle.ADDR_TYPE_RANDOM)

            self.notify_delegate = NotifyDelegate(self.initial_random_code)
            self.peri.withDelegate(self.notify_delegate)

            self.peri.writeCharacteristic(0x0010, bytes([0x01, 0x00]), True)

            if not self.peri.waitForNotifications(10.0):
                raise Exception("Failed to receive random code.")

            if self.notify_delegate._random_code == self.initial_random_code:
                raise Exception("Random code was not updated.")

            cobj = CMAC.new(bytes.fromhex(self.private_key), ciphermod=AES)
            cobj.update(self.notify_delegate._random_code)
            self.token = cobj.digest()
            self.notify_delegate._token = self.token

            login_command = bytes([0x02, self.token[0], self.token[1], self.token[2], self.token[3]])
            self.notify_delegate.send(self.peri, login_command, False)
            
            self.connected = True

            # リクエストを送信して、接続時にステータスを取得
            self.enqueue_command(self._send_status_request)

        except Exception as e:
            self._cleanup_connection()
            raise e

    def _send_status_request(self):
        if not self.is_connected():
            print("Not connected. Command 'status_request' ignored.")
            return
        status_request_command = bytes([0x08, 0x51])
        print("Sending status request command.")
        self.notify_delegate.send(self.peri, status_request_command, True)

    def disconnect(self):
        self.enqueue_command(self._cleanup_connection)

    def is_connected(self):
        with self.lock:
            return self.connected

    def send_unlock(self):
        self.enqueue_command(self._send_unlock)

    def _send_unlock(self):
        if not self.is_connected():
            print("Not connected. Command 'unlock' ignored.")
            return
        unlock_tag = 'Open by Python'.encode()
        unlock_command = bytes([0x53, len(unlock_tag)]) + unlock_tag
        self.notify_delegate.send(self.peri, unlock_command, True)

    def send_lock(self):
        self.enqueue_command(self._send_lock)

    def _send_lock(self):
        if not self.is_connected():
            print("Not connected. Command 'lock' ignored.")
            return
        lock_tag = 'Lock by Python'.encode()
        lock_command = bytes([0x52, len(lock_tag)]) + lock_tag
        self.notify_delegate.send(self.peri, lock_command, True)
        
    def get_Status(self):
        return self.notify_delegate.current_mech_status