import json
import base64
import logging
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DashboardRenderer:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        
        # Attempt to load Roboto-Bold.ttf with Canva specified sizes
        try:
            self.fonts = {
                "standard": ImageFont.truetype("Roboto-Bold.ttf", 25),
                "header": ImageFont.truetype("Roboto-Bold.ttf", 25),     # Header = 20
                "value": ImageFont.truetype("Roboto-Bold.ttf", 45),      # Value = 45
                "unit_font": ImageFont.truetype("Roboto-Bold.ttf", 25)   # Unit = 25
            }
            logger.info("Custom fonts loaded successfully.")
        except IOError:
            logger.warning("'Roboto-Bold.ttf' not found in directory! Falling back to default font.")
            default_font = ImageFont.load_default()
            self.fonts = {
                "standard": default_font,
                "header": default_font,
                "value": default_font,
                "unit_font": default_font
            }
        
    def _scale_and_anchor_icon(self, icon: Image.Image, target_w: int, target_h: int, anchor_x: int, anchor_y: int) -> tuple[Image.Image, tuple[int, int]]:
        # 1. Crop out completely transparent borders to ensure accurate visual anchoring
        bbox = icon.getbbox()
        if bbox:
            icon = icon.crop(bbox)
            
        # 2. Calculate scaling factors while maintaining aspect ratio
        orig_w, orig_h = icon.size
        
        # Defensive check against zero division
        if orig_w == 0 or orig_h == 0:
            logger.error("Image dimensions are zero, skipping scale.")
            return icon, (anchor_x, anchor_y)
            
        scale = min(target_w / orig_w, target_h / orig_h)
        
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        
        # 3. Resize the image using high-quality downsampling
        icon = icon.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 4. Calculate the top-left paste coordinates for a bottom-right (rb) anchor
        paste_x = anchor_x - new_w
        paste_y = anchor_y - new_h
        
        return icon, (paste_x, paste_y)
        
    def generate_image(self, data: dict) -> Image.Image:
        # Create a blank image with white background
        img = Image.new("RGB", (self.width, self.height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        entities = data.get("Entities", [])
        if not entities:
            logger.warning("No 'Entities' found in the provided configuration.")
            
        for entity in entities:
            e_type = entity.get("type")
            
            # Smart coordinate validation based on entity type
            if e_type == "line":
                if not all(k in entity for k in ("x1", "y1", "x2", "y2")):
                    logger.error(f"Line entity missing coordinate(s): {entity.get('id', 'UNKNOWN')}. Skipping.")
                    continue
            else:
                if "x" not in entity or "y" not in entity:
                    logger.error(f"Entity missing x or y coordinates: {entity.get('id', 'UNKNOWN')}. Skipping.")
                    continue

            # Standard color is black, if not specified as "red"
            base_color = (255, 0, 0) if entity.get("color") == "red" else (0, 0, 0)
            e_type = entity.get("type")

            if e_type == "label":
                font_name = entity.get("font", "standard")
                selected_font = self.fonts.get(font_name, self.fonts["standard"])
                
                # Draw label text centered around the x, y coordinates
                # anchor="ma" -> middle-acending
                draw.text(
                    (entity["x"], entity["y"]), 
                    entity.get("text", ""), 
                    fill=base_color, 
                    font=selected_font, 
                    anchor="ma"
                )

            elif e_type == "text":
                value_font = self.fonts.get(entity.get("font", "standard"), self.fonts["standard"])
                unit_font = self.fonts.get("unit_font", self.fonts["standard"])
                
                val_str = str(entity.get("value", "--"))
                unit_str = entity.get("unit", "")
                
                # Change color to red if value is outside "Limits": {LL and HH}
                val_color = base_color
                if "limits" in entity:
                    LL = entity["limits"].get("LL")
                    HH = entity["limits"].get("HH")
                    try:
                        val = float(val_str)
                        if LL is not None and val < LL:
                            val_color = (255, 0, 0)  # Red
                        elif HH is not None and val > HH:
                            val_color = (255, 0, 0)  # Red
                    except ValueError:
                        pass

                if "\n" in unit_str:
                    # Handle multi-line units with a custom tight vertical gap
                    lines = unit_str.split("\n")
                    
                    # Calculate bounding boxes for each line to get precise heights and widths
                    line_boxes = [draw.textbbox((0, 0), line, font=unit_font) for line in lines]
                    line_widths = [box[2] - box[0] for box in line_boxes]
                    line_heights = [box[3] - box[1] for box in line_boxes]
                    
                    unit_width = max(line_widths) if line_widths else 0
                    custom_gap = 2  # Tight pixel gap between lines
                    total_height = sum(line_heights) + custom_gap
                    
                    # Center the entire two-line block vertically around entity["y"]
                    start_y = entity["y"] - (total_height / 2)
                    
                    current_y = start_y
                    for i, line in enumerate(lines):
                        draw.text(
                            (entity["x"], current_y), 
                            line, 
                            fill=val_color, 
                            font=unit_font, 
                            anchor="rt"  # Right-Top anchored for each line
                        )
                        current_y += line_heights[i] + custom_gap
                else:
                    # Standard single-line unit logic
                    draw.text(
                        (entity["x"], entity["y"]), 
                        unit_str, 
                        fill=val_color, 
                        font=unit_font, 
                        anchor="rm"
                    )
                    bbox = draw.textbbox((0, 0), unit_str, font=unit_font)
                    unit_width = bbox[2] - bbox[0]
                
                margin = 8
                number_x = entity["x"] - unit_width - margin
                draw.text(
                    (number_x, entity["y"]), 
                    val_str, 
                    fill=val_color, 
                    font=value_font, 
                    anchor="rm"
                )

            elif e_type == "line":
                try:
                    thickness = entity.get("stroke_width", entity.get("thickness", 1))
                    coords = [entity["x1"], entity["y1"], entity["x2"], entity["y2"]]
                    draw.line(coords, fill=base_color, width=thickness)
                except KeyError as e:
                    logger.error(f"Missing coordinates for line entity {entity.get('id', 'UNKNOWN')}: {e}")

            elif e_type == "rect":
                try:
                    thickness = entity.get("stroke_width", entity.get("thickness", 1))
                    x, y = entity["x"], entity["y"]
                    coords = [x, y, x + entity["width"], y + entity["height"]]
                    draw.rectangle(coords, outline=base_color, width=thickness)
                except KeyError as e:
                    logger.error(f"Missing dimensions for rect entity {entity.get('id', 'UNKNOWN')}: {e}")

            elif e_type == "image":
                img_path = entity.get("file")
                target_w = entity.get("width")
                target_h = entity.get("height")
                
                if not img_path:
                    logger.warning(f"Image entity '{entity.get('id', 'UNKNOWN')}' is missing the 'file' parameter.")

                if img_path:
                    try:
                        icon = Image.open(img_path).convert("RGBA")
                        
                        if "rotation" in entity:
                            try:
                                rotation_val = float(entity["rotation"])
                                icon = icon.rotate(-rotation_val, resample=Image.Resampling.BICUBIC, expand=True)
                            except ValueError:
                                logger.error(f"Invalid rotation value '{entity['rotation']}' for {entity.get('id', 'UNKNOWN')}")
                        
                        if target_w is not None and target_h is not None:
                            icon, paste_coords = self._scale_and_anchor_icon(
                                icon, target_w, target_h, entity["x"], entity["y"]
                            )
                            img.paste(icon, paste_coords, icon)
                        else:
                            logger.info(f"Width or height missing for {entity.get('id', 'UNKNOWN')}. Pasting unscaled.")
                            img.paste(icon, (entity["x"], entity["y"]), icon)
                            
                    except FileNotFoundError:
                        logger.error(f"Image file not found at path: '{img_path}'")
                    except Exception as e:
                        logger.error(f"Failed to process image '{img_path}': {e}")
                else:
                    if target_w is not None and target_h is not None:
                        start_x = entity["x"] - target_w
                        start_y = entity["y"] - target_h
                        draw.rectangle(
                            [start_x, start_y, entity["x"], entity["y"]],
                            outline=base_color, width=1
                        )
                        draw.line([start_x, start_y, entity["x"], entity["y"]], fill=base_color, width=1)
                        draw.line([start_x, entity["y"], entity["x"], start_y], fill=base_color, width=1)
                
            elif e_type == "calendar":
                try:
                    x, y = entity["x"], entity["y"]
                    w, h = entity["width"], entity["height"]
                    
                    # Draw the outer frame of the calendar
                    draw.rectangle([x, y, x + w, y + h], outline=base_color, width=2)
                    
                    # Calculate grid dimensions (Header + 4 event rows)
                    row_height = h // 5
                    col_width = w // 2
                    
                    # Draw vertical divider for "Today" and "Tomorrow" columns
                    draw.line([x + col_width, y + row_height, x + col_width, y + h], fill=base_color, width=1)
                    
                    # Draw horizontal row dividers and placeholder event texts
                    for i in range(1, 5):
                        line_y = y + (i * row_height)
                        draw.line([x, line_y, x + w, line_y], fill=base_color, width=1)
                        
                        # Placeholder text for events
                        draw.text((x + 10, line_y + 10), f"Event {i}", fill=base_color, font=self.fonts["standard"])
                        draw.text((x + col_width + 10, line_y + 10), f"Tmrw {i}", fill=base_color, font=self.fonts["standard"])
                        
                    # Draw the centered header text for the calendar
                    header_x = x + (w // 2)
                    header_y = y + (row_height // 2)
                    draw.text(
                        (header_x, header_y), 
                        "Calendar : Today - Tomorrow", 
                        fill=base_color, 
                        font=self.fonts["standard"], 
                        anchor="mm"
                    )
                except KeyError as e:
                    logger.error(f"Missing dimensions for calendar entity {entity.get('id', 'UNKNOWN')}: {e}")

        return img
                
    
    def get_base64_chunks(self, img: Image.Image, chunk_count: int) -> list:
        if img.size != (800, 480):
            img = img.resize((800, 480))
        img = img.convert("RGB")

        # 1. Convert image to numpy matrix (Height, Width, Channels)
        pixel_data = np.array(img)

        # 2. Isolate color channels for fast matrix operations
        r = pixel_data[:, :, 0]
        g = pixel_data[:, :, 1]
        b = pixel_data[:, :, 2]

        # 3. Define color masks (Thresholding at 127)
        is_red = (r > 127) & (g < 127) & (b < 127)
        is_black = (r < 127) & (g < 127) & (b < 127)

        # 4. Initialize bit arrays according to Waveshare driver logic
        # Black buffer: 1 = White/Background, 0 = Black
        # Red buffer:   0 = White/Background, 1 = Red
        black_bits = np.ones((480, 800), dtype=np.uint8)
        red_bits = np.zeros((480, 800), dtype=np.uint8)

        # Apply masks
        black_bits[is_black] = 0
        red_bits[is_red] = 1

        # 5. Pack bits into bytes (MicroPython MONO_HLSB compatibility)
        black_bytes = np.packbits(black_bits, axis=-1, bitorder='big').flatten()
        red_bytes = np.packbits(red_bits, axis=-1, bitorder='big').flatten()

        # 6. Calculate optimal chunk size
        buffer_size = len(black_bytes)
        chunk_size = (buffer_size + chunk_count - 1) // chunk_count

        payloads = []
        
        # 7. Chunk and encode black buffer
        for i in range(0, buffer_size, chunk_size):
            chunk = black_bytes[i:i + chunk_size]
            b64_data = base64.b64encode(chunk).decode('ascii')
            
            payloads.append({
                "color": "black",
                "index": i // chunk_size,
                "total": chunk_count,
                "data": b64_data
            })

        # 8. Chunk and encode red buffer
        for i in range(0, buffer_size, chunk_size):
            chunk = red_bytes[i:i + chunk_size]
            b64_data = base64.b64encode(chunk).decode('ascii')
            
            payloads.append({
                "color": "red",
                "index": i // chunk_size,
                "total": chunk_count,
                "data": b64_data
            })

        return payloads
    
    def export_digital_twin(self, img: Image.Image, file_path: str) -> None:
        # TODO Export the digital twin representation to a file
        pass
    
    
if __name__ == "__main__":
    logger.info("Begin renderer testing...")
    
    # 1. Read config from JSON
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info("Config loaded successfully!")
    except FileNotFoundError:
        logger.critical("'config.json' not found in the current directory. Exiting.")
        exit(1)
    except json.JSONDecodeError as e:
        logger.critical(f"Failed to parse 'config.json': {e}. Exiting.")
        exit(1)
    
    try:
        w = config["SystemSettings"]["Resolution"]["Width"]
        h = config["SystemSettings"]["Resolution"]["Height"]
    except KeyError as e:
        logger.critical(f"Missing required resolution settings in config: {e}. Exiting.")
        exit(1)
    
    renderer = DashboardRenderer(width=w, height=h)
    
    # --- MOCK DATA INJECTION ---
    mock_sensor_data = {
        "sensor.bme688_temp": 22.5,
        "sensor.bme688_rh": 45.2,
        "sensor.bme688_co2": 1000,
        "sensor.bme688_pressure": 101.3,
        "sensor.bme688_voc": 120,
        "sensor.bme688_aq": 95,
        "sensor.fmi_temp": -5.2,
        "sensor.fmi_rh": 82,
        "sensor.fmi_wind": 4.5,
        "sensor.fmi_rain": 1.2,
        # Image tests
        "image.weather_icon": "weather_icons/cloudy.png",
        "image.precip_icon": "weather_icons/snowflake.png",
        "image.wind_dir": 45  # 45 degrees rotation
    }
    
    # Single, unified injection loop
    for entity in config.get("Entities", []):
        ent_id = entity.get("id")
        if ent_id in mock_sensor_data:
            if entity.get("type") == "image":
                if ent_id == "image.wind_dir":
                    entity["rotation"] = mock_sensor_data[ent_id]
                else:
                    entity["file"] = mock_sensor_data[ent_id]
            else:
                entity["value"] = mock_sensor_data[ent_id]
    # ---------------------------
    
    # 4. Generate the image
    logger.info("Generating layout image...")
    try:
        test_image = renderer.generate_image(config)
        test_image.save("test_layout.png")
        test_image.show()
        logger.info("Picture generated successfully: test_layout.png")
    except Exception as e:
        logger.critical(f"Failed to generate or save image: {e}")
        
        