import time
import numpy as np
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_motorkit import MotorKit
from adafruit_motor import stepper
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.ndimage import gaussian_filter
from threading import Thread, Event
import board
import subprocess

# Initialize the MotorKit instance for the bonnet
kit1 = MotorKit(address=0x60)  # First bonnet (default address)
kit2 = MotorKit(address=0x61)  # Second bonnet (different address)

# Define stepper motors 
motor_x = kit1.stepper1  # X-axis
motor_y = kit1.stepper2  # Y-axis
motor_z = kit2.stepper1  # Z-axis

# Define movement parameters
steps_per_mm = 200 / (2 * 3.14 * 10)  # Steps per mm (steps/revolution divided by mm/revolution)
travel_distance_x = 130  # mm for x-axis (total travel distance minus (end brackets + length of stage))
travel_distance_y = 130  # mm for y-axis (total travel distance minus (end brackets + length of stage))
step_increment_y = 10  # 1 cm increment for y-axis
steps_per_move_x = int(travel_distance_x * steps_per_mm)
steps_per_increment_y = int(step_increment_y * steps_per_mm)
total_increments_y = int(travel_distance_y / step_increment_y)

# Initialize ADS1115 ADC
i2c = board.I2C()
ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, ADS.P0)

# Global variables to hold data and control acquisition
data = []
stop_event = Event()

def acquire_data(sampling_rate):
    global data
    data = []
    stop_event.clear()
    interval = 1 / sampling_rate
    while not stop_event.is_set():
        voltage = chan.voltage
        data.append(voltage)
        time.sleep(interval)

# Function to move motor a given number of steps
def move_motor(motor, steps, direction):
    for _ in range(steps):
        motor.onestep(direction=direction)
        time.sleep(0.002)  # Adjust delay to increase/decrease speed of scan

# Function to move in a zig-zag pattern and acquire data simultaneously
def move_and_acquire():
    global data
    data = []
    stop_event.clear()
    interval = 1 / sampling_rate

    y_increment_count = 0
    for i in range(total_increments_y):
        # Move right (positive x direction) and acquire data
        for _ in range(steps_per_move_x):
            move_motor(motor_x, 1, stepper.FORWARD)
            voltage = chan.voltage
            data.append(voltage)
            time.sleep(interval)
        
        move_motor(motor_y, steps_per_increment_y, stepper.FORWARD)  # Move up (positive y direction)
        y_increment_count += 1
        if y_increment_count >= total_increments_y:
            break

        # Move left (negative x direction) and acquire data
        for _ in range(steps_per_move_x):
            move_motor(motor_x, 1, stepper.BACKWARD)
            voltage = chan.voltage
            data.append(voltage)
            time.sleep(interval)
        
        move_motor(motor_y, steps_per_increment_y, stepper.FORWARD)  # Move up (positive y direction)
        y_increment_count += 1
        if y_increment_count >= total_increments_y:
            break
    
    stop_event.set()

# Function to generate heat map
def generate_heatmap(data, y_steps):
    samples_per_row = len(data) // y_steps

    # Create matrix and ensure all rows are of equal length
    data_matrix = []
    row_data = []
    forward = True

    for i in range(len(data)):
        row_data.append(data[i])
        if len(row_data) == samples_per_row:
            if not forward:
                row_data.reverse()  # Reverse row for zigzag pattern
            data_matrix.append(row_data)
            row_data = []
            forward = not forward  # Toggle direction

    if row_data:
        if not forward:
            row_data.reverse()
        while len(row_data) < samples_per_row:
            row_data.append(np.nan)  # Pad with NaNs to maintain equal length
        data_matrix.append(row_data)

    data_matrix = np.array(data_matrix)
    data_matrix = gaussian_filter(data_matrix, sigma=1)

    x_labels = [f"{x:.1f}" for x in np.linspace(0, travel_distance_x, samples_per_row)]
    y_labels = [f"{y:.1f}" for y in np.linspace(0, travel_distance_y, len(data_matrix))]

    plt.figure(figsize=(10, 8))
    sns.heatmap(data_matrix, cmap="coolwarm", annot=True, fmt=".4f", vmin=0.700, vmax=0.715, xticklabels=x_labels, yticklabels=y_labels)
    plt.title('Heat Map of Signal Intensity')
    plt.xlabel('X Position (mm)')
    plt.ylabel('Y Position (mm)')
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.show()

# Main execution
if __name__ == "__main__":
    sampling_rate = float(input("Enter the sampling rate in Hz (samples per second): "))
    data_acquisition_thread = Thread(target=move_and_acquire)
    data_acquisition_thread.start()
    data_acquisition_thread.join()
    generate_heatmap(data, total_increments_y)
