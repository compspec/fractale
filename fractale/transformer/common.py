import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

# Requires Python 3.8+ for dataclass


@dataclass
class JobSpec:
    """
    A scheduler-agnostic data structure for defining a computational job.
    Version 2: Now includes accounting, priority, environment, and more constraints.
    """

    # Job Identity & Accounting
    job_name: Optional[str] = None
    account: Optional[str] = None

    # What to Run
    executable: Optional[str] = None
    arguments: List[str] = field(default_factory=list)
    container_image: Optional[str] = None
    working_directory: Optional[str] = None

    # Custom attributes or options
    attrs: Optional[dict] = field(default_factory=dict)
    options: Optional[dict] = field(default_factory=dict)

    # Resource Requests ---
    num_tasks: int = 1
    num_nodes: int = 1
    cpus_per_task: int = 1
    mem_per_task: Optional[str] = None
    gpus_per_task: int = 0

    # Scheduling and Constraints
    wall_time: Optional[str] = None
    queue: Optional[str] = None
    priority: Optional[int] = None
    exclusive_access: bool = False
    constraints: List[str] = field(default_factory=list)
    begin_time: Optional[str] = None

    # Environment and I/O
    environment: Dict[str, str] = field(default_factory=dict)
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    error_file: Optional[str] = None

    # Dependencies
    depends_on: Optional[Union[str, List[str]]] = None
