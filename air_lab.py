import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import queue
import time
import csv

from collections import deque

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


BAUDRATE = 115200
MAX_POINTS = 100

arduino = None
running = False
serial_thread = None

serial_lock = threading.Lock()
data_queue = queue.Queue()

# Datos recibidos
temperatures = deque(maxlen=MAX_POINTS)
times = deque(maxlen=MAX_POINTS)

temperature = None
setpoint = None
fan_value = 0
heater_state = False
pressure = 0
air_velocity = 0
air_flow = 0

start_time = time.time()

fan_job = None
temp_job = None



BG = "#151923"
PANEL = "#202838"
PANEL2 = "#283449"

WHITE = "#F1F5F9"
GRAY = "#AAB5C5"

BLUE = "#38BDF8"
GREEN = "#22C55E"
RED = "#EF4444"
ORANGE = "#F59E0B"

root = tk.Tk()

root.title("AIR LAB | Sistema de control")
root.geometry("1150x850")
root.minsize(950, 700)
root.configure(bg=BG)

style = ttk.Style()
style.theme_use("clam")

style.configure(
    "TCombobox",
    fieldbackground=PANEL,
    background=PANEL2,
    foreground=WHITE
)


def available_ports():

    ports = serial.tools.list_ports.comports()

    return [
        f"{port.device} - {port.description}"
        for port in ports
    ]


def refresh_ports():

    port_list = available_ports()

    port_combo["values"] = port_list

    if port_list:
        port_combo.current(0)
    else:
        port_combo.set("")


def send_command(command):

    global arduino

    if arduino is None or not arduino.is_open:
        set_message("Arduino no esta conectado.", RED)
        return False

    try:

        with serial_lock:

            arduino.write(
                (command + "\n").encode("utf-8")
            )

        return True

    except (serial.SerialException, OSError) as error:

        set_message(
            f"Error de comunicacion: {error}",
            RED
        )

        return False


def serial_reader():

    global running

    while running:

        try:

            if arduino is None or not arduino.is_open:
                break

            line = arduino.readline().decode(
                "utf-8",
                errors="ignore"
            ).strip()

            if line:
                data_queue.put(line)

        except (serial.SerialException, OSError) as error:

            data_queue.put(f"ERROR_SERIAL:{error}")
            break


def connect_arduino():

    global arduino
    global running
    global serial_thread

    if arduino is not None and arduino.is_open:
        disconnect_arduino()
        return

    selected = port_combo.get()

    if not selected:

        messagebox.showwarning(
            "AIR LAB",
            "Selecciona un puerto COM."
        )

        return

    port = selected.split(" - ")[0]

    try:

        arduino = serial.Serial(
            port,
            BAUDRATE,
            timeout=0.2
        )

        # El Mega puede reiniciarse al abrir el puerto
        time.sleep(2)

        arduino.reset_input_buffer()

        running = True

        serial_thread = threading.Thread(
            target=serial_reader,
            daemon=True
        )

        serial_thread.start()

        connect_button.config(
            text="DESCONECTAR",
            bg=RED
        )

        connection_label.config(
            text=f"● CONECTADO: {port}",
            fg=GREEN
        )

        set_message(
            "Conexion establecida. Activando control PC...",
            GREEN
        )

        # Activar control desde la computadora
        send_command("PC")

        # Asegurar calentador apagado
        send_command("HEATER OFF")

    except (serial.SerialException, OSError) as error:

        arduino = None

        messagebox.showerror(
            "Error de conexion",
            str(error)
        )


def disconnect_arduino():

    global arduino, running

    running = False

    if arduino is not None:

        try:

            if arduino.is_open:

                # Solicitar ventilador al 0% y calentador apagado
                with serial_lock:

                    arduino.write(b"FAN 0\n")
                    arduino.write(b"HEATER OFF\n")

                time.sleep(0.1)

                arduino.close()

        except (serial.SerialException, OSError):
            pass

    arduino = None

    connect_button.config(
        text="CONECTAR",
        bg=GREEN
    )

    connection_label.config(
        text="● DESCONECTADO",
        fg=RED
    )

    set_message(
        "Arduino desconectado.",
        ORANGE
    )



def process_serial_data(line):

    global temperature
    global setpoint
    global fan_value
    global heater_state
    global pressure
    global air_velocity
    global air_flow

    # Ignorar mensajes de confirmacion
    if line.startswith("ERROR_SERIAL:"):

        set_message(line, RED)
        return

    if line.startswith("CONTROL PC"):
        set_message(line, GREEN)
        return

    if line.startswith("CONTROL POTENCIOMETROS"):
        set_message(line, ORANGE)
        return

    if line.startswith("VENTILADOR"):
        set_message(line, BLUE)
        return

    if line.startswith("TEMPERATURA OBJETIVO"):
        set_message(line, BLUE)
        return

    # Leer los ocho valores CSV
    try:

        values = next(csv.reader([line]))

        if len(values) != 8:
            return

        tiempo = float(values[0])
        ventilador = float(values[1])
        temp = float(values[2])
        consigna = float(values[3])
        calentador = int(float(values[4]))
        dp = float(values[5])
        velocidad = float(values[6])
        caudal = float(values[7])

    except (ValueError, csv.Error, StopIteration):

        # Ignorar encabezados y mensajes que no sean CSV
        return

    # Guardar mediciones
    temperature = temp
    fan_value = ventilador
    setpoint = consigna
    heater_state = bool(calentador)

    pressure = dp
    air_velocity = velocidad
    air_flow = caudal

    # Actualizar etiquetas
    temperature_label.config(
        text=f"{temperature:.2f} °C"
    )

    setpoint_label.config(
        text=f"{setpoint:.1f} °C"
    )

    fan_label.config(
        text=f"{fan_value:.0f}%"
    )

    heater_status.config(
        text="ENCENDIDO" if heater_state else "APAGADO",
        fg=GREEN if heater_state else GRAY
    )

    pressure_label.config(
        text=f"{pressure:.2f} Pa"
    )

    velocity_label.config(
        text=f"{air_velocity:.2f} m/s"
    )

    flow_label.config(
        text=f"{air_flow:.2f} m³/h"
    )

    # Guardar temperatura para la grafica
    times.append(tiempo)
    temperatures.append(temperature)

    set_message(
        "Datos recibidos correctamente desde Arduino.",
        GREEN
    )


def read_queue():

    while not data_queue.empty():

        try:

            line = data_queue.get_nowait()

            process_serial_data(line)

        except queue.Empty:
            break

    root.after(100, read_queue)



def set_message(message, color=WHITE):

    message_label.config(
        text=message,
        fg=color
    )


def update_fan(value):

    global fan_value, fan_job

    fan_value = int(float(value))

    fan_label.config(
        text=f"{fan_value}%"
    )

    if fan_job is not None:
        root.after_cancel(fan_job)

    fan_job = root.after(
        300,
        lambda: send_command(
            f"FAN {fan_value}"
        )
    )


def fan_off():

    fan_scale.set(0)
    send_command("FAN 0")



def update_setpoint(value):

    global temp_job

    desired_temp = float(value)

    setpoint_label.config(
        text=f"{desired_temp:.1f} °C"
    )

    if temp_job is not None:
        root.after_cancel(temp_job)

    temp_job = root.after(
        300,
        lambda: send_command(
            f"TEMP {desired_temp:.1f}"
        )
    )


def consult_temperature():

    if temperature is None:

        set_message(
            "Esperando primera lectura de temperatura...",
            ORANGE
        )

    else:

        set_message(
            f"Ultima temperatura recibida: {temperature:.2f} °C",
            GREEN
        )



def heater_off():

    send_command("HEATER OFF")

    set_message(
        "Se solicito apagar el calentador.",
        ORANGE
    )



def activate_pc_control():

    send_command("PC")

    set_message(
        "Control desde computadora solicitado.",
        GREEN
    )


def activate_pot_control():

    send_command("POT")

    set_message(
        "Control mediante potenciometros solicitado.",
        ORANGE
    )



def update_graph():

    graph_line.set_data(
        list(times),
        list(temperatures)
    )

    if len(times) > 1:

        ax.set_xlim(
            times[0],
            max(times[-1] + 1, times[0] + 10)
        )

        low = min(temperatures)
        high = max(temperatures)

        if low == high:
            low -= 1
            high += 1

        margin = (high - low) * 0.15

        ax.set_ylim(
            low - margin,
            high + margin
        )

    canvas.draw_idle()

    root.after(1000, update_graph)


header = tk.Frame(
    root,
    bg=BG
)

header.pack(
    fill="x",
    padx=25,
    pady=15
)

tk.Label(
    header,
    text="AIR LAB",
    font=("Arial", 27, "bold"),
    bg=BG,
    fg=WHITE
).pack(side="left")

tk.Label(
    header,
    text="SISTEMA DE CONTROL Y MONITOREO",
    font=("Arial", 10),
    bg=BG,
    fg=GRAY
).pack(
    side="left",
    padx=20,
    pady=12
)



connection_panel = tk.Frame(
    root,
    bg=PANEL,
    padx=15,
    pady=12
)

connection_panel.pack(
    fill="x",
    padx=25,
    pady=5
)

connection_label = tk.Label(
    connection_panel,
    text="● DESCONECTADO",
    font=("Arial", 11, "bold"),
    bg=PANEL,
    fg=RED
)

connection_label.pack(side="left")

port_combo = ttk.Combobox(
    connection_panel,
    width=28,
    state="readonly"
)

port_combo.pack(
    side="left",
    padx=15
)

tk.Button(
    connection_panel,
    text="ACTUALIZAR PUERTOS",
    command=refresh_ports,
    bg=PANEL2,
    fg=WHITE,
    relief="flat",
    padx=10,
    pady=7
).pack(side="left", padx=5)

connect_button = tk.Button(
    connection_panel,
    text="CONECTAR",
    command=connect_arduino,
    bg=GREEN,
    fg="#101820",
    font=("Arial", 10, "bold"),
    relief="flat",
    padx=15,
    pady=7
)

connect_button.pack(side="right")



main_panel = tk.Frame(
    root,
    bg=BG
)

main_panel.pack(
    fill="both",
    expand=True,
    padx=25,
    pady=10
)

temp_panel = tk.Frame(
    main_panel,
    bg=PANEL,
    padx=15,
    pady=12
)

temp_panel.pack(
    fill="x",
    pady=7
)

tk.Label(
    temp_panel,
    text="TEMPERATURA ACTUAL",
    font=("Arial", 12, "bold"),
    bg=PANEL,
    fg=GRAY
).pack()

temperature_label = tk.Label(
    temp_panel,
    text="-- °C",
    font=("Arial", 32, "bold"),
    bg=PANEL,
    fg=BLUE
)

temperature_label.pack(pady=5)

tk.Label(
    temp_panel,
    text="ULTIMA TEMPERATURA RECIBIDA",
    font=("Arial", 9),
    bg=PANEL,
    fg=GRAY
).pack()

tk.Button(
    temp_panel,
    text="CONSULTAR ULTIMA LECTURA",
    command=consult_temperature,
    bg=PANEL2,
    fg=WHITE,
    relief="flat",
    padx=12,
    pady=7
).pack(pady=7)



metrics_panel = tk.Frame(
    main_panel,
    bg=BG
)

metrics_panel.pack(
    fill="x",
    pady=7
)


def create_metric(parent, title, initial_value):

    panel = tk.Frame(
        parent,
        bg=PANEL,
        padx=10,
        pady=12
    )

    panel.pack(
        side="left",
        fill="both",
        expand=True,
        padx=4
    )

    tk.Label(
        panel,
        text=title,
        font=("Arial", 10, "bold"),
        bg=PANEL,
        fg=GRAY
    ).pack()

    label = tk.Label(
        panel,
        text=initial_value,
        font=("Arial", 18, "bold"),
        bg=PANEL,
        fg=BLUE
    )

    label.pack(pady=6)

    return label


pressure_label = create_metric(
    metrics_panel,
    "PRESION DIFERENCIAL",
    "-- Pa"
)

velocity_label = create_metric(
    metrics_panel,
    "VELOCIDAD DEL AIRE",
    "-- m/s"
)

flow_label = create_metric(
    metrics_panel,
    "CAUDAL",
    "-- m³/h"
)


controls = tk.Frame(
    main_panel,
    bg=BG
)

controls.pack(
    fill="x",
    pady=7
)



fan_panel = tk.Frame(
    controls,
    bg=PANEL,
    padx=15,
    pady=12
)

fan_panel.pack(
    side="left",
    fill="both",
    expand=True,
    padx=(0, 5)
)

tk.Label(
    fan_panel,
    text="VENTILADOR",
    font=("Arial", 13, "bold"),
    bg=PANEL,
    fg=WHITE
).pack()

fan_label = tk.Label(
    fan_panel,
    text="0%",
    font=("Arial", 24, "bold"),
    bg=PANEL,
    fg=BLUE
)

fan_label.pack(pady=5)

fan_scale = tk.Scale(
    fan_panel,
    from_=0,
    to=100,
    orient="horizontal",
    command=update_fan,
    bg=PANEL,
    fg=WHITE,
    troughcolor=PANEL2,
    highlightthickness=0,
    length=280
)

fan_scale.pack(pady=5)

tk.Button(
    fan_panel,
    text="APAGAR VENTILADOR",
    command=fan_off,
    bg=RED,
    fg=WHITE,
    relief="flat",
    padx=12,
    pady=7
).pack(pady=5)



setpoint_panel = tk.Frame(
    controls,
    bg=PANEL,
    padx=15,
    pady=12
)

setpoint_panel.pack(
    side="left",
    fill="both",
    expand=True,
    padx=(5, 0)
)

tk.Label(
    setpoint_panel,
    text="TEMPERATURA OBJETIVO",
    font=("Arial", 13, "bold"),
    bg=PANEL,
    fg=WHITE
).pack()

setpoint_label = tk.Label(
    setpoint_panel,
    text="25.0 °C",
    font=("Arial", 24, "bold"),
    bg=PANEL,
    fg=ORANGE
)

setpoint_label.pack(pady=5)

temp_scale = tk.Scale(
    setpoint_panel,
    from_=25,
    to=80,
    resolution=1,
    orient="horizontal",
    command=update_setpoint,
    bg=PANEL,
    fg=WHITE,
    troughcolor=PANEL2,
    highlightthickness=0,
    length=280
)

temp_scale.set(25)
temp_scale.pack(pady=5)

tk.Label(
    setpoint_panel,
    text="Rango permitido: 25 a 80 °C",
    font=("Arial", 9),
    bg=PANEL,
    fg=GRAY
).pack(pady=5)



heater_panel = tk.Frame(
    main_panel,
    bg=PANEL,
    padx=15,
    pady=12
)

heater_panel.pack(
    fill="x",
    pady=7
)

tk.Label(
    heater_panel,
    text="CALENTADOR PTC",
    font=("Arial", 12, "bold"),
    bg=PANEL,
    fg=WHITE
).pack(side="left", padx=10)

heater_status = tk.Label(
    heater_panel,
    text="APAGADO",
    font=("Arial", 11, "bold"),
    bg=PANEL,
    fg=GRAY
)

heater_status.pack(side="left", padx=15)

tk.Button(
    heater_panel,
    text="APAGAR CALENTADOR",
    command=heater_off,
    bg=RED,
    fg=WHITE,
    relief="flat",
    padx=12,
    pady=7
).pack(side="right", padx=5)

tk.Label(
    heater_panel,
    text="Encendido remoto bloqueado durante las pruebas de seguridad.",
    font=("Arial", 9),
    bg=PANEL,
    fg=ORANGE
).pack(side="right", padx=10)



mode_panel = tk.Frame(
    main_panel,
    bg=PANEL,
    padx=15,
    pady=12
)

mode_panel.pack(
    fill="x",
    pady=7
)

tk.Label(
    mode_panel,
    text="MODALIDAD DE CONTROL:",
    font=("Arial", 10, "bold"),
    bg=PANEL,
    fg=WHITE
).pack(side="left", padx=10)

tk.Button(
    mode_panel,
    text="CONTROL DESDE PC",
    command=activate_pc_control,
    bg=GREEN,
    fg="#101820",
    relief="flat",
    padx=12,
    pady=7
).pack(side="left", padx=5)

tk.Button(
    mode_panel,
    text="CONTROL POR POTENCIOMETROS",
    command=activate_pot_control,
    bg=PANEL2,
    fg=WHITE,
    relief="flat",
    padx=12,
    pady=7
).pack(side="left", padx=5)


graph_panel = tk.Frame(
    main_panel,
    bg=PANEL,
    padx=12,
    pady=12
)

graph_panel.pack(
    fill="both",
    expand=True,
    pady=7
)

fig = Figure(
    figsize=(8, 2.4),
    dpi=100,
    facecolor=PANEL
)

ax = fig.add_subplot(111)

ax.set_title(
    "TEMPERATURA EN TIEMPO REAL",
    color=WHITE
)

ax.set_xlabel(
    "Tiempo (s)",
    color=GRAY
)

ax.set_ylabel(
    "Temperatura (°C)",
    color=GRAY
)

ax.set_facecolor(PANEL)
ax.tick_params(colors=GRAY)

ax.grid(
    True,
    alpha=0.2
)

for spine in ax.spines.values():
    spine.set_color(GRAY)

graph_line, = ax.plot(
    [],
    [],
    color=BLUE,
    linewidth=2
)

canvas = FigureCanvasTkAgg(
    fig,
    master=graph_panel
)

canvas.get_tk_widget().pack(
    fill="both",
    expand=True
)



footer = tk.Frame(
    root,
    bg=PANEL,
    padx=15,
    pady=10
)

footer.pack(
    fill="x",
    padx=25,
    pady=(0, 12)
)

tk.Label(
    footer,
    text="ESTADO DEL SISTEMA:",
    bg=PANEL,
    fg=GRAY,
    font=("Arial", 9, "bold")
).pack(side="left")

message_label = tk.Label(
    footer,
    text="Esperando conexion con Arduino...",
    bg=PANEL,
    fg=ORANGE,
    font=("Arial", 9)
)

message_label.pack(
    side="left",
    padx=10
)



def close_app():

    global running, arduino

    running = False

    if arduino is not None:

        try:

            if arduino.is_open:

                with serial_lock:

                    arduino.write(b"FAN 0\n")
                    arduino.write(b"HEATER OFF\n")

                time.sleep(0.1)

                arduino.close()

        except (serial.SerialException, OSError):
            pass

    root.destroy()


root.protocol(
    "WM_DELETE_WINDOW",
    close_app
)



refresh_ports()

read_queue()

update_graph()

root.mainloop()
