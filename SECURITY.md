# Security

Report vulnerabilities privately via **Security → Report a vulnerability**. Never post API keys or camera passwords.

- The API key is stored in the config entry, sent only as `Authorization: Bearer` header to the Alcedo app in your local network and redacted in diagnostics.
- Clips and snapshots are proxied by Home Assistant and require a logged-in user or a signed, time-limited URL.
