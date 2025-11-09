import os
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda, ECR
from diagrams.aws.storage import S3
from diagrams.aws.analytics import Glue, Athena
from diagrams.aws.integration import Eventbridge, SNS
from diagrams.aws.management import Cloudwatch

# GraphVizのPATHを追加
os.environ["PATH"] += os.pathsep + r"C:\Program Files\Graphviz\bin"

with Diagram("Baseball Stats Data Lake Architecture",
             filename="baseball-cdk-architecture",
             direction="TB",
             outformat="png",
             show=False):

    # スケジューラー
    scheduler = Eventbridge("EventBridge Scheduler\n(週次日曜0時 UTC)")

    with Cluster("Data Collection"):
        ecr = ECR("ECR\nv29 Image")
        data_fetch = Lambda("Data Fetch Lambda\n(3008MB, 15min timeout)")

    with Cluster("Data Lake (S3 + Glue)"):
        s3_bucket = S3("S3 Data Lake\nParquet (205KB)\n年度別パーティション")
        glue_db = Glue("Glue Data Catalog\nbaseball_stats DB")

    # クエリエンジン
    athena = Athena("Amazon Athena\nServerless SQL")

    with Cluster("Monitoring"):
        alarms = Cloudwatch("CloudWatch Alarms\n(Errors, Timeout, Throttles)")
        sns = SNS("SNS Topic")
        slack_notifier = Lambda("Slack Notifier")

    # データフロー
    scheduler >> Edge(label="週次実行") >> data_fetch
    ecr >> Edge(label="Image") >> data_fetch
    data_fetch >> Edge(label="4,367 records\n10 Parquet files") >> s3_bucket
    s3_bucket >> Edge(label="Auto catalog") >> glue_db
    glue_db >> Edge(label="Schema") >> athena
    s3_bucket >> Edge(label="Query") >> athena

    # アラートフロー
    data_fetch >> Edge(label="Errors", style="dashed", color="red") >> alarms
    alarms >> sns >> slack_notifier

print("Architecture diagram generated: baseball-cdk-architecture.png")
