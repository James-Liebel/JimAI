# Reaching JimAI from your phone over HTTPS (Tailscale)

This is the recommended way to use JimAI from your phone: a private, encrypted
connection with **real HTTPS** — which is required for the phone features (push
notifications, install-to-home-screen / PWA, and voice input all need a secure
context) and keeps the AI traffic between your two devices only.

It uses **single-origin hosting**: the backend serves the built frontend, so the
whole app is one origin behind `tailscale serve`. That means:

- the backend stays bound to `127.0.0.1` (the fail-closed `assert_safe_bind`
  guard is satisfied — nothing is ever exposed unauthenticated),
- no CORS and no second port to configure,
- Tailscale terminates TLS with a valid Let's Encrypt cert on your MagicDNS name.

> Do **not** use `tailscale funnel` — that exposes the app to the public
> internet. `tailscale serve` (below) keeps it private to your tailnet.

## One-time setup

1. **Install Tailscale** on the laptop and the phone, signed into the same
   account so both are on the same tailnet: <https://tailscale.com/download>.

2. **Enable HTTPS for your tailnet** (admin console → *DNS*): turn on
   **MagicDNS** and **HTTPS Certificates**. Your laptop then has a name like
   `laptop.tailnet-name.ts.net`.

## Each time you want to use it from the phone

From `frontend/`, build the UI so the backend can serve it:

```bash
npm run build
```

From `backend/`, start the backend (loopback default — do not change the bind):

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

On startup you should see: `Serving built frontend from .../frontend/dist
(single-origin mode).` (If you skip `npm run build`, the backend runs API-only
and you'd use the Vite dev server instead.)

Then put HTTPS in front of it with Tailscale (run once; `--bg` keeps it running):

```bash
tailscale serve --bg 8000
```

Verify and get the URL:

```bash
tailscale serve status
```

Open `https://laptop.tailnet-name.ts.net` on the phone. Add it to your home
screen to install it as an app (now possible because it's real HTTPS).

To stop fronting it later:

```bash
tailscale serve reset
```

> CLI note: `tailscale serve` syntax has varied across versions. If
> `tailscale serve --bg 8000` isn't accepted, try
> `tailscale serve --bg --https=443 http://127.0.0.1:8000` or check
> `tailscale serve --help`. `tailscale serve status` always shows the active map.

## Why this is safe / consistent with the local-first design

- **App never leaves loopback.** Tailscale proxies `https://…ts.net` → the
  encrypted WireGuard tunnel → `127.0.0.1:8000` on the laptop. The backend only
  ever binds localhost, so the code-exec / file-read / system-agent endpoints are
  not reachable on your LAN or the internet.
- **End-to-end encrypted, private.** Traffic is direct device-to-device over
  WireGuard. Tailscale's servers coordinate the connection but never see the
  content. For *zero* third party even in coordination, self-host
  [Headscale](https://github.com/juanfont/headscale) or run plain WireGuard —
  same data-path, more setup.
- **CSRF/CORS already handled.** Single-origin means same-origin API calls (no
  CORS). The `X-JimAI-CSRF` header the UI sends satisfies CSRF from any origin.

## Pausing generation from the phone (thermal safety)

The **Pause** control (top bar on desktop, floating pill on mobile) stops all
Ollama generation within ~0.5s and shows live status (Idle / Working / Model
loaded / Paused), so you can confirm from your phone that the laptop GPU isn't
running on nothing. See the generation kill-switch in `models/ollama_client.py`.
