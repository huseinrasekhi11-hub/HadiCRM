class Roles:
    ADMIN = "admin"
    CEO = "ceo"
    MANAGER = "manager"

    SALES = "sales"
    SALES_MANAGER = "sales_manager"

    SERVICE = "service"
    SERVICE_MANAGER = "service_manager"

    ACCOUNTING = "accounting"
    WAREHOUSE = "warehouse"

    HR = "hr"

    WEBSITE = "website"

    SYSTEM = "system"

    TENDER = "tender"

    POOL = "pool"

    HEAVY = "heavy"

    CUSTOMER = "customer"

    # مجموعه‌ی کامل نقش‌های معتبر — برای اعتبارسنجی ورودی در اسکیماها.
    # هر نقش جدیدی که بالا اضافه می‌شود باید اینجا هم ثبت شود.
    ALL: tuple[str, ...] = (
        ADMIN,
        CEO,
        MANAGER,
        SALES,
        SALES_MANAGER,
        SERVICE,
        SERVICE_MANAGER,
        ACCOUNTING,
        WAREHOUSE,
        HR,
        WEBSITE,
        SYSTEM,
        TENDER,
        POOL,
        HEAVY,
        CUSTOMER,
    )
