import base64
import re
import xmltodict
import subprocess
import threading
import os
import time

import fHDHR.exceptions


class Plugin_OBJ():

    def __init__(self, plugin_utils):
        self.lock = threading.Lock()
        self.plugin_utils = plugin_utils

        if not self.ceton_ip:
            raise fHDHR.exceptions.OriginSetupError("Ceton IP not set.")

        devices = self.ceton_ip
        if not isinstance(devices, list):
            devices = [devices]
        self.config_dict["devices"] = devices

        device_tuners = self.device_tuners
        if not isinstance(device_tuners, list):
            device_tuners = [device_tuners]
        self.config_dict["device_tuners"] = device_tuners

        self.tunerstatus = {}

        tuner_tmp_count = 0
        device_count = 0

        for device, tuners in zip(devices, device_tuners):
            port = 49990
            count = int(tuners)
            hwtype = ''
            for i in range(count):
                self.tunerstatus[str(tuner_tmp_count)] = {"ceton_ip": device}
                self.tunerstatus[str(tuner_tmp_count)]['ceton_device'] = str(device_count)
                self.tunerstatus[str(tuner_tmp_count)]['ceton_tuner'] = str(i)

                if i == 0:
                    hwtype = self.get_ceton_var(tuner_tmp_count, "HostConnection") # on PCI reset this will retry until tuner comes up

                if 'pci' in hwtype and os.path.exists('/dev'): # won't work on windows
                    self.tunerstatus[str(tuner_tmp_count)]['ceton_pcie']  = True
                    self.tunerstatus[str(tuner_tmp_count)]['port']  = "ctn91xx_mpeg0_%s" % i
                    self.tunerstatus[str(tuner_tmp_count)]['streamurl'] = "/dev/ctn91xx_mpeg0_%s" % i
                else:
                    self.tunerstatus[str(tuner_tmp_count)]['ceton_pcie']  = False
                    self.tunerstatus[str(tuner_tmp_count)]['port']  = port + i
                    # if we are using RTP on a pcie card, we need to stream to the ip it gives us
                    if 'pci' in hwtype:
                        dest_ip = self.pcie_ip
                    else:
                        dest_ip = self.plugin_utils.config.dict["fhdhr"]["address"]
                    self.tunerstatus[str(tuner_tmp_count)]['dest_ip'] = dest_ip
                    self.tunerstatus[str(tuner_tmp_count)]['streamurl'] = "rtp://%s:%s" % (dest_ip, port + i)

                self.startstop_ceton_tuner(tuner_tmp_count, 0)
                self.plugin_utils.logger.noob('tuner %s: %s %s' % (tuner_tmp_count, device, hwtype))
                
                tuner_tmp_count += 1
            device_count = device_count + 1

    @property
    def config_dict(self):
        return self.plugin_utils.config.dict["ceton"]

    @property
    def tuners(self):
        return self.config_dict["tuners"]

    @property
    def device_tuners(self):
        return self.config_dict["device_tuners"]

    @property
    def stream_method(self):
        return self.config_dict["stream_method"]

    @property
    def ceton_ip(self):
        return self.config_dict["ceton_ip"]

    @property
    def pcie_ip(self):
        return self.config_dict["pcie_ip"]

    def ceton_request(self, url, data=None, headers=None, retry=True, timeout=5, action=None):
        #ceton web server hangs on linux if the request is a certain length?!
        #kernel 6.x buffering issue? I have no clue.
        #pad if needed
        url += '\x00' * (255-len(url))
        while True:
            try:
                self.plugin_utils.logger.debug('%s %s' % (len(url), url))
                if data:
                    req = self.plugin_utils.web.session.post(url, data, headers=headers, timeout=timeout)
                else:
                    req = self.plugin_utils.web.session.get(url, headers=headers, timeout=timeout)
                req.raise_for_status()
                self.plugin_utils.logger.debug('%s %s %s' % (len(url), url, len(req.text)))
                return req
            except self.plugin_utils.web.exceptions.HTTPError as err:
                if e.response.status_code == 500: # ceton boot race condition
                    time.sleep(1)
                else:
                    raise err # do not retry on HTTP error
            # ceton may not be responding yet, so maybe retry.
            except Exception as err:
                if retry:
                    self.plugin_utils.logger.debug('%s %s %s' % (len(url), url, err))
                    url += '\x00' # buffering bug workaround, if it hangs adjust length by 1
                    time.sleep(1) # wait and try again
                else:
                    raise err # raise the error up

    def get_ceton_var(self, instance, query, retry=True):
        query_type = {
                      "Frequency": "&s=tuner&v=Frequency",
                      "ProgramNumber": "&s=mux&v=ProgramNumber",
                      "CopyProtectionStatus": "&s=diag&v=CopyProtectionStatus",
                      "Temperature": "&s=diag&v=Temperature",
                      "Signal_Channel": "&s=diag&v=Signal_Channel",
                      "Signal_Level": "&s=diag&v=Signal_Level",
                      "Signal_SNR": "&s=diag&v=Signal_SNR",
                      "Signal_BER": "&s=tuner&v=BER",
                      "Signal_Modulation": "&s=tuner&v=Modulation",
                      "TransportState": "&s=av&v=TransportState",
                      "HostConnection": "&s=diag&v=Host_Connection",
                      "HostSerial": "&s=diag&v=Host_Serial_Number",
                      "HostFirmware": "&s=diag&v=Host_Firmware",
                      "HostHardware": "&s=diag&v=Hardware_Revision",
                      "SignalCarrierLock": "&s=diag&v=Signal_Carrier_Lock",
                      "SignalPCRLock": "&s=diag&v=Signal_PCR_Lock",
                      "OOBStatus": "&s=diag&v=OOB_Status",
                      "Streaming_IP": "&s=diag&v=Streaming_IP",
                      "Streaming_Port": "&s=diag&v=Streaming_Port",
        }

        getVarUrl = ('http://%s/get_var?i=%s%s' % (self.tunerstatus[str(instance)]['ceton_ip'], self.tunerstatus[str(instance)]['ceton_tuner'], query_type[query]))

        try:
            getVarUrlReq = self.ceton_request(getVarUrl, retry=retry, action=query)
        except self.plugin_utils.web.exceptions.HTTPError as err:
            self.plugin_utils.logger.error('Error while getting variable for %s: %s' % (query, err))
            return None
        except Exception as err: # tuner is offline or not ready yet
            self.plugin_utils.logger.warning(err)
            return None

        result = re.search('get.>(.*)</body', getVarUrlReq.text)

        return result.group(1)

    def devinuse(self, instance):
        filename = self.tunerstatus[str(instance)]['streamurl']
        if '/dev' in filename:
            try:
                subprocess.check_output(['fuser', filename], stderr=subprocess.DEVNULL)
                # man: if access has been found, fuser returns zero
                # => Return True, device is in use
                return True
            except subprocess.CalledProcessError:
                # man: fuser returns a non-zero return code if none of the specified files is accessed
                # => Return False, device is not in use
                return False
        else:
            return False

    def get_ceton_tuner_status(self, chandict, scan=False):
        found = 0
        count = int(self.tuners)
        for instance in range(count):
            if self.get_ceton_var(instance, "HostConnection", retry=False): # tuner may not be ready, if not do not hang retrying
                status = self.tunerstatus[str(instance)]['status']
                hwinuse = False
                device = self.tunerstatus[str(instance)]['ceton_ip']
                instance = self.tunerstatus[str(instance)]['ceton_tuner']
                transport = self.get_ceton_var(instance, "TransportState")
                self.tunerstatus[str(instance)]['channel'] = self.get_ceton_var(instance, "Signal_Channel")
                self.tunerstatus[str(instance)]['level'] = self.get_ceton_var(instance, "Signal_Level")
                self.tunerstatus[str(instance)]['snr'] = self.get_ceton_var(instance, "Signal_SNR")
                self.tunerstatus[str(instance)]['ber'] = self.get_ceton_var(instance, "Signal_BER")
                if self.tunerstatus[str(instance)]['ceton_pcie']:
                    hwinuse = self.devinuse(instance)
                # Check to see if transport on (rtp/udp streaming), or direct HW device access (pcie)
                # This also handles the case of another client accessing the tuner!
                if (status == 'Inactive') and (transport == "STOPPED") and (not hwinuse):
                    if not scan:
                        self.plugin_utils.logger.info('Selected tuner#: %s' % str(instance))
                    else:
                        self.plugin_utils.logger.debug('Scanning tuner#: %s' % str(instance))
                    # Return needed info now (if not in scan mode)
                    if not scan:
                        found = 1
                        break
                else:
                    # Tuner is "in use" (or at least, not "not in use"), handle appropiately
                    if self.tunerstatus[str(instance)]['status'] != "Active":
                        # Check to see if stopping, may take some time to get to the state fully
                        if status == 'StopPending':
                            if (transport == "STOPPED") and (not hwinuse):
                                # OK, fully stopped now, set accordingly
                                self.plugin_utils.logger.info(
                                    'tuner %s, StopPending "cleared", set status to Inactive' % str(instance))
                                self.tunerstatus[str(instance)]['status'] = "Inactive"
                                self.tunerstatus[str(instance)]['stream_args'] = {}
                                # Return needed info now (if not in scan mode)
                                if not scan:
                                    found = 1
                                    break
                        else:
                            # To get here, status is External - but check for stop => and update
                            if (transport == "STOPPED") and (not hwinuse):
                                # No longer in use, set accordingly
                                self.plugin_utils.logger.info('tuner %s, External state "cleared", now Inactive' %
                                                            str(instance))
                                self.tunerstatus[str(instance)]['status'] = "Inactive"
                                self.tunerstatus[str(instance)]['stream_args'] = {}
                                # Return needed info now (if not in scan mode)
                                if not scan:
                                    found = 1
                                    break
                            else:
                                # External, and still in use
                                if self.tunerstatus[str(instance)]['status'] != "External":
                                    self.plugin_utils.logger.info('tuner %s, setting status to External' %
                                                                str(instance))
                                self.tunerstatus[str(instance)]['status'] = "External"
                self.plugin_utils.logger.debug('tuner %s: status = %s' %
                                            (str(instance), self.tunerstatus[str(instance)]['status']))
        return found, instance

    def startstop_ceton_tuner(self, instance, startstop):
        if not startstop:
            port = 0
            self.plugin_utils.logger.info('tuner %s to be stopped' % str(instance))
            self.tunerstatus[str(instance)]["status"] = "StopPending"
        else:
            self.plugin_utils.logger.info('tuner %s to be started' % str(instance))
            self.tunerstatus[str(instance)]["status"] = "Active"

        StartStopUrl = 'http://%s/stream_request.cgi' % self.tunerstatus[str(instance)]['ceton_ip']

        dest_ip = self.tunerstatus[str(instance)].get('dest_ip') # will not be set if pcie
        dest_port = self.tunerstatus[str(instance)]['port']

        StartStop_data = {"instance_id": instance,
                          "dest_ip": dest_ip,
                          "dest_port": dest_port,
                          "protocol": 0,
                          "start": startstop}

        # StartStop ... OK to Stop tuner for pcie (and safe), but do not Start => or blocks pcie (/dev)!
        if not (startstop and self.tunerstatus[str(instance)]['ceton_pcie']):
            try:
                StartStopUrlReq = self.ceton_request(StartStopUrl, StartStop_data, action=startstop)
                StartStopUrlReq.raise_for_status()
                return dest_port
            except self.plugin_utils.web.exceptions.HTTPError as err:
                self.plugin_utils.logger.error('Error while setting station stream: %s' % err)
                return None
        else:
            return dest_port #direct pcie stream
        

    def set_ceton_tuner(self, chandict, instance):
        tuneChannelUrl = 'http://%s/channel_request.cgi' % self.tunerstatus[str(instance)]['ceton_ip']
        tuneChannel_data = {"instance_id": instance,
                            "channel": chandict['origin_number']}

        try:
            tuneChannelUrlReq = self.ceton_request(tuneChannelUrl, tuneChannel_data, action=instance)
            tuneChannelUrlReq.raise_for_status()
            return tuneChannelUrlReq
        except self.plugin_utils.web.exceptions.HTTPError as err:
            self.plugin_utils.logger.error('Error while tuning station URL: %s' % err)
            return None


    def get_channels(self):
        cleaned_channels = []
        instance = 0 #Use the first tuner
        url_headers = {'accept': 'application/xml;q=0.9, */*;q=0.8'}

        count_url = 'http://%s/view_channel_map.cgi?page=1&xml=0' % self.tunerstatus[str(instance)]['ceton_ip']

        try:
            countReq = self.ceton_request(count_url, headers=url_headers)
        except self.plugin_utils.web.exceptions.HTTPError as err:
            self.plugin_utils.logger.error('Error while getting channel count: %s' % err)
            return []

        count = re.search('(?<=1 to 50 of )\\w+', countReq.text)
        count = int(count.group(0))
        page = 0

        while True:
            stations_url = "http://%s/view_channel_map.cgi?page=%s&xml=1" % (self.tunerstatus[str(instance)]['ceton_ip'], page)

            try:
                stationsReq = self.ceton_request(stations_url, headers=url_headers)
            except self.plugin_utils.web.exceptions.HTTPError as err:
                self.plugin_utils.logger.error('Error while getting stations: %s' % err)
                return []

            stationsRes = xmltodict.parse(stationsReq.content)

            for station_item in stationsRes['channels']['channel']:
                nameTmp = station_item["name"]
                nameTmp_bytes = nameTmp.encode('ascii')
                namebytes = base64.b64decode(nameTmp_bytes)
                name = namebytes.decode('ascii')
                clean_station_item = {
                                        "name": name,
                                        "callsign": name,
                                        "number": station_item["number"],
                                        "eia": station_item["eia"],
                                        "id": station_item["sourceid"],
                                        }

                cleaned_channels.append(clean_station_item)

            if (count > 1024):
                count -= 1024
                page = 21
                continue
            else:
                break

            if (count > 0):
                count -= 50
                page += 1
            else:
                break

        return cleaned_channels

    def get_channel_stream(self, chandict, stream_args):
        # Lock (immediately!) ... so "simultaneous" requests don't try to use the same tuner. Process, then release.
        with self.lock:
            found, instance = self.get_ceton_tuner_status(chandict)
            self.tunerstatus[str(instance)]["stream_args"] = stream_args

            # 1 to start or 0 to stop
            if found:
                port = self.startstop_ceton_tuner(instance, 1)
            else:
                port = None
                self.plugin_utils.logger.error('No tuners available')

            if port:
                self.plugin_utils.logger.noob('Opening tuner %s for %s' % (instance, chandict))
                tuned = self.set_ceton_tuner(chandict, instance)
            else:
                tuned = None

            if tuned:
                device = self.tunerstatus[str(instance)]['ceton_ip']
                self.get_ceton_var(instance, "Frequency")
                self.get_ceton_var(instance, "ProgramNumber")
                self.get_ceton_var(instance, "CopyProtectionStatus")
                self.plugin_utils.logger.noob('Initiate streaming channel %s from tuner %s on port %s' % (chandict['origin_number'], instance, port))
                streamurl = self.tunerstatus[str(instance)]['streamurl']
            else:
                streamurl = None

            stream_info = {"url": streamurl, "tuner": instance}
            return stream_info

    def close_stream(self, instance, stream_args):
        closetuner = stream_args["stream_info"]["tuner"]
        self.plugin_utils.logger.noob('Closing tuner %s' % closetuner)
        self.startstop_ceton_tuner(closetuner, 0)
