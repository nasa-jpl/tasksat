#!/usr/bin/env python3
"""
LLM-based task scheduler using Claude API + Lean validator.

ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────┐
    │ 1. Convert .tn → Lean JSON                              │
    │    (tools/lean_converter.py)                            │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────────┐
    │ 2. Analyze tasknet structure                            │
    │    - Extract constraints                                │
    │    - Identify type-level dependency patterns            │
    └─────────────────────┬───────────────────────────────────┘
                          │
                          ▼
    ┌─────────────────────────────────────────────────────────┐
    │ 3. LOOP: Generate-Validate                              │
    │                                                          │
    │   ┌──────────────────────────────────────────┐          │
    │   │ A. LLM generates candidate schedule      │          │
    │   │    Input: tasknet + semantic rules +     │          │
    │   │           violations from previous attempt│          │
    │   │    Output: schedule JSON                 │          │
    │   └──────────────────┬───────────────────────┘          │
    │                      │                                   │
    │                      ▼                                   │
    │   ┌──────────────────────────────────────────┐          │
    │   │ B. Lean validator checks schedule        │          │
    │   │    (src/lean/TaskNetExec/Main.lean)      │          │
    │   │    Output: valid=true/false + violations │          │
    │   └──────────────────┬───────────────────────┘          │
    │                      │                                   │
    │                      ▼                                   │
    │            ┌─────────┴─────────┐                        │
    │            │ Valid?             │                        │
    │            └─────────┬─────────┘                        │
    │              Yes ✓   │   No ✗                           │
    │                 │    │    │                             │
    │              SUCCESS  └────┘ Feed violations back       │
    │                          (loop continues)               │
    └─────────────────────────────────────────────────────────┘

WHY THIS WORKS:
- Schedule search is NP-hard (exponential search space)
- Schedule validation is polynomial (check constraints at zone boundaries)
- LLM can reason about constraints and learn from violation feedback
- Lean validator provides precise, actionable violation messages

SEMANTIC RULES:
The LLM is given semantic rules extracted from:
- Lean specification (src/lean/TaskNetExec/TaskNet/Semantics.lean)
- TaskSAT implementation (src/smt/tasknet_smt.py)
- Documentation (doc/SEMANTIC-RULES.md)

This knowledge allows the LLM to generate schedules that are likely to be valid,
rather than random guessing.
"""

import json
import subprocess
import sys
import requests
import os
from pathlib import Path

def get_jpl_genai_token() -> str:
    """Get authentication token from JPL GenAI API."""
    genai_api_dir = Path.home() / 'Desktop' / 'genai_api'

    if not genai_api_dir.exists():
        raise Exception(f"JPL GenAI API not found at {genai_api_dir}")

    # Run uv command from genai_api directory to get token
    result = subprocess.run(
        ['uv', 'run', 'genai_api', 'token'],
        cwd=genai_api_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"Failed to get JPL GenAI token: {result.stderr}")

    # Token is in stdout (may have warnings in stderr)
    token = result.stdout.strip()
    # Remove any extra lines (like "Shell cwd was reset...")
    token = token.split('\n')[0]

    return token

def get_jpl_genai_config() -> tuple[str, str]:
    """Get base URL and subscription ID from genai_api package."""
    genai_api_dir = Path.home() / 'Desktop' / 'genai_api'

    if not genai_api_dir.exists():
        raise Exception(f"JPL GenAI API not found at {genai_api_dir}")

    # Use uv run to get config values from genai_api package
    result = subprocess.run(
        ['uv', 'run', 'python3', '-c',
         'from genai_api.login.config import get_user_base_url, get_user_subscription_id; '
         'print(get_user_base_url()); '
         'print(get_user_subscription_id())'],
        cwd=genai_api_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"Failed to get JPL GenAI config: {result.stderr}")

    # Parse output (may have warnings, so take last two non-empty lines)
    lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    if len(lines) < 2:
        raise Exception(f"Could not parse config output: {result.stdout}")

    base_url = lines[-2]  # Second to last line
    subscription_id = lines[-1]  # Last line

    return base_url, subscription_id

def convert_tasknet_to_lean(tasknet_path: str) -> dict:
    """Convert .tn file to Lean JSON format."""
    lean_json_path = '/tmp/tasknet_for_scheduling.lean.json'

    converter = Path(__file__).parent.parent / 'tools' / 'lean_converter.py'
    result = subprocess.run(
        ['python3', str(converter), tasknet_path, lean_json_path],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise Exception(f"Conversion failed: {result.stderr}")

    with open(lean_json_path) as f:
        return json.load(f)

def augment_tasknet_with_dynamic_instances(tasknet_json: dict, schedule_json: dict) -> dict:
    """
    MEXEC semantic: Dynamically create task instances from taskdefs for schedule entries.

    If the schedule contains task IDs that don't exist in tasknet.tasks but match
    taskdefs, create instances from those taskdefs and add them to the tasknet.
    """
    tasknet = tasknet_json.copy()
    tasknet['tasks'] = tasknet_json['tasks'].copy()

    # Build map of taskdef name -> taskdef
    taskdefs_map = {td['id']: td for td in tasknet.get('taskdefs', [])}

    # Build set of existing task IDs
    existing_task_ids = {t['id'] for t in tasknet['tasks']}

    # Find task IDs in schedule that need to be created
    schedule_task_ids = set(schedule_json.get('tasks', {}).keys())
    missing_task_ids = schedule_task_ids - existing_task_ids

    # For each missing task ID, try to match it to a taskdef and create an instance
    next_ident = 200000  # High number to avoid conflicts
    for task_id in missing_task_ids:
        # Find matching taskdef by prefix
        matched_taskdef = None
        for taskdef_name, taskdef in taskdefs_map.items():
            if task_id.startswith(taskdef_name):
                matched_taskdef = taskdef
                break

        if matched_taskdef:
            # Create instance from taskdef
            new_task = matched_taskdef.copy()
            new_task['id'] = task_id
            new_task['ident'] = next_ident
            new_task['kind'] = 'optional'  # Dynamically created instances are optional
            next_ident += 1

            tasknet['tasks'].append(new_task)
            existing_task_ids.add(task_id)

    return tasknet

def validate_schedule(lean_json_path: str, schedule_path: str) -> tuple[bool, list[str]]:
    """Validate schedule using Lean semantics."""
    # Load tasknet and schedule
    with open(lean_json_path, 'r') as f:
        tasknet_json = json.load(f)
    with open(schedule_path, 'r') as f:
        schedule_json = json.load(f)

    # Augment tasknet with dynamically-created instances from schedule
    augmented_tasknet = augment_tasknet_with_dynamic_instances(tasknet_json, schedule_json)

    # Write augmented tasknet to temp file
    temp_tasknet_path = '/tmp/augmented_tasknet.json'
    with open(temp_tasknet_path, 'w') as f:
        json.dump(augmented_tasknet, f, indent=2)

    # Validate with augmented tasknet
    lean_dir = Path(__file__).parent.parent / 'src' / 'lean' / 'TaskNetExec'

    result = subprocess.run(
        ['lake', 'exe', 'tasknet-validate',
         '--tasknet', temp_tasknet_path,
         '--schedule', schedule_path],
        cwd=lean_dir,
        capture_output=True,
        text=True
    )

    if result.returncode not in [0, 1]:
        raise Exception(f"Validation failed: {result.stderr}")

    validation = json.loads(result.stdout)
    return validation['valid'], validation.get('violations', [])

def analyze_tasknet(tasknet_json: dict) -> dict:
    """Extract key information about tasknet for LLM."""
    tasks = tasknet_json['tasks']
    taskdefs = tasknet_json.get('taskdefs', [])
    timelines = tasknet_json['timelines']

    analysis = {
        'endTime': tasknet_json['endTime'],
        'num_tasks': len(tasks),
        'num_taskdefs': len(taskdefs),
        'task_summary': [],
        'timeline_summary': [],
        'constraint_patterns': {}
    }

    # Summarize tasks
    for task in tasks:
        task_info = {
            'id': task['id'],
            'kind': task['kind'],
            'startrng': task['startrng'],
            'endrng': task['endrng'],
            'durrng': task['durrng'],
            'after': task.get('after', []),
            'containedin': task.get('containedin', []),
            'after_definitions': task.get('after_definitions', []),
            'containedin_definitions': task.get('containedin_definitions', []),
            'has_preconditions': len(task.get('pre', [])) > 0,
            'has_invariants': len(task.get('inv', [])) > 0,
            'has_postconditions': len(task.get('post', [])) > 0,
            'num_impacts': len(task.get('impacts', []))
        }
        analysis['task_summary'].append(task_info)

    # Summarize timelines
    for tl in timelines:
        analysis['timeline_summary'].append({
            'id': tl['id'],
            'type': tl['tag']
        })

    # Identify constraint patterns
    for task in tasks:
        # Track after_definitions patterns
        for dep in task.get('after_definitions', []):
            if dep not in analysis['constraint_patterns']:
                analysis['constraint_patterns'][dep] = {'needed_by': [], 'type': 'after_definition'}
            analysis['constraint_patterns'][dep]['needed_by'].append(task['id'])

        # Track containedin_definitions patterns
        for dep in task.get('containedin_definitions', []):
            if dep not in analysis['constraint_patterns']:
                analysis['constraint_patterns'][dep] = {'needed_by': [], 'type': 'containedin_definition'}
            analysis['constraint_patterns'][dep]['needed_by'].append(task['id'])

    return analysis

def build_scheduling_prompt(analysis: dict, tasknet_json: dict, violations: list[str] = None, attempt: int = 1, user_guidance: str = None) -> str:
    """Build prompt for Claude API to generate schedule."""

    prompt = f"""You are a task scheduler. Generate a valid schedule for the following tasknet.

# TaskNet Semantic Rules (CRITICAL - READ CAREFULLY)

These rules define what makes a schedule valid. Extracted from Lean validator and TaskSAT implementation.

## Task Timing (CRITICAL)
- Tasks execute over [start, end) intervals (half-open)
- **Duration = end - start MUST BE WITHIN durrng range**
  - This is a HARD CONSTRAINT - violations will fail validation
  - Example: if durrng=[1, 690], then (end - start) must be ≤ 690
- Must also satisfy: startrng and endrng constraints
- **PREFER SHORTER DURATIONS**: When multiple durations are valid within durrng, prefer values closer to durrng.low
  - This frees up resources and timeline sooner
  - Even for request tasks, respect the maximum duration limit!

## Temporal Dependencies
- **after X**: X.end ≤ this.start (equal is valid!)
- **containedin Y**: Y.start ≤ this.start AND this.end ≤ Y.end
- **after_definitions ["foo"]**: ∃ task matching "foo*" that ends before this starts
- **containedin_definitions ["bar"]**: ∃ task matching "bar*" that contains this interval

## Type-Level Constraints (Existential Semantics)

**MEXEC Rule** (see SEMANTIC-RULES.md §2.4): If a task has a type-level constraint referencing a taskdef with NO instances, YOU MUST CREATE INSTANCES:
- Name them `{{taskdef_name}}__{{number}}` (e.g., comm_preheat__1)
- Inherit all constraints from the taskdef
- Schedule and include them in the "included" array
- Create as many as needed (use judgment + user guidance)

## Invariants (CRITICAL TIMING)
- Checked at (start, end] (exclusive start, inclusive end)
- At t=start: invariants NOT checked (PRE impacts take effect first)
- At t=start+ε: invariants checked with state AFTER PRE impacts
- This is why "atomic pattern" works: PRE impact enables INV check

## Impact Application
- PRE: applied at start time
- MAINT: applied throughout (start, end)
- POST: applied at end time

## Condition Checking
- PRE: checked at start BEFORE PRE impacts
- INV: checked throughout (start, end] AFTER impacts
- POST: checked at end AFTER POST impacts

## Task Kinds and Optimization
- **required**: Must be scheduled (failure if missing)
- **optional**: May be scheduled (include in "included" array if scheduled)
- **request**: Like optional, but represents user-desired activities
  - **IMPORTANT**: Schedule as many request task instances as possible!
  - Don't minimize the schedule—maximize request task inclusion
- **definition**: Template only, not a schedulable instance

---

# Tasknet Overview
- Total time horizon: 0 to {analysis['endTime']}
- Number of tasks: {analysis['num_tasks']}
- Number of task definitions (templates): {analysis['num_taskdefs']}
"""

    # Add user guidance if provided
    if user_guidance:
        prompt += f"""
# USER GUIDANCE (IMPORTANT)

The user has provided the following additional requirements and preferences for this schedule:

{user_guidance}

These requirements are in addition to the formal constraints. Please follow them carefully.

---
"""

    prompt += """
# Tasks to Schedule
"""

    for task_info in analysis['task_summary']:
        prompt += f"\n## {task_info['id']} ({task_info['kind']})\n"
        prompt += f"- Start range: [{task_info['startrng']['low']}, {task_info['startrng']['high']}]\n"
        prompt += f"- End range: [{task_info['endrng']['low']}, {task_info['endrng']['high']}]\n"
        dur_max = task_info['durrng']['high']
        prompt += f"- **Duration range: [{task_info['durrng']['low']}, {task_info['durrng']['high']}]** (end - start must be ≤ {dur_max})\n"

        if task_info['after']:
            prompt += f"- Must start after tasks: {', '.join(task_info['after'])}\n"
        if task_info['containedin']:
            prompt += f"- Must be contained within tasks: {', '.join(task_info['containedin'])}\n"
        if task_info['after_definitions']:
            prompt += f"- Must start after any instance of: {', '.join(task_info['after_definitions'])}\n"
        if task_info['containedin_definitions']:
            prompt += f"- Must be contained within any instance of: {', '.join(task_info['containedin_definitions'])}\n"

        if task_info['has_preconditions']:
            prompt += f"- Has preconditions (timeline constraints before start)\n"
        if task_info['has_invariants']:
            prompt += f"- Has invariants (timeline constraints during execution)\n"
        if task_info['has_postconditions']:
            prompt += f"- Has postconditions (timeline constraints after end)\n"
        if task_info['num_impacts'] > 0:
            prompt += f"- Has {task_info['num_impacts']} timeline impacts\n"

    # Add taskdef patterns if any
    if analysis['constraint_patterns']:
        prompt += f"\n# Type-Level Constraint Patterns\n"
        prompt += "Some tasks require instances of task definitions that may not exist yet.\n"
        for def_name, info in analysis['constraint_patterns'].items():
            prompt += f"\n- **{def_name}** ({info['type']}): needed by {', '.join(info['needed_by'])}\n"

    if violations and attempt > 1:
        prompt += f"\n# Previous Attempt #{attempt-1} - Violations Found\n"
        prompt += "Your previous schedule was invalid. Here are the violations:\n\n"
        for v in violations[:20]:  # Limit to first 20 violations
            prompt += f"- {v}\n"
        prompt += "\nPlease fix these violations in your next attempt.\n"

        if attempt >= 4:
            prompt += """
**IMPORTANT - Request Task Exclusion Strategy**:
If the same request task violates constraints in multiple consecutive attempts:
- It may be fundamentally unsatisfiable (e.g., impossible timing, conflicting constraints)
- Consider EXCLUDING it from the schedule (remove from both "tasks" and "included")
- A schedule with N-1 request tasks is better than no valid schedule
- Example: If battery_recharge_request_0 keeps violating battery_soc invariant, exclude it and schedule the other requests

Check if any request task appears repeatedly in violations above. If so, try excluding it this attempt.
"""

    prompt += """

# Output Format
Generate a JSON schedule in this exact format:

{
  "tasknet": "Tasknet_1",
  "tasks": {
    "task_id_1": {"start": <int>, "end": <int>},
    "task_id_2": {"start": <int>, "end": <int>},
    ...
  },
  "included": ["optional_task_id", "request_task_id"]
}

Important:
1. All required tasks must be scheduled
2. Include optional/request tasks in "included" array if you schedule them
3. **MAXIMIZE REQUEST TASKS**: Schedule as many request task instances as possible (they represent user-desired activities)
4. **CRITICAL - Duration constraint**: For EVERY task, ensure (end - start) ≤ durrng.high
   - Example: if a task has durrng=[1, 690] and you schedule it at [10100, 20000], duration is 9900 which VIOLATES the constraint!
   - Calculate: duration = end - start, then verify it's within [durrng.low, durrng.high]
5. **Respect all timing constraints**: Each task must also satisfy startrng and endrng
6. **Prefer shorter durations**: Within the valid durrng range, choose durations closer to durrng.low
7. Ensure "after" constraints: dependent task starts after prerequisite ends
8. Ensure "containedin" constraints: child task [start,end] ⊆ parent [start,end]
9. Timeline impacts and conditions will be checked by the validator

Return ONLY the JSON, no other text.
"""

    return prompt

def generate_schedule_with_llm(prompt: str, base_url: str, headers: dict, model_id: str) -> dict:
    """Use JPL GenAI API to generate schedule."""

    payload = {
        "model": model_id,
        "stream": False,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 16000
    }

    try:
        r = requests.post(base_url + "/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        response = r.json()

        # Extract content from OpenAI-style response
        content = response["choices"][0]["message"]["content"].strip()

        # Try to find JSON in response (might be wrapped in markdown)
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()

        return json.loads(content)

    except requests.RequestException as e:
        print(f"Error calling JPL GenAI API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Error Details: {e.response.text}")
        raise

def visualize_schedule_if_requested(schedule_path: str, attempt: int, visualize: bool, output_dir: str = '.'):
    """Create Gantt chart visualization if requested."""
    if not visualize:
        return

    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        with open(schedule_path) as f:
            schedule = json.load(f)

        tasks = schedule['tasks']

        # Group tasks by type (with granular distinctions)
        task_groups = {}
        for task_id, times in tasks.items():
            # Extract base type with distinctions for different definitions
            if 'preheat' in task_id:
                if 'comm' in task_id:
                    group_key = 'comm_preheat'
                elif 'global' in task_id:
                    group_key = 'global_localization_preheat'
                elif 'route' in task_id:
                    group_key = 'route_segment_preheat'
                else:
                    group_key = 'other_preheat'
            elif 'maintainheat' in task_id:
                if 'comm' in task_id:
                    group_key = 'comm_maintainheat'
                elif 'global' in task_id:
                    group_key = 'global_localization_maintainheat'
                elif 'route' in task_id:
                    group_key = 'route_segment_maintainheat'
                else:
                    group_key = 'other_maintainheat'
            elif 'downlink' in task_id:
                group_key = 'downlink'
            elif 'orbiter_visible' in task_id:
                group_key = 'orbiter_visible'
            elif 'orbiter_available' in task_id:
                group_key = 'orbiter_available'
            elif 'battery' in task_id:
                group_key = 'battery_recharge'
            elif 'global_localization_request' in task_id:
                group_key = 'global_localization_request'
            elif 'route_segment_request' in task_id:
                group_key = 'route_segment_request'
            elif 'localization' in task_id:
                group_key = 'localization'
            elif 'route' in task_id:
                group_key = 'route'
            else:
                # Fallback: use first two components
                parts = task_id.split('_')
                group_key = '_'.join(parts[:2]) if len(parts) > 1 else parts[0]

            if group_key not in task_groups:
                task_groups[group_key] = []
            task_groups[group_key].append((task_id, times))

        # Color scheme (matching visualize_schedule.py)
        colors = {
            'orbiter_visible': '#2c3e50',
            'orbiter_available': '#3498db',
            'comm_preheat': '#e74c3c',
            'comm_maintainheat': '#f39c12',
            'downlink': '#27ae60',
            'global_localization_preheat': '#c39bd3',
            'global_localization_maintainheat': '#a569bd',
            'global_localization_request': '#8e44ad',
            'battery_recharge': '#16a085',
            'route_segment_preheat': '#f8b4d9',
            'route_segment_maintainheat': '#f093c3',
            'route_segment_request': '#e91e63',
            'localization': '#9b59b6',
            'route': '#e91e63',
            'other': '#95a5a6'
        }

        # Create figure
        fig, ax = plt.subplots(figsize=(16, max(8, len(task_groups) * 0.8)))

        y_pos = 0
        y_labels = []
        y_ticks = []

        for group_key in sorted(task_groups.keys()):
            group_tasks = task_groups[group_key]
            color = colors.get(group_key, '#95a5a6')

            for task_id, times in sorted(group_tasks, key=lambda x: x[1]['start']):
                start = times['start']
                end = times['end']
                duration = end - start

                ax.barh(y_pos, duration, left=start, height=0.7,
                       color=color, alpha=0.85, edgecolor='black', linewidth=0.5)

                # Extract instance identifier for label
                label = None
                if '__' in task_id:
                    label = task_id.split('__')[-1]
                elif '_' in task_id:
                    parts = task_id.split('_')
                    for part in reversed(parts):
                        if part.isdigit() or (len(part) > 0 and part[-1].isdigit()):
                            label = part
                            break

                # Add label to bar
                if label:
                    fontsize = 8 if duration > 300 else (7 if duration > 100 else 6)
                    ax.text(start + duration/2, y_pos, label,
                           ha='center', va='center', fontsize=fontsize,
                           fontweight='bold', color='white')

            # Format group label
            label = f"{group_key.replace('_', ' ').title()} ({len(group_tasks)})"
            y_labels.append(label)
            y_ticks.append(y_pos)
            y_pos += 1

        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=10)
        ax.set_xlabel('Time', fontsize=12, fontweight='bold')
        ax.set_title(f'Schedule Attempt {attempt} - {len(tasks)} tasks',
                     fontsize=14, fontweight='bold')
        ax.grid(True, axis='x', alpha=0.6, linewidth=1.0)

        output_path = os.path.join(output_dir, f'schedule_attempt_{attempt}.png')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"   📊 Visualization: {output_path}")

    except ImportError:
        print(f"   ⚠ Visualization skipped (matplotlib not available)")
    except Exception as e:
        print(f"   ⚠ Visualization failed: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: llm_scheduler.py <tasknet.tn> [--model MODEL_ID] [--max-attempts N] [--guidance FILE] [--no-visualize]")
        sys.exit(1)

    tasknet_path = sys.argv[1]
    model_id = None
    max_attempts = 20  # Increased default since duration validation is now stricter
    guidance_file = None
    visualize = True  # Automatic by default

    # Parse optional arguments
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == '--model' and i+1 < len(sys.argv):
            model_id = sys.argv[i+1]
        elif arg == '--max-attempts' and i+1 < len(sys.argv):
            max_attempts = int(sys.argv[i+1])
        elif arg == '--guidance' and i+1 < len(sys.argv):
            guidance_file = sys.argv[i+1]
        elif arg == '--no-visualize':
            visualize = False

    # Authenticate with JPL GenAI API
    print("🔐 Authenticating with JPL GenAI API...")
    try:
        access_token = get_jpl_genai_token()
        base_url, subscription_id = get_jpl_genai_config()
        print(f"   Connected to: {base_url}")
    except Exception as e:
        print(f"   ERROR: {e}")
        sys.exit(1)

    headers = {
        "X-Subscription-ID": subscription_id,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    # If no model specified, try to find a Claude Sonnet model
    if not model_id:
        print("📋 Fetching available models...")
        try:
            r = requests.get(base_url + "/models", headers=headers)
            r.raise_for_status()
            available_models = r.json().get("data", [])

            # Try to find Claude Sonnet 4
            claude_models = [m['id'] for m in available_models if 'claude-sonnet-4' in m['id'].lower()]
            if claude_models:
                model_id = claude_models[0]
                print(f"   Using model: {model_id}")
            else:
                # Fallback to any Claude model
                claude_models = [m['id'] for m in available_models if 'claude' in m['id'].lower()]
                if claude_models:
                    model_id = claude_models[0]
                    print(f"   Using model: {model_id}")
                else:
                    print("   ERROR: No Claude models found in your subscription")
                    print("   Available models:", [m['id'] for m in available_models[:5]])
                    sys.exit(1)
        except requests.RequestException as e:
            print(f"   ERROR: Could not fetch models: {e}")
            sys.exit(1)

    print(f"🔄 Converting tasknet: {tasknet_path}")
    tasknet_json = convert_tasknet_to_lean(tasknet_path)
    lean_json_path = '/tmp/tasknet_for_scheduling.lean.json'

    print(f"📊 Analyzing tasknet structure...")
    analysis = analyze_tasknet(tasknet_json)
    print(f"   - {analysis['num_tasks']} tasks to schedule")
    print(f"   - Time horizon: 0 to {analysis['endTime']}")
    print(f"   - {len(analysis['constraint_patterns'])} type-level constraint patterns")

    # Load user guidance if provided
    user_guidance = None
    if guidance_file:
        print(f"📝 Loading user guidance from: {guidance_file}")
        with open(guidance_file, 'r') as f:
            user_guidance = f.read()
        print(f"   Guidance loaded ({len(user_guidance)} chars)")

    # ==================================================================
    # GENERATE-VALIDATE LOOP
    #
    # The core algorithm:
    # 1. LLM generates candidate schedule based on constraints + semantic rules
    # 2. Lean validator checks if schedule is valid
    # 3. If invalid, violations are fed back to LLM for next iteration
    # 4. Repeat until valid schedule found or max attempts reached
    #
    # This approach works because:
    # - Schedule generation is hard (NP-hard search space)
    # - Schedule validation is easy (polynomial time check)
    # - LLM can reason about constraints and learn from violations
    # ==================================================================

    violations = None
    for attempt in range(1, max_attempts + 1):
        # STEP 1: GENERATE candidate schedule with LLM
        print(f"\n🤖 Attempt {attempt}/{max_attempts}: Generating schedule with JPL GenAI API...")

        prompt = build_scheduling_prompt(analysis, tasknet_json, violations, attempt, user_guidance)
        schedule = generate_schedule_with_llm(prompt, base_url, headers, model_id)

        # Save schedule for inspection
        schedule_path = f'/tmp/candidate_schedule_attempt_{attempt}.json'
        with open(schedule_path, 'w') as f:
            json.dump(schedule, f, indent=2)

        print(f"   Scheduled {len(schedule['tasks'])} tasks")

        # Visualize if requested
        visualize_schedule_if_requested(schedule_path, attempt, visualize, output_dir='/tmp')

        # STEP 2: VALIDATE with Lean semantics
        print(f"✅ Validating with Lean...")
        valid, violations = validate_schedule(lean_json_path, schedule_path)

        if valid:
            # SUCCESS - found valid schedule!
            print(f"\n🎉 SUCCESS! Valid schedule found on attempt {attempt}")
            print(f"   Schedule saved to: {schedule_path}")

            # Save final schedule
            final_path = tasknet_path.replace('.tn', '_schedule.json')
            with open(final_path, 'w') as f:
                json.dump(schedule, f, indent=2)
            print(f"   Final schedule: {final_path}")

            # Visualize final schedule if requested
            if visualize:
                final_viz_path = final_path.replace('.json', '.png')
                visualize_schedule_if_requested(final_path, attempt, visualize, output_dir=os.path.dirname(final_path) or '.')
                # Rename to final name
                temp_viz = os.path.join(os.path.dirname(final_path) or '.', f'schedule_attempt_{attempt}.png')
                if os.path.exists(temp_viz):
                    os.rename(temp_viz, final_viz_path)
                    print(f"   📊 Final visualization: {final_viz_path}")

                    # Open the visualization
                    try:
                        import platform
                        system = platform.system()
                        if system == 'Darwin':  # macOS
                            subprocess.run(['open', final_viz_path], check=False)
                        elif system == 'Linux':
                            subprocess.run(['xdg-open', final_viz_path], check=False)
                        elif system == 'Windows':
                            subprocess.run(['start', final_viz_path], shell=True, check=False)
                        print(f"   🖼️  Opening visualization...")
                    except Exception as e:
                        print(f"   ⚠️  Could not auto-open: {e}")

            return 0
        else:
            # STEP 3: FEEDBACK - violations will be included in next prompt
            print(f"❌ Invalid schedule ({len(violations)} violations)")
            if len(violations) <= 5:
                for v in violations:
                    print(f"      {v}")
            else:
                print(f"      Showing first 5 of {len(violations)} violations:")
                for v in violations[:5]:
                    print(f"      {v}")
            # Loop continues with violations fed back to LLM

    print(f"\n❌ FAILED: Could not find valid schedule after {max_attempts} attempts")
    print(f"   Last attempt had {len(violations)} violations")
    return 1

if __name__ == '__main__':
    sys.exit(main())
