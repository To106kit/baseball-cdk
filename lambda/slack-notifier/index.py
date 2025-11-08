import json
import urllib3
import os
from datetime import datetime

http = urllib3.PoolManager()

def lambda_handler(event, context):
    """
    SNSからのCloudWatchアラーム通知をSlackに転送
    """
    
    webhook_url = os.environ['SLACK_WEBHOOK_URL']
    
    # SNSメッセージを解析
    sns_message = json.loads(event['Records'][0]['Sns']['Message'])
    
    alarm_name = sns_message.get('AlarmName', 'Unknown Alarm')
    new_state = sns_message.get('NewStateValue', 'UNKNOWN')
    reason = sns_message.get('NewStateReason', 'No reason provided')
    
    # Slackメッセージ作成
    if new_state == 'ALARM':
        color = 'danger'
        emoji = ':rotating_light:'
    elif new_state == 'OK':
        color = 'good'
        emoji = ':white_check_mark:'
    else:
        color = 'warning'
        emoji = ':warning:'
    
    # タイムスタンプ処理 (ISO 8601 → Unix timestamp)
    timestamp_str = event['Records'][0]['Sns']['Timestamp']
    try:
        # ISO 8601形式をパース
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        unix_timestamp = int(dt.timestamp())
    except:
        # パース失敗時は現在時刻
        unix_timestamp = int(datetime.now().timestamp())
    
    slack_message = {
        'attachments': [{
            'color': color,
            'title': f'{emoji} CloudWatch Alarm: {alarm_name}',
            'fields': [
                {
                    'title': 'Status',
                    'value': new_state,
                    'short': True
                },
                {
                    'title': 'Reason',
                    'value': reason,
                    'short': False
                }
            ],
            'footer': 'Baseball DB Monitoring',
            'ts': unix_timestamp
        }]
    }
    
    # Slackに送信
    response = http.request(
        'POST',
        webhook_url,
        body=json.dumps(slack_message),
        headers={'Content-Type': 'application/json'}
    )
    
    return {
        'statusCode': response.status,
        'body': json.dumps('Notification sent to Slack')
    }