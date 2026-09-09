# krkn-lib - Krkn Chaos and Resiliency Testing Foundation Library

## Project Overview

krkn-lib is a Python library that provides the foundational building blocks for [Krkn](https://github.com/krkn-chaos/krkn), a chaos engineering tool for Kubernetes and OpenShift. The library contains classes, models, and helper functions for interacting with Kubernetes/OpenShift APIs, collecting telemetry, monitoring pods, and integrating with observability platforms.

## Purpose

The library serves multiple goals:
- Provide reusable components for chaos scenario development
- Abstract Kubernetes/OpenShift API interactions behind clean interfaces
- Enable telemetry collection and distribution to Elasticsearch, Prometheus
- Improve testability and modularity of the Krkn codebase
- Monitor pod lifecycle events and recovery metrics during chaos experiments

## Repository Structure

```
src/krkn_lib/
├── k8s/                      # Kubernetes integration
│   ├── krkn_kubernetes.py    # Main Kubernetes API wrapper
│   ├── pod_monitor/          # Pod monitoring and lifecycle tracking
│   └── templates/            # Jinja2 templates for K8s resources
├── ocp/                      # OpenShift-specific integration
│   └── krkn_openshift.py     # OpenShift API extensions
├── telemetry/                # Telemetry collection and distribution
│   ├── k8s/                  # Kubernetes telemetry
│   └── ocp/                  # OpenShift telemetry
├── models/                   # Data models and schemas
│   ├── k8s/                  # Kubernetes resource models
│   ├── krkn/                 # Krkn-specific models
│   ├── pod_monitor/          # Pod monitoring models
│   ├── telemetry/            # Telemetry data models
│   └── elastic/              # Elasticsearch models
├── elastic/                  # Elasticsearch integration
│   └── krkn_elastic.py       # ES client wrapper
├── prometheus/               # Prometheus integration
├── utils/                    # Utility functions
│   ├── functions.py          # Common helper functions
│   └── safe_logger.py        # Logging utilities
├── tests/                    # Unit tests
├── aws_tests/                # AWS-specific integration tests
└── version/                  # Version management
```

## Key Technologies

- **Python 3.11+**: Primary language (Python 3.11 and above required)
- **Kubernetes Python Client 34.1.0**: Official Kubernetes API client
- **Poetry**: Dependency management and packaging
- **PyYAML**: YAML parsing for Kubernetes manifests
- **Jinja2**: Templating for dynamic resource generation
- **Elasticsearch 7.13.4**: Telemetry backend integration
- **Prometheus API Client**: Metrics collection
- **Black**: Code formatting (79 character line length)
- **Sphinx**: Documentation generation (reStructuredText format)

## Core Components

### 1. KrknKubernetes (`k8s/krkn_kubernetes.py`)

The main class for Kubernetes API interactions. Provides:
- Cluster configuration management (kubeconfig, service account tokens)
- API client access (CoreV1, AppsV1, BatchV1, NetworkingV1, CustomObjects)
- Node operations (cordon, drain, delete, label)
- Pod operations (create, delete, exec, logs, watch)
- Resource monitoring and event watching
- Template-based resource deployment using Jinja2
- Namespace management
- Service hijacking for chaos scenarios

**Key features:**
- Request chunking (default 250 items) for large responses
- Watch resource with timeout support
- Dynamic client for CRD interactions
- Safe logging to prevent credential exposure

### 2. KrknOpenshift (`ocp/krkn_openshift.py`)

Extends KrknKubernetes with OpenShift-specific functionality:
- MachineConfig and MachineConfigPool operations
- Project (namespace) management with labels
- OpenShift-specific resource types
- Prometheus integration for OpenShift metrics

### 3. Pod Monitor (`k8s/pod_monitor/`)

Tracks pod lifecycle events during chaos experiments:
- Pod status changes (READY, NOT_READY, DELETION_SCHEDULED, DELETED, ADDED)
- Recovery time metrics (readiness time, rescheduling time, total recovery)
- Rescheduled pod detection and correlation
- Snapshot-based monitoring with resource version tracking

**Models:**
- `PodStatus` enum: Pod state definitions
- `PodEvent`: Timestamped status change events
- `MonitoredPod`: Pod with status change history
- `PodsSnapshot`: Cluster-wide pod state snapshot

### 4. Telemetry (`telemetry/`)

Collects and distributes observability data:
- Cluster events with filtering by namespace and severity
- Node information (taints, resources, conditions)
- Prometheus metric queries and time-series data
- Elasticsearch integration for data persistence

**Key models:**
- `ClusterEvent`: Kubernetes event with metadata
- `NodeInfo`: Node details with resources and taints
- `Taint`: Node taint representation

### 5. Models (`models/`)

Type-safe data structures for:
- **k8s models**: Pod, Container, Volume, PVC, Node, ServiceHijacking
- **krkn models**: HogConfig, HogType (resource hogging scenarios)
- **pod_monitor models**: Pod lifecycle tracking (see section 3)
- **telemetry models**: Event and metric structures

### 6. Elasticsearch Integration (`elastic/krkn_elastic.py`)

- Index management and document operations
- Bulk data upload for telemetry
- Query interface for analyzing chaos experiment results

### 7. Utilities (`utils/`)

- **functions.py**: Common helpers (random strings, dictionary filtering, date parsing)
- **safe_logger.py**: Credential-safe logging with pattern redaction

## Development Patterns

### API Client Architecture

All Kubernetes API interactions go through KrknKubernetes properties:
```python
@property
def cli(self) -> client.CoreV1Api:
    return client.CoreV1Api(self.api_client)

@property
def apps_api(self) -> client.AppsV1Api:
    return client.AppsV1Api(self.api_client)
```

This pattern ensures:
- Single configuration source (self.client_config)
- Consistent authentication
- Easy mocking for tests

### Error Handling

Custom exceptions in models:
- `ApiRequestException`: Wraps Kubernetes API errors with context

Methods return typed results or raise explicit exceptions rather than returning None on errors.

### Resource Templates

Uses Jinja2 templates in `k8s/templates/` for dynamic resource generation:
- Allows parameterized chaos scenarios
- Separates resource definitions from logic
- Version-controllable manifests

### Safe Logging

The `SafeLogger` class redacts sensitive information:
- Prevents credential leakage in logs
- Pattern-based redaction for tokens, passwords, keys
- Used throughout the codebase

## Testing

### Test Structure

- **tests/**: Unit tests for core functionality
  - `test_krkn_kubernetes_*.py`: K8s API wrapper tests
  - `test_krkn_prometheus.py`: Prometheus integration tests
  - `test_utils.py`: Utility function tests
  - `test_krkn_kubernetes_pods_monitor_models.py`: Pod monitor model tests

- **aws_tests/**: AWS-specific integration tests
  - Tests telemetry collection in AWS environments

- **my_tests/**: Development/scratch tests (not tracked in git)

### CI/CD Pipeline

Defined in [.github/workflows/build.yaml](.github/workflows/build.yaml):

**Formatting checks:**
- isort (black profile)
- black (79 character line length)
- flake8 linting

**Build and test:**
- Python 3.11 matrix
- Multi-node KinD cluster for integration tests
- Prometheus deployment via redhat-chaos/actions
- Elasticsearch deployment for telemetry tests
- Coverage reporting (badge in README)

**Release workflow:**
- Semantic versioning from git tags
- PyPI publishing on tag pushes
- Documentation generation and deployment

### Running Tests Locally

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Generate coverage
poetry run coverage run -m pytest
poetry run coverage report
```

## Documentation

- **Published docs**: https://krkn-chaos.github.io/krkn-lib-docs/
- **Format**: reStructuredText docstrings
- **Generator**: Sphinx with RTD theme
- **Auto-generated**: On push to main branch

All public APIs must have docstrings following the reStructuredText format:
```python
def example_function(param1: str) -> bool:
    """
    Brief description.

    :param param1: description of param1
    :return: description of return value
    :raises ExceptionType: when this might raise
    """
```

## Version Management

- Uses git tags for versioning (e.g., `v1.0.0`)
- Poetry version set to `0.0.0` (overridden by CI from git tags)
- Version detection in `version/` module
- Follows semantic versioning

## Dependencies

### Core Dependencies

- **kubernetes**: Kubernetes API client
- **PyYAML**: YAML parsing
- **requests**: HTTP client
- **kubeconfig**: Kubeconfig parsing
- **prometheus-api-client**: Prometheus integration
- **elasticsearch**: ES client (version 7.13.4)
- **elasticsearch-dsl**: ES query DSL
- **jinja2**: Template engine (test group only)

### Build Dependencies

- **poetry**: Packaging
- **black**: Code formatting
- **coverage**: Test coverage
- **sphinx**: Documentation

## Code Style

### Line Length: 79 Characters (STRICT REQUIREMENT)

**CRITICAL: Every line of code MUST be ≤79 characters. This is non-negotiable.**

The project enforces this via Black formatter configuration in pyproject.toml and CI checks. When writing code, you must actively ensure compliance.

#### How to Keep Lines Under 79 Characters

**1. Function Calls with Multiple Arguments**
```python
# BAD - Too long
result = some_function(argument1, argument2, argument3, argument4, argument5)

# GOOD - Use parentheses for implicit continuation
result = some_function(
    argument1, argument2, argument3, argument4, argument5
)

# BETTER - One argument per line for many args
result = some_function(
    argument1,
    argument2,
    argument3,
    argument4,
    argument5,
)
```

**2. Long Imports**
```python
# BAD - Too long
from krkn_lib.models.telemetry import ClusterEvent, NodeInfo, Taint, MetricData

# GOOD - Parentheses for multi-line imports
from krkn_lib.models.telemetry import (
    ClusterEvent,
    NodeInfo,
    Taint,
    MetricData,
)
```

**3. Long Strings**
```python
# BAD - Too long
message = "This is a very long error message that exceeds the 79 character limit"

# GOOD - Implicit concatenation
message = (
    "This is a very long error message that exceeds "
    "the 79 character limit"
)

# GOOD - For f-strings
message = (
    f"Pod {pod_name} in namespace {namespace} failed to become "
    f"ready within {timeout} seconds"
)
```

**4. Long Conditionals**
```python
# BAD - Too long
if some_condition and another_condition and yet_another_condition and more:

# GOOD - Break with parentheses
if (
    some_condition
    and another_condition
    and yet_another_condition
    and more
):
```

**5. Dictionary/List Literals**
```python
# BAD - Too long
config = {"key1": "value1", "key2": "value2", "key3": "value3", "key4": "value4"}

# GOOD - One item per line
config = {
    "key1": "value1",
    "key2": "value2",
    "key3": "value3",
    "key4": "value4",
}
```

**6. Method Chaining**
```python
# BAD - Too long
result = obj.method1().method2().method3().method4().method5()

# GOOD - Break after dots
result = (
    obj.method1()
    .method2()
    .method3()
    .method4()
    .method5()
)
```

**7. List Comprehensions**
```python
# BAD - Too long
result = [process_item(item) for item in items if item.matches_criteria()]

# GOOD - Break into multiple lines or use regular loop
result = [
    process_item(item)
    for item in items
    if item.matches_criteria()
]
```

**8. Function Definitions**
```python
# BAD - Too long
def my_function(param1: str, param2: int, param3: bool, param4: dict) -> str:

# GOOD - Break parameters
def my_function(
    param1: str, param2: int, param3: bool, param4: dict
) -> str:

# BETTER - One parameter per line for many params
def my_function(
    param1: str,
    param2: int,
    param3: bool,
    param4: dict,
) -> str:
```

#### What Black Will Do

Black automatically formats code to fit 79 characters when possible:
- Adds trailing commas to encourage vertical formatting
- Breaks lines at natural boundaries (after commas, operators)
- Uses parentheses for implicit line continuation

#### Verification

Before submitting code:
```bash
# Check formatting
black --line-length 79 --check .

# Auto-format (what CI does)
black --line-length 79 .
```

### Other Style Requirements

- **Target Python**: 3.11, 3.12
- **Import sorting**: isort with black profile
- **Linting**: flake8
- **Docstrings**: reStructuredText format
- **Type hints**: Required for all public APIs
- **Trailing commas**: Preferred in multi-line structures

## Current State and Recent Work

Recent commits show focus on:
- Python 3.11+ migration
- Bug fixes (exception handling, attribute errors, proxy URL handling)
- KubeVirt integration for VM chaos scenarios
- Test coverage improvements
- Code quality improvements (typo fixes, duplicate code removal)

### Untracked Files in Workspace

- `LINE_LENGTH_FIX.md`: Documentation for line length standardization
- `POD_MONITOR_FIX_SUMMARY.md`: Pod monitor refactoring notes
- `src/krkn_lib/my_tests/`: Developer test scratch space
- `.coverage`: Coverage report data
- `output.log`, `output.out`: Test/debug output

## Publishing

Published to PyPI as `krkn-lib`:
- PyPI badge: ![PyPI](https://img.shields.io/pypi/v/krkn-lib?label=PyPi)
- Download stats tracked
- Automated releases on tag push via GitHub Actions

## Integration with Krkn

This library is consumed by:
- **Krkn**: Main chaos orchestration tool
- **krkn-hub**: Collection of pre-built chaos scenarios
- Custom chaos scenario implementations

Scenarios import from krkn-lib:
```python
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import Pod, Container
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
```

## Notes for AI Assistants

### CRITICAL REQUIREMENTS

1. **LINE LENGTH: Every single line MUST be ≤79 characters**
   - This is the #1 most important style requirement
   - Check EVERY line you write - no exceptions
   - Use the line-breaking patterns documented in the Code Style section above
   - If a line is close to 79 chars, break it anyway for safety
   - CI will fail if any line exceeds 79 characters

2. **Python version**: Always use Python 3.11+ syntax (required by project)
   - Use modern type hints (e.g., `list[str]` not `List[str]`)
   - Leverage 3.11+ features where appropriate

3. **Type hints**: Required throughout, especially in public APIs
   - All function parameters must have type hints
   - All return types must be specified
   - Use `Optional[T]` for nullable types

### Code Quality Standards

- **Docstrings**: Required for all public functions/classes (reStructuredText format)
- **Error handling**: Raise explicit exceptions, never fail silently
- **Testing**: Add tests in `tests/` for all new functionality
- **Safe logging**: Use SafeLogger for any output that might contain secrets
- **Trailing commas**: Always use in multi-line structures (Black style)

### Project-Specific Guidance

- **Kubernetes versions**: Client version 34.1.0 - check compatibility for new features
- **Pod monitor**: Complex logic for tracking pod recovery - test thoroughly, especially rescheduling
- **Templates**: New chaos scenarios may need Jinja2 templates in `k8s/templates/`
- **Models**: Define dataclasses in `models/` for all structured data passing
- **CI dependencies**: Tests require KinD cluster, Prometheus, and Elasticsearch

### Pre-Submission Checklist

Before considering code complete:
- [ ] Every line is ≤79 characters (count them!)
- [ ] All functions have type hints
- [ ] All public functions have reStructuredText docstrings
- [ ] Tests added for new functionality
- [ ] No credentials or secrets in logs
- [ ] Follows existing code patterns in the module
