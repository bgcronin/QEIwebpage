# Deployment checklist

The generated `site/` directory is a review snapshot, not a production clinical website.

Before a public cutover, QEI should approve all of the following:

- ownership and permitted use of QEI and third-party text, images, video, documents, fonts, and trademarks;
- clinical-content review dates, named reviewers, escalation pathways, and emergency wording;
- accessibility testing against WCAG 2.2 AA, including keyboard use, focus order, labels, contrast, zoom, screen readers, captions, and PDFs;
- Australian Privacy Principles compliance, privacy notices, cookie/analytics consent, data retention, breach response, and a privacy impact assessment;
- secure patient, referrer, medical-record, clinical-trial, newsletter, donation, and payment workflows hosted on approved systems;
- HTTPS, HSTS, Content Security Policy, secure headers, dependency review, vulnerability scanning, backups, logging, alerting, and incident response;
- canonical URLs, redirects, XML sitemaps, robots rules, structured data, analytics, Search Console, and removal of temporary `noindex` only at the approved launch;
- DNS, email authentication, uptime monitoring, disaster recovery, and a rollback plan;
- final review on representative phones, tablets, desktops, browsers, and slower connections.

GitHub Pages is suitable for a private review preview only when approved by QEI. A production deployment should use QEI-controlled hosting, domains, access, observability, and change management.
