import re

def normalize_persian_text(text: str | None) -> str:
    """
    Normalizes Persian and Arabic characters and removes extra spaces.
    """
    if not text:
        return ""
    text = text.strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r'\s+', ' ', text)
    return text

def normalize_mobile(mobile: str | None) -> str:
    """
    Normalizes mobile numbers to a standard format (e.g., 0912...).
    Converts Persian/Arabic digits to English.
    """
    if not mobile:
        return ""
    mobile = mobile.strip()
    
    persian_nums = "۰۱۲۳۴۵۶۷۸۹"
    arabic_nums  = "٠١٢٣۴٥٦٧٨٩"
    english_nums = "0123456789"
    trans = str.maketrans(persian_nums + arabic_nums, english_nums * 2)
    mobile = mobile.translate(trans)
    
    if mobile.startswith("+98"):
        mobile = "0" + mobile[3:]
    elif mobile.startswith("98") and len(mobile) == 12:
        mobile = "0" + mobile[2:]
    elif mobile.startswith("9") and len(mobile) == 10:
        mobile = "0" + mobile
        
    return mobile
