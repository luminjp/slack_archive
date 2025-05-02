#!/usr/bin/env python3
"""
Slack Conversation Exporter Bot

Dual-mode operation:
  • Bot mode: pass `--bot` to run as a Slack slash-command bot (Socket Mode).
  • CLI mode: list or archive via command-line arguments.

Bot mode: same OAuth scopes and env vars as before.
CLI mode: requires SLACK_BOT_TOKEN or pass --token.
"""
import os
import sys
import argparse
import logging
import tempfile
import zipfile
import datetime
import zoneinfo
import requests
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Determine timezone from env or default to Asia/Tokyo
TZ_NAME = os.environ.get('TIMEZONE', 'Asia/Tokyo')
try:
    TZ = zoneinfo.ZoneInfo(TZ_NAME)
except Exception:
    TZ = zoneinfo.ZoneInfo('Asia/Tokyo')

# Initialize Slack Bolt App for bot mode
app = App(
    token=os.environ.get('SLACK_BOT_TOKEN'),
    signing_secret=os.environ.get('SLACK_SIGNING_SECRET')
)

# ---- Shared utility functions ----

def list_conversations(client: WebClient) -> list[str]:
    types = ["public_channel", "private_channel", "im", "mpim"]
    convs = []
    cursor = None
    while True:
        resp = client.conversations_list(types=','.join(types), cursor=cursor, limit=200)
        convs.extend(resp.get('channels', []))
        cursor = resp.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break
    items = []
    for c in convs:
        if c.get('is_channel'):
            conv_type = 'channel'
            name = c.get('name')
        elif c.get('is_group'):
            conv_type = 'private_channel'
            name = c.get('name')
        elif c.get('is_im'):
            conv_type = 'dm'
            uid = c.get('user')
            try:
                u = client.users_info(user=uid)['user']
                name = u.get('profile', {}).get('display_name') or u.get('name')
            except SlackApiError:
                name = uid
        elif c.get('is_mpim'):
            conv_type = 'group_dm'
            member_ids = c.get('members', [])
            names = []
            for uid in member_ids:
                try:
                    u = client.users_info(user=uid)['user']
                    names.append(u.get('profile', {}).get('display_name') or u.get('name'))
                except SlackApiError:
                    names.append(uid)
            name = ", ".join(names)
        else:
            conv_type = 'unknown'
            name = c.get('name') or c.get('id')
        items.append(f"{c['id']}: {name} ({conv_type})")
    return items


def download_file(file_info: dict, token: str, dest_dir: str) -> str:
    url = file_info['url_private']
    filename = file_info['name']
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, filename)
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, stream=True)
    resp.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return path


def format_ts(ts: str) -> str:
    try:
        sec = float(ts)
        dt = datetime.datetime.fromtimestamp(sec, TZ)
        return dt.strftime('%Y/%m/%d_%H:%M:%S')
    except Exception:
        return ts


def export_conversation(client: WebClient, conv_id: str, token: str, output_base: str) -> str:
    info = client.conversations_info(channel=conv_id)['channel']
    # Auto-join public channel if needed
    if info.get('is_channel') and not info.get('is_member'):
        try:
            client.conversations_join(channel=conv_id)
        except SlackApiError:
            pass
    conv_name = info.get('name') or conv_id
    date_str = datetime.date.today().strftime('%Y%m%d')
    out_dir = os.path.join(output_base, conv_name)
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{conv_name}_{date_str}.md")
    user_cache: dict[str, str] = {}

    # Fetch and sort messages
    all_msgs = []
    cursor = None
    while True:
        resp = client.conversations_history(channel=conv_id, cursor=cursor, limit=200)
        all_msgs.extend(resp.get('messages', []))
        cursor = resp.get('response_metadata', {}).get('next_cursor')
        if not cursor:
            break
    try:
        all_msgs.sort(key=lambda m: float(m.get('ts', 0)))
    except Exception:
        pass

    # Write to Markdown
    with open(md_path, 'w', encoding='utf-8') as md:
        md.write(f"# Conversation: {conv_name} ({date_str})\n\n")
        for msg in all_msgs:
            ts_fmt = format_ts(msg.get('ts', ''))
            uid = msg.get('user', 'unknown')
            if uid not in user_cache and uid != 'unknown':
                try:
                    u = client.users_info(user=uid)['user']
                    user_cache[uid] = u.get('profile', {}).get('display_name') or u.get('name')
                except SlackApiError:
                    user_cache[uid] = uid
            uname = user_cache.get(uid, 'unknown')
            text = msg.get('text', '')
            text = re.sub(r'(?m)(^```)(?!\n)', '```\n', text)
            text = re.sub(r'(?m)(?<!\n)(```$)', '\n```', text)
            md.write(f"## {ts_fmt} — {uname} (<@{uid}>)\n\n{text}\n\n")
            for f in msg.get('files', []):
                try:
                    local = download_file(f, token, out_dir)
                    md.write(f"![{f['name']}]({os.path.basename(local)})\n\n")
                except:
                    md.write(f"[Failed to download {f['name']}]\n\n")
    return md_path

# ---- Bot command handler ----
@app.command("/export")
def handle_export(ack, respond, command, client: WebClient, logger):
    ack()
    parts = command.get('text', '').strip().split()
    if not parts:
        respond("Usage: `/export list` or `/export archive <conversation_id>`")
        return
    sub = parts[0]
    if sub == 'list':
        items = list_conversations(client)
        respond("Available conversations:\n" + "\n".join(items))
    elif sub == 'archive' and len(parts) >= 2:
        conv = parts[1]
        respond(f"Archiving conversation `{conv}`... this may take a while.")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                md_path = export_conversation(client, conv, os.environ.get('SLACK_BOT_TOKEN'), tmp)
                zip_path = os.path.join(tmp, f"{conv}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(os.path.dirname(md_path)):
                        for file in files:
                            zipf.write(os.path.join(root, file), arcname=file)
                client.files_upload_v2(
                    channels=[command['channel_id']],
                    file=zip_path,
                    filename=f"{conv}.zip",
                    title=f"Archive_{conv}",
                    initial_comment=f"Here is the archived export for `{conv}`."
                )
            except Exception as e:
                logger.error(e)
                respond(f"Failed to archive `{conv}`: {e}")
    else:
        respond("Invalid subcommand. Use `list` or `archive <conversation_id>`." )

# ---- CLI entry point ----
def cli_main():
    parser = argparse.ArgumentParser(description='Export Slack conversations to Markdown')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true', help='List available conversations')
    group.add_argument('--archive', nargs='+', metavar='CONV_ID', help='Archive conversation(s)')
    parser.add_argument('--output-dir', default='exports', help='Directory to save exports')
    parser.add_argument('--token', default=os.environ.get('SLACK_BOT_TOKEN'), help='Slack bot token')
    args = parser.parse_args()
    if not args.token:
        print('Error: Slack token required via --token or SLACK_BOT_TOKEN')
        sys.exit(1)
    client = WebClient(token=args.token)
    if args.list:
        for line in list_conversations(client):
            print(line)
    else:
        for conv in args.archive:
            try:
                md_path = export_conversation(client, conv, args.token, args.output_dir)
                print(f"Exported {conv} to {md_path}")
            except Exception as e:
                print(f"Failed to export {conv}: {e}")

# ---- App start ----
if __name__ == '__main__':
    if '--bot' in sys.argv:
        sys.argv.remove('--bot')
        handler = SocketModeHandler(app, os.environ.get('SLACK_APP_TOKEN'))
        handler.start()
    else:
        cli_main()
