import pybaseball as pyb
import psycopg2
from datetime import datetime

print("🔥 MLBデータ取得中...")

# 2025年シーズンの打者データを取得（100打席以上）
batting_data = pyb.batting_stats(2025, qual=100)

# 必要なカラムだけ抽出（上位20人）
df = batting_data[['Name', 'Team', 'HR', 'AVG', 'RBI']].head(20)

print(f"✅ {len(df)}人の選手データを取得しました")

# RDSに接続
print("🔌 RDSに接続中...")
conn = psycopg2.connect(
    host='baseballcdkstack-baseballdatabase1cf3ef3f-tuii6lbo74pr.cxwioiws4x0q.ap-northeast-1.rds.amazonaws.com',
    database='postgres',
    user='postgres',
    password='to106kita9mA'
)

cur = conn.cursor()

# テーブル作成
print("📊 テーブル作成中...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100),
        team VARCHAR(50),
        home_runs INT,
        batting_avg DECIMAL(5,3),
        rbi INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# データ投入
print("💾 データ投入中...")
for index, row in df.iterrows():
    cur.execute(
        "INSERT INTO players (name, team, home_runs, batting_avg, rbi) VALUES (%s, %s, %s, %s, %s)",
        (row['Name'], row['Team'], int(row['HR']), float(row['AVG']), int(row['RBI']))
    )

conn.commit()
cur.close()
conn.close()

print("🎉 完了！playersテーブルに20人のMLB選手データを投入しました")
