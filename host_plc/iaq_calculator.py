import math

class IAQCalculator:
    def __init__(self):
        # The highest gas resistance ever seen (represents the cleanest air)
        self.gas_baseline = None
        
    def calculate(self, temp: float, hum: float, gas_res: float) -> dict:
        # 1. Establish or dynamically update the clean air baseline
        if self.gas_baseline is None or gas_res > self.gas_baseline:
            self.gas_baseline = gas_res
            
        # 2. Calculate Gas Score (0% to 100%)
        gas_score = (gas_res / self.gas_baseline) * 100.0
        
        # 3. Calculate Humidity Score (0% to 100%)
        # Optimal indoor humidity is around 40%. 
        # We penalize the score as it deviates from 40%.
        hum_offset = abs(hum - 40.0)
        # 1.5 multiplier means every 1% deviation drops the hum_score by 1.5%
        hum_score = max(0.0, 100.0 - (hum_offset * 1.5))
        
        # 4. Combine scores (Gas has 75% weight, Humidity 25%)
        aq_percent = (gas_score * 0.75) + (hum_score * 0.25)
        # Ensure the final value stays strictly between 0 and 100
        aq_percent = max(0.0, min(100.0, aq_percent))
        
        # 5. Estimate equivalent CO2 (eCO2) in ppm based on the combined AQ
        eco2 = 400.0 + ((100.0 - aq_percent) * 16.0)
        
        # 6. Estimate VOC equivalent in ppb based on the combined AQ
        # When AQ is 100%, VOC is 0 ppb. Scales up to ~5000 ppb at 0% AQ.
        voc = (100.0 - aq_percent) * 50.0
        
        return {
            "sensor.bme688_temp": round(temp, 1),
            "sensor.bme688_rh": round(hum, 1),
            "sensor.bme688_aq": round(aq_percent, 1),
            "sensor.bme688_co2": int(eco2),
            "sensor.bme688_voc": int(voc)
        }