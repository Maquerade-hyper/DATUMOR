# DATUMOR Security Policy

## Reporting a vulnerability

Do not publish exploitable vulnerability details in a public issue.

Use the repository host's private vulnerability reporting feature if it is enabled. Otherwise, contact the project maintainers through a private channel and request a secure reporting method before sharing sensitive details.

Do not include real credentials, customer data, private datasets, or production access tokens in a report.

## What to include

Please provide:

- A concise description of the affected component.
- The impact and realistic attack scenario.
- Reproduction steps or a minimal proof of concept.
- Relevant versions, configuration, and logs with secrets removed.
- Any suggested mitigation, if known.

## Scope and response

The maintainers will review reports and work to reproduce and assess valid issues. Response and remediation timelines depend on severity, reproducibility, and maintainer availability.

Do not access, modify, or exfiltrate data that does not belong to you while researching a potential vulnerability.

## Deployment guidance

- Never commit `.env` or real secrets.
- Use strong, unique credentials.
- Keep databases, Redis, and object storage on trusted networks.
- Run workers with an unprivileged account.
- Keep dependencies and base images updated.
- Back up persistent data and test recovery procedures.