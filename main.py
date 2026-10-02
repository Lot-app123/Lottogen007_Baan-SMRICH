import io
import random
import zipfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Auth config (เปลี่ยน SECRET_KEY ก่อน deploy!) ───────────────────────────

SECRET_KEY = "change-me-before-deploy-use-openssl-rand-hex-32"
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 8

USERS = {"admin": "1234"}  # TODO: ใช้ DB + bcrypt จริง ๆ ใน production


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: Optional[str] = Cookie(default=None, alias="access_token")) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})


CurrentUser = Annotated[str, Depends(get_current_user)]


# ─── Image/font cache (โหลดครั้งเดียวตอน startup) ───────────────────────────

@lru_cache(maxsize=1)
def _load_bg() -> Image.Image:
    """โหลดภาพพื้นหลังครั้งเดียว แล้ว cache ไว้ใน RAM"""
    return Image.open("static/Baan.jpg").convert("RGBA")


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Cache แต่ละขนาด font แยกกัน"""
    return ImageFont.truetype("static/Prompt-Bold.ttf", size)


# ─── Image generation (ไม่แตะ disk เลย) ─────────────────────────────────────

def _get_auto_font(draw: ImageDraw.ImageDraw, text: str, max_width: int,
                   start: int = 50, min_size: int = 20) -> ImageFont.FreeTypeFont:
    for size in range(start, min_size - 1, -1):
        font = _load_font(size)
        w = draw.textbbox((0, 0), text, font=font)[2]
        if w <= max_width:
            return font
    return _load_font(min_size)


def _bold_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
               font: ImageFont.FreeTypeFont, fill: str = "#ffca08", boldness: int = 1) -> None:
    x, y = xy
    for dx in range(-boldness, boldness + 1):
        for dy in range(-boldness, boldness + 1):
            draw.text((x + dx, y + dy), text, font=font, fill=fill)


# 1. แทนที่การประกาศฟังก์ชัน create_image_bytes ทั้งหมด
def create_image_bytes(
    lottery_type: str, 
    main1: Optional[str] = None, 
    main2: Optional[str] = None,
    pair1: Optional[str] = None,
    pair2: Optional[str] = None,
    pair3: Optional[str] = None,
    pair4: Optional[str] = None,
    pair5: Optional[str] = None,
    pair6: Optional[str] = None,
    pair7: Optional[str] = None,
    pair8: Optional[str] = None,
    triple1: Optional[str] = None,
    triple2: Optional[str] = None
) -> bytes:
    image = deepcopy(_load_bg()).convert("RGB")
    draw  = ImageDraw.Draw(image)

    color_red = "#a91c21"
    color_white = "#ffffff"

    # 1. วันที่ (งวดประจำวันที่)
    date_text = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y")
    bbox_date = draw.textbbox((0, 0), date_text, font=_load_font(28)) # ลดขนาดฟอนต์นิดหน่อยให้พอดีกรอบ
    w_date = bbox_date[2] - bbox_date[0]
    # ปรับแกน X และ Y ให้อยู่กึ่งกลางแถบสีทอง (ประมาณ X=710 ถึง 960)
    #draw.text((710 + (250 - w_date)//2, 363), date_text, font=_load_font(28), fill=color_white)

    # 2. ชื่อประเภทหวย (ปรับให้อยู่กลางกล่องขาว)
    font_auto = _get_auto_font(draw, lottery_type, 440, start=70) 
    bbox_name = draw.textbbox((0, 0), lottery_type, font=font_auto)
    w_name = bbox_name[2] - bbox_name[0]
    h_name = bbox_name[3] - bbox_name[1]
    # ปรับกล่องขาวประมาณ X=470 กว้าง 460
    x_name = 530 + (460 - w_name) // 2
    # ปรับแกน Y ดันลงมาให้อยู่ตรงกลางกล่อง
    y_name = 240 + (90 - h_name) // 2 - 5 
    _bold_text(draw, (x_name, y_name), lottery_type, font_auto, fill=color_red)

    # 3. จัดการ Num1 และ Num2 (ลอจิกเดิม)
    m1 = int(main1) if main1 and main1.isdigit() else None
    m2 = int(main2) if main2 and main2.isdigit() else None

    if m1 is not None and m2 is not None:
        num1, num2 = m1, m2
        if num1 == num2:
            num2 = random.choice([i for i in range(10) if i != num1])
    elif m1 is not None:
        num1 = m1
        num2 = random.choice([i for i in range(10) if i != num1])
    elif m2 is not None:
        num2 = m2
        num1 = random.choice([i for i in range(10) if i != num2])
    else:
        num1, num2 = random.sample(range(10), 2)

    def get_or_random_pair(user_input, default_format):
        if user_input and len(user_input) == 2 and user_input.isdigit():
            return user_input
        return default_format

    def get_or_random_triple(user_input, default_format):
        if user_input and len(user_input) == 3 and user_input.isdigit():
            return user_input
        return default_format

    # 4. สร้าง Pairs List 1 (อิงจาก Num1) 4 ชุด
    r_avail1 = random.sample([d for d in range(10) if d != num1], 4)
    pairs_list1 = [
        get_or_random_pair(pair1, f"{num1}{r_avail1[0]}"),
        get_or_random_pair(pair2, f"{num1}{r_avail1[1]}"),
        get_or_random_pair(pair3, f"{r_avail1[2]}{num1}"),
        get_or_random_pair(pair4, f"{r_avail1[3]}{num1}")
    ]
    text_p1 = " - ".join(pairs_list1)

    # 5. สร้าง Pairs List 2 (อิงจาก Num2) 4 ชุด
    r_avail2 = random.sample([d for d in range(10) if d != num2], 4)
    pairs_list2 = [
        get_or_random_pair(pair5, f"{num2}{r_avail2[0]}"),
        get_or_random_pair(pair6, f"{num2}{r_avail2[1]}"),
        get_or_random_pair(pair7, f"{r_avail2[2]}{num2}"),
        get_or_random_pair(pair8, f"{r_avail2[3]}{num2}")
    ]
    text_p2 = " - ".join(pairs_list2)

    # 6. สร้าง Triple (เอา Num1 จับคู่กับเลขอื่น 2 ตัว) 2 ชุด
    t_avail = random.sample([d for d in range(10) if d != num1], 4)
    t1_list = [num1, t_avail[0], t_avail[1]]
    t2_list = [num1, t_avail[2], t_avail[3]]
    random.shuffle(t1_list)
    random.shuffle(t2_list)
    
    triple1_val = get_or_random_triple(triple1, "".join(map(str, t1_list)))
    triple2_val = get_or_random_triple(triple2, "".join(map(str, t2_list)))
    triple_text = f"{triple1_val} - {triple2_val}"

    # 7. วาดผลลัพธ์ตัวเลข
    f_main = _load_font(180)
    f_pairs = _load_font(58) # ลดขนาดฟอนต์เลขคู่ลงนิดนึงเพื่อไม่ให้เบียดขอบ
    
    # วาดเลขในวงกลม (ปรับตำแหน่งให้อยู่ตรงกลางวงกลมมากขึ้น)
    bbox_m1 = draw.textbbox((0,0), str(num1), font=f_main)
    w_m1 = bbox_m1[2] - bbox_m1[0]
    h_m1 = bbox_m1[3] - bbox_m1[1]
    # ปรับพิกัด X จาก 730 เป็น 760, และ Y ดันลงมา
    _bold_text(draw, (787 - w_m1//2, 650 - h_m1//2 - 20), str(num1), f_main, fill=color_red)

    # วาดแถวตัวเลข (ขยับแกน Y เพื่อจัดช่องไฟให้สวยงาม)
    _bold_text(draw, (135, 663), text_p1, f_pairs, fill=color_white)
    _bold_text(draw, (135, 773), text_p2, f_pairs, fill=color_white)
    _bold_text(draw, (260, 870), triple_text, f_pairs, fill=color_white)

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85, optimize=True)
    buf.seek(0)
    return buf.read()


# ─── Routes ──────────────────────────────────────────────────────────────────

# 1. ตัวที่ทำให้เกิด Error 405 คือตัวนี้หายไป (สำหรับโหลดหน้าเว็บเข้าสู่ระบบ)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# 2. สำหรับกดปุ่มเข้าสู่ระบบ (เช็ครหัสผ่าน)
@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if USERS.get(username) != password:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"},
            status_code=400
        )
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=create_token(username),
        httponly=True,
        samesite="lax",
        max_age=TOKEN_EXPIRE_HOURS * 3600,
    )
    return response

# 3. สำหรับออกจากระบบ
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


@app.get("/", response_class=HTMLResponse)
async def lottery_page(request: Request, user: CurrentUser):
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.post("/")
async def lottery_generate(
    user: CurrentUser,
    lottery_type: list[str] = Form(...),
    main1: Optional[str] = Form(None), 
    main2: Optional[str] = Form(None),
    pair1: Optional[str] = Form(None), 
    pair2: Optional[str] = Form(None), 
    pair3: Optional[str] = Form(None), 
    pair4: Optional[str] = Form(None),
    pair5: Optional[str] = Form(None),
    pair6: Optional[str] = Form(None), 
    pair7: Optional[str] = Form(None),
    pair8: Optional[str] = Form(None),
    triple1: Optional[str] = Form(None), 
    triple2: Optional[str] = Form(None), 
):
    if not lottery_type:
        raise HTTPException(status_code=400, detail="กรุณาเลือกประเภทหวยอย่างน้อย 1 รายการ")

    # --- Backend Validation (เช็คเลข) ---
    pairs1 = [pair1, pair2, pair3, pair4]
    for i, p in enumerate(pairs1, 1):
        if p and len(p) == 2:
            if not main1:
                raise HTTPException(status_code=400, detail=f"กรุณาระบุ วิ่ง ก่อนกำหนดคู่ของวิ่งชุดที่ {i}")
            if main1 not in p:
                raise HTTPException(status_code=400, detail=f"คู่ของวิ่งชุดที่ {i} ({p}) ต้องมีเลขวิ่ง ({main1}) ด้วย")
                
    pairs2 = [pair5, pair6, pair7, pair8]
    for i, p in enumerate(pairs2, 1):
        if p and len(p) == 2:
            if not main2:
                raise HTTPException(status_code=400, detail=f"กรุณาระบุ รูด ก่อนกำหนดคู่ของรูดชุดที่ {i}")
            if main2 not in p:
                raise HTTPException(status_code=400, detail=f"คู่ของรูดชุดที่ {i} ({p}) ต้องมีเลขรูด ({main2}) ด้วย")

    triples = [triple1, triple2]
    for i, t in enumerate(triples, 1):
        if t and len(t) == 3:
            if not main1:
                raise HTTPException(status_code=400, detail=f"กรุณาระบุ วิ่ง ให้ครบก่อนกำหนดเลข 3 ตัวชุดที่ {i}")
            if main1 not in t:
                raise HTTPException(status_code=400, detail=f"เลข 3 ตัวชุดที่ {i} ({t}) ต้องมีเลขวิ่ง ({main1}) รวมอยู่ด้วย")
    # --- สิ้นสุดส่วนตรวจสอบ ---

    parsed_items = []
    for lt_data in lottery_type:
        time_str, name_str = lt_data.split("|", 1) if "|" in lt_data else ("", lt_data)
        parsed_items.append({
            "time": time_str, 
            "name": name_str
        })
    
    parsed_items.sort(key=lambda x: x["time"] if x["time"] else "99:99")

    # ─── ไฟล์เดียว: ส่งตรง ─────────────────────────────────────────────────
    if len(parsed_items) == 1:
        item = parsed_items[0]
        time_str = item["time"]
        name_str = item["name"]
        
        filename = f"{time_str.replace(':', '.')}_{name_str}.jpg" if time_str else f"{name_str}.jpg"
        encoded_filename = quote(filename)
        
        # ส่งค่าทั้งหมด 12 ช่อง เข้าไป
        img_bytes = create_image_bytes(name_str, main1, main2, pair1, pair2, pair3, pair4, pair5, pair6, pair7, pair8, triple1, triple2)
        return StreamingResponse(
            io.BytesIO(img_bytes),
            media_type="image/jpeg",
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
        )

    # ─── หลายไฟล์: ZIP ใน RAM ──────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, item in enumerate(parsed_items, start=1):
            time_str = item["time"]
            name_str = item["name"]
            
            prefix = f"{index:02d}_" 
            time_part = f"{time_str.replace(':', '.')}_" if time_str else ""
            filename = f"{prefix}{time_part}{name_str}.jpg"
            
            zf.writestr(filename, create_image_bytes(name_str, main1, main2, pair1, pair2, pair3, pair4, pair5, pair6, pair7, pair8, triple1, triple2))
    zip_buf.seek(0)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="lottery_results.zip"'},
    )


# ─── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)
