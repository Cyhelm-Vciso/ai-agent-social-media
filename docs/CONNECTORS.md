# Connecting social networks

Every connector is optional. Without any, SocialAgent still writes posts and opens each platform's own post box
with the text filled in ("manual" route), or you copy and paste.

Fill `config/accounts.json` (copied from `accounts.example.json`), set `"enabled": true`, restart the agent,
and check the **Brand & accounts** tab to see which route each platform uses. Posting only happens for real when
`"dry_run": false` in `config/settings.json`.

Platform APIs, permissions and pricing change often. If a request fails, the error message from the platform is
shown on the draft; check the platform's developer documentation.

## Mastodon
1. Your instance → Preferences → Development → New application, scope `write:statuses`.
2. Copy the access token. Set `instance` (e.g. `https://mastodon.social`) and `access_token`.

## Bluesky
1. Settings → Privacy and security → App passwords → Add. **Never use your main password.**
2. Set `handle` (e.g. `you.bsky.social`) and `app_password`. Links and hashtags are made clickable automatically.

## X (Twitter)
1. Create a project and app at the X developer portal, with **Read and write** user authentication.
2. Generate the API key and secret (consumer) and the access token and secret for your account.
3. Fill `consumer_key`, `consumer_secret`, `access_token`, `access_token_secret`. Posts go to `POST /2/tweets`.
   Your developer plan's posting limits apply.

## LinkedIn
1. Create an app at the LinkedIn developer portal and add the product that grants `w_member_social`
   (posting as yourself; company pages need organisation permissions).
2. Get an OAuth 2.0 access token and your member URN (`urn:li:person:...`).
3. Set `api_version` to a currently supported `YYYYMM` version from LinkedIn's API docs; LinkedIn retires old ones.
   Special characters are escaped so your text appears exactly as written.

## Facebook Page
1. In Meta for Developers, create an app and obtain a **Page access token** with permission to publish to the Page.
2. Set `page_id`, `page_access_token`, and a current `graph_version` (e.g. `v21.0`).

## Telegram channel
1. Create a bot with @BotFather and copy its token.
2. Add the bot to your channel as an admin. Set `chat_id` to `@yourchannel` (or the numeric ID).

## Discord
Channel settings → Integrations → Webhooks → New webhook → copy URL into `webhook_url`.

## Everything else: the webhook bridge
Instagram, TikTok, YouTube, Pinterest, Threads, Google Business Profile and others either need media uploads or app
review that a pocket app can't do alone. Use an automation service you already trust:

1. In **Make**, **Zapier**, **n8n** (can be self-hosted), **IFTTT**, or **Buffer**, create a scenario that starts with a
   *webhook* trigger.
2. Put its URL in `webhook.url`. Optionally set `secret_header`/`secret_value` and check it in the scenario.
3. SocialAgent sends approved posts as JSON:
   ```json
   {"platform": "instagram", "text": "...", "draft_id": 12, "scheduled_for": "2026-11-10 09:00", "source": "social-agent"}
   ```
4. Route on `platform` to the matching module (e.g. Instagram for Business, TikTok, Buffer "create post"), adding
   the image or video there.

Platforms with a direct connector enabled use it; every other platform uses the webhook if it's enabled.

## Bulk scheduling via CSV
Drafts → **Export CSV** gives `id, platform, status, scheduled_for, text`, which you can adapt for bulk-upload tools.
