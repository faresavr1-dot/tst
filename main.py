import os
import sys
import json
import shutil
import zipfile
import subprocess
import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, Message

# ================= إعدادات البوت =================
API_ID = 24217199  # ضع الـ API_ID الخاص بك هنا
API_HASH = "11c12a66dbd23da592211771db1bce6b"  # ضع الـ API_HASH هنا
BOT_TOKEN = "8849723725:AAE-bq0S4D7iPg3Cq9mQWVU99iFWkI_qxmg"  # ضع توكن البوت هنا
ADMIN_ID = 7532687479  # ضع آيدي المطور (الآيدي الخاص بك) هنا

app = Client("HostingManager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= قاعدة البيانات =================
DB_FILE = "database.json"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({"users": {}, "banned": [], "locked": False}, f)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

user_states = {}  
running_bots = {} 

# ================= دوال مساعدة وذكية =================

def get_user_limit(user_id):
    if user_id == ADMIN_ID:
        return 999  # المطور عدد لا نهائي
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = 2  
        save_db(db)
    return db["users"][uid]

def get_active_slots(user_id):
    """جلب أرقام التنصيبات النشطة للمستخدم"""
    base_dir = f"hostings/{user_id}"
    if not os.path.exists(base_dir): return []
    slots = []
    for d in os.listdir(base_dir):
        if d.startswith("slot_"):
            slots.append(int(d.split("_")[1]))
    return sorted(slots)

def find_main_script(bot_dir):
    """البحث عن ملف بايثون أو PHP"""
    for root, dirs, files in os.walk(bot_dir):
        if "main.py" in files: return os.path.join(root, "main.py")
        if "index.php" in files: return os.path.join(root, "index.php")
        if "main.php" in files: return os.path.join(root, "main.php")
        
        for file in files:
            if file.endswith(".py") or file.endswith(".php"):
                return os.path.join(root, file)
    return None

def auto_install_requirements(bot_dir, script_path, is_python):
    """تثبيت المتطلبات حتى لو لم يكن هناك ملف requirements"""
    req_file = os.path.join(os.path.dirname(script_path), "requirements.txt")
    if not os.path.exists(req_file):
        req_file = os.path.join(bot_dir, "requirements.txt")
        
    if is_python:
        if os.path.exists(req_file):
            subprocess.run(["pip", "install", "-r", req_file])
        else:
            # اكتشاف تلقائي للمكتبات من خلال قراءة كود البايثون
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    content = f.read()
                imports = set()
                for line in content.split("\n"):
                    match = re.match(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', line)
                    if match:
                        mod = match.group(1)
                        if mod not in sys.builtin_module_names:
                            imports.add(mod)
                if imports:
                    subprocess.run(["pip", "install"] + list(imports))
            except:
                pass
    else:
        # إذا كان PHP، نبحث عن composer
        composer_file = os.path.join(os.path.dirname(script_path), "composer.json")
        if os.path.exists(composer_file):
            subprocess.run(["composer", "install"], cwd=os.path.dirname(script_path))

async def check_disk_space(client):
    """التحقق من مساحة السيرفر"""
    total, used, free = shutil.disk_usage("/")
    percent = (used / total) * 100
    if percent >= 85:
        await client.send_message(ADMIN_ID, f"⚠️ **تحذير:** مساحة الاستضافة وصلت إلى {percent:.1f}%!")

# ================= لوحات المفاتيح (أزرار الكيبورد) =================

def main_menu(user_id):
    btns = [[KeyboardButton("تنصيب بوت"), KeyboardButton("حذف تنصيب")]]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton("إدارة بوتك"), KeyboardButton("إدارة بوتات الأعضاء")])
        btns.append([KeyboardButton("قفل التنصيب"), KeyboardButton("تشغيل التنصيب")])
    else:
        btns.append([KeyboardButton("قسم الإدارة")])
    return ReplyKeyboardMarkup(btns, resize_keyboard=True)

def manage_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("سجل البوت"), KeyboardButton("حالة البوت")],
        [KeyboardButton("إيقاف مؤقت"), KeyboardButton("تشغيل البوت")],
        [KeyboardButton("⌨️ إدخال بيانات")],
        [KeyboardButton("رجوع")]
    ], resize_keyboard=True)

def admin_users_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("حذف تنصيب عضو"), KeyboardButton("إيقاف مؤقت لعضو")],
        [KeyboardButton("تشغيل لعضو"), KeyboardButton("فك حظر")],
        [KeyboardButton("زيادة تنصيب")],
        [KeyboardButton("رجوع")]
    ], resize_keyboard=True)

# ================= التوجيهات الأساسية =================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    db = load_db()
    if str(message.from_user.id) in db.get("banned", []):
        return await message.reply("أنت محظور.")
    
    user_states[message.from_user.id] = None
    await message.reply("أهلاً بك. اختر من القائمة أدناه:", reply_markup=main_menu(message.from_user.id))

@app.on_message(filters.text & filters.private)
async def handle_texts(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    db = load_db()
    state = user_states.get(user_id, {}) or {}

    # === زر الرجوع ===
    if text == "رجوع":
        user_states[user_id] = None
        return await message.reply("تم الرجوع للرئيسية.", reply_markup=main_menu(user_id))

    # ================= القائمة الرئيسية =================

    if text == "تنصيب بوت":
        await check_disk_space(client)
        if db.get("locked", False) and user_id != ADMIN_ID:
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("المطور", url=f"tg://user?id={ADMIN_ID}")]])
            return await message.reply("عذراً، لا يمكن تنصيب البوت حالياً، يرجى مراسلة المطور.", reply_markup=btn)
            
        limit = get_user_limit(user_id)
        slots = get_active_slots(user_id)
        
        if len(slots) >= limit:
            return await message.reply("وصلت للحد الأقصى للتنصيبات.")
            
        available_slot = next((i for i in range(1, limit + 2) if i not in slots), 1)
        user_states[user_id] = {"step": "WAITING_FOR_ZIP", "slot": available_slot}
        await message.reply("أرسل ملف البوت المضغوط (.zip) الآن:")

    elif text == "حذف تنصيب":
        slots = get_active_slots(user_id)
        if not slots:
            return await message.reply("لا يوجد لديك تنصيبات لحذفها.")
        elif len(slots) == 1:
            # الحذف المباشر (ذكي)
            slot = slots[0]
            process_key = f"{user_id}_{slot}"
            if process_key in running_bots:
                running_bots[process_key].terminate()
                del running_bots[process_key]
            shutil.rmtree(f"hostings/{user_id}/slot_{slot}", ignore_errors=True)
            await message.reply("تم حذف التنصيب بنجاح.")
        else:
            user_states[user_id] = {"step": "WAITING_SLOT_DELETE"}
            await message.reply("لديك أكثر من تنصيب، أدخل الرقم:")

    elif text in ["قسم الإدارة", "إدارة بوتك"]:
        slots = get_active_slots(user_id)
        if not slots:
            return await message.reply("لا يوجد تنصيبات لإدارتها.")
        elif len(slots) == 1:
            user_states[user_id] = {"selected_slot": slots[0]}
            await message.reply(f"تم اختيار التنصيب ({slots[0]}). اختر الإجراء:", reply_markup=manage_menu())
        else:
            user_states[user_id] = {"step": "WAITING_SLOT_MANAGE"}
            await message.reply("أدخل رقم التنصيب الذي تريد إدارته:")

    # ================= أزرار التحكم بالمطور (الخاصة بالأعضاء) =================

    elif text == "إدارة بوتات الأعضاء" and user_id == ADMIN_ID:
        await message.reply("إدارة الأعضاء:", reply_markup=admin_users_menu())

    elif text in ["حذف تنصيب عضو", "إيقاف مؤقت لعضو", "تشغيل لعضو"] and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_WAITING_USER_ID", "action": text}
        await message.reply("أدخل آيدي العضو:")

    elif text == "فك حظر" and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_UNBAN_ID"}
        await message.reply("أدخل الآيدي:")

    elif text == "زيادة تنصيب" and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_ADD_LIMIT"}
        await message.reply("أدخل الآيدي:")

    elif text == "قفل التنصيب" and user_id == ADMIN_ID:
        db["locked"] = True
        save_db(db)
        await message.reply("تم قفل التنصيب للجميع.")

    elif text == "تشغيل التنصيب" and user_id == ADMIN_ID:
        db["locked"] = False
        save_db(db)
        await message.reply("تم فتح التنصيب للجميع.")


    # ================= قسم إدارة التنصيب (بعد اختيار الرقم) =================

    elif text in ["سجل البوت", "حالة البوت", "إيقاف مؤقت", "تشغيل البوت", "⌨️ إدخال بيانات"]:
        slot = state.get("selected_slot")
        if not slot:
            return await message.reply("يرجى اختيار قسم الإدارة أولاً.", reply_markup=main_menu(user_id))
            
        process_key = f"{user_id}_{slot}"
        user_dir = f"hostings/{user_id}/slot_{slot}"

        if text == "سجل البوت":
            log_path = f"{user_dir}/log.txt"
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    log_text = "".join(f.readlines()[-50:])
                await message.reply(f"**سجل ({slot}):**\n```\n{log_text[-4000:]}\n```")
            else:
                await message.reply("لا يوجد سجل.")

        elif text == "حالة البوت":
            if process_key in running_bots and running_bots[process_key].poll() is None:
                await message.reply("الحالة: يعمل 🟢")
            else:
                await message.reply("الحالة: متوقف ⚪")

        elif text == "إيقاف مؤقت":
            if process_key in running_bots:
                running_bots[process_key].terminate()
                del running_bots[process_key]
                await message.reply("تم الإيقاف المؤقت.")
            else:
                await message.reply("البوت متوقف بالفعل.")

        elif text == "تشغيل البوت":
            script_path = find_main_script(f"{user_dir}/bot")
            if script_path:
                is_py = script_path.endswith(".py")
                cmd = "python3" if is_py else "php"
                log_file = open(f"{user_dir}/log.txt", "a")
                p = subprocess.Popen([cmd, os.path.basename(script_path)], cwd=os.path.dirname(script_path), stdin=subprocess.PIPE, stdout=log_file, stderr=subprocess.STDOUT)
                running_bots[process_key] = p
                await message.reply("تم إعادة التشغيل.")
            else:
                await message.reply("لم يتم العثور على ملفات للتشغيل.")

        elif text == "⌨️ إدخال بيانات":
            if process_key in running_bots and running_bots[process_key].poll() is None:
                user_states[user_id]["step"] = "WAITING_INPUT"
                await message.reply("أدخل القيمة:")
            else:
                await message.reply("عذراً، البوت لا يعمل لإدخال البيانات.")


    # ================= استقبال النصوص والخطوات =================

    step = state.get("step")

    if step == "WAITING_SLOT_DELETE" and text.isdigit():
        slot = int(text)
        shutil.rmtree(f"hostings/{user_id}/slot_{slot}", ignore_errors=True)
        if f"{user_id}_{slot}" in running_bots:
            running_bots[f"{user_id}_{slot}"].terminate()
            del running_bots[f"{user_id}_{slot}"]
        await message.reply("تم الحذف.", reply_markup=main_menu(user_id))
        user_states[user_id] = None

    elif step == "WAITING_SLOT_MANAGE" and text.isdigit():
        user_states[user_id] = {"selected_slot": int(text)}
        await message.reply(f"تم الدخول للتنصيب ({text}).", reply_markup=manage_menu())

    elif step == "WAITING_INPUT" and text:
        slot = state.get("selected_slot")
        process_key = f"{user_id}_{slot}"
        cleaned = text.replace(" ", "") if ":" in text else text.translate(str.maketrans("", "", " +-()"))
        
        if process_key in running_bots and running_bots[process_key].poll() is None:
            try:
                running_bots[process_key].stdin.write(f"{cleaned}\n".encode('utf-8'))
                running_bots[process_key].stdin.flush()
                await message.reply("تم الإدخال بنجاح.")
            except:
                await message.reply("خطأ في الإدخال.")
        user_states[user_id]["step"] = None # الرجوع لحالة الإدارة العادية

    # --- المطور ---
    elif step == "ADMIN_WAITING_USER_ID" and text.isdigit():
        target_id = int(text)
        slots = get_active_slots(target_id)
        if not slots:
            await message.reply("العضو ليس لديه تنصيبات.")
            user_states[user_id] = None
        elif len(slots) == 1:
            # التنفيذ المباشر لو عنده تنصيب واحد
            await execute_admin_user_action(message, state["action"], target_id, slots[0])
            user_states[user_id] = None
        else:
            user_states[user_id] = {"step": "ADMIN_WAITING_USER_SLOT", "action": state["action"], "target": target_id}
            await message.reply("العضو لديه أكثر من تنصيب، أدخل الرقم:")

    elif step == "ADMIN_WAITING_USER_SLOT" and text.isdigit():
        await execute_admin_user_action(message, state["action"], state["target"], int(text))
        user_states[user_id] = None

    elif step == "ADMIN_UNBAN_ID" and text.isdigit():
        if str(text) in db["banned"]: db["banned"].remove(str(text))
        save_db(db)
        await message.reply("تم فك الحظر.")
        user_states[user_id] = None

    elif step == "ADMIN_ADD_LIMIT" and text.isdigit():
        db["users"][str(text)] = db["users"].get(str(text), 2) + 1
        save_db(db)
        await message.reply("تمت الزيادة.")
        user_states[user_id] = None

async def execute_admin_user_action(message, action, target_id, slot):
    """دالة مساعدة لتنفيذ إجراءات المطور على الأعضاء بذكاء"""
    process_key = f"{target_id}_{slot}"
    user_dir = f"hostings/{target_id}/slot_{slot}"
    
    if action == "حذف تنصيب عضو":
        if process_key in running_bots:
            running_bots[process_key].terminate()
            del running_bots[process_key]
        shutil.rmtree(user_dir, ignore_errors=True)
        await message.reply(f"تم حذف التنصيب ({slot}) للعضو.")
        
    elif action == "إيقاف مؤقت لعضو":
        if process_key in running_bots:
            running_bots[process_key].terminate()
            del running_bots[process_key]
            await message.reply("تم الإيقاف.")
        else:
            await message.reply("متوقف بالفعل.")
            
    elif action == "تشغيل لعضو":
        script_path = find_main_script(f"{user_dir}/bot")
        if script_path:
            cmd = "python3" if script_path.endswith(".py") else "php"
            p = subprocess.Popen([cmd, os.path.basename(script_path)], cwd=os.path.dirname(script_path), stdin=subprocess.PIPE, stdout=open(f"{user_dir}/log.txt", "a"), stderr=subprocess.STDOUT)
            running_bots[process_key] = p
            await message.reply("تم التشغيل.")


# ================= رفع الملفات (التنصيب) =================

@app.on_message(filters.document & filters.private)
async def handle_docs(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    
    if state and state.get("step") == "WAITING_FOR_ZIP" and message.document.file_name.endswith(".zip"):
        slot = state.get("slot")
        msg = await message.reply("جاري التحميل...")
        
        bot_dir = f"hostings/{user_id}/slot_{slot}/bot"
        os.makedirs(bot_dir, exist_ok=True)
        zip_path = f"{bot_dir}/bot.zip"
        
        await message.download(file_name=zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(bot_dir)
        os.remove(zip_path)
        
        script_path = find_main_script(bot_dir)
        if not script_path:
            shutil.rmtree(f"hostings/{user_id}/slot_{slot}", ignore_errors=True)
            return await msg.edit_text("فشل: لم يتم العثور على ملف py أو php.")
            
        is_python = script_path.endswith(".py")
        script_name = os.path.basename(script_path)
        script_dir = os.path.dirname(script_path)
        
        # اكتشاف وتثبيت المتطلبات بذكاء (للبايثون والـ PHP)
        auto_install_requirements(bot_dir, script_path, is_python)
        
        extracted_files = [f for r, d, files in os.walk(bot_dir) for f in files if not f.startswith('.')]
        is_dropper = (len(extracted_files) == 1)

        cmd = "python3" if is_python else "php"
        process = subprocess.Popen([cmd, script_name], cwd=script_dir, stdin=subprocess.PIPE, stdout=open(f"hostings/{user_id}/slot_{slot}/log.txt", "w"), stderr=subprocess.STDOUT)
        running_bots[f"{user_id}_{slot}"] = process
        
        if is_dropper:
            await msg.edit_text("تم استلام ملف سحابي. جاري سحب الملفات، يرجى الانتظار...")
            await asyncio.sleep(6)
            await message.reply(f"تم التنصيب. (رقم: {slot})", reply_markup=main_menu(user_id))
        else:
            await msg.edit_text(f"تم تنصيب البوت بنجاح. (رقم: {slot})", reply_markup=main_menu(user_id))
            
        user_states[user_id] = None

app.run()
