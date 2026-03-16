# ShortQR (Short URL + QR) — Guide

ไฟล์นี้เป็นคู่มือสำหรับติดตั้ง ใช้งาน และนำเสนอโปรเจกต์ ShortQR (FastAPI + SQLite + Jinja2)

---

## 1) โครงสร้างโปรเจกต์

```
shorturl/
  ├─ app/
  │   ├─ main.py              # FastAPI app entrypoint
  │   ├─ routers/
  │   │   ├─ web.py           # หน้าเว็บ (login / dashboard / admin)
  │   │   └─ api.py           # API endpoints (JWT, URL CRUD, stats)
  │   ├─ models.py           # SQLAlchemy models (User, ShortURL, Click)
  │   ├─ core.py             # helper functions (JWT, URL builder, auth)
  │   ├─ database.py         # DB engine & session
  │   ├─ schemas.py          # pydantic schemas
  │   └─ templates/          # Jinja2 templates (HTML)
  ├─ requirements.txt
  ├─ README.md
  └─ .env                   # ตั้งค่า environment (ไม่ได้ commit)
```

---

## 2) ติดตั้ง & รัน (Local)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

เปิดเว็บที่:
- `http://localhost:8000` (UI)
- `http://localhost:8000/api/docs` (Swagger API)

---

## 3) ตั้งค่า `.env`

สร้างไฟล์ `.env` ใน root โปรเจกต์ (ไม่ต้อง commit)

```env
SHORTQR_BASE_URL=http://localhost:8000
SHORTQR_SECRET_KEY=replace-with-a-random-secret

# Google OAuth (ถ้าใช้)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

---

## 4) บัญชีทดลอง

- **Admin**  : `admin / admin123`
- **Student**: `student / student123`

---

## 5) ฟีเจอร์เด่นที่มีแล้ว

- สร้าง Short URL + QR Code
- **Custom Alias** (ตั้งชื่อเอง เช่น `/promo2026`)
- **วันหมดอายุลิงก์** (expiry date)
- **Copy URL** ในตาราง (คลิกเดียว)
- **ดาวน์โหลด QR เป็น PNG**
- **Top 5 Links** (7 วันล่าสุด)
- แสดงสถิติคลิก (mobile/desktop, browser, OS)
- ระบบล็อกอิน + admin panel
- API (JWT) สำหรับเชื่อมต่อภายนอก

---

## 6) การใช้งาน UI (Demo Flow)

### 1) Login / Register
- เปิด `http://localhost:8000/login` เพื่อเข้าสู่ระบบ
- หากยังไม่มีบัญชี ให้ไป `http://localhost:8000/register`

### 2) Dashboard (หลัง login)
- สร้างลิงก์ใหม่ พร้อมใส่ `Custom Alias` และ `Expiry Date`
- ดู QR ที่สร้างล่าสุด และดาวน์โหลดไฟล์ PNG ได้
- กด **Copy** เพื่อคัดลอก short link อัตโนมัติ
- แก้ไข / ลบลิงก์ได้จากตาราง
- ดู Top 5 links (7 วันล่าสุด) ด้านล่าง

### 3) Admin Panel (เฉพาะ admin)
- เข้า `http://localhost:8000/admin`
- ดูผู้ใช้ทั้งหมด และลิงก์ทั้งหมดได้

---

## 7) API สำคัญ (สำหรับนักพัฒนา)

### 7.1 ขอ JWT (Login)

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=student&password=student123"
```

ตอบกลับ:
```json
{ "access_token": "...", "token_type": "bearer" }
```

### 7.2 ตรวจสอบตัวเอง

```bash
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/auth/me
```

### 7.3 สร้าง Short URL (พื้นฐาน)

```bash
curl -X POST http://localhost:8000/api/shorten \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '"https://example.com"'
```

### 7.4 สร้าง Short URL พร้อม Custom Alias + Expiry

```bash
curl -X POST http://localhost:8000/api/shorten-json \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"original_url":"https://example.com","custom_alias":"promo2026","expires_at":"2026-12-31T23:59:59"}'
```

### 7.5 ดูลิงก์ทั้งหมดของผู้ใช้

```bash
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/my-urls
```

### 7.6 ดูสถิติคลิก

```bash
curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/url/<ID>/stats
```

---

## 8) วิธีแปลง Markdown -> PDF (ถ้าต้องการ)

ถ้ามี `pandoc` ติดตั้งอยู่:

```bash
pandoc GUIDE.md -o GUIDE.pdf
```

---

## 9) บทพูดสั้น ๆ สำหรับพรีเซนต์

1. **เกริ่น**: โปรเจกต์นี้คือระบบ “Short URL + QR” พร้อมระบบล็อกอินและสถิติการใช้งาน
2. **Login/Signup**: ใช้งานได้ทันทีผ่านหน้าจอ login/register
3. **Dashboard**:
   - สร้างลิงก์ใหม่ พร้อม Custom Alias
   - แสดง QR และดาวน์โหลด PNG ได้
   - ระบบ “copy” เพื่อให้ใช้ง่าย
   - แสดง Top 5 ลิงก์ จาก 7 วันล่าสุด
4. **Admin**: ดูผู้ใช้ทั้งหมด + ลิงก์ทั้งหมด
5. **API**: มี Swagger (`/api/docs`) และ JWT ให้ใช้งานต่อได้

---

หากอยากให้ผมผลิตไฟล์ PDF ให้พร้อมเลย (สร้างไฟล์จริงใน repo) บอกได้ครับ 😊
