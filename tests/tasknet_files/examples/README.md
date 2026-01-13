# TaskSAT Examples

This directory contains runnable example TaskNet specifications demonstrating various concepts and patterns.

## How to Run Examples

```bash
# Run any example with the verifier
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/FILENAME.tn --mode satisfy

# Example:
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/my_robot.tn --mode satisfy
```

## Main Examples

| File | Description | Documentation |
|------|-------------|---------------|
| [my_robot.tn](my_robot.tn) | Simple robot with battery management and driving | [Getting Started](../../../doc/getting-started.md) |
| [rover_mission.tn](rover_mission.tn) | Mars rover with drive, sample collection, and data transmission | [Tutorial](../../../doc/tutorial.md) |
| [mars_rover_day.tn](mars_rover_day.tn) | Complete Mars rover daily activity plan with 6 tasks | [Examples Guide](../../../doc/examples.md) |

## Pattern Examples

These examples demonstrate common scheduling patterns:

| File | Pattern | Use Case |
|------|---------|----------|
| [sequential_tasks.tn](sequential_tasks.tn) | Sequential Task Chain | Assembly lines, multi-phase processes |
| [resource_mutex.tn](resource_mutex.tn) | Resource Mutual Exclusion | Single antenna, exclusive machine access |
| [energy_budget.tn](energy_budget.tn) | Energy Budget Management | Battery management, fuel planning |
| [state_machine.tn](state_machine.tn) | State Machine Transitions | System startup/shutdown sequences |
| [data_collection.tn](data_collection.tn) | Data Collection & Transmission | Scientific missions, telemetry |
| [optional_tasks.tn](optional_tasks.tn) | Optional Tasks with Priorities | Best-effort activities, stretch goals |
| [thermal_management.tn](thermal_management.tn) | Thermal Management | Instrument warmup, thermal constraints |
| [time_windows.tn](time_windows.tn) | Time Window Constraints | Ground station contacts, charging windows |
| [parallel_resources.tn](parallel_resources.tn) | Parallel Tasks with Shared Resources | Multi-core processors, resource pooling |
| [conditional_execution.tn](conditional_execution.tn) | Conditional Task Execution | Error handling, safety protocols |

## What Each Example Demonstrates

### my_robot.tn
- **Concepts**: Basic rate timeline (battery), state timeline (location)
- **Impact types**: Rate impacts (+~)
- **Properties**: Simple safety constraint (battery >= 0)
- **Good for**: First-time users, understanding basics

### rover_mission.tn
- **Concepts**: Multiple timeline types, sequential tasks with `after`
- **Impact types**: Assignment (=), rate (+~)
- **Impact timing**: pre, maint, post
- **Properties**: Temporal properties with `eventually` and `active()`
- **Good for**: Understanding complete systems

### mars_rover_day.tn
- **Concepts**: Complex scheduling with time windows, 6-task sequence
- **Features**: start_range constraints for contact windows
- **Timelines**: Rate (battery, temperature), cumulative (data), state (wheels, arm)
- **Good for**: Real-world application patterns

## Pattern Details

See [doc/examples.md](../../../doc/examples.md) for detailed explanations of each pattern with code walkthroughs and use case discussions.

## Testing

All examples are included in the test suite and verified to produce valid schedules. To run tests:

```bash
pytest tests/
```

## Links

- [Main Documentation](../../../README.md)
- [Getting Started Guide](../../../doc/getting-started.md)
- [Tutorial](../../../doc/tutorial.md)
- [Language Reference](../../../doc/language-reference.md)
- [Examples Guide](../../../doc/examples.md)
