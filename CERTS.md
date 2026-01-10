Self-signed certificate for local development

Files generated:
- `static/certs/selfsigned.crt` — public certificate (PEM)
- `static/certs/selfsigned.key` — private key (PEM)

How to use:
- Nginx is configured to use these files and listens on port 443. The docker-compose file exposes port 443 ("443:443").
- In your browser, the certificate will be untrusted (self-signed). To avoid browser warnings, add `static/certs/selfsigned.crt` to your OS/browser trusted certificates.

Replace certs for production:
- Generate a proper certificate (e.g., Let's Encrypt) and copy `fullchain.pem` and `privkey.pem` into `static/certs/`, then update `nginx/nginx.conf` to point `ssl_certificate` and `ssl_certificate_key` to the new files.

Security note:
- Do NOT use these self-signed certs in production. The private key is stored here for local development convenience and should be kept out of public repositories if you plan to push the repo somewhere public.