# Slack App Setup Guide

Step-by-step guide to create the Slack bot for monitoring CFIT tickets.

## 1. Create the Slack App

1. Go to **https://api.slack.com/apps**
2. Click **"Create New App"** → **"From scratch"**
3. App Name: `bug-agent-bot`
4. Pick your HiBob workspace
5. Click **Create App**

## 2. Add Bot Token Scopes

1. In the sidebar, go to **OAuth & Permissions**
2. Scroll to **Bot Token Scopes** and add:
   - `channels:history` — read messages in public channels
   - `channels:read` — list public channels
   - `groups:history` — read messages in private channels (if the channel is private)
   - `groups:read` — list private channels (if the channel is private)

## 3. Enable Socket Mode

1. In the sidebar, go to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** ON
3. You'll be prompted to create an **App-Level Token**:
   - Token Name: `socket-token`
   - Scope: `connections:write`
   - Click **Generate**
4. Copy the token (starts with `xapp-`) → save as `SLACK_APP_TOKEN` in your `.env`

## 4. Subscribe to Events

1. In the sidebar, go to **Event Subscriptions**
2. Toggle **Enable Events** ON
3. Under **Subscribe to bot events**, click **Add Bot User Event** and add:
   - `message.channels` — messages in public channels
   - `message.groups` — messages in private channels (if needed)
4. Click **Save Changes**

## 5. Install App to Workspace

1. In the sidebar, go to **OAuth & Permissions**
2. Click **Install to Workspace** (or **Reinstall to Workspace** if updating scopes)
3. Authorize the app
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`) → save as `SLACK_BOT_TOKEN` in your `.env`

## 6. Invite the Bot to the Channel

In Slack, go to the `#workforce-planning-core-bugs` channel and run:

```
/invite @bug-agent-bot
```

Or right-click the channel → **View channel details** → **Integrations** → **Add apps** → select `bug-agent-bot`.

## Token Summary

| Token | Env Var | Starts with |
|-------|---------|-------------|
| App-Level Token (Socket Mode) | `SLACK_APP_TOKEN` | `xapp-` |
| Bot User OAuth Token | `SLACK_BOT_TOKEN` | `xoxb-` |
