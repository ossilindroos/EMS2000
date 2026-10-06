import json
import logging
import queue
from typing import Dict, List, Any

from db_renderer import DashboardRenderer
from fmi_client import FMIClient
from serial_host import SerialHost
from iaq_calculator import IAQCalculator
from database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class HostController:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the HostController with private attributes as defined in the UML.
        """
        logger.info("Initializing HostController...")
        
        # -config: dict
        self._config: Dict[str, Any] = config
        
        # -latest_data: dict
        self._latest_data: Dict[str, Any] = {}
        
        # -image_chunks: list
        self._image_chunks: List[str] = []
        
        # -active_transfer: bool    
        self._active_transfer: bool = False
        
        # Initialize the FMI data client
        self._fmi_client = FMIClient(self._config)
        
        # Initialize the renderer with resolution from config
        w = self._config.get("SystemSettings", {}).get("Resolution", {}).get("Width", 800)
        h = self._config.get("SystemSettings", {}).get("Resolution", {}).get("Height", 480)
        self._renderer = DashboardRenderer(width=w, height=h)
        
        # Initialize the serial host for communication with the Pico
        port = self._config.get("SystemSettings", {}).get("SerialPort", "COM5")
        baud = self._config.get("SystemSettings", {}).get("Baudrate", 115200)
        self._sensor_queue = queue.Queue()
        self._serial = SerialHost(port=port, baudrate=baud, sensor_queue=self._sensor_queue)
        
        # Initialize the IAQ calculator
        self._iaq_calculator = IAQCalculator()
        
        # Initialize the database manager
        self._db_manager = DatabaseManager(db_path="sensor_history.db")
        

    def start(self) -> None:
        """
        +start(): None
        Main loop or initialization routine for the daemon.
        """
        logger.info("Starting HostController daemon...")
                
        # Connect to the Pico
        if not self._serial.connect():
            logger.error("Could not connect to Pico. Check USB connection and port.")


    def trigger_screen_refresh(self) -> None:
        """
        +trigger_screen_refresh(): None
        Gathers data, triggers the DashboardRenderer, and prepares the image.
        """
        logger.info("Triggering screen refresh...")
        
        # 1. Fetch live FMI data
        try:
            self._fmi_client.fetch_raw_data()
            fmi_payload = self._fmi_client.get_dashboard_payload()
            logger.info(f"FMI payload retrieved successfully: {list(fmi_payload.keys())}")
        except Exception as e:
            logger.error(f"Failed to fetch FMI data: {e}")
            fmi_payload = {}

       # 2. Combine all flat sensor values into one dictionary
        live_data = {**self._latest_data, **fmi_payload}

        # 3. Create a deep copy of the static config to serve as the final payload
        import copy
        render_payload = copy.deepcopy(self._config)

        # 4. Inject live data into the copied entities
        for entity in render_payload.get("Entities", []):
            ent_id = entity.get("id")
            
            # Special: Wind Direction
            # Image rotation for wind direction is handled separately to ensure the arrow points correctly.
            if ent_id == "image.wind_dir":
                wind_angle = live_data.get("FMI.wind_dir")
                if wind_angle is not None:
                    entity["rotation"] = float(wind_angle)
                else:
                    logger.warning("Wind direction data not available; skipping rotation update.")
                continue  # Skip the rest of the loop for wind direction since it's handled

            
            if ent_id in live_data:
                # Handle image updates (file path or rotation)
                if entity.get("type") == "image":
                    if "wind_dir" in ent_id:
                        entity["rotation"] = float(live_data[ent_id])
                    else:
                        entity["file"] = str(live_data[ent_id])
                
                # Handle text/sensor updates (value injection)
                else:
                    entity["value"] = live_data[ent_id]
                    
                # Handle dynamic unit changes (e.g., mm to cm for snow)
                unit_key = f"{ent_id}_unit"
                if unit_key in live_data:
                    entity["unit"] = live_data[unit_key]

        # 5. Pass the SINGLE combined dictionary to the renderer
        try:
            img = self._renderer.generate_image(render_payload)
            # Digital Twin for the HomeAssistant
            output_file = "dashboard_latest.png"
            
            img.save(output_file)
            logger.info(f"Dashboard successfully rendered and saved to {output_file}")
            
            # 1. Split into 12 pieces (approx. 4000 bytes each for black and red = total 24 pieces)
            self._image_chunks = self._renderer.get_base64_chunks(img, chunk_count=12)
            logger.info(f"Image split into {len(self._image_chunks)} Base64 chunks.")
            
            # 2. Push the chunks to the Pico via serial link (if connected)
            if self._serial.is_running:
                logger.info("Transmitting image to Pico. This may take up to 20 seconds...")
                self._active_transfer = True
                
                success = self._serial.send_image_payloads(self._image_chunks)
                
                self._active_transfer = False
                if success:
                    logger.info("Transmission complete. Pico display is updating.")
                else:
                    logger.error("Transmission failed or timed out during ping-pong.")
            else:
                logger.warning("Serial port not connected. Skipping physical display update.")
            
        except Exception as e:
            logger.error(f"Failed to render dashboard image: {e}")


    def handle_sensor_data(self, data: dict) -> None:
        """
        +handle_sensor_data(data: dict): None
        Receives and processes incoming sensor data, fetches FMI data,
        and logs everything to the SQLite database.
        """
        logger.info("Handling incoming sensor data...")
        
        # 1. Extract raw values from the Pico payload
        raw_temp = data.get("temperature", 0.0)
        raw_hum = data.get("humidity", 0.0)
        raw_press = data.get("pressure", 0.0)
        raw_gas = data.get("gas_resistance", 0.0)
        
        # 2. Process IAQ metrics if gas resistance is valid
        # The BME688 might return 0.0 during the first few seconds of heating up
        if raw_gas > 0:
            processed_data = self._iaq_calculator.calculate(raw_temp, raw_hum, raw_gas)
        else:
            logger.warning("Gas resistance is 0. IAQ metrics will be skipped for this reading.")
            processed_data = {
                "temperature": raw_temp,
                "humidity": raw_hum,
                "aq": None,
                "eco2": None,
                "voc": None
            }
            
        # 3. Rebuild the BME payload for the database to match insert_reading keys
        final_bme_payload = {
            "temperature": processed_data.get("temperature"),
            "humidity": processed_data.get("humidity"),
            "pressure": raw_press,
            "voc": processed_data.get("voc"),
            "co2": processed_data.get("eco2"),
            "aq": processed_data.get("aq")
        }
        
        # 4. Fetch the latest FMI outdoor data
        # Ensure your FMI client has a method to get the current payload
        try:
            fmi_data = self._fmi_client.fetch_raw_data() or {}
        except Exception as e:
            logger.error(f"Failed to fetch FMI data: {e}")
            fmi_data = {}
            
        # 5. Insert the combined data into the SQLite database
        success = self._db_manager.insert_reading(final_bme_payload, fmi_data)
        # Log accurately based on the boolean return value
        if success:
            logger.info("Sensor and FMI data successfully logged to database.")
        else:
            logger.error("Failed to insert data into database. Check previous errors.")
        
        
        

    
    
def main():
        # Test the screen refresh logic using the real config.json
            try:
                with open("config.json", "r", encoding="utf-8") as f:
                    real_config = json.load(f)
                    
                controller = HostController(real_config)
                
                # Connect to the Pico and start the daemon
                controller.start() 
                
                # Fetch the latest data from the database to initialize the controller's state
                controller._latest_data = controller._db_manager.get_latest_data()
                
                # Give the Pico a moment to establish the serial connection before sending data
                import time
                time.sleep(2)
                
                # Run the refresh logic once
                controller.trigger_screen_refresh()
                
                # Keep the program running to allow for serial communication and potential future updates
                print("Waiting for sensor data (Ctrl+C to quit)...")
                
                import time
                last_display_update = time.time()
                # 15 minutes in seconds
                DISPLAY_UPDATE_INTERVAL = 15 * 60  
                
                while True:
                    # 1. Process all pending sensor data from the background thread
                    while not controller._sensor_queue.empty():
                        data = controller._sensor_queue.get()
                        # This will now calculate IAQ and save to SQLite!
                        controller.handle_sensor_data(data)
                        
                    # 2. Check if it's time to refresh the e-paper display
                    current_time = time.time()
                    if (current_time - last_display_update) >= DISPLAY_UPDATE_INTERVAL:
                        logger.info("15 minutes passed. Triggering display update...")
                        
                        # Fetch the absolute latest state from DB before rendering
                        controller._latest_data = controller._db_manager.get_latest_data()
                        
                        controller.trigger_screen_refresh()
                        last_display_update = current_time
                        
                    # Sleep slightly to prevent 100% CPU usage
                    time.sleep(0.1)
                    
            except FileNotFoundError:
                logger.error("Could not find 'config.json' for testing.")
            except KeyboardInterrupt:
                print("\nExiting testing mode.")


if __name__ == "__main__":
    main()