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

## Python Requirements

Due to an issue with the unishox2-py3 package, Windows requires Python version 3.12. Linux and macOS will work with Python
versions 3.8 and up.

## Known Issues

There is a bug in the takproto library which causes an exception in TAK Meshtastic Gateway when parsing XML CoT data.
There is a [PR](https://github.com/snstac/takproto/pull/16) that will fix the issue once it is merged. Until it is merged,
you will need to manually install from the pull request using the installation instructions below.

On Windows, the `unishox2-py3` library fails to build from the source distribution with the command `pip install unishox2-py3`.
TAK Meshtastic Gateway will instead install [this wheel](https://github.com/brian7704/OpenTAKServer-Installer/blob/master/unishox2_py3-1.0.0-cp312-cp312-win_amd64.whl).
As a result, Python 3.12 is required when running TAK Meshtastic Gateway on Windows.

## Installation

For installation you only need to create a Python virtual environment, activate the virtual environment, and install using pip.

### Linux/macOS

The unishox2-py3 Python library requires C build tools. In Debian based distros (i.e. Ubuntu) they can be installed with
`apt install build-essential`.

```shell
python3 -m venv tak_meshtastic_gateway_venv
. ./tak_meshtastic_gateway_venv/bin/activate
pip install git+https://github.com/snstac/takproto@refs/pull/16/merge
pip install tak-meshtastic-gateway
```

### Windows

```powershell
python -m venv tak_meshtastic_gateway_venv
.\tak_meshtastic_gateway_venv\Scripts\activate
pip install https://github.com/brian7704/OpenTAKServer-Installer/raw/master/unishox2_py3-1.0.0-cp312-cp312-win_amd64.whl
pip install git+https://github.com/snstac/takproto@refs/pull/16/merge
pip install tak-meshtastic-gateway
```

## Usage

When your virtual environment active, run the `tak-meshtastic-gateway` command

## Architecture

In most scenarios, the user will run TAK Meshtastic Gateway on the same computer that runs WinTAK. The Meshtastic node
can either be connected to the same computer via USB, or be on the same LAN as the computer. Connecting to the Meshtastic
node over the LAN allows it to be mounted in a spot outside with good mesh reception while the computer is inside.

## Meshtastic Node Configuration

The Meshtastic node should be set to the TAK role. TAK Meshtastic Gateway will automatically change the node's long name 
to the TAK client's callsign and the short name to the last four characters of the TAK client's UID. This ensures that 
the callsign shows up correctly for mesh users who are only using the Meshtastic app as well as ATAK plugin users.
TAK Meshtastic Gateway will also update the Meshtastic node's location with the location of the EUD.

## ATAK Plugin Settings

For best results, use the following settings on devices using the [Meshtastic ATAK Plugin.](https://meshtastic.org/docs/software/integrations/integrations-atak-plugin/).
You can find the settings in ATAK by clicking the Settings tool -> Tool Preferences -> Specific Tool Preferences ->
Meshtastic Preferences.

- Show all Meshtastic devices: On
- Don't sshow Meshtastic devices without GPS: On
- Do not show your local Meshtastic device: On

The rest of the settings can be changed as needed.

## Usage

All arguments are optional. If an argument is not specified its default value will be used.

| Flag | Parameter          | Description                                                                                                                                   | Default                                                                                          |
|------|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| `-i` | `--ip-address`     | The private IP address of the machine running TAK Meshtastic Gateway.                                                                         | TAK Meshtastic Gateway will attempt to automatically find the IP of the computer it's running on |
| `-s` | `--serial-device`  | The serial device of the Meshtastic node (i.e. `COM3` or `/dev/ttyACM0`). Cannot be used simultaneously with `--mesh-ip`                      | TAK Meshtastic Gateway will attempt to automatically determine the serial device                 |
| `-m` | `--mesh-ip`        | The IP address or DNS name of the gateway Meshtastic node. Cannot be used simultaneously with `--serial-device`                               | Uses a serial connection                                                                         |
| `-c` | `--tak-client-ip`  | The IP address of the device running the TAK client (ATAK, WinTAK, or iTAK)                                                                   | `localhost`                                                                                      |
| `-p` | `--dm-socket-port` | TCP Port to listen on for DMs                                                                                                                 | `4243`                                                                                           |
| `-t` | `--tx-interval`    | Minimum time (in seconds) to wait between PLI transmissions from the TAK client to the mesh network. This reduces strain on the mesh network. | `30`                                                                                             |
| `-l` | `--log-file`       | Save log messages to a file.                                                                                                                  | `None` (disabled)                                                                                |
| `-d` | `--debug`          | Enable debug log messages                                                                                                                     | `Disabled` Only messages at the `INFO` level or higher will be logged                            |

## Permissions

When the Meshtastic node is connected via USB, TAK Meshtastic Gateway needs to be run as root (or via `sudo`) in Linux
and in an administrator PowerShell or Command Prompt in Windows. Connecting to the Meshtastic node via TCP does
not require elevated permissions.

## Example Usage Scenarios

### Scenario 1

- WinTAK on a PC
- Meshtastic node connected to the PC via USB
- TAK Meshtastic Gateway running on the same PC
- Command: `tak_meshtastic_gateway`

### Scenario 2

- WinTAK on a PC
- Meshtastic node on the same LAN as the PC
- TAK Meshtastic Gateway running on the same PC as WinTAK
- Command: `tak_meshtastic_gateway --mesh-ip MESHTASTIC_NODE_IP` Note: Substitute `MESHTASTIC_NODE_IP` with
the node's actual IP (i.e. `192.168.1.10`)

### Scenario 3

- ATAK or iTAK on a mobile device connected to a Wi-Fi network
- Meshtastic node connected to the same network
- TAK Meshtastic Gateway running on a computer or VM on the same network
- Command: `tak_meshtastic_gateway --mesh-ip MESHTASTIC_NODE_IP --tak-client-ip TAK_CLIENT_IP` Note: Substitute
`MESHTASTIC_NODE_IP` and `TAK_CLIENT_IP` with their actual IPs (i.e. `192.168.1.10` and `192.168.1.11`)