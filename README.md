Join us on the OpenTAKServer [Discord server](https://discord.gg/6uaVHjtfXN)

# TAK Meshtastic Gateway

TAK Meshtastic Gateway listens for multicast data from TAK clients (ATAK, WinTAK, and iTAK) and forwards it to
a Meshtastic device which transmits it to a Meshtastic network. It will also forward messages from Meshtastic to 
TAK clients via multicast. Additionally, it enables sending and receiving chat messages and locations between TAK clients
and the Meshtastic app. For example, someone using WinTAK can send a message over a Meshtastic network to someone using 
the Meshtastic app and vice versa.

## Features

- Send chat and PLI messages from TAK clients (ATAK, WinTAK, and iTAK) over a Meshtastic network
- Receive chat and PLI messages from a Meshtastic network and display them in a TAK client
- See Meshtastic devices on the TAK client's map
- See the TAK client on the Meshtastic app's map
- Send and receive chat messages between the TAK client and Meshtastic app

TAK Meshtastic Gateway currently only supports sending and receiving chat and PLI messages. Other data types such as
data packages, markers, images, etc, are not supported due to the limited bandwidth of Meshtastic networks.

## Known Issues

There is a bug in the takproto library which causes an exception in TAK Meshtastic Gateway when parsing XML CoT data.
There is a [PR](https://github.com/snstac/takproto/pull/16) that will fix the issue once it is merged.

## Installation

### Linux

Steps may differ slightly on some distros

```bash
git clone https://github.com/brian7704/TAK_Meshtastic_Gateway.git
cd TAK_Meshtastic_Gateway
python3 -m venv venv
. ./venv/bin/activate
pip install bs4 meshtastic pubsub takproto colorlog unishox2-py3 netifaces2
```

### Windows

These instructions assume you already have git and Python installed. In a future release there will be a binary made
with PyInstaller which won't require git or Python to be installed.

```bash
git clone https://github.com/brian7704/TAK_Meshtastic_Gateway.git
cd TAK_Meshtastic_Gateway
python -m venv venv
.\venv\Scripts\activate.bat
pip install bs4 meshtastic pubsub takproto colorlog unishox2-py3 netifaces2
```

### MacOS

TAK Meshtastic Gateway is untested on MacOS but should work fine. Try the Linux installation instructions and open
an issue to let us know if there are any problems.

## Architecture

In most scenarios, the user will run TAK Meshtastic Gateway on the same computer that runs WinTAK. The Meshtastic node
can either be connected to the same computer via USB, or be on the same LAN as the computer. Connecting to the Meshtastic
node over the LAN allows it to be mounted in a spot outside with good mesh reception while the computer is inside.

## Usage

All arguments are optional. If an argument is not specified its default value will be used.

| Flag | Parameter         | Description                                                                                                                                   | Default                                                                                          |
|------|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| `-i` | `--ip-address`    | The private IP address of the machine running TAK Meshtastic Gateway.                                                                         | TAK Meshtastic Gateway will attempt to automatically find the IP of the computer it's running on |
| `-s` | `--serial-device` | The serial device of the Meshtastic node (i.e. `COM3` or `/dev/ttyACM0`).Cannot be used simultaneously with `--mesh-ip`                       | TAK Meshtastic Gateway will attempt to automatically determine the serial device                 |
| `-m` | `--mesh-ip`       | The IP address or DNS name of the gateway Meshtastic node. Cannot be used simultaneously with `--serial-device`                               | Uses a serial connection                                                                         |
| `-c` | `--tak-client-ip` | The IP address of the device running the TAK client (ATAK, WinTAK, or iTAK)                                                                   | `localhost`                                                                                      |
| `-t` | `--tx-interval`   | Minimum time (in seconds) to wait between PLI transmissions from the TAK client to the mesh network. This reduces strain on the mesh network. | `30`                                                                                             |
| `-l` | `--log-file`      | Save log messages to a file.                                                                                                                  | `None` (disabled)                                                                                |
| `-d` | `--debug`         | Enable debug log messages                                                                                                                     | Default: `Disabled` Only messages at the `INFO` level or higher will be logged                   |

## Permissions

When the Meshtastic node is connected via USB, TAK Meshtastic Gateway needs to be run as root (or via `sudo`) in Linux
and in an administrator PowerShell or Command Prompt. Connecting to the Meshtastic node via the network does not require
elevated permissions.

## Example Scenarios

### Scenario 1

- WinTAK on a PC
- Meshtastic node connected to the PC via USB
- TAK Meshtastic Gateway running on the same PC
- Command: `python3 tak_meshtastic_gateway.py`

### Scenario 2

- WinTAK on a PC
- Meshtastic node on the same LAN as the PC
- TAK Meshtastic Gateway running on the same PC as WinTAK
- Command: `python3 tak_meshtastic_gateway.py --mesh-ip MESHTASTIC_NODE_IP` Note: Substitute `MESHTASTIC_NODE_IP` with
the node's actual IP (i.e. `192.168.1.10`)

### Scenario 3

- ATAK or iTAK on a mobile device connected to a Wi-Fi network
- Meshtastic node connected to the same network
- TAK Meshtastic Gateway running on a computer or VM on the same network
- Command: `python3 tak_meshtastic_gateway.py --mesh-ip MESHTASTIC_NODE_IP --tak-client-ip TAK_CLIENT_IP` Note: Substitude
`MESHTASTIC_NODE_IP` and `TAK_CLIENT_IP` with their actual IPs (i.e. `192.168.1.10` and `192.168.1.11`)