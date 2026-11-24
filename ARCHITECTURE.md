# Power Analyzer — Architecture

## 1. System Overview

Power Analyzer is a cross-platform desktop application developed in Python and PySide6 for monitoring, recording, and managing electrical measurements from power analyzer instruments.

The application follows a modular architecture designed to support different instrument models, each with its own communication mechanisms, measurement protocols, data structures, and specific functionality.

The TES3600 is currently the first integrated instrument. Future integrations should not depend on its internal implementation.

## 2. Architectural Principles

The architecture follows four main principles:

- **Instrument independence:** Each instrument can implement its own communication, acquisition, decoding, and measurement structures.
- **Separation of responsibilities:** Device management, communication, data processing, persistence, and graphical presentation remain independent.
- **Transport independence:** TCP is not mandatory for every instrument. Each integration can use the communication mechanism it requires.
- **Progressive extensibility:** New integrations should reuse existing components when appropriate without introducing unnecessary abstractions.

## 3. High-Level Architecture

The application is organized into four main areas:

1. **Application:** Startup, main window, navigation, and general coordination.
2. **Device Management:** Device configuration, identification, and persistence.
3. **Instrument Integrations:** Communication, acquisition, decoding, and instrument-specific functionality.
4. **Graphical Interface:** Shared components and device-specific workspaces.

### General Data Flow

```text
      Physical Instrument
              |
              v
     Communication Layer
              |
              v
     Acquisition Services
              |
              v
      Instrument Decoder
              |
              v
      Measurement Data
              |
              v
       Device Widgets
              |
       +------+------+
       |             |
       v             v
   Real-Time      Recording
   Monitoring     and History
```

The actual implementation may vary depending on the instrument.

## 4. Device Management

Located in `app/device_manager/`.

This module manages configured devices and their associated information.

Its main components include:

- **Device:** Represents a configured instrument, including its model, connection type, and communication parameters.
- **DeviceRepository:** Handles device persistence using a local JSON file.

Device configuration is independent of measurement data and instrument-specific decoding.

## 5. Instrument Integrations

Each instrument integration contains the components required to operate a specific model.

The current implementation is located in:

`app/tes3600/`

It includes:

- Communication and network clients.
- Connection and acquisition services.
- Protocol handling.
- Measurement decoding.
- Instrument-specific measurement data.

### TES3600 Acquisition

The TES3600 uses a remote acquisition architecture.

The instrument is connected to an ODROID-C2 running an independent acquisition server:

[tes3600_server](https://github.com/thiagocruz664/tes3600_server)

Power Analyzer communicates with this server through TCP.

Two independent communication channels are currently used:

| Channel | Default Port | Purpose |
|---|---:|---|
| Real-time acquisition | 5000 | Continuous measurement reception |
| Historical data | 9001 | Historical measurement queries |

A VPN connection is required between the desktop computer and the remote acquisition server.

Tailscale is the recommended solution to simplify connectivity and avoid common endpoint and routing configuration problems.

### Communication and Decoding

The communication layer handles message reception, framing, timestamps, and transport validation.

The instrument decoder interprets the original measurement frames and converts them into structured electrical data.

These responsibilities must remain independent.

## 6. Measurement Management

The application handles real-time measurements and historical records through separate workflows.

### Real-Time Acquisition

Measurement services receive data, decode instrument frames, and distribute processed measurements through Qt signals.

This allows acquisition and network operations to run in background threads without blocking the graphical interface.

### Historical Data

The TES3600 integration provides a separate TCP client and service for retrieving historical measurements.

Users can select predefined or custom time intervals and choose between two download destinations:

- Internal Power Analyzer recording.
- Local files.

Both destinations can be selected simultaneously.

Supported export formats include CSV, XLSX, TXT, and PDF.

Measurement ordering must remain consistent across recording, historical retrieval, and export operations.

Currently, device configurations are persisted in JSON, while measurement recordings are maintained in memory during the application session.

## 7. Graphical Interface

Located in `app/ui/`.

The interface is developed with PySide6 and provides the main application window, navigation, device management, and measurement workspaces.

### Main Window

`MainWindow` coordinates:

- Application navigation.
- Device selection and configuration.
- Connection management.
- Measurement distribution.
- Workspace and tab management.

It also supports detachable tabs that can be opened in independent windows.

### Dynamic Tool Discovery

`ToolDiscoveryService` discovers available instrument-specific tools.

The `DeviceToolWidget` base class defines a common interaction contract between the main window and device workspaces.

This allows tools to receive measurements and acquisition events without implementing communication logic themselves.

### Widgets

The interface distinguishes between:

- **Common widgets:** Shared device management and configuration components.
- **Device-specific widgets:** Instrument-dependent measurement and recording workspaces.

Current TES3600 workspaces include real-time measurement, recording, and historical downloads.

Dynamic tool discovery is implemented, but this does not yet represent a complete plugin or instrument integration system.

## 8. Extensibility

The architecture is designed to support additional power analyzer models.

A new integration should provide its own:

1. Device configuration.
2. Communication mechanism.
3. Protocol implementation.
4. Measurement decoder.
5. Measurement data structures.
6. Acquisition services.
7. Device-specific graphical tools.

Existing integrations should remain independent.

Although device management and graphical tool discovery already provide reusable mechanisms, acquisition and decoding are still coupled to the TES3600 in parts of the current implementation.

Future development should progressively remove this coupling without introducing unnecessary architectural complexity.

## 9. Project Guidelines

The following guidelines should be maintained during development:

- Keep instrument-specific logic within its integration.
- Separate communication protocols from measurement decoding.
- Keep graphical components independent of transport implementations.
- Avoid blocking the main Qt thread.
- Use Qt signals for communication between background services and the interface.
- Maintain consistent measurement ordering.
- Avoid circular dependencies and unnecessary abstractions.
- Preserve existing instrument functionality when introducing new integrations.

## 10. Current Scope

The current implementation provides:

- Device registration and configuration.
- JSON-based device persistence.
- TES3600 TCP acquisition.
- Serial communication components for the TES3600.
- Measurement decoding and real-time visualization.
- Measurement recording and historical retrieval.
- CSV, XLSX, TXT, and PDF exports.
- Dynamic graphical tool discovery.
- Tab and independent window management.

Direct serial acquisition is not yet integrated into the main device connection workflow.

The architecture will continue evolving as additional instruments and shared capabilities are introduced.