# Helix Dashboard setup

The dashboard is served by the Helix bot itself at `http://127.0.0.1:8080` by default. It is a secure management surface—not a static mockup—and writes approved settings to the same database used by the Discord commands.

## Required environment values

Create a Discord OAuth2 redirect in the application Developer Portal, then add the following to `.env` (never commit this file):

```dotenv
DASHBOARD_CLIENT_ID=your_discord_application_id
DASHBOARD_CLIENT_SECRET=your_discord_oauth_client_secret
DASHBOARD_REDIRECT_URI=https://your-dashboard-domain.com/auth/callback
DASHBOARD_SESSION_SECRET=a_long_random_value_at_least_32_characters
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080
DASHBOARD_SECURE_COOKIES=true
```

For local testing, set the redirect URI to `http://127.0.0.1:8080/auth/callback` in both Discord's Developer Portal and `.env`, and set `DASHBOARD_SECURE_COOKIES=false`. Use HTTPS and `true` when deployed.

## Permission model

Discord login requests only the `identify` and `guilds` scopes. A server appears only if Helix is installed there and the logged-in user is its owner or has **Manage Server** / **Administrator** permission. Configuration requests repeat this check server-side. Cookies are signed, HTTP-only, short-lived, and kept only in process memory.

## Deployment

Put the bot/dashboard behind an HTTPS reverse proxy such as Caddy, Nginx, or Cloudflare Tunnel, make the public URL the OAuth redirect URI, set secure cookies to `true`, and keep the dashboard client secret and bot token only in environment variables.

The dashboard deliberately does not expose raw `eval`, bot-token administration, global profile changes, or destructive voice controls. Keep those owner-only operations in Discord.
