from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
import pytz
from datetime import datetime
from app.database.base import Base

def get_tehran_time():
    return datetime.now(pytz.timezone('Asia/Tehran'))

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    chat_id = Column(String, index=True)
    login_time = Column(DateTime, default=get_tehran_time)
    last_active = Column(DateTime, default=get_tehran_time)
    is_active = Column(Boolean, default=True)

    user = relationship("User")
