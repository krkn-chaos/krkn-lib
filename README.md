![action](https://github.com/krkn-chaos/krkn-lib/actions/workflows/build.yaml/badge.svg)
![coverage](https://krkn-chaos.github.io/krkn-lib-docs/coverage_badge.svg)
![PyPI](https://img.shields.io/pypi/v/krkn-lib?label=PyPi)
![PyPI - Downloads](https://img.shields.io/pypi/dm/krkn-lib)
# krkn-lib
## Krkn Chaos and resiliency testing tool Foundation Library

### Contents
The Library contains Classes, Models and helper functions used in [Kraken](https://github.com/redhat-chaos/krkn) to interact with
Kubernetes, Openshift and other external APIS.
The goal of this library is to give to developers the building blocks to realize new Chaos 
Scenarios and to increase the testability and the modularity of the Krkn codebase.

### Packages

The library is subdivided in several Packages

- **ocp:** Openshift Integration
- **k8s:** Kubernetes Integration
- **telemetry:** 
- - **k8s:** Kubernetes Telemetry collection and distribution
- - **ocp:** Openshift Telemetry collection and distribution
- **models:** Krkn shared data models
- **utils:** common functions

### Documentation

The Library documentation is available [here](https://redhat-chaos.github.io/krkn-lib-docs/).
The documentation is automatically generated by [Sphinx](https://www.sphinx-doc.org/en/master/) on top
of the [reStructuredText Docstring Format](https://peps.python.org/pep-0287/) comments present in the code.


