import os
import subprocess
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC, error as ID3Error

TOKEN = os.getenv("BOT_TOKEN", "ضع_التوكن_هنا")

user_data = {}

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {"title": None, "artist": None, "image": None}
    return user_data[uid]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid] = {"title": None, "artist": None, "image": None}
    text = (
        "🎵 *بوت تحرير الأغاني*\n\n"
        "الخطوات بالترتيب:\n"
        "1️⃣ /title اسم الأغنية\n"
        "2️⃣ /artist اسم الفنان\n"
        "3️⃣ أرسل *صورة* الغلاف\n"
        "4️⃣ أرسل *فيديو أو ملف صوتي*\n\n"
        "✅ البوت يحول الفيديو تلقائياً لـ MP3\n"
        "📋 /status لمشاهدة البيانات المدخلة"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ اكتب اسم الأغنية بعد الأمر\nمثال: /title حبيبي")
        return
    get_user(uid)["title"] = " ".join(context.args)
    await update.message.reply_text(f"✅ تم حفظ اسم الأغنية: *{get_user(uid)['title']}*", parse_mode="Markdown")

async def set_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❌ اكتب اسم الفنان بعد الأمر\nمثال: /artist ماجد المهندس")
        return
    get_user(uid)["artist"] = " ".join(context.args)
    await update.message.reply_text(f"✅ تم حفظ اسم الفنان: *{get_user(uid)['artist']}*", parse_mode="Markdown")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = get_user(uid)
    text = (
        "📋 *البيانات الحالية:*\n"
        f"🎵 الأغنية: {d['title'] or '❌ لم تُدخل'}\n"
        f"🎤 الفنان: {d['artist'] or '❌ لم تُدخل'}\n"
        f"🖼 الصورة: {'✅ محفوظة' if d['image'] else '❌ لم تُدخل'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    file = await update.message.photo[-1].get_file()
    path = f"cover_{uid}.jpg"
    await file.download_to_drive(path)
    get_user(uid)["image"] = path
    await update.message.reply_text("✅ تم حفظ صورة الغلاف!")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = get_user(uid)
    missing = []
    if not d["title"]:
        missing.append("اسم الأغنية /title")
    if not d["artist"]:
        missing.append("اسم الفنان /artist")
    if missing:
        await update.message.reply_text(
            "⚠️ ناقص:\n" + "\n".join(f"• {m}" for m in missing) +
            "\n\nأدخل البيانات الناقصة ثم أعد إرسال الملف."
        )
        return
    msg = await update.message.reply_text("⏳ جاري المعالجة...")
    if update.message.video:
        file = await update.message.video.get_file()
        raw_path = f"raw_{uid}.mp4"
    elif update.message.document:
        file = await update.message.document.get_file()
        fname = update.message.document.file_name or "file"
        ext = fname.rsplit(".", 1)[-1].lower()
        raw_path = f"raw_{uid}.{ext}"
    else:
        file = await update.message.audio.get_file()
        raw_path = f"raw_{uid}.mp3"
    await file.download_to_drive(raw_path)
    mp3_path = f"output_{uid}.mp3"
    if raw_path.endswith(".mp3"):
        os.rename(raw_path, mp3_path)
    else:
        await msg.edit_text("🔄 جاري تحويل الفيديو لـ MP3...")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_path, "-vn", "-ar", "44100", "-ac", "2", "-b:a", "192k", mp3_path],
            capture_output=True
        )
        os.remove(raw_path)
        if result.returncode != 0:
            await msg.edit_text("❌ فشل تحويل الفيديو! تأكد أن الملف صحيح.")
            return
    await msg.edit_text("🎨 جاري إضافة البيانات للملف...")
    try:
        audio = MP3(mp3_path, ID3=ID3)
        try:
            audio.add_tags()
        except ID3Error:
            pass
        audio["TIT2"] = TIT2(encoding=3, text=d["title"])
        audio["TPE1"] = TPE1(encoding=3, text=d["artist"])
        if d["image"]:
            with open(d["image"], "rb") as img:
                audio["APIC"] = APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=img.read()
                )
        audio.save()
    except Exception as e:
        await msg.edit_text(f"❌ خطأ في إضافة البيانات: {e}")
        return
    await msg.edit_text("📤 جاري الإرسال...")
    safe_title = d["title"].replace("/", "-")
    filename = f"{safe_title} - {d['artist']}.mp3"
    with open(mp3_path, "rb") as f:
        await update.message.reply_audio(
            audio=f,
            filename=filename,
            title=d["title"],
            performer=d["artist"],
            thumbnail=open(d["image"], "rb") if d["image"] else None
        )
    await msg.delete()
    for path in [mp3_path, d.get("image")]:
        if path and os.path.exists(path):
            os.remove(path)
    user_data[uid] = {"title": None, "artist": None, "image": None}

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("title", set_title))
app.add_handler(CommandHandler("artist", set_artist))
app.add_handler(CommandHandler("status", status))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.Document.ALL, handle_media))

print("✅ البوت شغال!")
app.run_polling()
