# Mini Project IT375: ระบบย่อ URL + QR Code

โปรเจกต์นี้เป็นตัวอย่างระบบสำหรับกลุ่ม 3 คน ตามโจทย์วิชา IT375 โดยมีครบ:
- Admin Panel
- Frontend สำหรับผู้ใช้
- API Service
- Database Models
- Authentication (Login/Logout + JWT)

## Tech Stack
- FastAPI
- SQLite + SQLAlchemy ORM
- Jinja2 Templates (Frontend)
- JWT (python-jose)
- QR Code (qrcode)

## เริ่มต้นใช้งาน
```bash
python -m venv venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

เข้าใช้งานที่: http://localhost:8000

## บัญชีเริ่มต้น
- Admin: `admin` / `admin123`
- User: `student` / `student123`

## ฟีเจอร์
1. ผู้ใช้ล็อกอินและย่อ URL ผ่านหน้า Dashboard
2. ระบบสร้าง Short URL และแสดง QR Code ทันที
3. Redirect ผ่าน `/s/{short_code}`
4. Admin ดูข้อมูลผู้ใช้และ URL ทั้งหมด
5. API สำหรับออก JWT Token, สร้าง short URL และดูรายการ URL ของตัวเอง

## ตัวอย่าง API
### ขอ token
```bash
curl -X POST http://localhost:8000/api/auth/token \
  -d 'username=student&password=student123'
```

### สร้าง short URL (ใช้ bearer token)
```bash
curl -X POST http://localhost:8000/api/shorten \
  -H "Authorization: Bearer <TOKEN>" \
  -d 'original_url=https://www.example.com'
```

### ดู URL ของตัวเอง
```bash
curl http://localhost:8000/api/my-urls \
  -H "Authorization: Bearer <TOKEN>"
```

## ไอเดียแบ่งงานในกลุ่ม 3 คน
- คนที่ 1: Backend/API/Auth
- คนที่ 2: Frontend/UI/UX
- คนที่ 3: Database/Admin/Test + เตรียมเดโม
