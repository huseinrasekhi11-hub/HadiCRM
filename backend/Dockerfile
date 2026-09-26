# استفاده از نسخه سبک پایتون به عنوان پایه
FROM python:3.11-slim

# تنظیم منطقه زمانی سرور روی تهران
ENV TZ="Asia/Tehran"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تنظیم پوشه کاری داخل سرور
WORKDIR /app

# نصب پیش‌نیازهای سیستمی برای دیتابیس (psycopg2) و healthcheck (curl)
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
# کپی کردن فایل پیش‌نیازها و نصب آن‌ها (لایه‌ی جدا برای کش بهتر build)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کد پروژه.
# .dockerignore مانع کپی‌شدن .env، uploads/ و اسکریپت‌های یک‌بارمصرف
# می‌شود — پیش از این با COPY . . همه‌چیز از جمله اسرار داخل ایمیج
# می‌رفت.
COPY . .

# اجرا با کاربر غیر-root
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/uploads/leads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
