# Power Analyzer

**Power Analyzer** is a desktop application developed in Python and PySide6 for monitoring, recording, and managing electrical measurements from different power analyzer instruments.

The application is designed around a modular architecture that allows multiple instrument models to be integrated independently, each with its own communication protocol, measurement decoder, and device-specific functionality.

Its goal is to provide a unified environment for real-time measurement visualization, data recording, historical management, and measurement export.

## Features

### Real-time monitoring
- Remote acquisition through TCP/IP communication.
- Continuous reception and decoding of measurement data.
- Real-time visualization of electrical parameters.
- Connection and data reception status monitoring.
- Support for multiple configured devices.

### Measurement recording
- Acquisition and recording of measurement samples.
- Internal measurement history management.
- Customizable historical data queries.
- Selection of time intervals for retrieving recorded measurements.
- Export of measurement records to CSV, XLSX, TXT, and PDF.
- Simultaneous storage in the internal history and local files.
- Consistent measurement ordering across recording and export operations.

### User interface
- Desktop interface built with PySide6 and Qt.
- Main navigation menu for application-wide operations.
- Sidebar for accessing available workspaces.
- Tab-based workspace management.
- Device configuration and selection.
- Connection and acquisition status indicators.

## Supported Equipment

### TES3600

Currently supported instrument:

- **TES3600 Power Analyzer**

  - Acquisition through a remote TCP server.
  - Instrument communication and measurement decoding.
  - Real-time measurement transmission.
  - Historical data acquisition.

  Repository: [tes3600_server](https://github.com/thiagocruz664/tes3600_server)

  **Note:** The current acquisition server implementation is adapted for the ODROID-C2 single-board computer.

Additional instrument models are intended to be integrated in future releases.

## Remote Communication

Remote instrument communication relies on a TCP connection between Power Analyzer and the corresponding acquisition server.

A **VPN connection is required on both ends** to establish secure and reliable communication between the desktop application and the remote acquisition device.

[Tailscale](https://tailscale.com/) is the recommended VPN solution. It simplifies network configuration and avoids common connectivity issues related to endpoint addressing, routing, and changing public IP addresses.

Both the acquisition server and the computer running Power Analyzer must be connected to the same Tailscale network.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| PySide6 / Qt | Desktop graphical interface |
| TCP/IP | Remote communication |
| PySerial | Serial communication with supported instruments |

## Architecture

Power Analyzer follows a modular architecture that separates device management, instrument-specific integrations, communication, measurement processing, historical data management, and graphical presentation.

Each instrument integration maintains its own communication protocol, decoder, measurement models, and acquisition services.

This approach allows new equipment to be incorporated without requiring changes to the internal implementation of existing integrations.

For further technical details, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Releases

**Current version: Beta 0.1.0**

The project is currently in its initial beta stage.

The goal is to provide downloadable installers for **Windows and Linux** through the GitHub Releases section.

[View available releases](https://github.com/thiagocruz664/power_analyzer/releases)

## License

This project is distributed under the [MIT License](LICENSE).