import httpx, json, io, sys

B = "http://127.0.0.1:8000"
c = httpx.Client(base_url=B, timeout=15)
results = []
def check(name, cond, detail=""):
    results.append((name, "PASS" if cond else "FAIL", detail))
    print(("PASS " if cond else "FAIL ") + name + ("  | "+str(detail)[:160] if detail else ""))

# 1 health
r = c.get("/"); check("health /", r.status_code==200 and r.json()["status"]=="Running", r.text[:80])

# 2 unauth probes
for path in ["/leads/", "/users/", "/dashboard/", "/notifications/feed", "/audit-logs/", "/deleted-leads/", "/admin/leads/1/timeline", "/products/"]:
    r = c.get(path)
    check(f"unauth GET {path} -> 401", r.status_code==401, r.status_code)

# 3 login
r = c.post("/auth/login", data={"username":"09120000000","password":"Admin123!"})
check("admin login 200", r.status_code==200, r.status_code)
tok = r.json(); AH = {"Authorization": f"Bearer {tok['access_token']}"}
RH = {"Authorization": f"Bearer {tok['refresh_token']}"}

# 4 wrong password vs nonexistent user -> same message (no enumeration)
r1 = c.post("/auth/login", data={"username":"09120000000","password":"wrong"})
r2 = c.post("/auth/login", data={"username":"09129999999","password":"wrong"})
check("no account enumeration", r1.status_code==401==r2.status_code and r1.json()["detail"]==r2.json()["detail"], r1.json().get("detail"))

# 5 token type separation
r = c.post("/auth/refresh-token", json={"refresh_token": tok["access_token"]})
check("access token rejected at refresh endpoint", r.status_code==401, r.status_code)
r = c.get("/auth/me", headers=RH)
check("refresh token rejected as bearer", r.status_code==401, r.status_code)
r = c.get("/auth/me", headers={"Authorization":"Bearer "+tok["access_token"][:-3]+"xyz"})
check("tampered token rejected", r.status_code==401, r.status_code)
r = c.get("/auth/me", headers=AH)
check("/auth/me with access token", r.status_code==200 and r.json()["mobile"]=="09120000000", r.status_code)

# 6 refresh flow works
r = c.post("/auth/refresh-token", json={"refresh_token": tok["refresh_token"]})
check("refresh-token issues new access", r.status_code==200 and "access_token" in r.json(), r.status_code)

# 7 oversized mobile -> currently unhandled?
r = c.post("/leads/", json={"customer_name":"Probe","mobile":"9"*40,"source":"site","need":None}, headers=AH)
check("BUG? 40-char mobile accepted/500", r.status_code in (201,500), f"status={r.status_code}")
oversized_status = r.status_code
r = c.post("/leads/", json={"customer_name":"x"*300,"mobile":"09121111111","source":"site","need":None}, headers=AH)
check("BUG? 300-char customer_name", r.status_code in (201,500), f"status={r.status_code}")
r = c.post("/leads/", json={"customer_name":"Empty Mobile","mobile":"   ","source":"site","need":None}, headers=AH)
check("BUG? blank mobile accepted", r.status_code in (201,422,400,500), f"status={r.status_code}")

# 8 negative sale_amount on status close
r = c.post("/leads/", json={"customer_name":"NegSale","mobile":"09122222222","source":"site","need":None}, headers=AH)
lid = r.json()["id"]
r = c.patch(f"/leads/{lid}/status", json={"status":"final_factor","sale_amount":-50000000}, headers=AH)
check("BUG? negative sale_amount accepted", r.status_code==200 and r.json()["sale_amount"]==-50000000, f"status={r.status_code} amt={r.json().get('sale_amount') if r.status_code==200 else ''}")
# negative sale item amount
r = c.post(f"/leads/{lid}/sale-items", json={"product_id":1,"amount":-10}, headers=AH)
check("sale item amount ge=0 enforced", r.status_code==422, r.status_code)

# 9 attachment upload + unauth static access
files = {"file": ("../../evil.py", io.BytesIO(b"print('pwn')"), "text/x-python")}
r = c.post(f"/leads/{lid}/attachments", files=files, headers=AH)
check("upload .py rejected by whitelist", r.status_code==400, r.status_code)
files = {"file": ("../../evil.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
r = c.post(f"/leads/{lid}/attachments", files=files, headers=AH)
check("upload traversal-name pdf stored safely", r.status_code==201, r.text[:120])
if r.status_code==201:
    fp = r.json()["file_path"]
    r2 = c.get("/"+fp)   # NO auth header
    check("BUG? unauth download of attachment", r2.status_code==200, f"status={r2.status_code} path=/{fp}")
# static traversal attempt
r = c.get("/uploads/../app/main.py")
check("static traversal blocked", r.status_code in (400,404), r.status_code)
r = c.get("/uploads/%2e%2e/app/config/settings.py")
check("encoded traversal blocked", r.status_code in (400,404), r.status_code)

# 10 CORS behavior
r = c.options("/leads/", headers={"Origin":"http://evil.example","Access-Control-Request-Method":"GET"})
check("disallowed origin: no ACAO", "access-control-allow-origin" not in r.headers, dict(r.headers))
r = c.options("/leads/", headers={"Origin":"http://localhost:5173","Access-Control-Request-Method":"GET","Access-Control-Request-Headers":"authorization"})
check("allowed origin preflight", r.headers.get("access-control-allow-origin")=="http://localhost:5173", r.headers.get("access-control-allow-origin"))
r = c.get("/leads/?limit=1", headers={**AH, "Origin":"http://localhost:5173"})
check("expose X-Total-Count/ETag on CORS GET", "x-total-count" in r.headers.get("access-control-expose-headers","").lower() or "etag" in r.headers.get("access-control-expose-headers","").lower(), r.headers.get("access-control-expose-headers"))

# 11 ETag + 304 keeps CORS headers (the fix)
r = c.get("/leads/?limit=1&with_total=true", headers={**AH, "Origin":"http://localhost:5173"})
etag = r.headers.get("etag")
check("etag present + X-Total-Count", bool(etag) and "x-total-count" in r.headers, f"etag={etag} total={r.headers.get('x-total-count')}")
r2 = c.get("/leads/?limit=1&with_total=true", headers={**AH, "Origin":"http://localhost:5173", "If-None-Match": etag})
check("304 returned", r2.status_code==304, r2.status_code)
check("FIX VERIFIED: 304 keeps CORS headers", r2.headers.get("access-control-allow-origin")=="http://localhost:5173", dict(r2.headers))

# 12 pagination boundary
r = c.get("/leads/?limit=101", headers=AH)
check("limit>100 rejected 422", r.status_code==422, r.status_code)
r = c.get("/leads/?skip=-1", headers=AH)
check("skip<0 rejected 422", r.status_code==422, r.status_code)
r = c.get("/leads/abc", headers=AH)
check("non-int lead id -> 422", r.status_code==422, r.status_code)
r = c.get("/leads/999999", headers=AH)
check("missing lead -> 404", r.status_code==404, r.status_code)

# 13 docs exposure
r = c.get("/docs")
check("INFO: /docs publicly exposed", r.status_code==200, r.status_code)
r = c.get("/openapi.json")
check("INFO: /openapi.json publicly exposed", r.status_code==200, r.status_code)

# 14 deactivated user is locked out immediately
r = c.post("/users/", json={"full_name":"Temp Sales","mobile":"09127777777","password":"Passw0rd!1","role":"sales"}, headers=AH)
check("create user", r.status_code==201, r.status_code)
uid = r.json()["id"]
r = c.post("/auth/login", data={"username":"09127777777","password":"Passw0rd!1"})
check("new user login", r.status_code==200, r.status_code)
st = r.json()["access_token"]
r = c.put(f"/users/{uid}", json={"is_active": False}, headers=AH)
check("deactivate user", r.status_code==200, r.status_code)
r = c.get("/auth/me", headers={"Authorization": f"Bearer {st}"})
check("deactivated user token rejected 403", r.status_code==403, r.status_code)
r = c.post("/auth/login", data={"username":"09127777777","password":"Passw0rd!1"})
check("deactivated user cannot login", r.status_code==403, r.status_code)

# 15 IDOR: sales cannot see admin's lead
r = c.post("/auth/login", data={"username":"09127777777","password":"Passw0rd!1"})
# re-activate first
c.put(f"/users/{uid}", json={"is_active": True}, headers=AH)
r = c.post("/auth/login", data={"username":"09127777777","password":"Passw0rd!1"})
SH = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = c.get(f"/leads/{lid}", headers=SH)
check("IDOR blocked: other's lead -> 404", r.status_code==404, r.status_code)
r = c.patch(f"/leads/{lid}/status", json={"status":"contacted"}, headers=SH)
check("IDOR blocked: status change -> 404", r.status_code==404, r.status_code)
r = c.get("/audit-logs/", headers=SH)
check("audit-logs admin-only -> 403", r.status_code==403, r.status_code)
r = c.get("/deleted-leads/", headers=SH)
check("deleted-leads admin-only -> 403", r.status_code==403, r.status_code)
r = c.get("/dashboard/charts/daily-sales", headers=SH)
check("charts admin-only -> 403", r.status_code==403, r.status_code)
r = c.get("/users/", headers=SH)
check("users list admin-only -> 403", r.status_code==403, r.status_code)
r = c.get("/users/assignable", headers=SH)
check("assignable list allowed for sales", r.status_code==200, r.status_code)
r = c.post("/users/", json={"full_name":"Escalation","mobile":"09128888888","password":"x","role":"admin"}, headers=SH)
check("sales cannot create users -> 403", r.status_code==403, r.status_code)

# 16 weak password accepted on user create? (policy check)
r = c.post("/users/", json={"full_name":"Weak Pass","mobile":"09126666666","password":"1","role":"sales"}, headers=AH)
check("BUG? 1-char password accepted", r.status_code==201, r.status_code)
r = c.post("/users/", json={"full_name":"Bad Role","mobile":"09125555555","password":"Passw0rd!1","role":"superuser"}, headers=AH)
check("invalid role rejected 422", r.status_code==422, r.status_code)

# 17 brute-force: 30 rapid wrong logins -> any throttling?
codes = [c.post("/auth/login", data={"username":"09120000000","password":"bad%d"%i}).status_code for i in range(30)]
check("INFO: no rate limiting on /auth/login", all(x==401 for x in codes), f"{len(codes)} attempts all 401, none throttled")

print()
fails = [x for x in results if x[1]=="FAIL"]
print(f"TOTAL: {len(results)} checks, {len(results)-len(fails)} pass, {len(fails)} fail")
