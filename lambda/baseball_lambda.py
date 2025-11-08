import os

# 最初に環境変数設定 (import前に実行!)
os.environ['PYBASEBALL_CACHE'] = '/tmp/.pybaseball'

import psycopg2
import pandas as pd
from pybaseball import batting_stats
from datetime import datetime
import json
import urllib3

def send_slack_notification(success=True, records=0, years="", failed_years=None, duration=0, error_msg=""):
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
            title = f"{emoji} Baseball Data Import Completed"

            fields = [
                {"title": "Status", "value": "Success", "short": True},
                {"title": "Records", "value": str(records), "short": True},
                {"title": "Years", "value": years, "short": True},
                {"title": "Duration", "value": f"{duration}s", "short": True}
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
            title = f"{emoji} Baseball Data Import Failed"

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
                "footer": "Baseball Lambda",
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
    Lambda関数のエントリーポイント
    """
    import time
    start_time = time.time()

    print("=" * 60)
    print("Baseball Historical Data Import - Lambda Version")
    print("=" * 60)

    # 環境変数から接続情報取得
    db_config = {
        'host': os.environ['DB_HOST'],
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ['DB_NAME'],
        'user': os.environ['DB_USER'],
        'password': os.environ['DB_PASSWORD'],
        'sslmode': 'require'
    }
    
    # 取得する年度範囲
    start_year = int(os.environ.get('START_YEAR', 2015))
    end_year = int(os.environ.get('END_YEAR', 2017))
    skip_years = [2022]  # pybaseballで取得できない年度
    
    try:
        # データ取得
        print(f"[1] Fetching data from {start_year} to {end_year}...")
        all_data = []
        failed_years = []
        
        for year in range(start_year, end_year + 1):
            # スキップ対象の年度チェック
            if year in skip_years:
                print(f"  ⊘ {year}: SKIPPED (pybaseball limitation)")
                failed_years.append(year)
                continue
            try:
                print(f"  Fetching {year} season data...")
                data = batting_stats(year, qual=100)
                data['season'] = year
                all_data.append(data)
                print(f"  ✓ {year}: {len(data)} players")
            except Exception as e:
                print(f"  ✗ {year}: FAILED - {str(e)}")
                print(f"  → Skipping {year} and continuing...")
                failed_years.append(year)
                continue
        
        # 失敗した年度をサマリー表示
        if failed_years:
            print(f"\n⚠️  Failed to fetch data for years: {failed_years}")
        
        # 全年度失敗チェック
        if not all_data:
            raise ValueError("No data fetched from any year! All years failed.")
        
        df = pd.concat(all_data, ignore_index=True)
        print(f"Total records: {len(df)}")
        
        # データ処理
        print("[2] Processing data...")
        df_clean = df[['Name', 'season', 'G', 'AB', 'R', 'H', 'HR', 'RBI', 'SB', 'AVG']].copy()
        df_clean.columns = ['name', 'season', 'games', 'at_bats', 'runs', 'hits', 'hr', 'rbi', 'sb', 'avg']
        df_clean = df_clean.dropna()
        
        # RDS接続
        print("[3] Connecting to RDS...")
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        
        # テーブル作成
        print("[4] Creating table if not exists...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS baseball_batting_historical (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            season INTEGER,
            games INTEGER,
            at_bats INTEGER,
            runs INTEGER,
            hits INTEGER,
            hr INTEGER,
            rbi INTEGER,
            sb INTEGER,
            avg DECIMAL(5,3),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cur.execute(create_table_sql)
        conn.commit()
        
        # データ挿入
        print("[5] Inserting data...")
        insert_count = 0
        for _, row in df_clean.iterrows():
            insert_sql = """
            INSERT INTO baseball_batting_historical 
            (name, season, games, at_bats, runs, hits, hr, rbi, sb, avg)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name, season) 
            DO UPDATE SET
                games = EXCLUDED.games,
                at_bats = EXCLUDED.at_bats,
                runs = EXCLUDED.runs,
                hits = EXCLUDED.hits,
                hr = EXCLUDED.hr,
                rbi = EXCLUDED.rbi,
                sb = EXCLUDED.sb,
                avg = EXCLUDED.avg
            """
            cur.execute(insert_sql, tuple(row))
            insert_count += 1
            
            if insert_count % 100 == 0:
                print(f"  Inserted {insert_count} records...")
        
        conn.commit()
        print(f"✓ Total inserted: {insert_count} records")
        
        # クリーンアップ
        cur.close()
        conn.close()
        
        # 結果サマリー
        result = {
            'statusCode': 200,
            'body': {
                'message': 'Success',
                'records_inserted': insert_count,
                'years': f"{start_year}-{end_year}",
                'failed_years': failed_years
            }
        }
        
        print("=" * 60)
        print("✓ Import completed successfully!")
        if failed_years:
            print(f"⚠️  Note: {len(failed_years)} year(s) failed: {failed_years}")
        print("=" * 60)

        # Slack通知送信
        duration = round(time.time() - start_time, 2)
        send_slack_notification(
            success=True,
            records=insert_count,
            years=f"{start_year}-{end_year}",
            failed_years=failed_years,
            duration=duration
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