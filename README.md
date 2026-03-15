# Mini Project IT375: Short URL + QR Code

ระบบย่อ URL พร้อม QR Code, ระบบล็อกอิน, admin panel และ API สำหรับใช้งานในรายวิชา IT375

## ฟีเจอร์ปัจจุบัน
- Login / Logout สำหรับผู้ใช้
- สร้าง Short URL พร้อม QR Code
- แก้ไขและลบลิงก์จากหน้า Dashboard
- ติดตามจำนวนคลิกของแต่ละลิงก์
- ดูสถิติ click analytics ผ่านกราฟ
- Admin panel สำหรับดูผู้ใช้และลิงก์ทั้งหมด
- JWT API สำหรับเชื่อมต่อกับแอปอื่น

## Tech Stack
- FastAPI
- SQLite + SQLAlchemy
- Jinja2 Templates
- JWT (`python-jose`)
- QR Code (`qrcode`)

## เริ่มต้นใช้งาน
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

เปิดใช้งานที่ `http://localhost:8000`

## บัญชีทดลอง
- Admin: `admin / admin123`
- User: `student / student123`

## API ตัวอย่าง
ขอ access token:

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d "username=student&password=student123"
```

สร้าง short URL:

```bash
curl -X POST http://localhost:8000/api/shorten \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '"https://example.com"'
```
