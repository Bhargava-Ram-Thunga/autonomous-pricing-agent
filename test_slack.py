import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv; load_dotenv()
import os
from slack_sdk import WebClient

bot = os.environ.get('SLACK_BOT_TOKEN', '')
ch  = os.environ.get('SLACK_CHANNEL', '')
print(f'token: {bot[:15]}...')
print(f'channel: {ch}')

try:
    r = WebClient(token=bot).chat_postMessage(channel=ch, text='🧪 Test message from Pricing Agent')
    print(f'sent ok, ts={r["ts"]}')
except Exception as e:
    print(f'ERROR: {e}')
