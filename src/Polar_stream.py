
'''
(c)2022 Andreas Seiderer

Polar connection code based on:
https://github.com/polarofficial/polar-ble-sdk/issues/226
https://github.com/polarofficial/polar-ble-sdk/blob/master/technical_documentation/Polar_Measurement_Data_Specification.pdf
'''

import os
from pathlib import Path
from sre_constants import AT_BOUNDARY
import sys
import statistics


from PySide6.QtWidgets import QApplication, QWidget, QListWidget, QPushButton, QVBoxLayout, QSizePolicy, QProgressBar, QLabel, QSpinBox, QLineEdit, QGraphicsView, QMessageBox
from PySide6.QtCore import QFile, QDateTime, Qt, QRunnable, Slot, QThreadPool, QObject, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QPainter
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

from bleak import BleakClient, BleakScanner
from bleak.uuids import uuid16_dict

import asyncio


class PolarBLEconsts():
    def __init__(self):
        self.uuid16_dict = {v: k for k, v in uuid16_dict.items()}

        # UUID for model number
        self.MODEL_NBR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
        
        # UUID for manufacturer name
        self.MANUFACTURER_NAME_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(
            self.uuid16_dict.get("Manufacturer Name String")
        )

        # UUID for battery level
        self.BATTERY_LEVEL_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(
            self.uuid16_dict.get("Battery Level")
        )

        # UUID for battery level
        self.HR_UUID = "0000{0:x}-0000-1000-8000-00805f9b34fb".format(
            self.uuid16_dict.get("Heart Rate Measurement")
        )

        # UUID for connection establsihment with device
        self.PMD_SERVICE = "FB005C80-02E7-F387-1CAD-8ACD2D8DF0C8"

        # UUID for Request of stream settings
        self.PMD_CONTROL = "FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8"

        # UUID for Request of start stream
        self.PMD_DATA = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"

        self.ECG_DATA = 0x00


class PolarDevice():

    def __init__(self, signals, settings):
        self.const = PolarBLEconsts()

        # UUID for Request of ECG Stream
        self.ECG_WRITE = bytearray(
            [0x02,  #start measurement
            0x00,   #measurement type (ECG)
            0x00,   #setting type 0x00 = sample rate
            0x01,   #array len
            0x82,   #sample rate (130)
            0x00,   #sample rate
            0x01,   #setting type 0x01 = resolution
            0x01,   #array len
            0x0E,   #resolution 14 bit
            0x00    #resolution
            ]
        )

        self.signals = signals

        self.settings = settings
        self.client_writer = None
        self.shutdown = False

        self.ecgvalues = 0


    async def data_conv(self, sender, data):
        if data[0] == self.const.ECG_DATA:
            print("received ECG data ...")
            timestamp = self.convert_to_unsigned_long(data, 1, 8)
            frame_type = data[9]

            if frame_type == 0:                
                step = 3
                
                samples = data[10:]
                offset = 0

                values = []
                while offset < len(samples):
                    val = self.convert_array_to_signed_int(samples, offset, step)
                    offset += step

                    values.append(val)

                    if self.client_writer is not None and not self.client_writer.is_closing():
                        self.client_writer.write(val.to_bytes(2, 'little', signed=True))

                self.signals.ecg.emit(values)
                self.ecgvalues += len(values)

            await self.client_writer.drain()

        else:
            print("other data types received")


    def convert_array_to_signed_int(self, data, offset, length):
        return int.from_bytes(
            bytearray(data[offset : offset + length]), byteorder="little", signed=True,
        )


    def convert_to_unsigned_long(self, data, offset, length):
        return int.from_bytes(
            bytearray(data[offset : offset + length]), byteorder="little", signed=False,
        )


    def got_result(self, sender, data):
        pass


    def HR_result(self, sender, data):
        print("Heart rate: {0} bpm".format(int(data[1])))

        self.signals.hr.emit(int(data[1]))


    def battery_result(self, sender, data):
        print("Battery Level: {0}%".format(int(data[0])))

        self.signals.bat.emit(int(data[0]))


    async def run(self, client, debug=False):

        await client.is_connected()
        print("---------Device connected--------------")

        model_number = await client.read_gatt_char(self.const.MODEL_NBR_UUID)
        print("Model Number: {0}".format("".join(map(chr, model_number))))

        manufacturer_name = await client.read_gatt_char(self.const.MANUFACTURER_NAME_UUID)
        print("Manufacturer Name: {0}".format("".join(map(chr, manufacturer_name))))

        battery_level = await client.read_gatt_char(self.const.BATTERY_LEVEL_UUID)
        print("Battery Level: {0}%".format(int(battery_level[0])))
        self.signals.bat.emit(int(battery_level[0]))

        await client.start_notify(self.const.BATTERY_LEVEL_UUID, self.battery_result)

        await client.start_notify(self.const.HR_UUID, self.HR_result)

        att_read = await client.read_gatt_char(self.const.PMD_CONTROL)

        await client.start_notify(self.const.PMD_CONTROL, self.got_result)
        await client.write_gatt_char(self.const.PMD_CONTROL, self.ECG_WRITE)  #=====================
        
        # stream start
        await client.start_notify(self.const.PMD_DATA, self.data_conv)

        print("Receiving data stream ...")

        # average sample rate
        avg_sr = [0] * 30
        avg_sr_pos = 0

        while not self.shutdown:
            ## Collecting data
            await asyncio.sleep(1)

            avg_sr[avg_sr_pos] = self.ecgvalues
            avg_sr_pos+=1
            avg_sr_pos%=30
            self.ecgvalues = 0

            avg_sr_val = statistics.mean(avg_sr)
            print("SR: {}".format(avg_sr_val))
            self.signals.ecg_sr.emit(float(avg_sr_val))

        print("Stopping data stream ...")

        await client.write_gatt_char(self.const.PMD_CONTROL, bytearray([0x03,0x00]))   #stop ecg 0x00
        await client.stop_notify(self.const.PMD_DATA)

        await client.stop_notify(self.const.BATTERY_LEVEL_UUID)
        await client.stop_notify(self.const.HR_UUID)


    def connect(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.loop())


    def stop(self):
        self.shutdown = True


    async def loop(self):
        try:
            async with BleakClient(self.settings["address"]) as client:

                reader, writer = await asyncio.open_connection(self.settings["host"], self.settings["port"])
                self.client_writer = writer

                tasks = [
                    asyncio.ensure_future(self.run(client, True)),
                ]

                await asyncio.gather(*tasks)
        except Exception as error:
            print(error)


class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)

    hr = Signal(int)
    bat = Signal(int)
    ecg = Signal(list)

    ecg_sr = Signal(float)


class Worker(QRunnable):
    def __init__(self, *args, **kwargs):
        super(Worker, self).__init__()
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        self.polardevice = PolarDevice(self.signals, args[0])

    @Slot()  # QtCore.Slot
    def run(self):
        self.polardevice.connect()

    def stop(self):
        self.polardevice.stop()


class BLEScanWorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(list)


class BLEScanWorker(QRunnable):
    def __init__(self, *args, **kwargs):
        super(BLEScanWorker, self).__init__()
        self.args = args
        self.kwargs = kwargs
        self.signals = BLEScanWorkerSignals()

    async def bleScan(self):
        scanner = BleakScanner()
        await scanner.start()
        await asyncio.sleep(5.0)
        await scanner.stop()

        self.signals.result.emit(scanner.discovered_devices)

        for d in scanner.discovered_devices:
            print(d)

    @Slot()  # QtCore.Slot
    def run(self):
        asyncio.run(self.bleScan())


class Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.load_ui()

        self.setFixedSize(580, 550)

        self.setWindowTitle("Polar Stream     ©2022 Dr. Andreas Seiderer, University of Augsburg")

        self.btnScan = self.findChild(QPushButton, 'btnScan')
        self.btnScan.clicked.connect(self.btnScan_clicked)

        self.btnStartStreaming = self.findChild(QPushButton, 'btnStartStreaming')
        self.btnStartStreaming.clicked.connect(self.btnStartStreaming_clicked)

        self.btnStopStreaming = self.findChild(QPushButton, 'btnStopStreaming')
        self.btnStopStreaming.clicked.connect(self.btnStopStreaming_clicked)
        self.btnStopStreaming.setEnabled(False)

        self.listBLE = self.findChild(QListWidget, 'listBLE')
        self.progressBat = self.findChild(QProgressBar, 'progressBat')
        self.labelHrVal = self.findChild(QLabel, 'labelHrVal')
        self.spinBoxPort = self.findChild(QSpinBox, 'spinBoxPort')
        self.lineEditHost = self.findChild(QLineEdit, 'lineEditHost')
        self.labelECG_SR_Val = self.findChild(QLabel, 'labelECG_SR_Val')
        
        self.widgetGraph = self.findChild(QWidget, 'widgetGraph')

        self.chart = QChart()
        #self.chart.setAnimationOptions(QChart.AllAnimations)
        self.add_series()

        self.lay = QVBoxLayout(self.widgetGraph)
        self.lay.setContentsMargins(0, 0, 0, 0)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setContentsMargins(0, 0, 0, 0)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setViewportUpdateMode(QGraphicsView.NoViewportUpdate)

        size = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        size.setHorizontalStretch(4)
        self.chart_view.setSizePolicy(size)

        self.lay.addWidget(self.chart_view)

        self.threadpool = QThreadPool()
        self.worker = None
        self.blescanworker = None


    def add_series(self):
        self.series = QLineSeries()

        # remove legend
        self.chart.legend().detachFromChart()
        self.chart.legend().hide()
        self.chart.addSeries(self.series)

        # Setting X-axis
        self.axis_x = QValueAxis()
        self.axis_x.setTickCount(1)
        self.axis_x.setRange(0,1300)
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.series.attachAxis(self.axis_x)

        # Setting Y-axis
        self.axis_y = QValueAxis()
        self.axis_y.setTickCount(1)
        self.axis_y.setRange(-1500, 1500)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        self.series.attachAxis(self.axis_y)
        

    def load_ui(self):
        loader = QUiLoader()
        path = Path(__file__).resolve().parent / "form.ui"
        ui_file = QFile(path)
        ui_file.open(QFile.ReadOnly)
        loader.load(ui_file, self)
        ui_file.close()


    def btnScan_clicked(self):
        print("btnScan clicked")

        self.listBLEdevices = []

        self.listBLE.clear()

        self.btnScan.setEnabled(False)
        self.btnStartStreaming.setEnabled(False)

        self.blescanworker = BLEScanWorker()
        self.blescanworker.signals.result.connect(self.blescan_fn)

        self.threadpool.start(self.blescanworker)


    def blescan_fn(self, n):
        for d in n:
            print(d)
            if d.name is not None and "Polar H10" in d.name:
                self.listBLEdevices.append(d.address)
                self.listBLE.addItems([d.address + "     " + d.name ])

        self.btnScan.setEnabled(True)
        self.btnStartStreaming.setEnabled(True)


    def resetGUI(self):
        self.progressBat.setValue(0)
        self.labelHrVal.setText("000 bpm")
        self.labelECG_SR_Val.setText("000.0 Hz")
        self.series.clear()


    def btnStartStreaming_clicked(self):
        print("btnStartStreaming clicked")

        if self.listBLE.currentRow() == -1:
            button = QMessageBox.information(
            self,
            "Device not selected",
            "Please scan and select a Polar device first!",
            buttons=QMessageBox.Ok
            )

            return

        self.resetGUI()
        self.btnScan.setEnabled(False)
        self.btnStartStreaming.setEnabled(False)
        self.btnStopStreaming.setEnabled(True)

        print("selected BLE address {}".format(self.listBLEdevices[self.listBLE.currentRow()]))
        print("host: {} port: {}".format(self.lineEditHost.text(), self.spinBoxPort.value()))

        settings = {
            "address" : self.listBLEdevices[self.listBLE.currentRow()],
            "host" : self.lineEditHost.text(),
            "port" : self.spinBoxPort.value()
        }
                
        self.worker = Worker(settings)
        self.worker.signals.hr.connect(self.hr_fn)
        self.worker.signals.bat.connect(self.bat_fn)
        self.worker.signals.ecg.connect(self.ecg_fn)
        self.worker.signals.ecg_sr.connect(self.ecg_sr_fn)

        self.threadpool.start(self.worker)


    def hr_fn(self, n):
        self.labelHrVal.setText("{} bpm".format(n))


    def bat_fn(self, n):
        self.progressBat.setValue(n)


    def ecg_fn(self, n):

        newvals = len(n)

        if self.series.count()+newvals > 1300:
            self.series.clear()
                
        start = self.series.count()
        end = self.series.count()+newvals

        for i in range(start, end):
            self.series.append(i, n[i-start])

        self.chart_view.viewport().update()


    def ecg_sr_fn(self, n):
        self.labelECG_SR_Val.setText("{} Hz".format(round(n,1)))


    def btnStopStreaming_clicked(self):
        print("btnStopStreaming clicked")

        if self.worker is not None:
            self.worker.stop()

        self.btnScan.setEnabled(True)
        self.btnStartStreaming.setEnabled(True)
        self.btnStopStreaming.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = Widget()
    widget.show()
    sys.exit(app.exec())
