# Security and privacy

This repository must never contain real patient, referrer, clinical-trial participant, donor, payment, credential, or staff-account data.

Do not paste personal or health information into GitHub issues, pull requests, Actions logs, fixtures, screenshots, or test data. Use synthetic data only.

The discovery stage rejects private, loopback, link-local, reserved, or otherwise non-public IP addresses; out-of-scope redirects; access-controlled responses; and apparent login portals. It does not brute-force DNS names.

The generated static mirror disables forms and form controls, strips active field names, clears sensitive input values, blocks browser non-read requests and beacons, disables external sensitive transaction links, removes configured tracking references, adds page-level `noindex`, and installs a site-wide `robots.txt` block. The audit treats any incomplete form guard, missing noindex/robots control, remaining configured tracker, active external transaction endpoint, or oversized GitHub file as a failure.

Treat any change that weakens those controls as security-sensitive and require QEI review before deployment.

Do not mirror or publish administration panels, webmail, APIs, VPNs, staging systems, login portals, private documents, backups, or internal subdomains.

Security concerns should be reported through QEI's approved internal security process rather than a public issue.
