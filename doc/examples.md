# TaskSAT Examples

This document provides annotated examples demonstrating common patterns and real-world applications.

## Example Files

Complete working examples can be found in `tests/tasknet_files/valid/`:

- [tasknet1.tn](../tests/tasknet_files/valid/tasknet1.tn) - Rover with heating, driving, communication
- [tasknet6_optional.tn](../tests/tasknet_files/valid/tasknet6_optional.tn) - Optional tasks and optimization
- [tasknet15_numeric_states.tn](../tests/tasknet_files/valid/tasknet15_numeric_states.tn) - Numeric state values

## Common Patterns

### Pattern 1: Sequential Task Chain

Tasks that must execute in order.

```tasknet
task task1 {
  id 1;
  duration 10;
}

task task2 {
  id 2;
  duration 10;
  after task1;  // Must start after task1 ends
}

task task3 {
  id 3;
  duration 10;
  after task2;  // Must start after task2 ends
}
```

**Use case:** Assembly line operations, multi-phase processes.

### Pattern 2: Resource Mutex (Mutual Exclusion)

Ensure only one task uses a resource at a time.

```tasknet
timelines {
  resource : claim [0.0, 1.0] = 1.0;  // Only 1 unit available
}

task use_resource_a {
  id 1;
  duration 20;
  pre { resource in [1.0, 1.0]; }  // Need full resource
  impacts {
    pre { resource -= 1.0; }   // Claim it
    post { resource += 1.0; }  // Release it
  }
}

task use_resource_b {
  id 2;
  duration 15;
  pre { resource in [1.0, 1.0]; }
  impacts {
    pre { resource -= 1.0; }
    post { resource += 1.0; }
  }
}
```

**Result:** Solver ensures tasks don't overlap.

**Use case:** Single antenna, exclusive machine access, critical sections.

### Pattern 3: Energy Budget

Tasks consume energy, charging tasks replenish it.

```tasknet
timelines {
  battery : rate [-10.0, 5.0] bounds [0.0, 100.0] = 50.0;
}

task charge {
  id 1;
  duration 30;
  impacts {
    maint { battery +~ 2.0; }  // Charge at 2 units/time
  }
}

task drive {
  id 2;
  duration 40;
  pre { battery in [40.0, 100.0]; }  // Need sufficient charge
  impacts {
    maint { battery +~ -1.0; }  // Drain 1 unit/time
  }
}

constraints {
  prop safe: always (battery >= 0.0);
  prop must_drive: eventually active(drive);
}
```

**Result:** Solver schedules charging before driving if needed.

**Use case:** Battery management, fuel planning, thermal budgets.

### Pattern 4: State Machines

Model system modes with state transitions.

```tasknet
timelines {
  system_mode : state(off, booting, ready, active, error) = off;
}

task boot {
  id 1;
  duration 10;
  pre { system_mode = off; }
  impacts {
    pre { system_mode = booting; }
    post { system_mode = ready; }
  }
}

task process_data {
  id 2;
  duration 30;
  pre { system_mode = ready; }
  impacts {
    pre { system_mode = active; }
    post { system_mode = ready; }
  }
}

task shutdown {
  id 3;
  duration 5;
  pre { system_mode = ready; }
  impacts {
    post { system_mode = off; }
  }
}

constraints {
  prop boot_first: active(process_data) -> once active(boot);
}
```

**Use case:** System startup/shutdown sequences, operational modes.

### Pattern 5: Data Collection and Transmission

Collect data, then transmit it.

```tasknet
timelines {
  data_storage : cumulative [0.0, 10.0] bounds [0.0, 500.0] = 0.0;
  battery : rate [-5.0, 2.0] bounds [0.0, 100.0] = 100.0;
}

task collect_science {
  id 1;
  duration 50;
  impacts {
    maint {
      data_storage +~ 3.0;   // Collect 3 units/time
      battery +~ -0.5;        // Use 0.5 battery/time
    }
  }
}

task transmit_data {
  id 2;
  duration 30;
  pre {
    data_storage in [50.0, 500.0];  // Need data to transmit
  }
  impacts {
    maint {
      data_storage +~ -5.0;   // Transmit 5 units/time
      battery +~ -1.0;
    }
  }
}

constraints {
  prop collect_then_transmit: active(transmit_data) -> once active(collect_science);
}
```

**Use case:** Scientific missions, telemetry, data relay.

### Pattern 6: Optional Tasks with Priorities

Some tasks are required, others are optional bonuses.

```tasknet
task primary_mission {
  id 1;
  priority 100;  // High priority
  duration 60;
  // Required task
}

optional task bonus_science_1 {
  id 2;
  priority 50;
  duration 40;
  // Include if resources available
}

optional task bonus_science_2 {
  id 3;
  priority 30;
  duration 40;
  // Lower priority bonus
}
```

**With `--mode optimize`:** Solver minimizes optional tasks, preferring higher priority ones if they fit.

**Use case:** Best-effort activities, stretch goals, opportunistic observations.

### Pattern 7: Thermal Management

Heat up before operation, cool down after.

```tasknet
timelines {
  temperature : rate [-2.0, 2.0] bounds [0.0, 100.0] = 20.0;
  heater : atomic = false;
}

task warmup {
  id 1;
  duration 30;
  impacts {
    pre { heater = true; }
    maint { temperature +~ 1.0; }  // Heat at 1 degree/time
    post { heater = false; }
  }
}

task operate {
  id 2;
  duration 40;
  after warmup;
  pre { temperature in [50.0, 80.0]; }  // Operating range
  inv { temperature in [40.0, 90.0]; }
  impacts {
    maint { temperature +~ -0.3; }  // Gradual cooling
  }
}

constraints {
  prop safe_temp: always (temperature <= 95.0);
}
```

**Use case:** Instrument warmup, machinery preheating, thermal constraints.

### Pattern 8: Time Windows

Tasks must occur within specific time ranges.

```tasknet
task morning_observation {
  id 1;
  duration 30;
  start_range [0, 50];    // Must start in first 50 time units
  end_range [30, 80];     // Must end by time 80
}

task evening_transmission {
  id 2;
  duration 20;
  start_range [150, 180]; // Must start between 150-180
}
```

**Use case:** Ground station contact windows, solar panel charging windows, tidal constraints.

### Pattern 9: Parallel Tasks with Shared Resources

Multiple tasks can run in parallel if resources allow.

```tasknet
timelines {
  cpu : claim [0.0, 100.0] = 100.0;
  memory : claim [0.0, 1000.0] = 1000.0;
}

task process_a {
  id 1;
  duration 50;
  pre {
    cpu in [30.0, 100.0];
    memory in [200.0, 1000.0];
  }
  impacts {
    pre {
      cpu -= 30.0;
      memory -= 200.0;
    }
    post {
      cpu += 30.0;
      memory += 200.0;
    }
  }
}

task process_b {
  id 2;
  duration 40;
  pre {
    cpu in [40.0, 100.0];
    memory in [300.0, 1000.0];
  }
  impacts {
    pre {
      cpu -= 40.0;
      memory -= 300.0;
    }
    post {
      cpu += 40.0;
      memory += 300.0;
    }
  }
}

task process_c {
  id 3;
  duration 30;
  pre {
    cpu in [50.0, 100.0];
    memory in [150.0, 1000.0];
  }
  impacts {
    pre {
      cpu -= 50.0;
      memory -= 150.0;
    }
    post {
      cpu += 50.0;
      memory += 150.0;
    }
  }
}
```

**Result:** Solver finds non-overlapping schedule or allows partial overlap if resources permit.

**Use case:** Multi-core processors, parallel job scheduling, resource pooling.

### Pattern 10: Conditional Execution

Use temporal logic to express "if X happens, then Y must happen".

```tasknet
task risky_operation {
  id 1;
  duration 40;
  // Might cause problems
}

task safety_check {
  id 2;
  duration 10;
  // Required after risky operation
}

constraints {
  prop safety_after_risk: active(risky_operation) -> eventually active(safety_check);
}
```

**Use case:** Error handling, safety protocols, recovery procedures.

## Real-World Example: Mars Rover

A complete Mars rover activity plan:

```tasknet
tasknet MarsRoverDay {
  end = 240;  // 4-hour window

  timelines {
    battery : rate [-5.0, 10.0] bounds [0.0, 100.0] = 80.0;
    data : cumulative [0.0, 5.0] bounds [0.0, 200.0] = 0.0;
    wheels : state(stopped, moving) = stopped;
    arm : state(stowed, deployed) = stowed;
    temperature : rate [-1.0, 2.0] bounds [-20.0, 50.0] = 10.0;
  }

  // Morning: Charge with solar panels
  task solar_charge {
    id 1;
    duration 60;
    start_range [0, 30];
    impacts {
      maint { battery +~ 1.5; }
    }
  }

  // Drive to science target
  task drive_to_target {
    id 2;
    duration 40;
    after solar_charge;
    pre {
      battery in [50.0, 100.0];
      wheels = stopped;
      temperature in [0.0, 40.0];
    }
    impacts {
      pre { wheels = moving; }
      maint {
        battery +~ -2.0;
        temperature +~ 0.5;
      }
      post { wheels = stopped; }
    }
  }

  // Deploy arm for sampling
  task deploy_arm {
    id 3;
    duration 10;
    after drive_to_target;
    pre {
      arm = stowed;
      wheels = stopped;
    }
    impacts {
      pre { arm = deployed; }
      maint { battery +~ -0.3; }
    }
  }

  // Collect sample
  task collect_sample {
    id 4;
    duration 30;
    after deploy_arm;
    pre {
      arm = deployed;
      battery in [30.0, 100.0];
    }
    impacts {
      maint {
        battery +~ -1.0;
        data +~ 2.0;
        temperature +~ 0.3;
      }
    }
  }

  // Stow arm
  task stow_arm {
    id 5;
    duration 10;
    after collect_sample;
    impacts {
      maint { battery +~ -0.3; }
      post { arm = stowed; }
    }
  }

  // Transmit data to Earth
  task transmit_data {
    id 6;
    duration 40;
    after stow_arm;
    start_range [180, 220];  // Earth contact window
    pre {
      data in [20.0, 200.0];
      battery in [40.0, 100.0];
    }
    impacts {
      maint {
        data +~ -3.0;
        battery +~ -1.5;
      }
    }
  }

  constraints {
    prop battery_safe: always (battery >= 10.0);
    prop temp_safe: always (temperature <= 45.0);
    prop arm_safe: always ((wheels = moving) -> (arm = stowed));
    prop must_sample: eventually active(collect_sample);
    prop must_transmit: eventually active(transmit_data);
  }
}
```

**Run with:**
```bash
python src/smt/tasknet_verifier.py mars_rover.tn --mode satisfy
```

## Tips for Writing Good TaskNets

1. **Start Simple**: Begin with a minimal example and add complexity incrementally

2. **Test Incrementally**: Verify each addition works before moving on

3. **Use Meaningful Names**: `battery` is better than `r1`, `charging` is better than `t2`

4. **Comment Complex Logic**: Explain non-obvious constraints

5. **Check Bounds**: Ensure timeline bounds are realistic

6. **Verify Properties**: Use temporal properties to catch unintended behaviors

7. **Use satisfy Mode First**: Get a working schedule before optimizing

8. **Watch for Over-Constraints**: If UNSAT, try relaxing constraints one at a time

9. **Consider Scaling**: See [performance.md](performance.md) for complexity guidelines

10. **Leverage Existing Examples**: Adapt patterns from `tests/tasknet_files/valid/`
