import os

# 最初に環境変数設定 (import前に実行!)
os.environ['PYBASEBALL_CACHE'] = '/tmp/.pybaseball'

import boto3
import pandas as pd
from pybaseball import batting_stats, pitching_stats, team_batting, team_pitching, team_fielding
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

def fetch_batting_data(s3_bucket, s3_prefix, start_year, end_year, skip_years):
    """
    打撃成績データを取得してS3に保存
    """
    print(f"\n[Batting Stats] Fetching data from {start_year} to {end_year}...")
    total_records = 0
    failed_years = []
    exported_files = []

    for year in range(start_year, end_year + 1):
        if year in skip_years:
            print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
            failed_years.append(year)
            continue

        try:
            print(f"  Fetching {year} batting data...")
            data = batting_stats(year, qual=100)

            df_clean = data[['Name', 'G', 'AB', 'R', 'H', 'HR', 'RBI', 'SB', 'AVG']].copy()
            df_clean.columns = ['name', 'games', 'at_bats', 'runs', 'hits', 'hr', 'rbi', 'sb', 'avg']
            df_clean['season'] = year
            df_clean['created_at'] = datetime.now()
            df_clean = df_clean.dropna()

            record_count = len(df_clean)
            total_records += record_count

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
            failed_years.append(year)

    return total_records, failed_years, exported_files

def fetch_pitching_data(s3_bucket, s3_prefix, start_year, end_year, skip_years):
    """
    投手成績データを取得してS3に保存
    """
    print(f"\n[Pitching Stats] Fetching data from {start_year} to {end_year}...")
    total_records = 0
    failed_years = []
    exported_files = []

    for year in range(start_year, end_year + 1):
        if year in skip_years:
            print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
            failed_years.append(year)
            continue

        try:
            print(f"  Fetching {year} pitching data...")
            data = pitching_stats(year, qual=50)  # 50イニング以上

            # 投手成績の主要カラムを抽出
            df_clean = data[['Name', 'G', 'W', 'L', 'ERA', 'SO', 'IP', 'WHIP']].copy()
            df_clean.columns = ['name', 'games', 'wins', 'losses', 'era', 'strikeouts', 'innings_pitched', 'whip']
            df_clean['season'] = year
            df_clean['created_at'] = datetime.now()
            df_clean = df_clean.dropna()

            record_count = len(df_clean)
            total_records += record_count

            s3_key = f"{s3_prefix}/year={year}/pitching_stats.parquet"
            parquet_buffer = df_clean.to_parquet(index=False, engine='pyarrow')

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=parquet_buffer
            )

            exported_files.append(s3_key)
            print(f"  ✓ {year}: {record_count} pitchers → s3://{s3_bucket}/{s3_key}")

        except Exception as e:
            print(f"  ✗ {year}: FAILED - {str(e)}")
            failed_years.append(year)

    return total_records, failed_years, exported_files

def fetch_team_batting_data(s3_bucket, s3_prefix, start_year, end_year, skip_years):
    """
    チーム打撃成績データを取得してS3に保存
    """
    print(f"\n[Team Batting Stats] Fetching data from {start_year} to {end_year}...")
    total_records = 0
    failed_years = []
    exported_files = []

    for year in range(start_year, end_year + 1):
        if year in skip_years:
            print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
            failed_years.append(year)
            continue

        try:
            print(f"  Fetching {year} team batting data...")
            data = team_batting(year, year)

            # created_atカラムを追加
            data['created_at'] = datetime.now()

            record_count = len(data)
            total_records += record_count

            s3_key = f"{s3_prefix}/year={year}/team_batting.parquet"
            parquet_buffer = data.to_parquet(index=False, engine='pyarrow')

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=parquet_buffer
            )

            exported_files.append(s3_key)
            print(f"  ✓ {year}: {record_count} teams → s3://{s3_bucket}/{s3_key}")

        except Exception as e:
            print(f"  ✗ {year}: FAILED - {str(e)}")
            failed_years.append(year)

    return total_records, failed_years, exported_files

def fetch_team_pitching_data(s3_bucket, s3_prefix, start_year, end_year, skip_years):
    """
    チーム投手成績データを取得してS3に保存
    """
    print(f"\n[Team Pitching Stats] Fetching data from {start_year} to {end_year}...")
    total_records = 0
    failed_years = []
    exported_files = []

    for year in range(start_year, end_year + 1):
        if year in skip_years:
            print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
            failed_years.append(year)
            continue

        try:
            print(f"  Fetching {year} team pitching data...")
            data = team_pitching(year, year)

            # created_atカラムを追加
            data['created_at'] = datetime.now()

            record_count = len(data)
            total_records += record_count

            s3_key = f"{s3_prefix}/year={year}/team_pitching.parquet"
            parquet_buffer = data.to_parquet(index=False, engine='pyarrow')

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=parquet_buffer
            )

            exported_files.append(s3_key)
            print(f"  ✓ {year}: {record_count} teams → s3://{s3_bucket}/{s3_key}")

        except Exception as e:
            print(f"  ✗ {year}: FAILED - {str(e)}")
            failed_years.append(year)

    return total_records, failed_years, exported_files

def fetch_team_fielding_data(s3_bucket, s3_prefix, start_year, end_year, skip_years):
    """
    チーム守備成績データを取得してS3に保存
    """
    print(f"\n[Team Fielding Stats] Fetching data from {start_year} to {end_year}...")
    total_records = 0
    failed_years = []
    exported_files = []

    for year in range(start_year, end_year + 1):
        if year in skip_years:
            print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
            failed_years.append(year)
            continue

        try:
            print(f"  Fetching {year} team fielding data...")
            data = team_fielding(year, year)

            # created_atカラムを追加
            data['created_at'] = datetime.now()

            record_count = len(data)
            total_records += record_count

            s3_key = f"{s3_prefix}/year={year}/team_fielding.parquet"
            parquet_buffer = data.to_parquet(index=False, engine='pyarrow')

            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=parquet_buffer
            )

            exported_files.append(s3_key)
            print(f"  ✓ {year}: {record_count} teams → s3://{s3_bucket}/{s3_key}")

        except Exception as e:
            print(f"  ✗ {year}: FAILED - {str(e)}")
            failed_years.append(year)

    return total_records, failed_years, exported_files

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

    # 取得する年度範囲
    start_year = int(os.environ.get('START_YEAR', 2015))
    end_year = int(os.environ.get('END_YEAR', 2025))
    skip_years = [2022]  # pybaseballで取得できない年度

    try:
        print(f"Fetching data from {start_year} to {end_year}...")
        print(f"S3 Destination: s3://{s3_bucket}/")

        # 打撃成績データ取得
        batting_records, batting_failed, batting_files = fetch_batting_data(
            s3_bucket, 'batting_stats', start_year, end_year, skip_years
        )

        # 投手成績データ取得
        pitching_records, pitching_failed, pitching_files = fetch_pitching_data(
            s3_bucket, 'pitching_stats', start_year, end_year, skip_years
        )

        # チーム打撃成績データ取得
        team_batting_records, team_batting_failed, team_batting_files = fetch_team_batting_data(
            s3_bucket, 'team_batting_stats', start_year, end_year, skip_years
        )

        # チーム投手成績データ取得
        team_pitching_records, team_pitching_failed, team_pitching_files = fetch_team_pitching_data(
            s3_bucket, 'team_pitching_stats', start_year, end_year, skip_years
        )

        # チーム守備成績データ取得
        team_fielding_records, team_fielding_failed, team_fielding_files = fetch_team_fielding_data(
            s3_bucket, 'team_fielding_stats', start_year, end_year, skip_years
        )

        total_records = (batting_records + pitching_records + team_batting_records +
                        team_pitching_records + team_fielding_records)
        total_files = (len(batting_files) + len(pitching_files) + len(team_batting_files) +
                      len(team_pitching_files) + len(team_fielding_files))
        all_failed = list(set(batting_failed + pitching_failed + team_batting_failed +
                             team_pitching_failed + team_fielding_failed))

        # 全年度失敗チェック
        if total_records == 0:
            raise ValueError("No data exported to S3! All years failed.")

        print(f"\n[Summary] Export completed!")
        print(f"    Player Batting records: {batting_records}")
        print(f"    Player Pitching records: {pitching_records}")
        print(f"    Team Batting records: {team_batting_records}")
        print(f"    Team Pitching records: {team_pitching_records}")
        print(f"    Team Fielding records: {team_fielding_records}")
        print(f"    Total records: {total_records}")
        print(f"    Files exported: {total_files}")

        # 結果サマリー
        s3_path = f"s3://{s3_bucket}/"
        result = {
            'statusCode': 200,
            'body': {
                'message': 'Success',
                'batting_records': batting_records,
                'pitching_records': pitching_records,
                'team_batting_records': team_batting_records,
                'team_pitching_records': team_pitching_records,
                'team_fielding_records': team_fielding_records,
                'total_records': total_records,
                'files_exported': total_files,
                's3_location': s3_path,
                'years': f"{start_year}-{end_year}",
                'failed_years': all_failed,
                'athena_queries': {
                    'batting': f"SELECT * FROM baseball_stats.batting_stats WHERE year = {end_year} LIMIT 10;",
                    'pitching': f"SELECT * FROM baseball_stats.pitching_stats WHERE year = {end_year} LIMIT 10;",
                    'team_batting': f"SELECT * FROM baseball_stats.team_batting_stats WHERE year = {end_year};",
                    'team_pitching': f"SELECT * FROM baseball_stats.team_pitching_stats WHERE year = {end_year};",
                    'team_fielding': f"SELECT * FROM baseball_stats.team_fielding_stats WHERE year = {end_year};"
                }
            }
        }

        print("=" * 60)
        print("✓ Export completed successfully!")
        print(f"📊 Athena Queries:")
        print(f"   Player Batting: SELECT * FROM baseball_stats.batting_stats")
        print(f"   Player Pitching: SELECT * FROM baseball_stats.pitching_stats")
        print(f"   Team Batting: SELECT * FROM baseball_stats.team_batting_stats")
        print(f"   Team Pitching: SELECT * FROM baseball_stats.team_pitching_stats")
        print(f"   Team Fielding: SELECT * FROM baseball_stats.team_fielding_stats")
        if all_failed:
            print(f"⚠️  Note: {len(all_failed)} year(s) failed: {all_failed}")
        print("=" * 60)

        # Slack通知送信
        duration = round(time.time() - start_time, 2)
        send_slack_notification(
            success=True,
            records=total_records,
            years=f"{start_year}-{end_year}",
            failed_years=all_failed,
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
