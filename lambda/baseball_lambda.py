import os

# 最初に環境変数設定 (import前に実行!)
os.environ['PYBASEBALL_CACHE'] = '/tmp/.pybaseball'

import boto3
import pandas as pd
from pybaseball import batting_stats
from datetime import datetime
import json
import urllib3

s3_client = boto3.client('s3')

def send_slack_notification(success=True, records=0, years="", failed_years=None, duration=0, error_msg="", s3_path=""):
    """
    Slack通知を送信
    """
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if not webhook_url:
        print("⚠️  SLACK_WEBHOOK_URL not set, skipping notification")
        return

    try:
        http = urllib3.PoolManager()

        if success:
            # 成功時の通知
            color = "good"
            emoji = ":white_check_mark:"
            title = f"{emoji} Baseball Data Export Completed"

            fields = [
                {"title": "Status", "value": "Success", "short": True},
                {"title": "Records", "value": str(records), "short": True},
                {"title": "Years", "value": years, "short": True},
                {"title": "Duration", "value": f"{duration}s", "short": True},
                {"title": "S3 Location", "value": s3_path, "short": False}
            ]

            if failed_years:
                fields.append({
                    "title": "Failed Years",
                    "value": str(failed_years),
                    "short": False
                })
        else:
            # エラー時の通知
            color = "danger"
            emoji = ":x:"
            title = f"{emoji} Baseball Data Export Failed"

            fields = [
                {"title": "Status", "value": "Failed", "short": True},
                {"title": "Duration", "value": f"{duration}s", "short": True},
                {"title": "Error", "value": error_msg[:500], "short": False}
            ]

        slack_message = {
            "attachments": [{
                "color": color,
                "title": title,
                "fields": fields,
                "footer": "Baseball Lambda (Data Lake)",
                "ts": int(datetime.now().timestamp())
            }]
        }

        response = http.request(
            'POST',
            webhook_url,
            body=json.dumps(slack_message),
            headers={'Content-Type': 'application/json'}
        )

        if response.status == 200:
            print("✓ Slack notification sent successfully")
        else:
            print(f"⚠️  Slack notification failed: {response.status}")

    except Exception as e:
        print(f"⚠️  Failed to send Slack notification: {str(e)}")

def lambda_handler(event, context):
    """
    Lambda関数のエントリーポイント - S3 Data Lake版
    """
    import time
    start_time = time.time()

    print("=" * 60)
    print("Baseball Historical Data Export to S3 Data Lake")
    print("=" * 60)

    # 環境変数取得
    s3_bucket = os.environ['S3_BUCKET']
    s3_prefix = os.environ.get('S3_PREFIX', 'batting_stats')

    # 取得する年度範囲
    start_year = int(os.environ.get('START_YEAR', 2015))
    end_year = int(os.environ.get('END_YEAR', 2025))
    skip_years = [2022]  # pybaseballで取得できない年度

    try:
        print(f"[1] Fetching data from {start_year} to {end_year}...")
        print(f"    S3 Destination: s3://{s3_bucket}/{s3_prefix}/")

        total_records = 0
        failed_years = []
        exported_files = []

        for year in range(start_year, end_year + 1):
            # スキップ対象の年度チェック
            if year in skip_years:
                print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
                failed_years.append(year)
                continue

            try:
                print(f"  Fetching {year} season data...")
                data = batting_stats(year, qual=100)

                # データ処理
                df_clean = data[['Name', 'G', 'AB', 'R', 'H', 'HR', 'RBI', 'SB', 'AVG']].copy()
                df_clean.columns = ['name', 'games', 'at_bats', 'runs', 'hits', 'hr', 'rbi', 'sb', 'avg']
                df_clean['season'] = year
                df_clean['created_at'] = datetime.now()
                df_clean = df_clean.dropna()

                record_count = len(df_clean)
                total_records += record_count

                # Parquet形式でS3に保存（年度別パーティション）
                s3_key = f"{s3_prefix}/year={year}/batting_stats.parquet"
                parquet_buffer = df_clean.to_parquet(index=False, engine='pyarrow')

                s3_client.put_object(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    Body=parquet_buffer
                )

                exported_files.append(s3_key)
                print(f"  ✓ {year}: {record_count} players → s3://{s3_bucket}/{s3_key}")

            except Exception as e:
                print(f"  ✗ {year}: FAILED - {str(e)}")
                print(f"  → Skipping {year} and continuing...")
                failed_years.append(year)
                continue

        # 失敗した年度をサマリー表示
        if failed_years:
            print(f"\n⚠️  Failed to fetch data for years: {failed_years}")

        # 全年度失敗チェック
        if total_records == 0:
            raise ValueError("No data exported to S3! All years failed.")

        print(f"\n[2] Export completed!")
        print(f"    Total records: {total_records}")
        print(f"    Files exported: {len(exported_files)}")

        # 結果サマリー
        s3_path = f"s3://{s3_bucket}/{s3_prefix}/"
        result = {
            'statusCode': 200,
            'body': {
                'message': 'Success',
                'total_records': total_records,
                'files_exported': len(exported_files),
                's3_location': s3_path,
                'years': f"{start_year}-{end_year}",
                'failed_years': failed_years,
                'athena_query': f"SELECT * FROM baseball_stats.batting_stats WHERE year = {end_year} LIMIT 10;"
            }
        }

        print("=" * 60)
        print("✓ Export completed successfully!")
        print(f"📊 Athena Query: SELECT * FROM baseball_stats.batting_stats")
        if failed_years:
            print(f"⚠️  Note: {len(failed_years)} year(s) failed: {failed_years}")
        print("=" * 60)

        # Slack通知送信
        duration = round(time.time() - start_time, 2)
        send_slack_notification(
            success=True,
            records=total_records,
            years=f"{start_year}-{end_year}",
            failed_years=failed_years,
            duration=duration,
            s3_path=s3_path
        )

        return result

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

        # エラー時のSlack通知
        duration = round(time.time() - start_time, 2)
        send_slack_notification(
            success=False,
            duration=duration,
            error_msg=str(e)
        )

        return {
            'statusCode': 500,
            'body': {
                'message': 'Error',
                'error': str(e)
            }
        }
