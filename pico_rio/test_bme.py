from machine import Pin, I2C
import bme688 as BME680
import time

# Alustetaan täsmälleen samat pinnit joita käytät
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)

print("Skannataan I2C-väylä...")
laitteet = i2c.scan()

if not laitteet:
    print("Ei löytynyt mitään! Vika on johdoissa.")
else:
    for laite in laitteet:
        print("Laite löytyi osoitteesta: 0x{:02X}".format(laite))

# Alusta I2C0 käyttäen pinnejä GP4 (SDA) ja GP5 (SCL)
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)

try:
    # Ohitetaan ajurin I2C1-oletus syöttämällä meidän oma i2c_device
    sensor = BME680.BME680(i2c_device=i2c)
    
    print("BME680 kytketty onnistuneesti!")
    print("----------------------------")
    
    # Kuumennetaan kaasuanturia hieman (suositeltu alkuasetus)
    sensor.set_gas_heater_temperature(320)
    sensor.set_gas_heater_duration(150)
    sensor.select_gas_heater_profile(0)
    
    # Luetaan arvot 5 kertaa sekunnin välein
    for _ in range(5):
        if sensor.get_sensor_data():
            print("Lämpötila: {:.2f} °C".format(sensor.data.temperature))
            print("Ilmankosteus: {:.2f} %".format(sensor.data.humidity))
            print("Ilmanpaine: {:.2f} hPa".format(sensor.data.pressure))
            if sensor.data.heat_stable:
                print("Kaasunvastus: {:.0f} Ohmia".format(sensor.data.gas_resistance))
            print("----------------------------")
        time.sleep(1)

except Exception as e:
    print("Virhe:", e)