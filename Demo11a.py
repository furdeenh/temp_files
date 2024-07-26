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

# Function to move in a zig-zag pattern
def move_in_zigzag_pattern():
    y_increment_count = 0
    for i in range(total_increments_y):
        move_motor(motor_x, steps_per_move_x, stepper.FORWARD) # Move right (positive x direction)
        move_motor(motor_y, steps_per_increment_y, stepper.FORWARD) # Move up (positive y direction)
        y_increment_count += 1 
        if y_increment_count > total_increments_y:  # Stop y-axis stage if condition is satisfied
            break
        move_motor(motor_x, steps_per_move_x, stepper.BACKWARD) # Move left (negative x direction)
        move_motor(motor_y, steps_per_increment_y, stepper.FORWARD) # Move up (positive y direction)
        y_increment_count += 1 
        if y_increment_count > total_increments_y:  # Stop y-axis stage if condition is satisfied
            break
 
 # Function to move the third actuator (Z-axis)           
def move_third_actuator():
    max_travel_z = 50  # Maximum travel distance in mm
    steps_per_mm_z = 10  # Steps per mm for Z-axis
    
    while True:
        try:
            move_distance_z = float(input("Enter the distance to move the third actuator (in mm, max 50mm): "))
            if move_distance_z < 0 or move_distance_z > max_travel_z:
                print(f"Please enter a value between 0 and {max_travel_z} mm.")
                continue
            break
        except ValueError:
            print("Invalid input. Please enter a numerical value.")

    steps_per_move_z = int(move_distance_z * steps_per_mm_z)
    
    # Move the Z-axis actuator
    move_motor(motor_z, steps_per_move_z, stepper.FORWARD)
   
# Function to take a photo    
def take_picture(filename="image.jpg"):
    try:
        # Run the libcamera-still command
        subprocess.run(["libcamera-still", "-o", filename], check=True)
        print(f"Picture saved as {filename}")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")

# Function to generate heat map
def generate_heatmap(data, x_steps, y_steps):
    # Determine the number of samples per row
    samples_per_row = len(data) // y_steps

    # Create an empty matrix to hold the data
    data_matrix = []
    
    # Initialize direction and position trackers
    forward = True
    row_data = []
    for i in range(len(data)):
        row_data.append(data[i])
        if len(row_data) == samples_per_row:
            if not forward:
                row_data.reverse()  # Reverse the row if moving backwards
            data_matrix.append(row_data)
            row_data = []
            forward = not forward  # Toggle direction

    if row_data:  # Handle any remaining data
        if not forward:
            row_data.reverse()
        data_matrix.append(row_data)

    # Convert to numpy array
    data_matrix = np.array(data_matrix)

    # Apply Gaussian filter for smoothing
    data_matrix = gaussian_filter(data_matrix, sigma=1)

    # Create axis labels
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

# Run sequence of functions to carry out scan, take data, and display data
if __name__ == "__main__":
    # move_third_actuator()  # Move the third actuator first
    sampling_rate = float(input("Enter the sampling rate in Hz (samples per second): "))
    # take_picture("image.jpg")
    data_acquisition_thread = Thread(target=acquire_data, args=(sampling_rate,))
    data_acquisition_thread.start()
    move_in_zigzag_pattern()
    stop_event.set()
    data_acquisition_thread.join()
    generate_heatmap(data, total_increments_y, total_increments_y)
