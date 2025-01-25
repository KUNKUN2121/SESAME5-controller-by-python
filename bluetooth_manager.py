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
            print("Buffer reset.")

        self._buffer += data[1:]
        header_type = data[0] >> 1

        if header_type == 0:
            print("Continuation of data.")
            return

        if header_type == 2:
            try:
                decrypted_data = self.decrypt(self._buffer)
                print(f"Decrypted Data: {decrypted_data.hex()}")
            except Exception as e:
                print(f"Decryption failed: {e}")
                return
        else:
            decrypted_data = self._buffer
            print(f"Received Data: {decrypted_data.hex()}")

        if len(decrypted_data) < 2:
            print("Invalid data length.")
            return

        op_code = decrypted_data[0]
        self._last_item_code = decrypted_data[1]

        print(f"Op Code: {op_code}, Item Code: {self._last_item_code}")
        
        # ランダムコードの取得処理
        if self._last_item_code == 0x0E:
            self._random_code = decrypted_data[2:6]
            print(f"Random Code Updated: {self._random_code.hex()}")
            
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
            print(f"Encrypted send_data: {send_data.hex()}")

        remain = len(send_data)
        offset = 0
        while remain > 0:
            header = 0
            if offset == 0:
                header += 1  # 最初のパケット

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
            print(f"Sent data chunk: {buffer.hex()}")

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
        self.command_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self.command_worker, daemon=True)
        self.worker_thread.start()

    def command_worker(self):
        while True:
            try:
                try:
                    command, args = self.command_queue.get(timeout=0.1)
                    command(*args)
                    self.command_queue.task_done()
                except queue.Empty:
                    pass

                # 通知の待機
                if self.connected and self.peri:
                    if self.peri.waitForNotifications(1.0):
                        continue
            except btle.BTLEInternalError as e:
                print(f"BTLEInternalError: {e}. Attempting to reconnect...")
                self.disconnect()
                self.connect()
            except Exception as e:
                print(f"An error occurred in command_worker: {e}")
                self.disconnect()

    def enqueue_command(self, command, *args):
        self.command_queue.put((command, args))

    def connect(self):
        self.enqueue_command(self._connect)

    def _connect(self):
        try:
            print("Connecting to peripheral...")
            self.peri = btle.Peripheral()
            self.peri.connect(self.device_address, btle.ADDR_TYPE_RANDOM)
            print("Connected.")

            self.notify_delegate = NotifyDelegate(self.initial_random_code)
            self.peri.withDelegate(self.notify_delegate)

            enable_notify_data = bytes([0x01, 0x00])
            print(f"Writing enable notify data: {enable_notify_data.hex()}")
            self.peri.writeCharacteristic(0x0010, enable_notify_data, True)

            print("Waiting for random code from notifications...")
            if self.peri.waitForNotifications(10.0):
                print("Random code received.")
            else:
                print("Failed to receive random code.")
                raise Exception("Random code not received.")

            if self.notify_delegate._random_code == self.initial_random_code:
                print("Error: Random code was not updated.")
                raise Exception("Random code was not updated.")

            cobj = CMAC.new(bytes.fromhex(self.private_key), ciphermod=AES)
            cobj.update(self.notify_delegate._random_code)
            self.token = cobj.digest()
            self.notify_delegate._token = self.token

            login_command = bytes([0x02, self.token[0], self.token[1], self.token[2], self.token[3]])
            print("Sending login command: " + login_command.hex())
            self.notify_delegate.send(self.peri, login_command, False)

            self.connected = True

            print("Connected and logged in successfully.")

        except Exception as e:
            print(f"An error occurred during connection: {e}")
            self.disconnect()

    def disconnect(self):
        self.enqueue_command(self._disconnect)

    def _disconnect(self):
        if self.peri:
            try:
                self.peri.disconnect()
                print("Disconnected from peripheral.")
            except Exception as e:
                print(f"An error occurred while disconnecting: {e}")
            finally:
                self.peri = None
        self.connected = False

    def send_unlock(self):
        self.enqueue_command(self._send_unlock)

    def _send_unlock(self):
        if not self.connected:
            print("Not connected to peripheral.")
            return
        unlock_tag = 'Open by Python'.encode()
        unlock_command = bytes([0x53, len(unlock_tag)]) + unlock_tag
        print("Sending unlock command: " + unlock_command.hex())
        self.notify_delegate.send(self.peri, unlock_command, True)

    def send_lock(self):
        self.enqueue_command(self._send_lock)

    def _send_lock(self):
        if not self.connected:
            print("Not connected to peripheral.")
            return
        lock_tag = 'Lock by Python'.encode()
        lock_command = bytes([0x52, len(lock_tag)]) + lock_tag
        print("Sending lock command: " + lock_command.hex())
        self.notify_delegate.send(self.peri, lock_command, True)
        
    def get_Status(self):
        return self.notify_delegate.current_mech_status
        

    def notification_loop(self):
        try:
            print("Entering notification loop.")
            while self.connected:
                if self.peri.waitForNotifications(1.0):
                    continue
        except btle.BTLEInternalError as e:
            print(f"BTLEInternalError: {e}. Retrying...")
            self.disconnect()
            self.connect()
        except Exception as e:
            print(f"An error occurred in notification loop: {e}")
            self.disconnect()

    def start_notification_loop(self):
        print("start notification")
        threading.Thread(target=self.notification_loop, daemon=True).start()
