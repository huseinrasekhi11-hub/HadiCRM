import logging, io, re
buf = io.StringIO()
h = logging.StreamHandler(buf)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.engine').addHandler(h)
import os
os.environ.setdefault("SECRET_KEY","x"); os.environ.setdefault("DATABASE_URL","postgresql+psycopg2://hadiflow:hadiflow123@localhost:5432/hadiflow")
os.environ.setdefault("ENABLE_SCHEDULER","false")
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
r = c.post("/auth/login", data={"username":"09120000000","password":"Admin123!"})
AH={"Authorization": f"Bearer {r.json()['access_token']}"}
buf.truncate(0); buf.seek(0)
c.get("/dashboard/", headers=AH)
n_dash = len(re.findall(r"\[raw sql\]|\[generated in|SELECT", buf.getvalue()))
buf.truncate(0); buf.seek(0)
c.get("/leads/?limit=100&with_total=true", headers=AH)
n_leads = len(re.findall(r"SELECT", buf.getvalue()))
buf.truncate(0); buf.seek(0)
c.get("/dashboard/charts/sales-by-user?days=90", headers=AH)
n_chart = len(re.findall(r"SELECT", buf.getvalue()))
print(f"queries: /dashboard/={n_dash} statements, /leads/?limit=100={n_leads}, sales-by-user={n_chart}")
