FROM public.ecr.aws/lambda/python:3.9

# 依存パッケージをインストール（pyarrowはスキップ）
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}" || \
    pip install --no-cache-dir psycopg2-binary==2.9.9 pandas==2.1.4 numpy==1.26.4 --target "${LAMBDA_TASK_ROOT}" && \
    pip install --no-cache-dir --no-deps pybaseball==2.2.7 --target "${LAMBDA_TASK_ROOT}"

# Lambda関数コードをコピー
COPY baseball_lambda.py ${LAMBDA_TASK_ROOT}

# ハンドラー設定
CMD ["baseball_lambda.lambda_handler"]
