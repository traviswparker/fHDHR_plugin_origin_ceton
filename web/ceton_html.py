from flask import request, render_template_string
import pathlib
from io import StringIO
import subprocess


class Ceton_HTML():
    endpoints = ["/ceton", "/ceton.html"]
    endpoint_name = "page_ceton_html"
    endpoint_category = "pages"
    pretty_name = "Ceton"

    def __init__(self, fhdhr, plugin_utils):
        self.fhdhr = fhdhr
        self.plugin_utils = plugin_utils

        self.origin_obj = plugin_utils.origin_obj
        self.origin_name = self.origin_obj.name

        self.template_file = pathlib.Path(plugin_utils.path).joinpath('ceton.html')
        self.template = StringIO()
        self.template.write(open(self.template_file).read())

    def __call__(self, *args):
        return self.get(*args)

    def get(self, *args):
        if self.origin_obj.setup_success:
            origin_status_dict = {"Devices": len(self.fhdhr.config.dict["ceton"]["device_tuners"])}
            for i in range(len(self.fhdhr.config.dict["ceton"]["device_tuners"])):
                device = self.plugin_utils.origin_obj.tunerstatus[str(i)]['ceton_ip']
                origin_status_dict["Device"+str(i)] = {}
                origin_status_dict["Device"+str(i)]["Setup"] = "Success"
                origin_status_dict["Device"+str(i)]["Temp"] = self.plugin_utils.origin_obj.get_ceton_var(i, "Temperature")
                origin_status_dict["Device"+str(i)]["HWType"] = self.plugin_utils.origin_obj.get_ceton_var(i, "HostConnection")
                origin_status_dict["Device"+str(i)]["HostHardware"] = self.plugin_utils.origin_obj.get_ceton_var(i, "HostHardware")
                origin_status_dict["Device"+str(i)]["HostFirmware"] = self.plugin_utils.origin_obj.get_ceton_var(i, "HostFirmware")
                origin_status_dict["Device"+str(i)]["HostSerial"] = self.plugin_utils.origin_obj.get_ceton_var(i, "HostSerial")

            for i in range(int(self.fhdhr.config.dict["ceton"]["tuners"])):
                origin_status_dict["Tuner"+str(i)] = {}
                origin_status_dict["Tuner"+str(i)]['Device'] = int(self.plugin_utils.origin_obj.tunerstatus[str(i)]['ceton_device'])
                origin_status_dict["Tuner"+str(i)]['Transport'] = self.plugin_utils.origin_obj.get_ceton_var(i, "TransportState")
                origin_status_dict["Tuner"+str(i)]['HWState'] = self.plugin_utils.origin_obj.devinuse(i)
                origin_status_dict["Tuner"+str(i)]['Channel'] = self.plugin_utils.origin_obj.get_ceton_var(i, "Signal_Channel")
                origin_status_dict["Tuner"+str(i)]['SignalLock'] = self.plugin_utils.origin_obj.get_ceton_var(i, "SignalCarrierLock")
                origin_status_dict["Tuner"+str(i)]['PCRLock'] = self.plugin_utils.origin_obj.get_ceton_var(i, "SignalPCRLock")
                origin_status_dict["Tuner"+str(i)]['Signal'] = self.plugin_utils.origin_obj.get_ceton_var(i, "Signal_Level")
                origin_status_dict["Tuner"+str(i)]['SNR'] = self.plugin_utils.origin_obj.get_ceton_var(i, "Signal_SNR")
                origin_status_dict["Tuner"+str(i)]['BER'] = self.plugin_utils.origin_obj.get_ceton_var(i, "Signal_BER")
                origin_status_dict["Tuner"+str(i)]['Modulation'] = self.plugin_utils.origin_obj.get_ceton_var(i, "Signal_Modulation")
        else:
            origin_status_dict = {"Setup": "Failed"}

        return render_template_string(self.template.getvalue(), request=request, fhdhr=self.fhdhr, origin_name=self.origin_name, origin_status_dict=origin_status_dict, list=list)
