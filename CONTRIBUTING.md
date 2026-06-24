# How to Contribute

We're excited to have you consider contributing to krkn-lib! Contributions are always appreciated.

krkn-lib is the foundation library for [Krkn](https://github.com/krkn-chaos/krkn), providing classes, models, and helper functions used to interact with Kubernetes, OpenShift, and other external APIs. Contributions that improve the library's reliability, test coverage, and documentation are especially welcome.

## Getting Started

If you would like to contribute to krkn-lib but are not sure exactly what to work on, you can find a number of open issues that are awaiting contributions in
[issues](https://github.com/krkn-chaos/krkn-lib/issues?q=is%3Aissue+state%3Aopen+label%3A%22good+first+issue%22).

Please start by discussing potential solutions and your proposed approach for the issue you plan to work on. We encourage you to gather feedback from maintainers and contributors and to have the issue assigned to you before opening a pull request with a solution.

## Development Environment

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/) (1.8.x recommended)

### Setup

1. Fork the repository and clone your fork:
   ```bash
   git clone https://github.com/<your-username>/krkn-lib.git
   cd krkn-lib
   ```

2. Install dependencies with Poetry:
   ```bash
   poetry install --no-interaction
   ```

### Code Formatting

This project uses [Black](https://github.com/psf/black), [isort](https://pycqa.github.io/isort/), and [flake8](https://flake8.pycqa.org/) for code formatting and linting. CI will check formatting automatically.

To run formatting checks locally:
```bash
pip install black flake8 isort
isort --profile black .
black --line-length 79 .
flake8 --max-line-length 79 --extend-ignore E501 .
```

## Running Tests

Tests are run using Python's built-in `unittest` framework with `coverage`:

```bash
poetry run python3 -m coverage run -a -m unittest discover -v src/krkn_lib/tests/
poetry run python3 -m coverage html
```

> **Note:** The full CI test suite requires a running Kubernetes cluster (via KinD), Prometheus, and Elasticsearch. Some tests may be skipped in a local environment without these services. See `.github/workflows/build.yaml` for the complete CI setup.

## Pull Request Process

### Good PR Checklist

- One feature/change per PR
- One commit per PR (squash your commits)
- PR rebased on `main` (`git rebase`, not `git pull`)
- Good descriptive commit message, with link to issue
- No changes to code not directly related to your PR
- Includes tests where applicable
- Fill out the [PR template](.github/PULL_REQUEST_TEMPLATE.md)

### Work in Progress PRs

If you are working on a contribution and would like to get a new set of eyes on your work, go ahead and open a PR with `[WIP]` at the start of the title and tag the [maintainers](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md) for review. We will review your changes and give you suggestions to keep you moving!

## DCO Sign-Off

All commits must include a Developer Certificate of Origin (DCO) sign-off line:

```
Signed-off-by: Your Name <your.email@example.com>
```

You can add this automatically by committing with:
```bash
git commit -s
```

This is enforced by CI. PRs without DCO sign-off will be labeled `needs-dco` and cannot be merged.

## Reporting Issues

If you find a bug, have a question, or want to suggest an enhancement, please open a [GitHub issue](https://github.com/krkn-chaos/krkn-lib/issues). Include reproduction steps and relevant environment details where applicable.

## Office Hours

If you have any questions that you think could be better discussed in a meeting, we have monthly office hours — [Zoom link](https://zoom-lfx.platform.linuxfoundation.org/meetings/krkn?view=month). Please add items to the agenda beforehand so we can best prepare to help you.

## AI-Assisted Contributions

We welcome contributions that use AI tools (LLMs, code generators, AI coding agents, etc.) as development assistants. If you use AI tools in your contribution, please disclose AI usage in your commit trailers and make sure you understand and can explain every line of code you submit. See the krkn project's [AI Contribution Policy](https://github.com/krkn-chaos/krkn/blob/main/AI_CONTRIBUTION_POLICY.md) for full details.

## Ecosystem Policies

krkn-lib is part of the [Krkn](https://github.com/krkn-chaos/krkn) ecosystem. The following policies apply across all Krkn repositories:

- [Code of Conduct](https://github.com/krkn-chaos/krkn/blob/main/CODE_OF_CONDUCT.md)
- [Governance](https://github.com/krkn-chaos/krkn/blob/main/GOVERNANCE.md)
- [Maintainers](https://github.com/krkn-chaos/krkn/blob/main/MAINTAINERS.md)
- [Krkn Contribution Guide](https://github.com/krkn-chaos/krkn/blob/main/CONTRIBUTING.md) — for roadmap proposals, ecosystem-wide conventions, and new scenario guidelines

## Questions?

Reach out to us on Slack if you ever have any questions or want to know how to get started. You can join the Kubernetes Slack [here](https://communityinviter.com/apps/kubernetes/community) and find us in the [#krkn channel](https://kubernetes.slack.com/archives/C05SFMHRWK1).
