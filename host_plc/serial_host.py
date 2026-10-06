import serial
import json
import time
import threading

class SerialHost:
    def __init__(self, port: str, baudrate: int, sensor_queue=None):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.is_running = False
        
        # Queue to hold incoming sensor data from Pico
        self.sensor_queue = sensor_queue
        
        # Threading event to handle flow control (ACK from Pico)
        self.ack_received = threading.Event()
        # Flag to indicate if an error was received from the Pico
        self.error_received = False

    def load_system_config(filepath: str = "config.json") -> dict:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("SystemSettings", {})
        except FileNotFoundError:
            print(f"Warning: {filepath} not found. Using defaults.")
        return {}
    
    
    def connect(self) -> bool:
        try:
            # Open the serial port with a 1-second read timeout
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0
            )
            
            # Search windows DTR/RTS signals to reset the Pico if needed
            self.serial_conn.setDTR(False)
            self.serial_conn.setRTS(False)
            
            # Force Pico soft reset
            print("Sending soft reset to Pico...")
            self.serial_conn.write(b'\x02')  # Ctrl+B to disconnect REPL mode
            time.sleep(0.1)
            self.serial_conn.write(b'\x03')  # Ctrl+C to interrupt any running code
            time.sleep(0.1)
            self.serial_conn.write(b'\x04')  # Ctrl+D to soft reset
            self.serial_conn.flush()
            time.sleep(1)  # Give Pico time to reset and start up
            
            self.is_running = True
            
            # Start the background thread to listen for Pico's messages
            self.start_listening()
            
            print(f"Connected successfully to {self.port} at {self.baudrate} bps.")
            return True
            
        except serial.SerialException as e:
            print(f"Connection failed on {self.port}. Is the Pico plugged in and port free? Error: {e}")
            self.is_running = False
            return False


    def disconnect(self):
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
                print(f"Disconnected from {self.port}.")
            except serial.SerialException as e:
                print(f"Error while closing serial port: {e}")


    def start_listening(self):
        # Create a thread pointing to the _listen_loop method
        listener_thread = threading.Thread(target=self._listen_loop)
        
        # Set as daemon so it automatically closes when the main program exits
        listener_thread.daemon = True
        
        # Start executing the background thread
        listener_thread.start()


    def _listen_loop(self):
        while self.is_running and self.serial_conn and self.serial_conn.is_open:
            try:
                # Read one line until '\n' is encountered (or timeout is reached)
                raw_line = self.serial_conn.readline()
                
                # If timeout was reached, raw_line will be empty (b'')
                if not raw_line:
                    continue
                    
                # Decode bytes to string and remove trailing/leading whitespace/newlines
                decoded_line = raw_line.decode('utf-8', errors='ignore').strip()
                
                if not decoded_line:
                    continue
                    
                # Attempt to parse NDJSON
                try:
                    payload = json.loads(decoded_line)
                    
                    # 1. Flow Control: Check if Pico acknowledged a chunk
                    if payload.get("status") == "ack":
                        self.ack_received.set()
                        
                    # 2. Error Handling: Check if Pico sent an error message
                    elif payload.get("status") == "error":
                        print(f"[Pico Error]: {payload.get('details', 'No details provided')}")
                        self.error_received = True
                        self.ack_received.set()  # Unblock any waiting senders even on error
                        
                    # 3. Sensor Data: Check if payload contains BME688 readings
                    elif "temperature" in payload:
                        t = payload.get("temperature", 0.0)
                        h = payload.get("humidity", 0.0)
                        p = payload.get("pressure", 0.0)
                        gas = payload.get("gas_resistance", None)
                        
                        gas_str = f" | Gas: {gas:.0f} ohm" if gas else ""
                        print(f"[BME688] T: {t:.2f} °C | H: {h:.2f} % | P: {p:.2f} hPa{gas_str}")
                        # Put the entire payload dictionary into the queue for daemon.py to process
                        if self.sensor_queue is not None:
                            self.sensor_queue.put(payload)
                        
                    # 4. Handle any other arbitrary messages (e.g., Pico logging)
                    else:
                        print(f"[Pico Log]: {payload}")
                        
                except json.JSONDecodeError:
                    # Gracefully handle partial lines or serial noise during startup
                    print(f"[PICO RAW TEXT]: {decoded_line}")
                    
            except serial.SerialException as e:
                # Handle physical disconnection (e.g., USB cable unplugged)
                print(f"[Error] Serial connection lost during read: {e}")
                self.is_running = False
                break


    def send_image_payloads(self, payloads: list) -> bool:
        if not self.is_running or not self.serial_conn or not self.serial_conn.is_open:
            print("[Error] Serial port is not open.")
            return False

        total_chunks = len(payloads)
        self.error_received = False  # Reset error flag before sending
    
        for i, payload in enumerate(payloads):
            # 1. Clear the ACK flag before sending new data
            self.ack_received.clear()
            
            # 2. Convert dictionary to JSON string and append newline (NDJSON standard)
            json_str = json.dumps(payload) + '\n'
            
            # 3. Encode string to raw bytes and transmit
            self.serial_conn.write(json_str.encode('utf-8'))
            self.serial_conn.flush()  # Ensure data is pushed out of the OS buffer immediately
            
            # 4. Wait for the background listener to receive an ACK from Pico
            # The last chunk triggers the e-paper display refresh, which blocks the Pico for ~15 seconds.
            # Normal chunks are processed in milliseconds.
            timeout_duration = 20.0 if i == total_chunks - 1 else 3.0
            
            ack_success = self.ack_received.wait(timeout=timeout_duration)
            
            # Check if lock was released due to an error or succesful ACK message from Pico
            if self.error_received:
                print(f"[Error] Transfer aborted at chunk {i}/{total_chunks} due to a Pico error.")
                return False
            
            if not ack_success:
                color = payload.get("color", "unknown")
                index = payload.get("index", "?")
                print(f"[Error] Timeout waiting for ACK on {color} chunk {index}/{total_chunks}.")
                return False

        print("[Success] All image payloads transmitted and acknowledged.")
        return True