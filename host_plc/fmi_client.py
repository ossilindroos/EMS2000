import requests
import xml.etree.ElementTree as ET
import json


class FMIClient:
    def __init__(self, config):
        self.config = config
        # Read the location from the configuration file. If not found, default to "Espoo".
        self.location = config.get("SystemSettings", {}).get("location", "Espoo")
        self.fmi_data = {}


    def fetch_raw_data(self):
        # 1. Build API URL for FMI Open Data
        # Parameters: t2m = temperature, rh = relative humidity, ws_10min = wind speed, r_1h = rain amount, wawa = weather code, wd_10min = wind direction
        url = (
            f"http://opendata.fmi.fi/wfs?service=WFS&version=2.0.0"
            f"&request=getFeature&storedquery_id=fmi::observations::weather::simple"
            f"&place={self.location}"
            f"&parameters=t2m,rh,ws_10min,r_1h,wawa,wd_10min"
        )
        
        try:
            # 2. Fetch data from FMI API
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 3. Parse the XML response
            root = ET.fromstring(response.content)
            
            # FMI uses XML namespaces, so we need to handle that when searching for elements.
            # Search for all BsWfsElement elements in the XML, which contain the parameter names and values.
            namespace = {'BsWfs': 'http://xml.fmi.fi/schema/wfs/2.0'}
            elements = root.findall('.//BsWfs:BsWfsElement', namespace)
            
            # Gather the parameter names and values into a dictionary. If FMI returns "NaN" for a value, we convert it to 0.0.
            parsed_data = {}
            for elem in elements:
                param_name = elem.find('BsWfs:ParameterName', namespace).text
                param_value = elem.find('BsWfs:ParameterValue', namespace).text
                
                # FMI returns "NaN" for missing values, so we convert those to 0.0 for our purposes.
                if param_value == "NaN":
                    param_value = 0.0
                else:
                    param_value = float(param_value)
                    
                # Because XML can contain multiple entries for the same parameter (e.g., multiple observations), we overwrite the value in the dictionary, so we always have the most recent one.
                # Logic: If there are multiple entries for the same parameter, we take the last one (most recent).
                parsed_data[param_name] = param_value
                
            # 4. Translate the parsed data into our internal format. We also ensure that if a parameter is missing, we default to 0.0.
            self.fmi_data = {
                "temperature": parsed_data.get("t2m", 0.0),
                "humidity": parsed_data.get("rh", 0.0),
                "wind_speed": parsed_data.get("ws_10min", 0.0),
                "wind_dir": parsed_data.get("wd_10min", 0.0),
                "rain_amount": parsed_data.get("r_1h", 0.0),
                "weather_code": int(parsed_data.get("wawa", 0))
            }
            
        except Exception as e:
            print(f"Virhe FMI-datan haussa: {e}")
            # Tähän voisi lisätä logiikan, joka palauttaa aiemman välimuistin (cached_data) 
            # jos netti pätkii, mutta mennään nyt tällä.

    def _calculate_precipitation(self, temp, raw_mm, wawa_code):
        # Returns precipitation value, unit, and icon path based on temperature and weather code.
        if temp < 0 or (50 <= wawa_code <= 59):
            return round(raw_mm * 10, 1), "cm", "weather_icons/snowflake.png"
        return raw_mm, "mm", "weather_icons/rain_drop.png"


    def _map_weather_icon(self, wawa_code):
        # Mapping of FMI weather codes to local icon paths. This is a simplified mapping; more codes can be added as needed.
        if wawa_code in [0, 1, 2]:
            return "weather_icons/sun.png"
        elif wawa_code == 3:
            return "weather_icons/half_coudy.png"
        elif wawa_code in [4, 5]:
            return "weather_icons/cloudy.png"
        elif (20 <= wawa_code <= 39) or (80 <= wawa_code <= 84):
            return "weather_icons/rainy.png"
        elif (40 <= wawa_code <= 59) or (85 <= wawa_code <= 89):
            return "weather_icons/snowy.png"
        elif 90 <= wawa_code <= 99:
            return "weather_icons/thunderstorm.png"
        return "weather_icons/cloudy.png"


    def get_dashboard_payload(self):
        temp = self.fmi_data.get("temperature", 0.0)
        raw_rain = self.fmi_data.get("rain_amount", 0.0)
        wawa_code = self.fmi_data.get("weather_code", 0)

        # Run the precipitation calculation and icon mapping based on the current temperature and weather code.
        precip_val, precip_unit, precip_icon = self._calculate_precipitation(temp, raw_rain, wawa_code)
        main_icon_path = self._map_weather_icon(wawa_code)

        return {
            "FMI.outdoor_temperature": temp,
            "FMI.outdoor_humidity": self.fmi_data.get("humidity"),
            "FMI.wind_speed": self.fmi_data.get("wind_speed"),
            "FMI.wind_dir": self.fmi_data.get("wind_dir"),
            "FMI.rain_amount": precip_val,
            "unit.FMI.rain_amount": precip_unit,
            "image.precip_icon": precip_icon,   # New: Drop or Snowflake icon based on precipitation type
            "image.weather_icon": main_icon_path # Updated: Main weather icon based on FMI weather code
        }
    
    
    
# --- LOKAALI YKSIKKÖTESTAUS ---
if __name__ == "__main__":
    print("--- FMIClient Live Data Test ---")
    
    mock_config = {
        "SystemSettings": {
            "location": "Espoo"
        }
    }
    
    weather = FMIClient(mock_config)
    print(f"Haetaan oikea säädata sijainnille: {weather.location}...")
    
    weather.fetch_raw_data()
    payload = weather.get_dashboard_payload()
    
    print("\nTuore Payload suoraan Ilmatieteen laitokselta:")
    for key, val in payload.items():
        print(f"  {key}: {val}")
        
    print("\nHomma toimii! Data on valmis puskettavaksi ruudulle.")