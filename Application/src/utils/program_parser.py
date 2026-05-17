from typing import Tuple, List, Dict, Any, Union

ProgramInstruction = Dict[str, Any]
ParseError = Tuple[int, str]


def ProgramParser(
    program_text: str,
) -> Tuple[bool, Union[List[ProgramInstruction], List[ParseError]]]:
    """
    Returns:
        - (True, [{'instruction': 'delay', 'delayMs': 1000}, ...]) on success
        - (False, [(1, "Error message"), (5, "Error message")]) on failure
    """
    lines = program_text.strip().split("\n")
    instructions = []
    errors = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # Remove inline comments
        if "#" in stripped:
            stripped = stripped[: stripped.index("#")].strip()

        parts = stripped.split()

        if not parts:
            continue

        command = parts[0]

        if command == "delay":
            if len(parts) != 3:
                errors.append(
                    (
                        line_num,
                        "delay requires exactly 2 arguments: delay <number> <sec|ms>",
                    )
                )
                continue

            try:
                delay_value = int(parts[1])
            except ValueError:
                errors.append(
                    (line_num, f"Invalid delay value: {parts[1]} (must be an integer)")
                )
                continue

            time_unit = parts[2].lower()
            if time_unit not in ["sec", "ms"]:
                errors.append(
                    (
                        line_num,
                        f"Invalid time unit: {time_unit} (must be 'sec' or 'ms')",
                    )
                )
                continue

            delay_ms = delay_value * 1000 if time_unit == "sec" else delay_value
            instructions.append({"instruction": "delay", "delayMs": delay_ms})

        elif command == "throttle":
            if len(parts) != 2:
                errors.append(
                    (
                        line_num,
                        "throttle requires exactly 1 argument: throttle <number>",
                    )
                )
                continue

            try:
                throttle_value = int(parts[1])
            except ValueError:
                errors.append(
                    (
                        line_num,
                        f"Invalid throttle value: {parts[1]} (must be an integer)",
                    )
                )
                continue

            if throttle_value < 0 or throttle_value > 100:
                errors.append(
                    (
                        line_num,
                        f"Invalid throttle value: {throttle_value} (must be between 0 and 100)",
                    )
                )
                continue

            instructions.append({"instruction": "throttle", "command": throttle_value})

        elif command == "ramp":
            if len(parts) != 4:
                errors.append(
                    (
                        line_num,
                        "ramp requires exactly 3 arguments: ramp <number> <number> <sec|ms>",
                    )
                )
                continue

            try:
                target_throttle = int(parts[1])
                ramp_duration = int(parts[2])
            except ValueError:
                errors.append(
                    (
                        line_num,
                        f"Invalid ramp values: target={parts[1]}, duration={parts[2]} (must be integers)",
                    )
                )
                continue

            time_unit = parts[3].lower()
            if time_unit not in ["sec", "ms"]:
                errors.append(
                    (
                        line_num,
                        f"Invalid time unit: {time_unit} (must be 'sec' or 'ms')",
                    )
                )
                continue

            if target_throttle < 0 or target_throttle > 100:
                errors.append(
                    (
                        line_num,
                        f"Invalid target throttle: {target_throttle} (must be between 0 and 100)",
                    )
                )
                continue

            duration_ms = ramp_duration * 1000 if time_unit == "sec" else ramp_duration
            instructions.append(
                {
                    "instruction": "ramp",
                    "targetThrottle": target_throttle,
                    "durationMs": duration_ms,
                }
            )

        else:
            errors.append((line_num, f"Unknown instruction: {command}"))

    if errors:
        return (False, errors)

    return (True, instructions)
