import os
import time
import asyncio
import lmdb
import pickle
import base64
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from hopx_ai import Sandbox
from asyncio import Semaphore

DB_PATH = "users.lmdb"
MAX_CONCURRENT = 50  
REQUEST_SEMAPHORE = Semaphore(MAX_CONCURRENT)
SANDBOX_SEMAPHORE = Semaphore(10)  

env = lmdb.open(DB_PATH, map_size=10*1024*1024*1024)

def get_user(user_id):
    try:
        with env.begin() as txn:
            data = txn.get(str(user_id).encode())
            if data:
                return pickle.loads(data)
    except:
        pass
    return None

def save_user(user_id, **kwargs):
    try:
        with env.begin(write=True) as txn:
            user = get_user(user_id)
            if user is None:
                user = {
                    'user_id': user_id,
                    'api_key': None,
                    'sandbox_id': None,
                    'session_file': None,
                    'screen_name': None,
                    'created_at': datetime.now().isoformat(),
                    'status': 'waiting',
                    'temp_action': None,
                    'temp_data': None
                }
            
            for key, value in kwargs.items():
                if key in ['api_key', 'sandbox_id', 'session_file', 'screen_name', 'status', 'temp_action', 'temp_data']:
                    user[key] = value
            
            txn.put(str(user_id).encode(), pickle.dumps(user))
            return True
    except Exception as e:
        print(f"Error saving user: {e}")
        return False

def delete_user(user_id):
    try:
        with env.begin(write=True) as txn:
            txn.delete(str(user_id).encode())
            return True
    except:
        return False

API_ID = int(os.environ.get("API_ID", "29571279"))
API_HASH = os.environ.get("API_HASH", "b7963cd36c7b9c2c57171394ceb1956f")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7399940837:AAEHq5LyU0j4ckhN_Y334t0wV2bOipm-t8Q")

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAIN_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("تشغيل السورس", callback_data="run_bot"),
        InlineKeyboardButton("ايقاف السورس", callback_data="stop_bot")
    ],
    [
        InlineKeyboardButton("حالة السورس", callback_data="status_bot"),
        InlineKeyboardButton("اعادة تشغيل", callback_data="restart_bot")
    ],
    [
        InlineKeyboardButton("ادارة الملفات", callback_data="files_menu"),
        InlineKeyboardButton("حذف الجلسة", callback_data="delete_session")
    ],
    [
        InlineKeyboardButton("حذف البيانات بالكامل", callback_data="delete_data")
    ]
])

FILES_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("عرض الملفات", callback_data="list_files"),
        InlineKeyboardButton("رفع ملف", callback_data="upload_file")
    ],
    [
        InlineKeyboardButton("حذف ملف", callback_data="delete_file"),
        InlineKeyboardButton("رجوع للقائمة", callback_data="back_main")
    ]
])

def get_stdout(result):
    if hasattr(result, 'stdout'):
        return result.stdout.strip()
    return str(result).strip()

async def setup_sandbox(user_id, api_key):
    async with SANDBOX_SEMAPHORE:
        try:
            THIRTY_DAYS = 30 * 24 * 60 * 60
            
            sandbox = await asyncio.to_thread(
                Sandbox.create, 
                template="code-interpreter", 
                api_key=api_key,
                timeout_seconds=THIRTY_DAYS
            )
            save_user(user_id, sandbox_id=sandbox.sandbox_id, status="installing")
            
            commands = (
                "apt-get update && apt-get install -y ffmpeg git gcc python3-dev libffi-dev libssl-dev make g++ screen && "
                "pip install --upgrade pip setuptools wheel && "
                "pip install mtranslate google-genai requests g4f mutagen tgcalls==3.0.0.dev6 "
                "py-tgcalls~=2.2.11 telethon aiosqlite aiocron emoji pytz gtts qrcode "
                "Telegram aiohttp fake_useragent user_agent hijri_converter gpytranslate watchdog"
            )
            
            await asyncio.to_thread(sandbox.run_code, f"import os; os.system('{commands}')")
            await asyncio.to_thread(sandbox.run_code, "import os; os.system('git clone https://github.com/2mrxe2/pro /root/pro')")
            
            save_user(user_id, status="ready")
            return True, "تم تجهيز الساندبوكس بنجاح"
        except Exception as e:
            save_user(user_id, status="error")
            return False, f"خطأ: {str(e)}"

async def extend_sandbox_timeout(sandbox):
    try:
        THIRTY_DAYS = 30 * 24 * 60 * 60
        await asyncio.to_thread(sandbox.set_timeout, THIRTY_DAYS)
        return True
    except:
        return False

async def get_bot_logs(sandbox, lines=30):
    try:
        code = f"""
import os
log_file = '/root/pro/bot.log'
if os.path.exists(log_file):
    with open(log_file, 'r') as f:
        lines = f.readlines()[-{lines}:]
    print(''.join(lines))
else:
    print('لا توجد سجلات')
"""
        result = await asyncio.to_thread(sandbox.run_code, code)
        return get_stdout(result)
    except:
        return "خطأ في جلب السجلات"

async def check_bot_running(sandbox, screen_name):
    try:
        code = f"""
import os
import subprocess
try:
    output = subprocess.check_output(['screen', '-ls'], stderr=subprocess.DEVNULL, text=True)
    if '{screen_name}' in output:
        print('running')
    else:
        print('stopped')
except:
    print('stopped')
"""
        result = await asyncio.to_thread(sandbox.run_code, code)
        return 'running' in get_stdout(result)
    except:
        return False

async def get_files_list(sandbox):
    try:
        code = """
import os
files = []
for f in os.listdir('/root/pro'):
    if os.path.isfile(f'/root/pro/{f}'):
        files.append(f)
print('\\n'.join(files))
"""
        result = await asyncio.to_thread(sandbox.run_code, code)
        files = get_stdout(result).split('\n')
        return [f for f in files if f]
    except:
        return []

def heavy_operation(func):
    async def wrapper(*args, **kwargs):
        user_id = None
        if args and hasattr(args[0], 'from_user'):
            user_id = args[0].from_user.id
        elif args and len(args) > 0 and hasattr(args[0], 'message') and hasattr(args[0].message, 'from_user'):
            user_id = args[0].message.from_user.id
        
        if not user_id:
            return await func(*args, **kwargs)
        
        async with REQUEST_SEMAPHORE:
            return await func(*args, **kwargs)
    return wrapper

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.reply(
            "مرحباً!\n"
            "ارسل API_KEY الخاص بك للبدء:\n"
            "مثال: hopx_live_xxxxx"
        )
    else:
        await message.reply(
            "القائمة الرئيسية",
            reply_markup=MAIN_MENU
        )

@app.on_message(filters.text & filters.private)
@heavy_operation
async def handle_messages(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    user = get_user(user_id)
    
    if text.startswith("hopx_live_") and len(text) > 20:
        api_key = text
        if user and user.get('api_key') == api_key:
            await message.reply("هذا المفتاح مستخدم مسبقاً")
            return
        
        save_user(user_id, api_key=api_key, status="processing")
        msg = await message.reply("جاري تجهيز الساندبوكس... قد يستغرق 2-3 دقائق للتحميل والتثبيت")
        
        success, result = await setup_sandbox(user_id, api_key)
        
        if success:
            await msg.edit_text(
                f"{result}\n\n"
                "ارسل ملف الجلسة بصيغة .session\nمن البوت @in90bot\n"
                "ثم استخدم زر تشغيل السورس",
                reply_markup=MAIN_MENU
            )
        else:
            await msg.edit_text(f"فشل التجهيز: {result}\nيرجى المحاولة مرة اخرى")
        return
    
    if user and user.get('temp_action') == "delete_file" and text.isdigit():
        file_index = int(text) - 1
        try:
            sandbox = await asyncio.to_thread(Sandbox.connect, user['sandbox_id'], api_key=user['api_key'])
            files = await get_files_list(sandbox)
            
            if 0 <= file_index < len(files):
                filename = files[file_index]
                await asyncio.to_thread(sandbox.run_code, f"import os; os.remove('/root/pro/{filename}')")
                save_user(user_id, temp_action=None, temp_data=None)
                await message.reply(
                    f"تم حذف الملف: {filename}",
                    reply_markup=FILES_MENU
                )
            else:
                await message.reply("رقم غير صحيح، يرجى المحاولة مرة اخرى")
        except Exception as e:
            await message.reply(f"خطأ: {str(e)}")
        return
    
    if user and user.get('temp_action') == "delete_file" and text.lower() == "الغاء":
        save_user(user_id, temp_action=None, temp_data=None)
        await message.reply("تم الغاء العملية", reply_markup=FILES_MENU)
        return
    
    if user and user.get('sandbox_id'):
        try:
            sandbox = await asyncio.to_thread(Sandbox.connect, user['sandbox_id'], api_key=user['api_key'])
            result = await asyncio.to_thread(sandbox.run_code, f"import os; print(os.system('{text}'))")
            await message.reply(f"نتيجة التنفيذ:\n{get_stdout(result)}")
        except Exception as e:
            await message.reply(f"خطأ: {str(e)}")
    else:
        await message.reply("ارسل API_KEY اولاً")
        
@app.on_message(filters.document & filters.private)
@heavy_operation
async def handle_session_file(client, message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user or not user.get('api_key'):
        await message.reply("ارسل API_KEY اولاً")
        return
    
    if not user.get('sandbox_id'):
        await message.reply("لم يتم انشاء الساندبوكس بعد")
        return
    
    try:
        temp_path = f"/tmp/{message.document.file_name}"
        await message.download(temp_path)
        
        sandbox = await asyncio.to_thread(Sandbox.connect, user['sandbox_id'], api_key=user['api_key'])
        
        # قراءة الملف وتحويله إلى base64
        with open(temp_path, 'rb') as f:
            file_content = f.read()
        
        encoded = base64.b64encode(file_content).decode('utf-8')
        
        # رفع الملف باستخدام run_code مع base64
        code = f"""
import base64
file_data = base64.b64decode('{encoded}')
with open('/root/pro/{message.document.file_name}', 'wb') as f:
    f.write(file_data)
print('تم رفع الملف')
"""
        await asyncio.to_thread(sandbox.run_code, code)
        
        if message.document.file_name.endswith('.session'):
            save_user(user_id, session_file=message.document.file_name)
            response_text = f"تم رفع الجلسة بنجاح: {message.document.file_name}"
        else:
            response_text = f"تم رفع الملف بنجاح: {message.document.file_name}"
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        await message.reply(
            f"{response_text}\n"
            "يمكنك التحكم الآن من خلال القائمة أدناه:",
            reply_markup=MAIN_MENU
        )
    except Exception as e:
        await message.reply(f"خطأ في رفع الملف: {str(e)}")

@app.on_callback_query()
@heavy_operation
async def handle_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    user = get_user(user_id)
    
    if not user or not user.get('api_key'):
        await callback_query.answer("ارسل API_KEY اولاً", show_alert=True)
        return
    
    if not user.get('sandbox_id'):
        await callback_query.answer("الساندبوكس غير موجود", show_alert=True)
        return
    
    try:
        sandbox = await asyncio.to_thread(Sandbox.connect, user['sandbox_id'], api_key=user['api_key'])
        await extend_sandbox_timeout(sandbox)
    except Exception as e:
        await callback_query.answer("اعادة انشاء الساندبوكس...", show_alert=True)
        success, result = await setup_sandbox(user_id, user['api_key'])
        if not success:
            await callback_query.message.edit_text(f"فشل: {result}")
            return
        sandbox = await asyncio.to_thread(Sandbox.connect, user['sandbox_id'], api_key=user['api_key'])
    
    if data == "back_main":
        await callback_query.message.edit_text(
            "القائمة الرئيسية",
            reply_markup=MAIN_MENU
        )
    
    elif data == "files_menu":
        await callback_query.message.edit_text(
            "ادارة الملفات",
            reply_markup=FILES_MENU
        )
    
    elif data == "run_bot":
        if not user.get('session_file'):
            await callback_query.answer("ارفع ملف الجلسة اولاً", show_alert=True)
            return
        
        screen_name = f"bot_{user_id}"
        
        if await check_bot_running(sandbox, screen_name):
            await callback_query.answer("السورس يعمل بالفعل", show_alert=True)
            logs = await get_bot_logs(sandbox)
            await callback_query.message.edit_text(
                f"السورس يعمل بالفعل\n\nآخر 30 سطر:\n{logs}",
                reply_markup=MAIN_MENU
            )
            return
        
        try:
            code = f"""
import os
os.system('which screen || apt-get install -y screen')
os.system(f'screen -S {screen_name} -X quit')
cmd = f"cd /root/pro && screen -dmS {screen_name} python3 main.py"
os.system(cmd)
print('running')
"""
            await asyncio.to_thread(sandbox.run_code, code)
            save_user(user_id, screen_name=screen_name, status="running")
            
            await asyncio.sleep(3)
            logs = await get_bot_logs(sandbox)
            
            await callback_query.answer("تم تشغيل السورس", show_alert=True)
            await callback_query.message.edit_text(
                f"تم تشغيل السورس في الخلفية (screen)\n\nآيرجى انتظار لمدة 1 دقيقة ثم .فحص",
                reply_markup=MAIN_MENU
            )
        except Exception as e:
            await callback_query.message.edit_text(f"خطأ: {str(e)}")
    
    elif data == "stop_bot":
        if not user.get('screen_name'):
            await callback_query.answer("السورس غير مشغل", show_alert=True)
            return
        
        if not await check_bot_running(sandbox, user['screen_name']):
            await callback_query.answer("السورس متوقف بالفعل", show_alert=True)
            save_user(user_id, screen_name=None, status="stopped")
            await callback_query.message.edit_text(
                "السورس متوقف بالفعل",
                reply_markup=MAIN_MENU
            )
            return
        
        try:
            code = f"""
import os
os.system(f'screen -S {user["screen_name"]} -X quit')
os.system(f'pkill -f "python3 main.py"')
os.system(f'pkill -f "main.py"')
os.system(f'ps aux | grep "/root/pro" | grep -v grep | awk \'{{print $2}}\' | xargs kill -9 2>/dev/null')
print('stopped')
"""
            await asyncio.to_thread(sandbox.run_code, code)
            save_user(user_id, screen_name=None, status="stopped")
            await callback_query.answer("تم ايقاف السورس", show_alert=True)
            await callback_query.message.edit_text(
                "تم ايقاف السورس",
                reply_markup=MAIN_MENU
            )
        except Exception as e:
            await callback_query.message.edit_text(f"خطأ: {str(e)}")
    
    elif data == "restart_bot":
        try:
            if user.get('screen_name') and await check_bot_running(sandbox, user['screen_name']):
                code_stop = f"""
import os
os.system(f'screen -S {user["screen_name"]} -X quit')
os.system(f'pkill -f "python3 main.py"')
"""
                await asyncio.to_thread(sandbox.run_code, code_stop)
                await asyncio.sleep(2)
            
            if not user.get('session_file'):
                await callback_query.answer("ارفع ملف الجلسة اولاً", show_alert=True)
                return
            
            screen_name = f"bot_{user_id}"
            code_start = f"""
import os
os.system('which screen || apt-get install -y screen')
os.system(f'screen -S {screen_name} -X quit')
cmd = f"cd /root/pro && screen -dmS {screen_name} python3 main.py"
os.system(cmd)
print('running')
"""
            await asyncio.to_thread(sandbox.run_code, code_start)
            save_user(user_id, screen_name=screen_name, status="running")
            await asyncio.sleep(3)
            logs = await get_bot_logs(sandbox)
            
            await callback_query.answer("تم اعادة تشغيل السورس", show_alert=True)
            await callback_query.message.edit_text(
                f"تم اعادة تشغيل السورس\n\nآخر 30 سطر:\n{logs}",
                reply_markup=MAIN_MENU
            )
        except Exception as e:
            await callback_query.message.edit_text(f"خطأ: {str(e)}")
    
    elif data == "status_bot":
        try:
            if user.get('screen_name'):
                if await check_bot_running(sandbox, user['screen_name']):
                    status = "يعمل"
                else:
                    status = "متوقف"
                    save_user(user_id, screen_name=None, status="stopped")
            else:
                status = "غير مشغل"
            
            logs = await get_bot_logs(sandbox)
            await callback_query.message.edit_text(
                f"الحالة: {status}\n\nآخر 30 سطر:\n{logs}",
                reply_markup=MAIN_MENU
            )
        except Exception as e:
            await callback_query.message.edit_text(f"خطأ: {str(e)}")
    
    elif data == "list_files":
        files = await get_files_list(sandbox)
        if files:
            files_text = "\n".join([f"{i+1}. {f}" for i, f in enumerate(files)])
            await callback_query.message.edit_text(
                f"الملفات في /root/pro:\n\n{files_text}",
                reply_markup=FILES_MENU
            )
        else:
            await callback_query.message.edit_text(
                "لا توجد ملفات في المجلد",
                reply_markup=FILES_MENU
            )
    
    elif data == "upload_file":
        await callback_query.message.edit_text(
            "ارسل الملف الذي تود رفعه\n"
            "سيرفع تلقائياً الى /root/pro",
            reply_markup=FILES_MENU
        )
    
    elif data == "delete_file":
        files = await get_files_list(sandbox)
        if not files:
            await callback_query.answer("لا توجد ملفات للحذف", show_alert=True)
            return
        
        files_text = "\n".join([f"{i+1}. {f}" for i, f in enumerate(files)])
        save_user(user_id, temp_action="delete_file")
        
        await callback_query.message.edit_text(
            f"الملفات المتاحة للحذف:\n\n{files_text}\n\n"
            "ارسل رقم الملف الذي تود حذفه\n"
            "او اكتب (الغاء) للالغاء",
            reply_markup=FILES_MENU
        )
    
    elif data == "delete_session":
        if user.get('session_file'):
            try:
                await asyncio.to_thread(sandbox.run_code, f"import os; os.remove('/root/pro/{user['session_file']}')")
                save_user(user_id, session_file=None)
                await callback_query.answer("تم حذف الجلسة", show_alert=True)
                await callback_query.message.edit_text(
                    "تم حذف ملف الجلسة",
                    reply_markup=MAIN_MENU
                )
            except Exception as e:
                await callback_query.message.edit_text(f"خطأ: {str(e)}")
        else:
            await callback_query.answer("لا توجد جلسة للحذف", show_alert=True)
    
    elif data == "delete_data":
        try:
            if user.get('screen_name'):
                await asyncio.to_thread(sandbox.run_code, f"import os; os.system('screen -S {user['screen_name']} -X quit')")
                await asyncio.to_thread(sandbox.run_code, "pkill -f 'main.py'")
            await asyncio.to_thread(sandbox.delete)
        except:
            pass
        
        delete_user(user_id)
        await callback_query.answer("تم حذف البيانات", show_alert=True)
        await callback_query.message.edit_text(
            "تم حذف جميع بياناتك\nارسل /start للبدء"
        )

print("السورس يعمل بكامل طاقته التزامنية وبدون حظر...")
app.run()
