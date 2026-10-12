import __main__

from PIL import Image
import logging
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from matplotlib import dates as mdates
import io
from zoneinfo import ZoneInfo

from matplotlib.ticker import FuncFormatter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphMaker:
    def __init__(self):
        # Default settings for e-paper display (400x120 pixels, black and white)
        # So that all graphs have a consistent look and feel, we set global parameters here.
        
        # 1. White background for the entire figure and axes
        plt.rcParams['figure.facecolor'] = 'white'
        plt.rcParams['axes.facecolor'] = 'white'
        
        # 2. Black axes and grid lines for clarity on the e-paper display
        plt.rcParams['axes.edgecolor'] = 'black'
        plt.rcParams['grid.color'] = 'black'
        plt.rcParams['grid.linestyle'] = ':'      # Dotted grid lines for better readability
        
        # 3. Black text and font size adjustment
        plt.rcParams['text.color'] = 'black'
        plt.rcParams['axes.labelcolor'] = 'black'
        plt.rcParams['xtick.color'] = 'black'
        plt.rcParams['ytick.color'] = 'black'
        plt.rcParams['font.size'] = 10            # Scale font size for the small e-paper display, ensuring readability without clutter
        
        # 4. Black and thick data line by default
        plt.rcParams['lines.color'] = 'black'
        plt.rcParams['lines.linewidth'] = 2.0


    def generate_graph(self, history_data: list, draw_id: str, width: int, height: int) -> Image.Image:
        # 2. Main router method
        # This is the ONLY method db_renderer will ever call.
        
        # Check if history_data is empty and return a placeholder image if true
        if not history_data:
            logger.warning(f"No historical data available for draw_id '{draw_id}'")
            return None  # Return None to indicate no graph can be generated
        
        
        if draw_id == "sensor.bme688_temp":
            df = self._extract_series(history_data, "indoor_temp")
            return self._draw_graph(df[0], df[1], width, height, unit="°C", title="Indoor Temperature")
            
        elif draw_id == "sensor.bme688_co2":
            df = self._extract_series(history_data, "indoor_co2")
            return self._draw_graph(df[0], df[1], width, height, unit="ppm", title="Indoor eCO2")    
        elif draw_id == "sensor.bme688_rh":
            df = self._extract_series(history_data, "indoor_rh")
            return self._draw_graph(df[0], df[1], width, height, unit="RH%", title="Indoor Relative Humidity")
            
        else:
            logger.error(f"Unknown draw_id '{draw_id}' received. Returning placeholder image.")
            return Image.new("RGB", (width, height), color=(255, 255, 255))  
        
        
    def _draw_graph(self, timestamps: list, values: list, width: int, height: int, unit: str = "", limit_line: float = None, title: str = "") -> Image.Image:
        # 1. Handle empty data gracefully
        if not timestamps or not values:
            return Image.new("RGB", (width, height), color=(255, 255, 255))
            
        # 2. Create the Matplotlib figure
        dpi = 100
        fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)

        # 3. Plot the data line
        ax.plot(timestamps, values, color='black', linewidth=2)
        
        # 4. Optional title for the graph
        if title:
            ax.set_title(title, fontsize=9, loc='center', pad=4)
        
        # 4. Optional visual limit line (e.g. for eCO2 high limits)
        if limit_line is not None:
            ax.axhline(y=limit_line, color='black', linestyle='--', linewidth=1)
            
        # Units
        if unit:
            # {x:g} removes unnecessary trailing zeros and decimal points for cleaner display
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:g} {unit}"))

        # 5. Format X-axis and apply layout
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H', tz=ZoneInfo("Europe/Helsinki")))
        ax.grid(True)
        plt.tight_layout(pad=0.5)

        # 6. Save to RAM and convert to Pillow
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

        buf.seek(0)
        img = Image.open(buf).convert("RGB")
        return img.resize((width, height))
            
            
    def _extract_series(self, data: list, value_key: str) -> tuple[list, list]:
        timestamps = []
        values = []
        
        # Define Finnish timezone for proper timestamp handling
        helsinki_tz = ZoneInfo("Europe/Helsinki")
        
        for entry in data:
            ts_str = entry.get("timestamp")
            val = entry.get(value_key)
            
            if ts_str and val is not None:
                # Convert timestamp string to datetime object in Helsinki timezone
                dt_naive = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                # Label as UTC
                dt_utc = dt_naive.replace(tzinfo=timezone.utc)
                timestamps.append(dt_utc)
                values.append(val)
                
        return timestamps, values
    
    
    
if __name__ == "__main__":
    # Example usage for testing
    gm = GraphMaker()
    # Simulated historical data for testing
    testDB = [
        {"timestamp": "2024-06-01 00:00:00", "indoor_temp": 22.5, "indoor_rh": 45.0, "indoor_co2": 400},
        {"timestamp": "2024-06-01 01:00:00", "indoor_temp": 22.0, "indoor_rh": 46.0, "indoor_co2": 420},
        {"timestamp": "2024-06-01 02:00:00", "indoor_temp": 21.5, "indoor_rh": 47.0, "indoor_co2": 430},
        {"timestamp": "2024-06-01 03:00:00", "indoor_temp": 21.0, "indoor_rh": 48.0, "indoor_co2": 450},
        {"timestamp": "2024-06-01 04:00:00", "indoor_temp": 20.5, "indoor_rh": 49.0, "indoor_co2": 470},
        {"timestamp": "2024-06-01 05:00:00", "indoor_temp": 20.0, "indoor_rh": 50.0, "indoor_co2": 500},]
    
    # Test to see if the timezone conversion works
    for entry in testDB:
        ts_str = entry.get("timestamp")
        dt_naive = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = dt_naive.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone(ZoneInfo("Europe/Helsinki"))
        print(f"Original: {ts_str} | UTC: {dt_utc} | Local (Helsinki): {dt_local}")
    
    img = gm.generate_graph(testDB, draw_id="sensor.bme688_temp", width=400, height=120)
    if img:
        img.show()  # Display the generated graph for visual inspection