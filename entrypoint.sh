gunicorn \
    --bind 0.0.0.0:80 \
    --workers 3 \
    --worker-class 'uvicorn.workers.UvicornWorker' \
    'app.main:app'
#--log-level error \