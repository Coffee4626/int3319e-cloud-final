FROM public.ecr.aws/lambda/python:3.12
RUN dnf install -y libgomp && dnf clean all
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c "from autogluon.tabular import TabularPredictor" \
    && pip check
COPY app ${LAMBDA_TASK_ROOT}/app
ENV PYTHONUNBUFFERED=1
ENV MPLCONFIGDIR=/tmp/matplotlib XDG_CACHE_HOME=/tmp/cache
CMD ["app.predict.handler"]
