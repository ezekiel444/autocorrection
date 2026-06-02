# Custom CA Certificates

Place your CA certificate bundle here as `ca-certificates.crt`.

This file is mounted into containers that need to make HTTPS requests
(e.g., pulling LLM models from Ollama registry).

## Setup

Copy your system's CA bundle (which should already include any corporate proxy certs):

```bash
cp /etc/ssl/certs/ca-certificates.crt ./certs/ca-certificates.crt
```

If your proxy cert is separate, append it first:

```bash
cat /etc/ssl/certs/your-proxy.pem >> /etc/ssl/certs/ca-certificates.crt
sudo update-ca-certificates
cp /etc/ssl/certs/ca-certificates.crt ./certs/ca-certificates.crt
```

## Why?

Corporate proxies (Cato Networks, Zscaler, Netskope) intercept TLS traffic
with their own certificate. Containers don't trust these by default, causing
"certificate signed by unknown authority" errors when pulling models.
