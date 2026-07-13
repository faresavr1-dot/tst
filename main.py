import os
import json
import shutil
import zipfile
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# ================= إعدادات البوت =================
API_ID = 24217199  # ضع الـ API_ID الخاص بك هنا
API_HASH = "11c12a66dbd23da592211771db1bce6b"  # ضع الـ API_HASH هنا
BOT_TOKEN = "7399940837:AAEHq5LyU0j4ckhN_Y334t0wV2bOipm-t8Q"  # ضع توكن البوت هنا
ADMIN_ID = 7532687479  # ضع آيدي المطور (الآيدي الخاص بك) هنا

app = Client("HostingManager", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= قاعدة البيانات وحفظ الحالة =================
DB_FILE = "database.json"

if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({"users": {}, "banned": []}, f)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

user_states = {}  # لحفظ حالة المستخدم المؤقتة
running_bots = {} # لتخزين العمليات النشطة

# ================= دوال البحث والتحكم =================

def find_main_script(bot_dir):
    """البحث التلقائي عن ملف تشغيل البوت المكتوب بالبايثون"""
    for root, dirs, files in os.walk(bot_dir):
        # إذا وجدنا ملف باسم main.py نعطيه الأولوية
        if "main.py" in files:
            return os.path.join(root, "main.py")
        # وإلا، نأخذ أول ملف ينتهي بـ .py
        for file in files:
            if file.endswith(".py"):
                return os.path.join(root, file)
    return None

def get_user_limit(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = 2  # الحد الافتراضي (تنصيبين)
        save_db(db)
    return db["users"][uid]

def is_banned(user_id):
    db = load_db()
    return str(user_id) in db.get("banned", [])

def get_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("تنصيب بوت", callback_data="install_bot")],
        [InlineKeyboardButton("حذف التنصيب", callback_data="delete_bot")],
        [
            InlineKeyboardButton("إيقاف مؤقت", callback_data="pause_bot"),
            InlineKeyboardButton("تشغيل البوت", callback_data="resume_bot")
        ],
        [
            InlineKeyboardButton("حالة البوت", callback_data="status_bot"),
            InlineKeyboardButton("سجل البوت", callback_data="logs_bot")
        ]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("إيقاف تنصيب معين", callback_data="admin_stop_user"),
            InlineKeyboardButton("إعادة التنصيب (فك حظر)", callback_data="admin_unban_user")
        ])
        keyboard.append([InlineKeyboardButton("زيادة 1 تنصيب لمستخدم", callback_data="admin_add_limit")])
        
    return InlineKeyboardMarkup(keyboard)

# ================= الأوامر والتحكم عبر الأزرار =================

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    if is_banned(message.from_user.id):
        return await message.reply("أنت محظور من استخدام هذا البوت.")
    
    text = (
        "أهلاً بك في بوت تنصيب البوتات وإدارة الاستضافة.\n\n"
        "لرفع ملفاتك وتنصيب بوتك، اختر من الأزرار بالأسفل للتحكم الكامل ببيئة عملك."
    )
    await message.reply(text, reply_markup=get_keyboard(message.from_user.id))
    user_states[message.from_user.id] = None

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if is_banned(user_id) and user_id != ADMIN_ID:
        return await query.answer("أنت محظور من استخدام البوت.", show_alert=True)

    # 1. تنصيب بوت
    if data == "install_bot":
        limit = get_user_limit(user_id)
        user_dir = f"hostings/{user_id}"
        
        if os.path.exists(user_dir) and len(os.listdir(user_dir)) >= limit:
            return await query.answer(f"لقد وصلت للحد الأقصى المسموح لك ({limit} تنصيبات).", show_alert=True)
            
        user_states[user_id] = "WAITING_FOR_ZIP"
        await query.message.reply("يرجى إرسال ملف البوت المضغوط بصيغة `.zip` الآن.")
        await query.answer()

    # 2. حذف التنصيب النهائي
    elif data == "delete_bot":
        user_dir = f"hostings/{user_id}"
        if str(user_id) in running_bots:
            running_bots[str(user_id)].terminate()
            del running_bots[str(user_id)]
        
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            
        await query.message.reply("تم حذف التنصيب وحذف ملف الـ zip وأي ملفات نهائياً من السيرفر.")
        await query.answer()

    # 3. إيقاف البوت مؤقتاً
    elif data == "pause_bot":
        if str(user_id) in running_bots:
            process = running_bots[str(user_id)]
            process.terminate()
            del running_bots[str(user_id)]
            await query.answer("تم إيقاف البوت مؤقتاً.", show_alert=True)
        else:
            await query.answer("لا يوجد بوت يعمل حالياً لإيقافه.", show_alert=True)

    # 4. تشغيل البوت المؤقت (إعادة التشغيل)
    elif data == "resume_bot":
        bot_dir = f"hostings/{user_id}/bot"
        script_path = find_main_script(bot_dir)
        
        if script_path:
            script_dir = os.path.dirname(script_path)
            script_name = os.path.basename(script_path)
            
            log_file = open(f"hostings/{user_id}/log.txt", "a")
            process = subprocess.Popen(
                ["python3", script_name], 
                cwd=script_dir, 
                stdout=log_file, 
                stderr=subprocess.STDOUT
            )
            running_bots[str(user_id)] = process
            await query.answer("تم إعادة تشغيل البوت المتوقف مؤقتاً بنجاح.", show_alert=True)
        else:
            await query.answer("لم يتم العثور على أي ملف ينتهي بـ .py لتشغيله.", show_alert=True)

    # 5. حالة البوت
    elif data == "status_bot":
        if str(user_id) in running_bots:
            process = running_bots[str(user_id)]
            status = "شغال ومستقر 🟢" if process.poll() is None else "متوقف أو به خطأ 🔴"
        else:
            status = "غير شغال (متوقف مؤقتاً أو لم ينصب بعد) ⚪"
        await query.answer(f"حالة البوت: {status}", show_alert=True)

    # 6. سجل البوت (آخر 50 سطر)
    elif data == "logs_bot":
        log_path = f"hostings/{user_id}/log.txt"
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                lines = f.readlines()[-50:]
            
            log_text = "".join(lines) if lines else "السجل فارغ حالياً."
            if len(log_text) > 4000:
                log_text = log_text[-4000:]
            await query.message.reply(f"**سجل البوت (آخر 50 سطر):**\n```\n{log_text}\n```")
        else:
            await query.answer("لا يوجد سجل متوفر لهذا البوت.", show_alert=True)
        await query.answer()

    # ================= أزرار التحكم الخاصة بالمطور =================
    
    elif data == "admin_stop_user" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_WAITING_DEL_ID"
        await query.message.reply("أرسل الآن آيدي الشخص الذي تريد إلغاء تنصيبه وحذفه:")
        await query.answer()

    elif data == "admin_unban_user" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_WAITING_UNBAN_ID"
        await query.message.reply("أرسل آيدي الشخص لفك حظره وإتاحة التنصيب له مجدداً:")
        await query.answer()

    elif data == "admin_add_limit" and user_id == ADMIN_ID:
        user_states[user_id] = "ADMIN_WAITING_ADD_LIMIT_ID"
        await query.message.reply("أرسل آيدي الشخص لزيادة عدد تنصيباته المتاحة بمقدار (+1):")
        await query.answer()


# ================= معالجة المدخلات والملفات المرفوعة =================
@app.on_message(filters.private & ~filters.command("start"))
async def handle_inputs(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state:
        return

    # معالجة رفع ملف الـ ZIP وتثبيته وتشغيله تلقائياً
    if state == "WAITING_FOR_ZIP" and message.document:
        if not message.document.file_name.endswith(".zip"):
            return await message.reply("عذراً، يجب إرسال ملف مضغوط بصيغة `.zip` فقط.")
        
        msg = await message.reply("جاري تحميل الملف المضغوط وفك التشفير والتنصيب...")
        
        user_dir = f"hostings/{user_id}"
        bot_dir = f"{user_dir}/bot"
        os.makedirs(bot_dir, exist_ok=True)
        
        zip_path = os.path.join(user_dir, "bot.zip")
        await message.download(file_name=zip_path)
        
        try:
            # فك الضغط عن الملف
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(bot_dir)
            
            # حذف ملف الأرشيف المضغوط (ZIP) فوراً بعد فكه بناءً على طلبك
            os.remove(zip_path) 
            
            # البحث التلقائي عن ملف البايثون التشغيلي الداخلي (.py)
            script_path = find_main_script(bot_dir)
            if not script_path:
                shutil.rmtree(user_dir) # تنظيف المجلد لعدم وجود ملف صالح
                user_states[user_id] = None
                return await msg.edit_text("❌ فشل التنصيب: لم يتم العثور على أي ملف ينتهي بامتداد بايثون `.py` داخل الملف المضغوط!")

            script_dir = os.path.dirname(script_path)
            script_name = os.path.basename(script_path)

            await msg.edit_text(f"📦 تم اكتشاف ملف التشغيل الداخلي: `{script_name}`\nجاري فحص وتثبيت المتطلبات المذكورة...")

            # تثبيت المكاتب إذا وُجد ملف requirements.txt بجانب السكريبت أو في المجلد الرئيسي
            req_file = os.path.join(script_dir, "requirements.txt")
            if not os.path.exists(req_file):
                req_file = os.path.join(bot_dir, "requirements.txt")
                
            if os.path.exists(req_file):
                subprocess.run(["pip", "install", "-r", req_file])
            
            # فتح ملف السجلات وتشغيل سكريبت البايثون المكتشف تلقائياً بالاسم الصحيح له
            log_file = open(f"{user_dir}/log.txt", "w")
            process = subprocess.Popen(
                ["python3", script_name], 
                cwd=script_dir, 
                stdout=log_file, 
                stderr=subprocess.STDOUT
            )
            
            running_bots[str(user_id)] = process
            await msg.edit_text(f"🚀 تم تنصيب بوتك بنجاح! السكريبت يعمل الآن في الخلفية باسم `{script_name}`.")
            
        except Exception as e:
            await msg.edit_text(f"حدث خطأ غير متوقع أثناء التنصيب:\n`{e}`")
        
        user_states[user_id] = None

    # [مطور] حذف تنصيب مستخدم معين وحظره
    elif state == "ADMIN_WAITING_DEL_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        user_dir = f"hostings/{target_id}"
        
        if target_id in running_bots:
            running_bots[target_id].terminate()
            del running_bots[target_id]
            
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            await message.reply(f"تم إيقاف وحذف كافة ملفات تنصيب المستخدم {target_id} بنجاح.")
        else:
            await message.reply("لم يتم العثور على ملفات تنصيب نشطة لهذا الآيدي.")
        
        db = load_db()
        if target_id not in db.get("banned", []):
            db.setdefault("banned", []).append(target_id)
            save_db(db)
            
        user_states[user_id] = None

    # [مطور] رفع الحظر وإعادة السماح بالتنصيب
    elif state == "ADMIN_WAITING_UNBAN_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        db = load_db()
        if target_id in db.get("banned", []):
            db["banned"].remove(target_id)
            save_db(db)
            await message.reply(f"تم إلغاء الحظر للمستخدم {target_id} ويمكنه التنصيب مجدداً الآن.")
        else:
            await message.reply("هذا الآيدي غير محظور مسبقاً.")
        user_states[user_id] = None

    # [مطور] زيادة حد التنصيب بمقدار واحد
    elif state == "ADMIN_WAITING_ADD_LIMIT_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        db = load_db()
        current_limit = db["users"].get(target_id, 2)
        db["users"][target_id] = current_limit + 1
        save_db(db)
        await message.reply(f"تمت زيادة السعة بنجاح للآيدي {target_id}.\nالسعة الإجمالية الحالية لهصبحت: {current_limit + 1} تنصيبات.")
        user_states[user_id] = None

app.run()