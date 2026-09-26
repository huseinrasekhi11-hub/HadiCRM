from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id"), 
        nullable=False, 
        index=True
    )
    
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), 
        nullable=False
    )
    
    file_name: Mapped[str] = mapped_column(
        String(255), 
        nullable=False
    )
    
    file_path: Mapped[str] = mapped_column(
        String(500), 
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
