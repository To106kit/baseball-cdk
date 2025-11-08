FROM public.ecr.aws/lambda/python:3.9

# 依存パッケージをインストール
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}" || \
    pip install --no-cache-dir boto3==1.34.34 pandas==2.1.4 numpy==1.26.4 pyarrow==14.0.1 --target "${LAMBDA_TASK_ROOT}" && \
    pip install --no-cache-dir --no-deps pybaseball==2.2.7 --target "${LAMBDA_TASK_ROOT}"

# Lambda関数コードをコピー
COPY baseball_lambda.py ${LAMBDA_TASK_ROOT}

# ハンドラー設定
CMD ["baseball_lambda.lambda_handler"]
