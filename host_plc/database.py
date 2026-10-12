import sqlite3
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path: str = "sensor_history.db"):
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        conn = None
        try:
            # Connect to the SQLite database (creates the file if it doesn't exist)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
        
            # Create the main table for storing sensor and weather readings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    indoor_temp REAL,
                    indoor_hum REAL,
                    indoor_pressure INTEGER,
                    indoor_voc INTEGER,
                    indoor_co2 REAL,
                    indoor_aq REAL,
                    outdoor_temp REAL,
                    outdoor_hum REAL,
                    outdoor_wind_speed REAL,
                    outdoor_wind_dir REAL,
                    outdoor_rain REAL,
                    outdoor_weather_code INTEGER
                )
            ''')
            
            # Save changes and close the connection safely
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"[DatabaseError]: Failed to create tables: {e}")
        finally:
            if conn:
                conn.close()
                

    def insert_reading(self, bme_data: dict, fmi_data: dict):
        # Ensure that both bme_data and fmi_data are dictionaries, even if they are None
        if bme_data is None:
            bme_data = {}
        if fmi_data is None:
            fmi_data = {}
            
        conn = None
        try:     
            # Open connection and create cursor
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Extract variables from the payload dictionaries
            # Using .get() allows us to safely insert None (NULL in SQLite) if a reading is missing
            in_temp = bme_data.get("sensor.bme688_temp")
            in_hum = bme_data.get("sensor.bme688_rh")
            in_press = bme_data.get("sensor.bme688_pressure")
            in_voc = bme_data.get("sensor.bme688_voc")
            in_co2 = bme_data.get("sensor.bme688_co2")
            in_aq = bme_data.get("sensor.bme688_aq")
            
            # Keys match the FMI payload structure from your logs
            out_temp = fmi_data.get("FMI.temp")
            out_hum = fmi_data.get("FMI.rh")
            out_wind_speed = fmi_data.get("FMI.wind_speed")
            out_wind_dir = fmi_data.get("FMI.wind_dir")
            out_rain = fmi_data.get("FMI.rain_amount")
            out_weather_code = fmi_data.get("FMI.weather_code")
            
            # Get current UTC time as string
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            
            # Execute INSERT INTO statement
            cursor.execute('''
                INSERT INTO sensor_readings (
                    timestamp,
                    indoor_temp, indoor_hum, indoor_pressure, 
                    indoor_voc, indoor_co2, indoor_aq,
                    outdoor_temp, outdoor_hum, 
                    outdoor_wind_speed, outdoor_wind_dir, outdoor_rain,
                    outdoor_weather_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                current_time,
                in_temp, in_hum, in_press, 
                in_voc, in_co2, in_aq,
                out_temp, out_hum, 
                out_wind_speed, out_wind_dir, out_rain,
                out_weather_code
            ))
            
            # Commit changes and close connection safely
            conn.commit()
            conn.close()
            return True  # Indicate successful insertion
        except sqlite3.Error as e:
            # This will print the exact SQL error to your terminal
            print(f"[Database Error] Failed to insert reading: {e}")
        except Exception as e:
            print(f"[Unexpected Error] Something went wrong during DB insert: {e}")
        finally:
            # Ensure the connection is ALWAYS closed, even if an error occurs
            if conn:
                conn.close()


    def get_history_for_graphs(self, hours: int) -> list:
        from datetime import datetime, timedelta
        
        # Calculate the time threshold
        cutoff_time = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Open connection
        conn = sqlite3.connect(self.db_path)
        
        # Set row_factory to return dict-like objects instead of raw tuples
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Execute SELECT statement filtering by timestamp
        cursor.execute('''
            SELECT * FROM sensor_readings 
            WHERE timestamp >= ? 
            ORDER BY timestamp ASC
        ''', (cutoff_str,))
        
        # Fetch all matching rows
        rows = cursor.fetchall()
        
        # Commit and close safely
        conn.close()
        
        # Convert the sqlite3.Row objects into standard Python dictionaries
        history_data = [dict(row) for row in rows]
        
        return history_data
    
    
    def get_latest_data(self) -> dict:
        """
        Fetches the most recent indoor sensor reading from the database
        and formats it using the required dictionary keys.
        """
        # Open connection and set row_factory for easy dict-like access
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetch the single newest row based on timestamp
        cursor.execute('''
            SELECT * FROM sensor_readings 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        # If a reading exists, map it to the requested key structure
        if row:
            r = dict(row)  # Convert sqlite3.Row to a standard dictionary
            
            # Helper function to safely get values from the row, defaulting to None if missing
            def safe_get(key, default):
                val = r.get(key)
                return val if val is not None else default
            
            return {
                "sensor.bme688_temp": safe_get("indoor_temp", -1.0),
                "sensor.bme688_rh": safe_get("indoor_hum", -1.0),
                "sensor.bme688_co2": round(safe_get("indoor_co2", -1)),
                "sensor.bme688_pressure": safe_get("indoor_pressure", -1),
                "sensor.bme688_voc": safe_get("indoor_voc", -1),
                "sensor.bme688_aq": safe_get("indoor_aq", -1.0),
                
                "FMI.temp": safe_get("outdoor_temp", -1.0),
                "FMI.rh": safe_get("outdoor_hum", -1.0),
                "FMI.wind_speed": safe_get("outdoor_wind_speed", -1.0),
                "FMI.wind_dir": safe_get("outdoor_wind_dir", 0.0),
                "FMI.rain_amount": safe_get("outdoor_rain", -1.0),
                "unit.FMI.rain_amount": safe_get("outdoor_rain_unit", "mm"),
                "FMI.weather_code": safe_get("outdoor_weather_code", 0)
                
            }
        else:
            # Fallback for the very first run before any data is logged
            return {
                "sensor.bme688_temp": -1.0,
                "sensor.bme688_rh": -1.0,
                "sensor.bme688_co2": -1.0,
                "sensor.bme688_pressure": -1,
                "sensor.bme688_voc": -1,
                "sensor.bme688_aq": -1.0,
                "FMI.temp": -1.0,
                "FMI.rh": -1.0,
                "FMI.wind_speed": -1.0,
                "FMI.wind_dir": 0.0,
                "FMI.rain_amount": -1.0,
                "unit.FMI.rain_amount": "mm",
                "FMI.weather_code": 0
            }