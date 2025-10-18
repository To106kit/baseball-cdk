#!/usr/bin/env python3
"""
Baseball Historical Data Import Script
2015-2025年のMLB打者データをRDSに投入
"""

import pybaseball as pyb
import psycopg2
import pandas as pd
from datetime import datetime

# RDS接続情報
RDS_HOST = 'baseballcdkstack-baseballdatabase1cf3ef3f-tuii6lbo74pr.cxwioiws4x0q.ap-northeast-1.rds.amazonaws.com'
RDS_DATABASE = 'postgres'
RDS_USER = 'postgres'
RDS_PASSWORD = 'to106kita9mA'
RDS_PORT = 5432

print("=" * 60)
print("Baseball Historical Data Import Script")
print("=" * 60)

try:
    # RDSに接続
    print("\n[1] Connecting to RDS PostgreSQL...")
    conn = psycopg2.connect(
        host=RDS_HOST,
        database=RDS_DATABASE,
        user=RDS_USER,
        password=RDS_PASSWORD,
        port=RDS_PORT,
        sslmode='require'
    )
    cur = conn.cursor()
    print("✓ Connected to RDS successfully")

    # 既存テーブルをドロップ（クリーンスレート）
    print("\n[2] Preparing database schema...")
    cur.execute("DROP TABLE IF EXISTS players_historical CASCADE")
    
    # テーブル作成
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players_historical (
            id SERIAL PRIMARY KEY,
            player_name VARCHAR(100),
            season INT,
            team VARCHAR(50),
            position VARCHAR(10),
            games_played INT,
            at_bats INT,
            runs INT,
            hits INT,
            doubles INT,
            triples INT,
            home_runs INT,
            rbi INT,
            stolen_bases INT,
            batting_avg DECIMAL(5,3),
            obp DECIMAL(5,3),
            slg DECIMAL(5,3),
            ops DECIMAL(5,3),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    print("✓ Table created successfully")

    # 2015-2025年のデータを年ごとに取得
    print("\n[3] Fetching historical batting data from pybaseball...")
    print("(This may take a few minutes...)\n")

    all_data = []
    years = range(2015, 2026)  # 2015-2025
    total_records = 0

    for year in years:
        print(f"  Fetching {year} season data...", end='', flush=True)
        try:
            # 100打席以上の打者データを取得
            batting_data = pyb.batting_stats(year, qual=100)
            
            # 必要なカラムだけ抽出
            if batting_data is not None and len(batting_data) > 0:
                batting_data['Season'] = year
                all_data.append(batting_data)
                print(f" ✓ ({len(batting_data)} players)")
                total_records += len(batting_data)
            else:
                print(" (No data)")
        except Exception as e:
            print(f" ✗ Error: {e}")

    print(f"\n  Total records fetched: {total_records}")

    # すべてのデータを結合
    if all_data:
        df_combined = pd.concat(all_data, ignore_index=True)
        print(f"\n[4] Processing data ({len(df_combined)} total rows)...")

        # データの正規化・クリーニング
        df_combined = df_combined.fillna(0)
        df_combined['Season'] = df_combined['Season'].astype(int)

        # 必要なカラムをマッピング
        column_mapping = {
            'Name': 'player_name',
            'Season': 'season',
            'Tm': 'team',
            'Pos': 'position',
            'G': 'games_played',
            'AB': 'at_bats',
            'R': 'runs',
            'H': 'hits',
            '2B': 'doubles',
            '3B': 'triples',
            'HR': 'home_runs',
            'RBI': 'rbi',
            'SB': 'stolen_bases',
            'BA': 'batting_avg',
            'OBP': 'obp',
            'SLG': 'slg',
            'OPS': 'ops',
        }

        # 存在するカラムだけを選択
        existing_cols = [k for k in column_mapping.keys() if k in df_combined.columns]
        df_processed = df_combined[existing_cols].rename(
            columns={k: column_mapping[k] for k in existing_cols}
        )

        print(f"✓ Data processed: {len(df_processed)} rows")

        # RDSに投入
        print("\n[5] Inserting data into RDS...")
        insert_count = 0

        for index, row in df_processed.iterrows():
            try:
                cur.execute("""
                    INSERT INTO players_historical 
                    (player_name, season, team, position, games_played, at_bats, runs, 
                     hits, doubles, triples, home_runs, rbi, stolen_bases, 
                     batting_avg, obp, slg, ops)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    row.get('player_name', ''),
                    int(row.get('season', 0)),
                    row.get('team', ''),
                    row.get('position', ''),
                    int(row.get('games_played', 0)),
                    int(row.get('at_bats', 0)),
                    int(row.get('runs', 0)),
                    int(row.get('hits', 0)),
                    int(row.get('doubles', 0)),
                    int(row.get('triples', 0)),
                    int(row.get('home_runs', 0)),
                    int(row.get('rbi', 0)),
                    int(row.get('stolen_bases', 0)),
                    float(row.get('batting_avg', 0)),
                    float(row.get('obp', 0)),
                    float(row.get('slg', 0)),
                    float(row.get('ops', 0)),
                ))
                insert_count += 1
                
                # 100件ごとにコミット
                if insert_count % 100 == 0:
                    conn.commit()
                    print(f"  Inserted {insert_count} records...", flush=True)
            except Exception as e:
                print(f"  ✗ Error inserting row {index}: {e}")

        conn.commit()
        print(f"✓ Total inserted: {insert_count} records")

        # 統計情報を表示
        print("\n[6] Data Summary:")
        cur.execute("""
            SELECT 
                season, 
                COUNT(*) as player_count,
                ROUND(AVG(home_runs)::numeric, 2) as avg_hr,
                MAX(home_runs) as max_hr
            FROM players_historical
            GROUP BY season
            ORDER BY season DESC
        """)
        
        results = cur.fetchall()
        print("\n  Season | Players | Avg HR | Max HR")
        print("  " + "-" * 40)
        for row in results:
            print(f"  {row[0]}   | {row[1]:7d} | {row[2]:6} | {row[3]:6}")

        print("\n" + "=" * 60)
        print("✓ Import completed successfully!")
        print("=" * 60)

    else:
        print("No data fetched from pybaseball")

    cur.close()
    conn.close()

except psycopg2.Error as e:
    print(f"✗ Database error: {e}")
except Exception as e:
    print(f"✗ Error: {e}")
