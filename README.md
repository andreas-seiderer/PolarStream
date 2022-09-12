# PolarStream

A Python application with GUI allowing to stream the ECG signal of a [Polar H10](https://www.polar.com/en/sensors/h10-heart-rate-sensor) chestbelt to an TCP server. It is mainly developed to stream the data to the [SSI framework](https://github.com/hcmlab/ssi). It is based on information and code that can be found in the official repository from Polar and in some issue threads: 
* https://github.com/polarofficial/polar-ble-sdk
* https://github.com/polarofficial/polar-ble-sdk/issues/226#issuecomment-1074824570

Please note that this software is not intended to expose all features and settings of the Polar H10 device! Additionally, not all types of errors are handled. In worst case the software has to be restarted.

## Features
* works on Windows (10) and Linux
* scan and select Polar H10 device via GUI
* set the settings of the TCP client via GUI
* stream ECG data (binary: signed 16 bit integer) at about 130 Hz to an TCP server
* shows current battery level, heart rate, ECG signal and sample rate of ECG signal
* a sample SSI pipeline which can receive the ECG signal is provided in the "SSI" directory of this repository.


## Setup
* Python 3.10 (tested)
* pip install -r requirements.txt

## Usage
1. enable Bluetooth
2. start TCP server e.g. the sample SSI pipeline
3. put on Polar H10 sensor (from this point please make sure to stay with the sensor nearby your Bluetooth receiver at all times)
4. click on "Scan" -> the sensor should appear in the list (the device ID is also printed on the side of the sensor)
5. select the device from the list
6. click on "Connect and stream data" -> this can take a moment where nothing seems to happen
7. the heart rate (HR) and battery level should be shown first; after a while also the ECG signal is plotted as it is sent to the TCP server
8. to stop the streaming press "Stop" (you should do this before stopping the TCP server e.g. the SSI pipeline)

![Screenshot](/Polar%20Stream.png)
