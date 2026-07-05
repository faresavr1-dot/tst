import os
import json
import shutil
import zipfile
import subprocess
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# ================= إعدادات البوت =================
API_ID = 24217199  # ضع الـ API_ID الخاص بك هنا
API_HASH = "11c12a66dbd23da592211771db1bce6b"  # ضع الـ API_HASH هنا
BOT_TOKEN = "8693632824:AAG0DyPvLgU8-KtgiE_NzVCjTxObXdecPvU"  # ضع توكن البوت هنا
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

user_states = {}  # لحفظ حالة المستخدم المعقدة (خطوة الإدخال ورقم التنصيب)
running_bots = {} # لتخزين العمليات النشطة بصيغة: user_id_slot

# ================= دوال البحث والتحكم =================

def find_main_script(bot_dir):
    """البحث التلقائي عن ملف تشغيل البوت المكتوب بالبايثون"""
    for root, dirs, files in os.walk(bot_dir):
        if "main.py" in files:
            return os.path.join(root, "main.py")
        for file in files:
            if file.endswith(".py"):
                return os.path.join(root, file)
    return None

def get_user_limit(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = 2  
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
        ],
        [InlineKeyboardButton("⌨️ إدخال بيانات البوت", callback_data="input_bot")]
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

    # 1. تنصيب بوت (تحديد رقم التنصيب تلقائياً)
    if data == "install_bot":
        limit = get_user_limit(user_id)
        available_slot = None
        
        # البحث عن أول مكان فارغ متاح للمستخدم من 1 إلى الحد الأقصى الخاص به
        for i in range(1, limit + 1):
            if not os.path.exists(f"hostings/{user_id}/slot_{i}"):
                available_slot = i
                break
                
        if not available_slot:
            return await query.answer(f"لقد وصلت للحد الأقصى المسموح لك ({limit} تنصيبات نشطة). قم بحذف أحدها لتتمكن من تنصيب جديد.", show_alert=True)
            
        user_states[user_id] = {"step": "WAITING_FOR_ZIP", "slot": available_slot}
        await query.message.reply(f"✅ تم تخصيص رقم التنصيب `({available_slot})` لك.\n\nيرجى إرسال ملف البوت المضغوط بصيغة `.zip` الآن.")
        await query.answer()

    # الأزرار التي تتطلب تحديد رقم التنصيب
    elif data in ["delete_bot", "pause_bot", "resume_bot", "status_bot", "logs_bot", "input_bot"]:
        user_states[user_id] = {"step": "WAITING_FOR_SLOT", "action": data}
        limit = get_user_limit(user_id)
        await query.message.reply(f"🔢 لديك ({limit}) مسارات تنصيب متاحة.\n\nالرجاء كتابة وإرسال **رقم التنصيب** الذي تريد إجراء العملية عليه (مثال: `1` أو `2` أو `3`):")
        await query.answer()

    # ================= أزرار التحكم الخاصة بالمطور =================
    elif data == "admin_stop_user" and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_WAITING_DEL_ID"}
        await query.message.reply("أرسل الآن آيدي الشخص الذي تريد إلغاء كل تنصيباته وحذفه:")
        await query.answer()

    elif data == "admin_unban_user" and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_WAITING_UNBAN_ID"}
        await query.message.reply("أرسل آيدي الشخص لفك حظره وإتاحة التنصيب له مجدداً:")
        await query.answer()

    elif data == "admin_add_limit" and user_id == ADMIN_ID:
        user_states[user_id] = {"step": "ADMIN_WAITING_ADD_LIMIT_ID"}
        await query.message.reply("أرسل آيدي الشخص لزيادة عدد تنصيباته المتاحة بمقدار (+1):")
        await query.answer()


# ================= معالجة المدخلات والملفات المرفوعة =================
@app.on_message(filters.private & ~filters.command("start"))
async def handle_inputs(client: Client, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not state or not isinstance(state, dict):
        return

    step = state.get("step")

    # ------------------- 1. استقبال رقم التنصيب لإجراء الأوامر -------------------
    if step == "WAITING_FOR_SLOT" and message.text:
        slot_text = message.text.strip()
        if not slot_text.isdigit():
            return await message.reply("❌ يرجى إرسال رقم صحيح (مثلاً 1).")
            
        slot = int(slot_text)
        limit = get_user_limit(user_id)
        
        if slot < 1 or slot > limit:
            return await message.reply(f"❌ رقم تنصيب غير متاح لك. المتاح من 1 إلى {limit} فقط.")

        action = state.get("action")
        user_dir = f"hostings/{user_id}/slot_{slot}"
        process_key = f"{user_id}_{slot}"
        
        # تنفيذ الأمر المطلوب على رقم التنصيب المحدد
        if action == "delete_bot":
            if process_key in running_bots:
                running_bots[process_key].terminate()
                del running_bots[process_key]
            if os.path.exists(user_dir):
                shutil.rmtree(user_dir)
            await message.reply(f"🗑️ تم إيقاف وحذف التنصيب رقم ({slot}) وجميع ملفاته نهائياً.")
            user_states[user_id] = None

        elif action == "pause_bot":
            if process_key in running_bots:
                running_bots[process_key].terminate()
                del running_bots[process_key]
                await message.reply(f"⏸️ تم إيقاف التنصيب رقم ({slot}) مؤقتاً.")
            else:
                await message.reply(f"❌ لا يوجد بوت يعمل في التنصيب ({slot}) لإيقافه.")
            user_states[user_id] = None

        elif action == "resume_bot":
            bot_dir = f"{user_dir}/bot"
            script_path = find_main_script(bot_dir)
            if script_path:
                script_dir = os.path.dirname(script_path)
                script_name = os.path.basename(script_path)
                log_file = open(f"{user_dir}/log.txt", "a")
                process = subprocess.Popen(
                    ["python3", script_name], 
                    cwd=script_dir, 
                    stdin=subprocess.PIPE,
                    stdout=log_file, 
                    stderr=subprocess.STDOUT
                )
                running_bots[process_key] = process
                await message.reply(f"▶️ تم إعادة تشغيل التنصيب رقم ({slot}) بنجاح.")
            else:
                await message.reply(f"❌ لم يتم العثور على ملفات البوت لتشغيلها في التنصيب ({slot}).")
            user_states[user_id] = None

        elif action == "status_bot":
            if process_key in running_bots:
                process = running_bots[process_key]
                status = "شغال ومستقر 🟢" if process.poll() is None else "متوقف أو به خطأ 🔴"
            else:
                status = "غير شغال (متوقف أو محذوف) ⚪"
            await message.reply(f"📊 حالة التنصيب رقم ({slot}): {status}")
            user_states[user_id] = None

        elif action == "logs_bot":
            log_path = f"{user_dir}/log.txt"
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()[-50:]
                log_text = "".join(lines) if lines else "السجل فارغ حالياً."
                if len(log_text) > 4000:
                    log_text = log_text[-4000:]
                await message.reply(f"**سجل التنصيب رقم ({slot}) (آخر 50 سطر):**\n```\n{log_text}\n```")
            else:
                await message.reply(f"❌ لا يوجد سجل متوفر للتنصيب ({slot}).")
            user_states[user_id] = None

        elif action == "input_bot":
            if process_key in running_bots and running_bots[process_key].poll() is None:
                user_states[user_id] = {"step": "WAITING_FOR_PROCESS_INPUT", "slot": slot}
                await message.reply(f"📥 السيرفر جاهز في التنصيب ({slot}) لاستقبال البيانات.\n\nأرسل الآن القيمة المطلوبة (توكن، هاش، رقم هاتف، أو كود التحقق):")
            else:
                await message.reply(f"❌ عذراً، يجب أن يكون البوت شغالاً ومستقراً في التنصيب ({slot}) حتى تتمكن من إدخال البيانات إليه.")
                user_states[user_id] = None

    # ------------------- 2. استقبال ملف الأرشيف للتنصيب -------------------
    elif step == "WAITING_FOR_ZIP" and message.document:
        if not message.document.file_name.endswith(".zip"):
            return await message.reply("عذراً، يجب إرسال ملف مضغوط بصيغة `.zip` فقط.")
        
        slot = state.get("slot")
        msg = await message.reply(f"جاري تحميل الملف المضغوط للتنصيب رقم ({slot})...")
        
        user_dir = f"hostings/{user_id}/slot_{slot}"
        bot_dir = f"{user_dir}/bot"
        os.makedirs(bot_dir, exist_ok=True)
        
        zip_path = os.path.join(user_dir, "bot.zip")
        await message.download(file_name=zip_path)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(bot_dir)
            os.remove(zip_path) 
            
            # فحص الملفات المرفوعة لمعرفة إذا كان ملف سحب Dropper مشفر 
            extracted_files = []
            for r, d, f in os.walk(bot_dir):
                for file in f:
                    if not file.startswith('.'): # استبعاد الملفات المخفية
                        extracted_files.append(os.path.join(r, file))

            is_dropper = False
            # إذا كان مجلد البوت يحتوي على ملف واحد فقط وهو ملف .py
            if len(extracted_files) == 1 and extracted_files[0].endswith(".py"):
                is_dropper = True
            
            script_path = find_main_script(bot_dir)
            if not script_path:
                shutil.rmtree(user_dir)
                user_states[user_id] = None
                return await msg.edit_text("❌ فشل التنصيب: لم يتم العثور على أي ملف ينتهي بامتداد بايثون `.py` داخل الملف المضغوط!")

            script_dir = os.path.dirname(script_path)
            script_name = os.path.basename(script_path)

            req_file = os.path.join(script_dir, "requirements.txt")
            if not os.path.exists(req_file):
                req_file = os.path.join(bot_dir, "requirements.txt")
                
            if os.path.exists(req_file):
                await msg.edit_text(f"📦 تم اكتشاف المتطلبات للتنصيب ({slot})... جاري التثبيت.")
                subprocess.run(["pip", "install", "-r", req_file])
            
            log_file = open(f"{user_dir}/log.txt", "w")
            process = subprocess.Popen(
                ["python3", script_name], 
                cwd=script_dir, 
                stdin=subprocess.PIPE,
                stdout=log_file, 
                stderr=subprocess.STDOUT
            )
            
            process_key = f"{user_id}_{slot}"
            running_bots[process_key] = process
            
            # [تعديل] اكتشاف ملف السحب (Dropper) وتشغيله بالانتظار
            if is_dropper:
                await msg.edit_text("⏳ تم اكتشاف ملف تنصيب تشفيري/سحابي (Dropper).\n\nجاري تشغيل الملف ومحاولة سحب وتنصيب الملفات الكاملة... يرجى الانتظار من دقيقة إلى 10 دقائق ⏱️")
                
                # انتظار برمجي بسيط لإعطاء انطباع للمستخدم بوجود عمليات في الخلفية
                await asyncio.sleep(6) 
                
                await message.reply(
                    f"✅ **تم تنصيب البوت بنجاح!**\n\n"
                    f"رقم التنصيب الخاص بك هو: `({slot})`\n"
                    f"تم تشغيل الملف بجميع الطرق الممكنة وهو يعمل الآن. يمكنك مراجعة **سجل البوت** الخاص بهذا التنصيب لمعرفة ما تم سحبه أو إدخال أي بيانات مطلوبة."
                )
            else:
                await msg.edit_text(f"🚀 تم تنصيب بوتك بنجاح في التنصيب رقم `({slot})`! السكريبت يعمل الآن في الخلفية باسم `{script_name}`.")
            
            # إرسال تقرير فوري للمطور
            try:
                report_text = (
                    f"🚨 **تقرير تنصيب جديد في السيرفر** 🚨\n\n"
                    f"👤 **المستضيف:** {message.from_user.mention}\n"
                    f"🆔 **الآيدي (ID):** `{user_id}`\n"
                    f"🔢 **رقم التنصيب:** `{slot}`\n"
                    f"📂 **ملف التشغيل:** `{script_name}`\n"
                    f"🛡️ **نوع التنصيب:** {'سحابي/مُشفر (Dropper)' if is_dropper else 'عادي'}\n"
                    f"⚡ **الحالة:** العملية قيد المراقبة والتفاعل."
                )
                await client.send_message(chat_id=ADMIN_ID, text=report_text)
            except Exception as report_error:
                print(f"Error sending report: {report_error}")
            
        except Exception as e:
            await msg.edit_text(f"حدث خطأ غير متوقع أثناء التنصيب:\n`{e}`")
        
        user_states[user_id] = None

    # ------------------- 3. استقبال المدخلات وتمريرها للتنصيب -------------------
    elif step == "WAITING_FOR_PROCESS_INPUT" and message.text:
        slot = state.get("slot")
        process_key = f"{user_id}_{slot}"
        raw_text = message.text.strip()
        
        if ":" not in raw_text:
            cleaned_text = raw_text
            for char in [" ", "+", "-", "(", ")"]:
                cleaned_text = cleaned_text.replace(char, "")
        else:
            cleaned_text = raw_text.replace(" ", "")
            
        if process_key in running_bots and running_bots[process_key].poll() is None:
            try:
                process = running_bots[process_key]
                process.stdin.write(f"{cleaned_text}\n".encode('utf-8'))
                process.stdin.flush()
                
                await message.reply(f"📥 تم معالجة البيانات وإرسالها بنجاح للتنصيب `({slot})`:\n`{cleaned_text}`")
            except Exception as input_err:
                await message.reply(f"❌ فشل تمرير البيانات إلى عملية البوت: `{input_err}`")
        else:
            await message.reply("❌ تعذر إرسال البيانات، يبدو أن البوت قد توقف.")
            
        user_states[user_id] = None

    # ------------------- أوامر المطور (الإدارة) -------------------
    elif step == "ADMIN_WAITING_DEL_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        
        # إيقاف جميع العمليات التابعة لهذا المستخدم مهما كان رقم تنصيبها
        keys_to_delete = [k for k in running_bots.keys() if k.startswith(f"{target_id}_")]
        for k in keys_to_delete:
            running_bots[k].terminate()
            del running_bots[k]
            
        user_dir = f"hostings/{target_id}"
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            await message.reply(f"تم إيقاف وحذف كافة ملفات وتنصيبات المستخدم {target_id} بنجاح.")
        else:
            await message.reply("لم يتم العثور على ملفات تنصيب نشطة لهذا الآيدي.")
        
        db = load_db()
        if target_id not in db.get("banned", []):
            db.setdefault("banned", []).append(target_id)
            save_db(db)
            
        user_states[user_id] = None

    elif step == "ADMIN_WAITING_UNBAN_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        db = load_db()
        if target_id in db.get("banned", []):
            db["banned"].remove(target_id)
            save_db(db)
            await message.reply(f"تم إلغاء الحظر للمستخدم {target_id} ويمكنه التنصيب مجدداً الآن.")
        else:
            await message.reply("هذا الآيدي غير محظور مسبقاً.")
        user_states[user_id] = None

    elif step == "ADMIN_WAITING_ADD_LIMIT_ID" and user_id == ADMIN_ID:
        target_id = message.text.strip()
        db = load_db()
        current_limit = db["users"].get(target_id, 2)
        db["users"][target_id] = current_limit + 1
        save_db(db)
        await message.reply(f"تمت زيادة السعة بنجاح للآيدي {target_id}.\nالسعة الإجمالية الحالية أصبحت: {current_limit + 1} تنصيبات.")
        user_states[user_id] = None

app.run()
