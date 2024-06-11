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
                self.logger.info("Receiving data")
                data = self.connection.recv(4096)
                self.logger.info(data)
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
            self.logger.warning(parsed_data)

            xml = "<details>" + parsed_data.cotEvent.detail.xmlDetail + "</details>"
            details = BeautifulSoup(xml, 'xml')
            remarks = details.find('remarks')
            chat = details.find("__chat")
            chatgrp = details.find("chatgrp")

            # For some unknown reason, WinTAK can send a GeoChat CoT without a <remarks> tag
            if not remarks or not chat or not chatgrp:
                continue

            self.logger.warning(f"Sending message: {remarks.text}")

            tak_packet = atak_pb2.TAKPacket()
            tak_packet.contact.callsign = chat.attrs['senderCallsign']
            tak_packet.contact.device_callsign = chatgrp.attrs['uid0']
            tak_packet.chat.message = remarks.text
            tak_packet.chat.to = chat.attrs['id']

            self.meshtastic_interface.sendData(tak_packet, portNum=portnums_pb2.PortNum.ATAK_PLUGIN)
            self.logger.debug(tak_packet)

    def stop(self):
        self.logger.warning("Shutting down")
        self.shutdown = True
