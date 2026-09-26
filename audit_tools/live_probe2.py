import httpx, io
B = "http://127.0.0.1:8000"
c = httpx.Client(base_url=B, timeout=15)
res = []
def check(name, cond, detail=""):
    res.append((name, cond)); print(("PASS " if cond else "FAIL ")+name+("  | "+str(detail)[:140] if detail else ""))

r = c.post("/auth/login", data={"username":"09120000000","password":"Admin123!"}); tok=r.json()
AH={"Authorization":f"Bearer {tok['access_token']}"}

# validation fixes
r = c.post("/leads/", json={"customer_name":"P","mobile":"9"*40,"source":"site"}, headers=AH)
check("40-char mobile -> 422 (was 500)", r.status_code==422, r.status_code)
r = c.post("/leads/", json={"customer_name":"x"*300,"mobile":"09121234567","source":"site"}, headers=AH)
check("300-char name -> 422 (was 500)", r.status_code==422, r.status_code)
for bad in ["   ", "", "abc123"]:
    r = c.post("/leads/", json={"customer_name":"B","mobile":bad,"source":"site"}, headers=AH)
    check(f"mobile {bad!r} -> 422 (was 201)", r.status_code==422, r.status_code)
r = c.post("/leads/", json={"customer_name":"Good","mobile":"۰۹۱۲۱۱۱۲۲۳۳","source":"site"}, headers=AH)
check("persian-digit mobile accepted 201", r.status_code==201, r.status_code)
lid = r.json()["id"]
r = c.patch(f"/leads/{lid}/status", json={"status":"final_factor","sale_amount":-5}, headers=AH)
check("negative sale_amount -> 422", r.status_code==422, r.status_code)
r = c.patch(f"/leads/{lid}/status", json={"status":"final_factor","sale_amount":5000}, headers=AH)
check("positive sale_amount ok 200", r.status_code==200, r.status_code)
r = c.post("/users/", json={"full_name":"W","mobile":"09123334444","password":"1","role":"sales"}, headers=AH)
check("1-char password -> 422", r.status_code==422, r.status_code)

# attachment flow: upload + authed download + no static serving
files={"file":("contract.pdf", io.BytesIO(b"%PDF-1.4 live"), "application/pdf")}
r = c.post(f"/leads/{lid}/attachments", files=files, headers=AH)
check("upload 201", r.status_code==201, r.status_code)
att = r.json()
r = c.get("/"+att["file_path"])
check("unauth /uploads static -> 404 (mount removed)", r.status_code==404, r.status_code)
r = c.get(f"/leads/{lid}/attachments/{att['id']}/download")
check("unauth download -> 401", r.status_code==401, r.status_code)
r = c.get(f"/leads/{lid}/attachments/{att['id']}/download", headers=AH)
check("authed download 200 + bytes", r.status_code==200 and r.content==b"%PDF-1.4 live", r.status_code)

# sales user IDOR on download
r = c.post("/users/", json={"full_name":"Live Sales","mobile":"09124445555","password":"Sales1234!","role":"sales"}, headers=AH)
r = c.post("/auth/login", data={"username":"09124445555","password":"Sales1234!"})
SH={"Authorization":f"Bearer {r.json()['access_token']}"}
r = c.get(f"/leads/{lid}/attachments/{att['id']}/download", headers=SH)
check("other-user download -> 404 (no leak)", r.status_code==404, r.status_code)

# ETag 304 with CORS header preserved (live)
h={**AH,"Origin":"http://localhost:5173"}
r=c.get("/leads/?limit=1",headers=h); etag=r.headers.get("etag")
r2=c.get("/leads/?limit=1",headers={**h,"If-None-Match":etag})
check("live: 304 keeps ACAO", r2.status_code==304 and r2.headers.get("access-control-allow-origin")=="http://localhost:5173", (r2.status_code, r2.headers.get("access-control-allow-origin")))

# error handlers don't leak internals
r = c.post("/leads/", json={"customer_name":"Good2","mobile":"09121112234","source":"s"*80}, headers=AH)
check("oversized source -> 422", r.status_code==422, r.status_code)

# duplicate product race -> 409 via IntegrityError handler (sequential dup still 400 by route check)
r = c.post("/products/", json={"name":"چیلر"}, headers=AH)
check("duplicate product -> 400/409", r.status_code in (400,409), r.status_code)

fails=[x for x in res if not x[1]]
print(); print(f"TOTAL {len(res)} checks, {len(res)-len(fails)} pass, {len(fails)} FAIL")
