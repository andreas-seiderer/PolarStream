# PolarStream

A Python application with GUI allowing to stream the ECG signal of a Polar H10 chestbelt to an TCP server. It is mainly developed to stream the data to the [SSI framework](https://github.com/hcmlab/ssi). It is based on information and code that can be found in the official repository from Polar and in some issue threads: https://github.com/polarofficial/polar-ble-sdk

Please note that this software is not intended to expose all features and settings of the Polar H10 device!

## Features
* scan and select Polar H10 device via GUI
* set the settings of the TCP client via GUI
* stream ECG data (binary: signed 16 bit integer) at about 130 Hz to an TCP server
* shows current battery level, heart rate, ECG signal and sample rate of ECG signal
* a sample SSI pipeline which can receive the ECG signal is provided in the "SSI" directory of this repository.

![Screenshot](/Polar%20Stream.png)
