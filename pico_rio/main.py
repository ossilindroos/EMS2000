import time
import ubinascii
from machine import Pin, SPI, I2C
import json

# Hardware drivers
from bme688 import BME680
# from epaper import EPD
from epaper import EPD_7in5_B
# Our new communication module
from serial_link import SerialLink

class DashboardNode:
    def __init__(self):
        try:
            # 0. Initialize Communication Link FIRST
            self.link = SerialLink(timeout_ms=10)
        
            # 1. Hardware Initialization
            self.i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)
            self.sensor = BME680(i2c_device=self.i2c)
        
            self.sensor.set_gas_heater_temperature(320)
            self.sensor.set_gas_heater_duration(150)
            self.sensor.select_gas_heater_profile(0)
        
            self.spi = SPI(1, baudrate=20_000_000, polarity=0, phase=0, sck=Pin(10), mosi=Pin(11))
            self.cs = Pin(9, Pin.OUT)
            self.dc = Pin(8, Pin.OUT)
            self.rst = Pin(12, Pin.OUT)
            self.busy = Pin(13, Pin.IN)
        
            # 2. Initialize e-paper display Object
            self.epd = EPD_7in5_B()
            self.black_offset = 0
            self.red_offset = 0
        
            # 3. State Management
            self.last_sensor_read = 0
            self.sensor_interval_ms = 60000 # 1 minute interval for sensor reads
        except Exception as e:
            self.link.send_error(f"Initialization failed: {e}")
            raise
        

    def read_and_send_sensor_data(self):
        try:
            if self.sensor.get_sensor_data():
                payload = {
                    "sensor.bme688_temp": round(self.sensor.data.temperature, 1),
                    "sensor.bme688_rh": round(self.sensor.data.humidity, 1),
                    "sensor.bme688_pressure": round(self.sensor.data.pressure, 0)
                }
                if self.sensor.data.heat_stable:
                    payload["sensor.bme688_gas_resistance"] = round(self.sensor.data.gas_resistance, 2)
                
                # Using our new link module!
                self.link.send_message(payload)
        except Exception as e:
            self.link.send_error(f"BME688 read failed: {e}")


    def process_incoming_chunk(self, payload: dict):
        try:
            color = payload.get("color")
            index = payload.get("index", 0)
            total = payload.get("total", 1)
            b64_data = payload.get("data", "")
            
            target_buffer = self.epd.buffer_black if color == "black" else self.epd.buffer_red
            decoded_bytes = ubinascii.a2b_base64(b64_data)
            
            # Reset the offset when the first chunk of a new image is received
            if index == 0:
                if color == "black":
                    self.black_offset = 0
                else:
                    self.red_offset = 0
                    
            # Fetch the correct offset in the buffer based on color and current offset
            current_offset = self.black_offset if color == "black" else self.red_offset
            
            # Write the decoded bytes directly into the target buffer at the current offset
            target_buffer[current_offset : current_offset + len(decoded_bytes)] = decoded_bytes

            # Move the pointer forward by the length of the received data
            if color == "black":
                self.black_offset += len(decoded_bytes)
            else:
                self.red_offset += len(decoded_bytes)
            
            self.link.send_ack()
            
            if color == "red" and index == total - 1:
                self.update_display()
                
        except Exception as e:
            self.link.send_error(f"Chunk processing failed: {e}")
            
    
    def update_display(self):
        try:
            self.epd.init()
            self.epd.display()
            self.epd.sleep()
            
        except Exception as e:
            # Use the link module for errors
            self.link.send_error(f"Display update failed: {e}")
    

    def run(self):
        self.read_and_send_sensor_data()
        self.last_sensor_read = time.ticks_ms()
        
        while True:
            try:
                # Look how clean the main loop is now!
                incoming_msg = self.link.poll_message()
                
                if incoming_msg:
                    self.process_incoming_chunk(incoming_msg)
                
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, self.last_sensor_read) >= self.sensor_interval_ms:
                    self.read_and_send_sensor_data()
                    self.last_sensor_read = current_time
                    
            except KeyboardInterrupt:
                self.link.send_message({"status": "Pico script stopped by user"})
                break
            except Exception as e:
                self.link.send_error(f"Main loop crashed: {e}")
                time.sleep(1)

if __name__ == '__main__':
    node = DashboardNode()
    node.run()