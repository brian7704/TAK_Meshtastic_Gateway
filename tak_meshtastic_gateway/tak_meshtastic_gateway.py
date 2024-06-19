import argparse
import sys
import traceback
from tak_meshtastic_gateway.dm_socket_thread import DMSocketThread
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, tostring
from meshtastic import portnums_pb2, mesh_pb2, atak_pb2, protocols
import meshtastic.serial_interface
import meshtastic.tcp_interface
from pubsub import pub
import datetime
import socket
import takproto
import time
import select
import colorlog
import logging
import unishox2
import uuid
import base64
import netifaces
import ipaddress
import platform

# Outputs
chat_out = ("224.10.10.1", 17012)
sa_multicast_out = ("239.2.3.1", 6969)

# Inputs
chat_in = ("224.10.10.1", 17012)  # UDP
default_in = ("0.0.0.0", 4242)  # UDP
default_in_tcp = ("0.0.0.0", 4242)  # TCP
prc_152 = ("0.0.0.0", 10001)  # UDP
request_notify = ("0.0.0.0", 8087)  # TCP
route_management = ("0.0.0.0", 8087)  # UDP
sa_multicast_in = ("239.2.3.1", 6969)  # UDP
sa_multicast_sensor_data_in = ("239.5.5.55", 7171)  # UDP


class TAKMeshtasticGateway:
    def __init__(self, ip=None, serial_device=None, mesh_ip=None, tak_client_ip="localhost", tx_interval=30,
                 dm_port=4243, log_file=None, debug=False):
        self.meshtastic_devices = {}
        self.node_names = {}
        self.tak_client = {}
        self.chat_sock = None
        self.sa_multicast_sock = None
        self.ip = ip
        self.dm_port = dm_port
        self.serial_device = serial_device
        self.mesh_ip = mesh_ip
        self.tak_client_ip = tak_client_ip
        self.tx_interval = tx_interval
        self.log_file = log_file
        self.log_level = logging.DEBUG if debug else logging.INFO
        self.interface = None
        self.meshtastic_connected = False
        self.meshtastic_device_info = None
        self.socket_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_client.connect((tak_client_ip, 4242))

        color_log_handler = colorlog.StreamHandler()
        color_log_formatter = colorlog.ColoredFormatter(
            '%(log_color)s[%(asctime)s] - TAK Meshtastic Gateway[%(process)d] - %(module)s - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s',
            datefmt="%Y-%m-%d %H:%M:%S")
        color_log_handler.setFormatter(color_log_formatter)
        self.logger = colorlog.getLogger('TAK Meshtastic Gateway')
        self.logger.setLevel(self.log_level)
        self.logger.addHandler(color_log_handler)
        self.logger.propagate = False

        if self.log_file:
            try:
                fh = logging.FileHandler(self.log_file)
                fh.setLevel(self.log_level)
                fh.setFormatter(logging.Formatter(
                    "[%(asctime)s] - TAK Meshtastic Gateway[%(process)d] - %(module)s - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s"))
                self.logger.addHandler(fh)
            except BaseException as e:
                self.logger.error(f"Failed to add log file handler: {e}")
                sys.exit()

        pub.subscribe(self.on_receive, "meshtastic.receive")
        pub.subscribe(self.on_connection, "meshtastic.connection.established")
        pub.subscribe(self.on_connection_lost, "meshtastic.connection.established.lost")
        self.connect_to_meshtastic_node()

        self.dm_sock = DMSocketThread(self.logger, self.interface)

    def connect_to_meshtastic_node(self):
        if self.mesh_ip:
            self.interface = meshtastic.tcp_interface.TCPInterface(self.mesh_ip)
        else:
            self.interface = meshtastic.serial_interface.SerialInterface(self.serial_device)

    def cot(self, pb, from_id, to_id, portnum, how='m-g', cot_type='a-f-G-U-C', uid=None):
        if not uid and from_id in self.meshtastic_devices and self.meshtastic_devices[from_id]['uid']:
            uid = self.meshtastic_devices[from_id]['uid']
        elif not uid:
            uid = from_id

        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        stale = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        event = Element('event', {'how': how, 'type': cot_type, 'version': '2.0',
                                  'uid': uid, 'start': now, 'time': now, 'stale': stale})

        SubElement(event, 'point', {'ce': '9999999.0', 'le': '9999999.0',
                                    'hae': str(self.meshtastic_devices[from_id]['last_alt']),
                                    'lat': str(self.meshtastic_devices[from_id]['last_lat']),
                                    'lon': str(self.meshtastic_devices[from_id]['last_lon'])})

        detail = SubElement(event, 'detail')
        if portnum == "TEXT_MESSAGE_APP" or (portnum == "ATAK_PLUGIN" and pb.HasField('chat')):
            return event, detail
        else:
            SubElement(detail, 'takv', {'device': self.meshtastic_devices[from_id]['hw_model'],
                                        'version': self.meshtastic_devices[from_id]['firmware_version'],
                                        'platform': 'Meshtastic', 'os': 'Meshtastic',
                                        'macaddr': self.meshtastic_devices[from_id]['macaddr'],
                                        'meshtastic_id': self.meshtastic_devices[from_id]['meshtastic_id']})
            SubElement(detail, 'contact',{'callsign': self.meshtastic_devices[from_id]['long_name'], 'endpoint': f'{self.ip}:{self.dm_port}:tcp'})
            SubElement(detail, 'uid', {'Droid': self.meshtastic_devices[from_id]['long_name']})
            SubElement(detail, 'precisionlocation', {'altsrc': 'GPS', 'geopointsrc': 'GPS'})
            SubElement(detail, 'status', {'battery': str(self.meshtastic_devices[from_id]['battery'])})
            SubElement(detail, 'track', {'course': '0.0', 'speed': '0.0'})
            SubElement(detail, '__group', {'name': self.meshtastic_devices[from_id]['team'],
                                           'role': self.meshtastic_devices[from_id]['role']})
        return event

    def position(self, pb, from_id, to_id, portnum):
        try:
            self.meshtastic_devices[from_id]['last_lat'] = pb.latitude_i * .0000001
            self.meshtastic_devices[from_id]['last_lon'] = pb.longitude_i * .0000001
            self.meshtastic_devices[from_id]['last_alt'] = pb.altitude
            if portnum == portnums_pb2.PortNum.POSITION_APP:
                self.meshtastic_devices[from_id]['course'] = pb.ground_track if pb.ground_track else "0.0"
                self.meshtastic_devices[from_id]['speed'] = pb.ground_speed if pb.ground_speed else "0.0"

            return self.cot(pb, from_id, to_id, portnum)
        except BaseException as e:
            self.logger.error("Failed to create CoT: {}".format(str(e)))
            self.logger.error(traceback.format_exc())
            return

    def text_message(self, pb, from_id, to_id, portnum):
        callsign = from_id
        if from_id in self.meshtastic_devices:
            callsign = self.meshtastic_devices[from_id]['long_name']
        self.logger.debug(self.meshtastic_devices)

        to_id = f"!{to_id:08x}"
        chatroom = "All Chat Rooms"
        self.logger.debug(f"to_id: {to_id} mesh id: {self.meshtastic_device_info['user']['id']}")
        if str(to_id) == str(self.meshtastic_device_info['user']['id']) and self.tak_client:
            chatroom = self.tak_client['uid']
        self.logger.debug(f"Chatroom is {chatroom}")

        if from_id in self.meshtastic_devices and self.meshtastic_devices[from_id]['uid']:
            from_uid = self.meshtastic_devices[from_id]['uid']
        else:
            from_uid = from_id

        message_uid = str(uuid.uuid4())
        event, detail = self.cot(pb, from_uid, chatroom, portnum, how='h-g-i-g-o', cot_type='b-t-f',
                                 uid="GeoChat.{}.{}.{}".format(from_uid, chatroom, message_uid))

        chat = SubElement(detail, '__chat',
                          {'chatroom': chatroom, 'groupOwner': "false", 'id': chatroom,
                           'messageId': message_uid, 'parent': 'RootContactGroup',
                           'senderCallsign': callsign})
        SubElement(chat, 'chatgrp', {'id': chatroom, 'uid0': from_uid, 'uid1': chatroom})
        SubElement(detail, 'link', {'relation': 'p-p', 'type': 'a-f-G-U-C', 'uid': from_uid})
        remarks = SubElement(detail, 'remarks', {'source': 'BAO.F.ATAK.{}'.format(from_uid),
                                                 'time': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                 'to': chatroom})

        remarks.text = pb.decode('utf-8', 'replace')

        return event

    def node_info(self, pb, from_id, to_id, portnum):
        if portnum == "ATAK_PLUGIN":
            if pb.is_compressed:
                uid = unishox2.decompress(pb.contact.device_callsign, len(pb.contact.device_callsign))
            else:
                uid = pb.contact.device_callsign
            self.meshtastic_devices[from_id]['uid'] = uid

            if pb.is_compressed:
                self.meshtastic_devices[from_id]['long_name'] = unishox2.decompress(pb.contact.callsign,
                                                                                    len(pb.contact.callsign))
            else:
                self.meshtastic_devices[from_id]['long_name'] = pb.contact.callsign

            self.meshtastic_devices[from_id]['short_name'] = uid[-4:]
            self.meshtastic_devices[from_id]['battery'] = pb.status.battery
            if pb.group.team != 0:
                self.meshtastic_devices[from_id]['team'] = atak_pb2.Team.Name(pb.group.team)
            if pb.group.role != 0:
                self.meshtastic_devices[from_id]['role'] = atak_pb2.MemberRole.Name(pb.group.role)

            return self.cot(pb, uid, to_id, portnum)
        else:
            hw_model = mesh_pb2.HardwareModel.Name(pb.hw_model)
            if hw_model and not self.meshtastic_devices[from_id]['hw_model']:
                self.meshtastic_devices[from_id]['hw_model'] = hw_model
            if pb.long_name and not self.meshtastic_devices[from_id]['long_name']:
                self.meshtastic_devices[from_id]['long_name'] = str(pb.long_name)
            if pb.short_name and not self.meshtastic_devices[from_id]['short_name']:
                self.meshtastic_devices[from_id]['short_name'] = str(pb.short_name)
            if pb.macaddr and not self.meshtastic_devices[from_id]['macaddr']:
                self.meshtastic_devices[from_id]['macaddr'] = base64.b64encode(pb.macaddr).decode('ascii')

            return self.cot(pb, from_id, to_id, portnum)

    def telemetry(self, pb, from_id, to_id, portnum):
        if pb.HasField('device_metrics'):
            self.meshtastic_devices[from_id]['battery'] = pb.device_metrics.battery_level
            self.meshtastic_devices[from_id]['voltage'] = pb.device_metrics.voltage
            self.meshtastic_devices[from_id]['uptime'] = pb.device_metrics.uptime_seconds
        elif pb.HasField('environment_metrics'):
            self.meshtastic_devices[from_id]['temperature'] = pb.environment_metrics.temperature
            self.meshtastic_devices[from_id]['relative_humidity'] = pb.environment_metrics.relative_humidity
            self.meshtastic_devices[from_id]['barometric_pressure'] = pb.environment_metrics.barometric_pressure
            self.meshtastic_devices[from_id]['gas_resistance'] = pb.environment_metrics.gas_resistance
            self.meshtastic_devices[from_id]['voltage'] = pb.environment_metrics.voltage
            self.meshtastic_devices[from_id]['current'] = pb.environment_metrics.current
            self.meshtastic_devices[from_id]['iaq'] = pb.environment_metrics.iaq

    def atak_plugin(self, pb, from_id, to_id, portnum):
        if pb.HasField('contact') and pb.is_compressed:
            uid = unishox2.decompress(pb.contact.device_callsign, len(pb.contact.device_callsign))
            callsign = unishox2.decompress(pb.contact.callsign, len(pb.contact.callsign))
        elif pb.HasField('contact') and not pb.is_compressed:
            uid = pb.contact.device_callsign
            callsign = pb.contact.callsign
        else:
            self.logger.warning("Got an ATAK_PLUGIN packet without the contact field")
            self.logger.warning(pb)
            return

        if uid not in self.meshtastic_devices:
            self.meshtastic_devices[uid] = {'hw_model': '', 'long_name': callsign, 'short_name': uid[-4:],
                                            'macaddr': '',
                                            'firmware_version': '', 'last_lat': "0.0", 'last_lon': "0.0",
                                            'meshtastic_id': '',
                                            'battery': 0, 'voltage': 0, 'uptime': 0, 'last_alt': "9999999.0",
                                            'course': '0.0',
                                            'speed': '0.0', 'team': 'Cyan', 'role': 'Team Member', 'uid': uid}

        self.node_info(pb, uid, to_id, portnum)

        if pb.HasField('status'):
            self.meshtastic_devices[uid]['battery'] = pb.status.battery

        if pb.HasField('pli'):
            self.meshtastic_devices[uid]['last_lat'] = pb.pli.latitude_i * .0000001
            self.meshtastic_devices[uid]['last_lon'] = pb.pli.longitude_i * .0000001
            self.meshtastic_devices[uid]['last_alt'] = pb.pli.altitude
            self.meshtastic_devices[uid]['course'] = pb.pli.course
            self.meshtastic_devices[uid]['speed'] = pb.pli.speed
            return self.cot(pb, uid, to_id, portnum)
        elif pb.HasField('chat'):
            if pb.is_compressed:
                to = unishox2.decompress(pb.chat.to, len(pb.chat.to))
                message = unishox2.decompress(pb.chat.message, len(pb.chat.message))
            else:
                to = pb.chat.to
                message = pb.chat.message

            self.logger.debug(
                "Got chat: {} {}->{}: {}".format(to, from_id, to_id, message))

            message_uid = str(uuid.uuid4())

            message_uid = "GeoChat.{}.{}.{}".format(uid, to, message_uid)

            event, detail = self.cot(pb, uid, to_id, portnum, how='h-g-i-g-o', cot_type='b-t-f', uid=message_uid)

            chat = SubElement(detail, '__chat',
                              {'chatroom': 'All Chat Rooms', 'groupOwner': "false", 'id': to,
                               'messageId': message_uid, 'parent': 'RootContactGroup',
                               'senderCallsign': callsign})
            SubElement(chat, 'chatgrp', {'id': to, 'uid0': uid, 'uid1': to})
            SubElement(detail, 'link', {'relation': 'p-p', 'type': 'a-f-G-U-C', 'uid': uid})
            remarks = SubElement(detail, 'remarks', {'source': 'BAO.F.ATAK.{}'.format(uid),
                                                     'time': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                     'to': to})
            remarks.text = message
            return event

    def protobuf_to_cot(self, pb, from_id, to_id, portnum):
        event = None

        if from_id[0] != "!":
            from_id = "!" + from_id
        if from_id != self.meshtastic_device_info['user']['id'] and from_id not in self.meshtastic_devices:
            self.meshtastic_devices[from_id] = {'hw_model': '', 'long_name': '', 'short_name': '', 'macaddr': '',
                                                'firmware_version': '', 'last_lat': "0.0", 'last_lon': "0.0",
                                                'meshtastic_id': from_id,
                                                'battery': 0, 'voltage': 0, 'uptime': 0, 'last_alt': "9999999.0",
                                                'course': '0.0',
                                                'speed': '0.0', 'team': 'Cyan', 'role': 'Team Member', 'uid': None}
            self.dm_sock.add_meshtastic_node(from_id)

        if portnum == "MAP_REPORT_APP" or (portnum == "POSITION_APP" and pb.latitude_i):
            event = self.position(pb, from_id, to_id, portnum)
        elif portnum == "NODEINFO_APP":
            event = self.node_info(pb, from_id, to_id, portnum)
        elif portnum == "TEXT_MESSAGE_APP":
            event = self.text_message(pb, from_id, to_id, portnum)
        elif portnum == "ATAK_PLUGIN":
            event = self.atak_plugin(pb, from_id, to_id, portnum)
        elif portnum == "TELEMETRY_APP":
            self.telemetry(pb, from_id, to_id, portnum)

        try:
            if event is not None:
                self.logger.debug(f"Sending {tostring(event)}")
                self.socket_client.send(tostring(event))
        except BaseException as e:
            self.logger.error(str(e))
            self.logger.error(traceback.format_exc())

    def on_receive(self, packet, interface):  # called when a packet arrives
        from_id = packet['from']
        from_id = f"!{from_id:08x}"

        # Ignore messages sent from this Meshtastic device
        if from_id == self.meshtastic_device_info['user']['id']:
            return

        to_id = packet['to']

        self.logger.debug(packet)
        if 'decoded' not in packet:
            return

        self.logger.info(f"Got a message from {from_id}")

        pn = packet['decoded']['portnum']

        handler = protocols.get(portnums_pb2.PortNum.Value(packet['decoded']['portnum']))
        if handler is None:
            if packet['decoded']['portnum'] == "ATAK_PLUGIN":
                try:
                    tak_packet = atak_pb2.TAKPacket()
                    tak_packet.ParseFromString(packet['decoded']['payload'])
                    self.logger.debug(tak_packet)
                    self.protobuf_to_cot(tak_packet, from_id, to_id, pn)
                except BaseException as e:
                    self.logger.debug(f"Failed to decode ATAK_PLUGIN protobuf: {e}")
            return

        if handler.protobufFactory is None:
            self.protobuf_to_cot(packet['decoded']['payload'], from_id, to_id, pn)
        else:
            try:
                pb = handler.protobufFactory()
                pb.ParseFromString(packet['decoded']['payload'])
                if pn == portnums_pb2.PortNum.NODEINFO_APP:
                    self.node_names[from_id] = pb.long_name
                self.logger.debug(pb)
                self.protobuf_to_cot(pb, from_id, to_id, pn)
            except:
                self.logger.error(traceback.format_exc())

    def on_connection(self, interface, topic=pub.AUTO_TOPIC):
        self.logger.info("Connected to the Meshtastic Device")
        self.meshtastic_connected = True
        self.meshtastic_device_info = interface.getMyNodeInfo()
        self.logger.debug(self.meshtastic_device_info)
        nodes = interface.nodes
        self.logger.debug(nodes)
        for node in nodes:
            if interface.nodes[node] != self.meshtastic_device_info:
                self.meshtastic_devices[node] = {'hw_model': nodes[node]['user']['hwModel'], 'long_name': nodes[node]['user']['longName'],
                                                 'short_name': nodes[node]['user']['shortName'], 'macaddr': '',
                                                 'firmware_version': '', 'last_lat': "0.0", 'last_lon': "0.0",
                                                 'meshtastic_id': node, 'battery': 0, 'voltage': 0, 'uptime': 0,
                                                 'last_alt': "9999999.0", 'course': '0.0', 'speed': '0.0', 'team': 'Cyan',
                                                 'role': 'Team Member', 'uid': node}
                self.dm_sock.add_meshtastic_node(node)

        self.logger.debug(self.meshtastic_devices)

    def on_connection_lost(self, interface):
        self.logger.error("Lost connection to the Meshtastic device, attempting to reconnect...")
        self.meshtastic_connected = False
        self.connect_to_meshtastic_node()

    def main(self):
        for interface in netifaces.interfaces():
            if self.ip:
                break

            addresses = netifaces.ifaddresses(interface)
            for address in addresses:
                try:
                    ip = ipaddress.IPv4Address(addresses[address][0]['addr'])
                    if ip.is_private and not ip.is_loopback and not ip.is_multicast:
                        self.ip = str(ip)
                        self.logger.info(f"Your IP address is {self.ip}")
                        break
                except ValueError:
                    self.logger.debug(f"{addresses[address][0]['addr']} is not an IPv4 address")

        self.logger.debug(f"The system platform is {platform.system()}")

        self.chat_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        if platform.system() == 'Windows':
            self.chat_sock.bind((self.ip, chat_in[1]))
            self.chat_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.ip))
            self.chat_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(chat_in[0]) + socket.inet_aton(self.ip))
        else:
            self.chat_sock.bind(chat_in)
            self.chat_sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.ip))
            self.chat_sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(chat_in[0]) + socket.inet_aton(self.ip))

        self.sa_multicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sa_multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)

        if platform.system() == 'Windows':
            self.sa_multicast_sock.bind((self.ip, sa_multicast_in[1]))
            self.sa_multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.ip))
            self.sa_multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(sa_multicast_in[0]) + socket.inet_aton(self.ip))
        else:
            self.sa_multicast_sock.bind(sa_multicast_in)
            self.sa_multicast_sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.ip))
            self.sa_multicast_sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(sa_multicast_in[0]) + socket.inet_aton(self.ip))

        self.dm_sock.start()

        while True:
            data = None
            try:
                inputready, outputready, exceptready = select.select([self.chat_sock, self.sa_multicast_sock], [], [])
                for s in inputready:
                    data, sender = s.recvfrom(4096)

                    # Only accept multicast data from one TAK client
                    if sender[0] != self.ip and sender[0] != self.tak_client_ip:
                        self.logger.warning(f"Got data from {sender[0]}, ignoring")
                        continue
            except KeyboardInterrupt:
                self.logger.info("Exiting....")
                self.dm_sock.stop()
                self.interface.close()
                break

            if data:
                self.logger.debug(data)
                parsed_data = takproto.parse_proto(data)
                if not parsed_data:
                    parsed_data = takproto.parse_proto(takproto.xml2proto(data.decode('utf-8')))
                    if not parsed_data:
                        self.logger.warning(f"Failed to parse data: {data}")
                        continue

                if parsed_data and parsed_data.cotEvent.type == 'b-t-f':
                    xml = "<detail>" + parsed_data.cotEvent.detail.xmlDetail + "</detail>"
                    soup = BeautifulSoup(xml, 'xml')
                    chat = soup.find("__chat")
                    chatroom = chat.attrs['chatroom']
                    sender_callsign = chat.attrs['senderCallsign']
                    chat_group = chat.find("chatgrp")
                    sender_uid = chat_group.attrs['uid0']
                    receiver_uid = chat_group.attrs['uid1']
                    remarks = soup.find("remarks")
                    message = remarks.text

                    if chatroom == "All Chat Rooms":
                        # Send as a Meshtastic text message so both the Meshtastic app and ATAK Plugin will receive it
                        self.interface.sendText(message)
                        self.logger.info("Sent text message to Meshtastic")
                    else:
                        tak_packet = atak_pb2.TAKPacket()
                        tak_packet.is_compressed = True
                        tak_packet.contact.callsign, size = unishox2.compress(sender_callsign)
                        tak_packet.contact.device_callsign, size = unishox2.compress(sender_uid)
                        tak_packet.group.team = self.tak_client['group_name']
                        tak_packet.group.role = self.tak_client['group_role']
                        tak_packet.status.battery = self.tak_client['battery']
                        tak_packet.chat.message, size = unishox2.compress(message)
                        tak_packet.chat.to = receiver_uid
                        self.interface.sendData(tak_packet, portNum=portnums_pb2.PortNum.ATAK_PLUGIN)
                        self.logger.info("Sent ATAK GeoChat to Meshtastic")

                elif parsed_data:
                    uid = parsed_data.cotEvent.uid
                    if not uid:
                        continue

                    if not self.tak_client:
                        self.tak_client = {'lat': parsed_data.cotEvent.lat, 'lon': parsed_data.cotEvent.lon,
                                           'hae': parsed_data.cotEvent.hae, 'uid': uid,
                                           'ce': parsed_data.cotEvent.ce, 'le': parsed_data.cotEvent.le,
                                           'callsign': '', 'device': '', 'platform': '', 'os': '', 'version': '',
                                           'group_name': '', 'group_role': '',
                                           'course': 0, 'speed': 0, 'battery': 0, 'last_tx_time': 0}
                        self.logger.debug(self.tak_client)
                    else:
                        self.tak_client['lat'] = parsed_data.cotEvent.lat
                        self.tak_client['lon'] = parsed_data.cotEvent.lon
                        self.tak_client['hae'] = parsed_data.cotEvent.hae
                        self.tak_client['ce'] = parsed_data.cotEvent.ce
                        self.tak_client['le'] = parsed_data.cotEvent.le

                    if parsed_data.cotEvent.detail.HasField("contact"):
                        contact = parsed_data.cotEvent.detail.contact
                        if not self.tak_client['callsign']:
                            self.tak_client['callsign'] = contact.callsign
                            self.interface.localNode.setOwner(f"{contact.callsign} Mesh Node", uid[-4:])

                    if parsed_data.cotEvent.detail.HasField("takv"):
                        takv = parsed_data.cotEvent.detail.takv
                        self.tak_client['device'] = takv.device
                        self.tak_client['platform'] = takv.platform
                        self.tak_client['os'] = takv.os
                        self.tak_client['version'] = takv.version

                    if parsed_data.cotEvent.detail.HasField("group"):
                        group = parsed_data.cotEvent.detail.group
                        self.tak_client['group_name'] = group.name
                        self.tak_client['group_role'] = group.role

                    if parsed_data.cotEvent.detail.HasField("track"):
                        self.tak_client['course'] = parsed_data.cotEvent.detail.track.course
                        self.tak_client['speed'] = parsed_data.cotEvent.detail.track.speed

                    if parsed_data.cotEvent.detail.HasField("status"):
                        self.tak_client['battery'] = parsed_data.cotEvent.detail.status.battery

                    if time.time() - self.tak_client['last_tx_time'] >= self.tx_interval:
                        if self.meshtastic_connected:
                            # Send as a Meshtastic protobuf to show up in the Meshtastic app
                            self.logger.info("Sending position to Meshtastic")
                            self.interface.sendPosition(latitude=parsed_data.cotEvent.lat,
                                                        longitude=parsed_data.cotEvent.lon,
                                                        altitude=parsed_data.cotEvent.hae)

                        # Send as a TAKPacket to show up in ATAK
                        atak_packet = atak_pb2.TAKPacket()
                        if self.tak_client['group_name']:
                            atak_packet.group.team = self.tak_client['group_name'].replace(" ", "_")

                        if self.tak_client['group_role']:
                            atak_packet.group.role = self.tak_client['group_role'].replace(" ", "")

                        atak_packet.status.battery = self.tak_client['battery']

                        pli = atak_pb2.PLI()
                        pli.latitude_i = int(self.tak_client['lat'] / .0000001)
                        pli.longitude_i = int(self.tak_client['lon'] / .0000001)
                        pli.altitude = int(self.tak_client['hae'])
                        pli.speed = int(self.tak_client['speed'])
                        pli.course = int(self.tak_client['course'])
                        atak_packet.pli.CopyFrom(pli)

                        contact = atak_pb2.Contact()
                        contact.callsign = self.tak_client['callsign'].encode()
                        contact.device_callsign = uid.encode()
                        atak_packet.contact.CopyFrom(contact)

                        if self.meshtastic_connected:
                            self.interface.sendData(atak_packet, portNum=portnums_pb2.PortNum.ATAK_PLUGIN)
                            self.tak_client['last_tx_time'] = time.time()
                            self.logger.info("Sent ATAK packet to Meshtastic")
                            self.logger.debug(atak_packet)
                    else:
                        self.logger.debug("Not sending packet to Meshtastic")


def main():
    parser = argparse.ArgumentParser(
        prog='TAK Meshtastic Gateway',
        description='Listens for multicast messages from TAK clients and forwards them to a Meshtastic network and vice-versa')
    parser.add_argument('-i', '--ip-address', help='Network interface to listen on for multicast messages',
                        default=None)
    parser.add_argument('-s', '--serial-device', help='Serial device of the Meshtastic node', default=None)
    parser.add_argument('-m', '--mesh-ip', help='IP address of the Meshtastic node', default=None)
    parser.add_argument('-c', '--tak-client-ip', help='IP address of the TAK client', default="localhost")
    parser.add_argument('-t', '--tx-interval', help='Minimum time to wait in seconds before sending PLI to the mesh',
                        default=30)
    parser.add_argument('-l', '--log-file', help='Save log messages to the specified file', default=None)
    parser.add_argument('-p', '--dm-socket-port', help='Port to listen on for DMs', default=4243)
    parser.add_argument('-d', '--debug', help='Enable debug logging', action='store_true')
    args = parser.parse_args()

    if args.ip_address:
        try:
            ipaddress.IPv4Address(args.ip_address)
        except ipaddress.AddressValueError:
            print(f"Invalid IPv4 Address: {args.ip_address}")
            sys.exit()

    if args.mesh_ip:
        try:
            ipaddress.IPv4Address(args.mesh_ip)
        except ipaddress.AddressValueError:
            print(f"Invalid Mesh IPv4 Address: {args.mesh_ip}")
            sys.exit()

    if args.serial_device and args.mesh_ip:
        print("Please specify either --serial-device or --mesh-ip, not both. If neither is specified this program will "
              "try to automatically find the correct serial device.")
        sys.exit()

    tak_meshtastic_gateway = TAKMeshtasticGateway(args.ip_address, args.serial_device, args.mesh_ip, args.tak_client_ip,
                                                  args.tx_interval, args.dm_socket_port, args.log_file, args.debug)
    tak_meshtastic_gateway.main()


if __name__ == '__main__':
    main()
