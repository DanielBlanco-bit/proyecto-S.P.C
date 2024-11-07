# importamos librerias a utilizar durante el transcurso del programa
import socket
from max30102 import MAX30102, MAX30105_PULSE_AMP_MEDIUM
import _thread
from machine import sleep, SoftI2C, Pin, reset, Timer
from utime import ticks_diff, ticks_us
import json
import network
import ujson
import ure
import time
import ssd1306

# designamos nuestros perifericos 
boton_server = Pin(18, Pin.IN, Pin.PULL_UP)
led = Pin(12, Pin.OUT)

# variables a utilizar
MAX_HISTORY = 32
history = []
beats_history = []
beat = False
beats = 0

wifi_ip = ''
wifi_ok = 0
sensor_detect = False

# iniciamos protocolo I2C
i2c = SoftI2C(sda=Pin(21), scl=Pin(22), freq=400000)

sensor = MAX30102(i2c=i2c)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# limpiamos la pantalla oled para que inicie en negro
oled.fill(0)
oled.show()

# mini presentacion del grupo en el oled
oled.text('Proyecto General', 0, 20)
oled.text('Electronica', 20, 30)
oled.text('6to 6ta', 30, 40)
oled.show()
time.sleep(4)

# hilo 1, corrobora que haya conexion wifi cada cierto determinado tiempo, caso contrario a que no haya intenta la reconexion
def hilo1():
    global wifi_ok
    global wifi_ip
    
    wifi_ssid, wifi_password = cargar_config()
    
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)
        wlan.active(True)
    except OSError as err:
                print(f'Error : {err.errno}')
    while True:
        if not wlan.isconnected():
            print('Conectando...')
            oled.fill(0)
            oled.text('Conectando...', 0, 0)
            oled.show()
            time.sleep(1)
            try:
                wlan.connect(wifi_ssid,wifi_password)
            except OSError as err:
                print(f'Error : {err.errno}')
            print(wlan.status())
            if wlan.status() == 1001:
                pass

            time.sleep(1)
            wifi_ok=0
        else:
            wifi_ok=1
            Wifi_data=wlan
            print(f'Wifi conectado en {wlan.ifconfig()}')
            wifi_ip = wlan.ifconfig()[0]
            time.sleep(10)
    
# funcion para el max30102, utilizada para la deteccion y calibracion de las pulsaciones    
def hilo2():
    while True:
        global history
        global beats_history
        global beat
        global beats
        global t_start

        sensor.check()
        
        # Check if the storage contains available samples
        if sensor.available():
            # Access the storage FIFO and gather the readings (integers)
            red_reading = sensor.pop_red_from_storage()
            ir_reading = sensor.pop_ir_from_storage()
            
            value = red_reading
            history.append(value)
            # Get the tail, up to MAX_HISTORY length
            history = history[-MAX_HISTORY:]
            minima = 0
            maxima = 0
            threshold_on = 0
            threshold_off = 0

            minima, maxima = min(history), max(history)

            threshold_on = (minima + maxima * 3) // 4   # 3/4
            threshold_off = (minima + maxima) // 2      # 1/2
              
            if value > 1000:
                if not beat and value > threshold_on:
                    beat = True                    
                    led.on()
                    t_us = ticks_diff(ticks_us(), t_start)
                    t_s = t_us/1000000
                    f = 1/t_s
                
                    bpm = f * 60
                    
                    if bpm < 500:
                        t_start = ticks_us()
                        beats_history.append(bpm)                    
                        beats_history = beats_history[-MAX_HISTORY:] 
                        beats = round(sum(beats_history)/len(beats_history) ,2)  
                                        
                if beat and value< threshold_off:
                    beat = False
                    led.off()
                
            else:
                led.off()
                beats = 0.00
       
# guardamos datos en config.json (wifi ssid, wifi password)
def guardar_config(wifi_ssid, wifi_password):
    config_data = {
        'wifi_ssid': wifi_ssid,
        'wifi_password': wifi_password
        }
    with open('config.json', 'w') as f:
        ujson.dump(config_data, f)

# cargamos datos de config.json (wifi ssid, wifi password) 
def cargar_config():
    
    try:
        with open('config.json', 'r') as f:
            config_data = ujson.load(f)
            print('Configuración cargada:', config_data)
            return config_data.get('wifi_ssid', ''), config_data.get('wifi_password', '')
    except (OSError, ValueError) as e:
        print('Error al cargar configuración:', e)
        print('Creando nuevo archivo de configuración...')
        guardar_config('', '')  # Crear un nuevo archivo de configuración
        return '', ''

# funcion dedicada a determinar que tipo de archivo pide el "GET" del cliente
def get_content_type(filename):
    if filename.endswith('.html'):
        return 'text/html'
    elif filename.endswith('.css'):
        return 'text/css'
    elif filename.endswith('.png'):
        return 'image/png'
    else:
        return 'application/octet-stream'

# web server dedicado a el protocolo de wifi
def wifi_config(s):
    
    def replace_values(content, config):
        replacements = [
            ('wifi_value', config[0]),
            ('wifipass_value', config[1])
        ]
        for old, new in replacements:
            content = content.replace(old, new)
        return content
    
    config = cargar_config()
    while True:
        conn, addr = s.accept()
        print('Nueva conexion desde {}'.format(addr))
        request = conn.recv(1024)
        request = str(request)
        print(request)
        
        filename = request.split()[1]
        if filename == '/':
            filename = '/index.html'
        
        if request.find('POST /config') != -1:
            match = ure.search(r"wifi_ssid=([\w.+\s-]+)&wifi_password=([\w.+-]+)", request)
            print(f'match : {match}')
            if match:
                print("match")
                wifi_ssid = match.group(1)
                wifi_password = match.group(2)
                print(f'WIFI SSID : {wifi_ssid}\nWIFI PASSWORD : {wifi_password}')
                guardar_config(wifi_ssid, wifi_password)
                reset()
        try:
            with open(filename[1:], 'rb') as file:
                content = file.read()
            content_type = get_content_type(filename)
            
            if filename.endswith('.html'):
                content = content.decode('utf-8')
                content = replace_values(content, config)
                content = content.encode('utf-8')
            
            response = 'HTTP/1.1 200 OK\r\nContent-Type: {}\r\n\r\n'.format(content_type)
            conn.send(response.encode())
            conn.sendall(content)
        except OSError:
            response = 'HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n'
            conn.send(response.encode())
            conn.sendall(b'<html><body><h1>404 Not Found</h1></body></html>')
            
        conn.close()

# codigo HTML+CSS para el web server de lecutura del sensor
def web_page(): 
    html = """
    <head>
    <title>Proyecto General</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    <link rel="icon" href="data:,">
    <style>
        meter {
            -webkit-writing-mode: horizontal-tb !important;
            appearance: auto;
            box-sizing: border-box;
            display: inline-block;
            height: 3em;
            width: 13em;
            vertical-align: -1.0em;
            -webkit-user-modify: read-only !important;
        }
        html {
            font-family: Helvetica;
            display: inline-block;
            margin: 0px auto;
            text-align: center;
        }
        h1 {
            color: #0F3376;
            padding: 2vh;
        }
        p {
            font-size: 1.5rem;
        }
        table {
            margin: auto;
        }
        td {
            padding: 3px;           
        }
        .Button {
            border-radius: 31px;
            display: inline-block;
            cursor: pointer;
            color: #ffffff;
            font-family: Arial;
            font-size: 10px;
            font-weight: bold;
            font-style: italic;
            padding: 4px 5px;
            text-decoration: none;
        }
        .ButtonR {
            background-color: #ec5449;
            border: 3px solid #991f1f;
            text-shadow: 0px 2px 2px #47231e;
        }
        .ButtonR:hover {
            background-color: #f54a16;
        }
        .Button:active {
            position: relative;
            top: 1px;
        }
        .ButtonG {
            background-color: #49ece4;
            border: 3px solid #1f8b99;
            text-shadow: 0px 2px 2px #1e3b47;
        }
        .ButtonG:hover {
            background-color: #16b6f5;
        }
        .ButtonB {
            background-color: #4974ec;
            border: 3px solid #1f3599;
            text-shadow: 0px 2px 2px #1e2447;
        }
        .ButtonB:hover {
            background-color: #165df5;
        }
    </style>
</head>
<body>
    <h1>Proyecto General : S.P.C</h1>
    <p>Sensor MAX30102</p>
    <table>
        <tbody>
            <tr>
                <td>
                    <p class="center">
                        <a href="/update"><button class="ButtonR Button">
                                <i class="fa fa-heartbeat fa-2x" aria-hidden="true"></i> BPM
                            </button></a>
                    </p>
                </td>
                <td>
                    <strong> """+ str(beats) +""" </strong>                   
                </td>
                <td>                    
                    <meter id="fuel" min="0" max="200" low="59" high="100" optimum="60" value=" @@""" + str(beats) +""" @@">
                        at 50/100
                    </meter>
                </td>
            </tr>
            <tr>
                <td>
                    <p><a href="/update"><button class="ButtonG Button">
                                <i class="fa fa-thermometer-quarter fa-2x" aria-hidden="true"></i> Temp.
                            </button></a></p>
                </td>
                <td>
                    <strong> """+ str(round(sensor.read_temperature(),2)) +""" &#176;C</strong>                   
                </td>
                <td>                    
                    <meter id="fuel" min="0" max="100" low="20" high="40" optimum="30" value=" @@""" + str(round(sensor.read_temperature(),2)) +""" @@">
                        at 50/100
                    </meter>
                </td>
            </tr>            
        </tbody>
    </table>
</body>
<script>
    setInterval(updateValues, 2000);
    function updateValues() {
        location.reload(); 
    }
</script>
</html> 
   
    """
    return html

# web server para la lectura del sensor    
def webserver_sensor(s):
    print("inicio web server")
    oled.fill(0)
    oled.text('Webserver', 20, 0)
    oled.text('Iniciado', 20, 10)
    oled.text('Conectate a ip :', 0, 20)
    oled.text(wifi_ip, 10, 30)
    oled.show()
    time.sleep(5)
    while True:
        try:
            conn, addr = s.accept()
            print('Got a connection from %s' % str(addr))
            request = conn.recv(1024)
            request = str(request)   
            update = request.find('/update')        
            
            if update == 6:
                print('update') 
                
            response = web_page()
            response = response.replace(" @@","")
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')
            conn.sendall(response)
            conn.close()
        except Exception as e:
            print(e)
        time.sleep(1)

# inicia un web server y pregunta si es para la lectura del sensor o para el protocolo de wifi            
def webserver(protocolo):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(1)
    if protocolo == 1:
        webserver_sensor(s)
    else:
        #web server para cargar datos de la red wifi
        wifi_config(s)

# Inicia el HOST WIFI para el protocolo wifi
def setup_ap():
    ap = network.WLAN(network.AP_IF) 
    ap.active(True)
    ap.config(ssid='Proyecto General', security=network.AUTH_WPA2_PSK, key='94528301')
    while not ap.active():
        pass
    print('Red WiFi "Proyecto General" activada')
    print('IP del servidor:', ap.ifconfig()[0])
    return ap.ifconfig()[0]

# pregunta si el sensor esta correctamente conectado o si no es el modelo de sensor necesitado
if sensor.i2c_address not in i2c.scan():
    print("No se a detectado un sensor en el puerto I2C")
    sensor_detect = False
    oled.fill(0)
    oled.text('No se detecto un dispositivo', 0, 0)
    oled.text('verifique la conexion', 0, 10)
    oled.show()
    time.sleep(2)   
elif not (sensor.check_part_id()):
    print("el puerto I2C no reconoce un sensor MAX30102 o MAX30105.")
    sensor_detect = False
    oled.fill(0)
    oled.text('No se reconoce un MAX30102', 0, 0)
    oled.text('verifique la conexion', 0, 10)
    oled.show()
    time.sleep(2)
else:
    print("Sensor conectado y reorganizado.")
    sensor_detect = True
    oled.fill(0)
    oled.text('Sensor', 0, 0)
    oled.text('Conectado', 0, 10)
    oled.show()
    time.sleep(2)

# configuramos el sensor para una correcta deteccion    
sensor.setup_sensor()
sensor.set_sample_rate(400)
sensor.set_fifo_average(8)
sensor.set_active_leds_amplitude(MAX30105_PULSE_AMP_MEDIUM)
sensor.set_led_mode(2)
sleep(1)

t_start = ticks_us()

# preguntamos si el protocolo de web server wifi se esta ejecutando
if boton_server.value() == 0:
    ip = setup_ap()
    if not ip == None:
        print('Conecta tu dispositivo a la red "Proyecto General" e introduce la contraseña')
        print('luego, abre el navegador y visita http://{}'.format(ip))
        oled.fill(0)
        oled.text('webserver wifi', 0, 0)
        oled.text('iniciado', 0, 10)
        oled.text('Conectate', 0, 20)
        oled.text('a la red wifi', 0, 30)
        oled.text('luego ingrese a', 0, 40)
        oled.text(f'{ip}', 0, 50)
        oled.show()
        webserver(0)
    else:
        print('No se pudo establecer el puerto de comunicacion')
 
# inciamos hilo1    
_thread.start_new_thread(hilo1, ())    
    
# bucle principal    
while True:
    # preguntamos si hay conexion wifi
    if wifi_ok:
        oled.fill(0)
        oled.text('Conexion WIFI', 0, 0)
        oled.text('EXITOSA', 0, 10)
        oled.show()
        time.sleep(4)
        print("Inicio web")
        # iniciamos el hilo2
        _thread.start_new_thread(hilo2, ())
        webserver(1)
    time.sleep(0.1)
