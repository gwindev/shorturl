# Mini Project IT375: Short URL + QR Code

ระบบย่อ URL พร้อม QR Code, ระบบล็อกอิน, admin panel และ API สำหรับใช้งานในรายวิชา IT375

## ฟีเจอร์ปัจจุบัน
- Login / Logout สำหรับผู้ใช้
- สร้าง Short URL พร้อม QR Code
- ใส่ **Custom Alias** (เช่น `/promo2026`) ได้เอง
- ตั้ง **วันหมดอายุลิงก์** เพื่อให้ใช้งานเฉพาะช่วงเวลาที่กำหนด
- copy short link (คลิกเดียว) + **ดาวน์โหลด QR เป็น PNG** ได้ทันที
- แสดง **Top Links** (5 อันดับ) จาก 7 วันล่าสุด
- แก้ไขและลบลิงก์จากหน้า Dashboard
- ติดตามจำนวนคลิกของแต่ละลิงก์
- ดูสถิติ click analytics ผ่านกราฟ (browser/OS/desktop vs mobile)
- Admin panel สำหรับดูผู้ใช้และลิงก์ทั้งหมด
- JWT API สำหรับเชื่อมต่อกับแอปอื่น

## Tech Stack
- FastAPI
- SQLite + SQLAlchemy
- Jinja2 Templates
- JWT (`python-jose`)
- QR Code (`qrcode`)
- OAuth Google Login (`httpx`)
- `.env` config (`python-dotenv`)

## เริ่มต้นใช้งาน
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

เปิดใช้งานที่ `http://localhost:8000`

## ตั้งค่า (Environment variables)
สร้างไฟล์ `.env` (ใน root โปรเจกต์) แล้วใส่ค่า:

```env
SHORTQR_BASE_URL=http://localhost:8000
SHORTQR_SECRET_KEY=replace-with-a-random-secret

# Google OAuth (ถ้าต้องการเปิด Google login)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

> หมายเหตุ: ถ้าไม่ต้องการใช้ Google login ให้ปล่อยสองค่าสุดท้ายไว้ หรือไม่ต้องใส่ได้ แต่ระบบจะไม่เปิดปุ่ม Google login

## บัญชีทดลอง
- Admin: `admin / admin123`
- User: `student / student123`

## API
สำหรับตรวจ API ให้เปิดไปที่

- Swagger UI: `https://<your-host>/api/docs`
- OpenAPI JSON: `https://<your-host>/api/openapi.json`

ตัวอย่างคำสั่ง:

### ขอ access token
```bash
curl -X POST https://<your-host>/api/auth/token \
  -d "username=student&password=student123"
```

### สร้าง short URL (แบบพื้นฐาน)
```bash
curl -X POST https://<your-host>/api/shorten \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '"https://example.com"'
```

### สร้าง short URL พร้อม Custom Alias / Expiry (JSON)
```bash
curl -X POST https://<your-host>/api/shorten-json \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com","custom_alias": "promo2026","expires_at": "2026-12-31T23:59:59"}'
```
