from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
import pytz
from datetime import datetime
from app.database.base import Base # مسیر درست Base خودتان

def get_tehran_time():
    return datetime.now(pytz.timezone('Asia/Tehran'))

# ۱. جدول یادداشت‌ها
class Note(Base):
    __tablename__ = "notes"
    __table_args__ = {'extend_existing': True} # ✅ این خط اضافه شد
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"))
    author_id = Column(Integer, ForeignKey("users.id"))
    content = Column(String)
    created_at = Column(DateTime, default=get_tehran_time)

# ۲. جدول فایل‌های ضمیمه
#
# حذف شد. پیش از این اینجا یک مدل دوم برای همان جدول «attachments»
# تعریف شده بود (با ستون‌های uploader_id/file_type) که با مدل رسمی
# app/models/attachment.py (با ستون‌های uploaded_by_id/file_name —
# همان چیزی که مهاجرت 50529198cc8e می‌سازد) تناقض داشت.
# extend_existing=True فقط خطای import را پنهان می‌کرد و در عمل،
# بسته به اینکه کدام ابزار دیتابیس را ساخته بود، یا INSERTهای ربات
# یا کوئری‌های وب با خطای «column does not exist» شکست می‌خوردند.
#
# مدل رسمی و یگانه:  from app.models.attachment import Attachment

# ۳. جدول برچسب‌ها (Tags)
class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = {'extend_existing': True} # ✅ این خط اضافه شد
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

# ۴. جدول واسط تگ‌ها
class LeadTag(Base):
    __tablename__ = "lead_tags"
    __table_args__ = {'extend_existing': True} # ✅ این خط اضافه شد
    
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
