# Application Code
## Thrust Bench

Thrust test-bench for determining the performance of motor-propeller pairs. The application software communicates with a microcontroller over serial to read raw load-cell data, current, and voltage in real time. Data is recorded and processed for output.

## Features

- **Manual control**
- **Automated programs**
- **Sensor calibration**
- **Live plots**
- **CSV export** - `timestamp_s`, `thrust_raw`, `thrust_gf`, `torque_ncm`, `efficiency_gpw`, `voltage_mv`, `current_a`, `throttle_pct`

## Requirements

```
pip install -r requirements.txt
```

Requires Python 3.10+, PyQt6, pyqtgraph, numpy, and pyserial.

## Running

```bash
python src
```

A serial-port setup dialog appears first. Select the port your microcontroller is on and click **Connect**.

## Regenerating UI code

The `src/views/ui_*.py` files are auto-generated from `src/ui/*.ui` (Qt Designer files). To regenerate after editing a `.ui` file:

```bash
./pyqt_transfer.sh
```

## Project structure

```
├── src
│   ├── controllers
│   │   ├── start_splash_controller.py      # Home screen - navigate to each mode
│   │   ├── manual_control_controller.py    # Manual throttle control + recording
│   │   ├── automated_program_controller.py # Script runner + execution engine
│   │   └── calibration_controller.py       # All calibration procedures and save/load
│   ├── services
│   │   ├── data_service.py                 # Singleton - stores all sensor arrays, calibration points, spike filter
│   │   ├── serial_service.py               # Serial read/write loop, frame parsing
│   │   └── thrust_service.py               # Singleton - current throttle command
│   ├── ui
│   │   └── *.ui                            # Qt Designer source files
│   ├── utils
│   │   ├── decorators.py                   # @singleton decorator
│   │   └── program_parser.py               # Lexer/parser for the throttle program language
│   ├── views
│   │   ├── live_plot.py                    # pyqtgraph live-plot widget (mono + 2×2 multi-plot)
│   │   └── ui_*.py                         # Auto-generated PyQt6 view classes (do not edit)
│   └── __main__.py                         # Entry point - wires widgets, controllers, serial timer
├── pyqt_transfer.sh                        # Regenerates ui_*.py from *.ui
├── requirements.txt
└── pyrightconfig.json
```

## Throttle programs (`.tprog`)

Programs are plain-text files executed by the Automated Program page. Lines are executed top to bottom; blank lines and `# comments` are ignored.

### Commands

| Syntax | Description |
|---|---|
| `throttle <0–100>` | Instantly set throttle to a percentage |
| `delay <n> sec\|ms` | Hold the current throttle for `n` seconds or milliseconds |
| `ramp <0–100> <n> sec\|ms` | Linearly interpolate throttle from its current value to the target over `n` seconds or milliseconds |

### Example

```
# Spin-up test
throttle 0
delay 2 sec

ramp 50 3 sec      # sweep to 50% over 3 s
delay 5 sec        # hold at 50%

ramp 100 3 sec     # sweep to 100%
delay 5 sec

ramp 0 2 sec       # spool down
```

The editor validates the program as you type and underlines any lines with errors. Programs can be saved and loaded from the UI.
