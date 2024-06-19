import socket
import takproto
from threading import Thread
from bs4 import BeautifulSoup
from meshtastic import portnums_pb2, atak_pb2


class DMSocketThread(Thread):
    def __init__(self, logger, meshtastic_interface, port=4243):
        super().__init__()

        self.meshtastic_interface = meshtastic_interface
        self.shutdown = False
        self.socket = None
        self.port = port
        self.logger = logger
        self.connection = None
        self.connection_address = None
        self.meshtastic_nodes = []

    def run(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', self.port))
        self.socket.listen(1)

        self.socket.settimeout(1.0)

        while not self.shutdown:
            try:
                self.connection, self.connection_address = self.socket.accept()
                self.logger.info(f"Got a connection from {self.connection_address[0]}")
            except KeyboardInterrupt:
                break
            except TimeoutError:
                if self.shutdown:
                    self.socket.shutdown(socket.SHUT_RDWR)
                    self.socket.close()
                continue
            except BaseException as e:
                self.logger.warning(e)
                continue

            try:
                data = self.connection.recv(4096)
                self.logger.debug(data)
                self.connection.close()
            except (ConnectionError, ConnectionResetError) as e:
                self.logger.warning(e)
                break
            except TimeoutError:
                if self.shutdown:
                    self.logger.warning("Got TimeoutError, exiting...")
                    break
                else:
                    continue

            parsed_data = takproto.parse_proto(data)
            if not parsed_data:
                parsed_data = takproto.parse_proto(takproto.xml2proto(data.decode('utf-8')))
                if not parsed_data:
                    self.logger.warning(f"Failed to parse data: {data}")
                    continue

            xml = "<details>" + parsed_data.cotEvent.detail.xmlDetail + "</details>"
            details = BeautifulSoup(xml, 'xml')
            remarks = details.find('remarks')
            chat = details.find("__chat")
            chatgrp = details.find("chatgrp")

            # For some unknown reason, WinTAK can send a GeoChat CoT without a <remarks> tag
            if not remarks or not chat or not chatgrp:
                continue

            self.logger.debug(f"Sending message: {remarks.text} to {chat.attrs['id']}")

            # DM to a node with the Meshtastic app
            if chat.attrs['id'] in self.meshtastic_nodes:
                self.meshtastic_interface.sendText(text=remarks.text, destinationId=chat.attrs['id'])
            # DM to a node running the ATAK plugin
            else:
                tak_packet = atak_pb2.TAKPacket()
                tak_packet.contact.callsign = chat.attrs['senderCallsign']
                tak_packet.contact.device_callsign = chatgrp.attrs['uid0']
                tak_packet.chat.message = remarks.text
                tak_packet.chat.to = chat.attrs['id']

                self.meshtastic_interface.sendData(tak_packet, portNum=portnums_pb2.PortNum.ATAK_PLUGIN)
                self.logger.debug(tak_packet)

    def add_meshtastic_node(self, node_id):
        if node_id not in self.meshtastic_nodes:
            self.logger.debug(f"Adding {node_id}")
            self.meshtastic_nodes.append(node_id)

    def stop(self):
        self.logger.warning("Shutting down")
        self.shutdown = True
