import re
import asyncio
import time
import aiohttp
import discord
import random
from discord.ext import commands, tasks
import yt_dlp
import os
import io
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import requests
import urllib.parse

# ================== CONFIG ==================
TOKEN =  os.getenv("TOKEN_DISCORD")
PREFIX = "!"
ADMIN_ID = 894935877833334894

WELCOME_CHANNEL_ID = 1531815754570403881

# ================= CONFIG API =================
GOROUTER_API_URL = "https://gorouter.app/v1/chat/completions"
GOROUTER_API_KEY = "sk-N9g2oyVPrpU0jIJS49V6WHhPxf1A8NpPBsbTrzQqHeTC5Nlm"
MODEL_NAME = "claude-opus-5-thinking"

# ===== CONFIG THEGIARE =====
THEGIARE_USERNAME = "catvuc@gmail.com"  # Email hoặc Số điện thoại/Tên đăng nhập
THEGIARE_PASSWORD = "Tranvu2010"

# ===== DANH SÁCH NHÀ MẠNG HỖ TRỢ =====
VALID_CARD_TYPES = ["VIETTEL", "VINAPHONE", "MOBIFONE", "GARENA", "VCOIN", "ZING", "SCOIN24H"]

# ================= CONFIG API =================
LIKE_API_BASE = "http://api.arafatcodex.xyz:6112/like"
DEFAULT_KEY = "FREE3DAYS"
DEFAULT_SERVER = "vn"


# ================== CONFIG QLING API ==================
QLING_BASE_URL = "http://qling.ddns.net" 
CTV_API_KEY = "ctv_06ade37eed24869898c5cea328e0511c9215db7a"
CTV_PREFIX = "tranvuctv-"

# ================== CONFIG SEPAY & BANK ==================
SEPAY_API_KEY = "DTFIM8QUU2ENQWXPYPNCVMFUNVFD47498K6VE6XHB1AS3AJIOGGRIDLZRCQTTLTW"  # Lấy tại my.sepay.vn (Mục Cấu hình Công ty -> API Access)
MB_STK      = "9006688668"               # Số tài khoản nhận tiền
MB_ACCOUNT_NAME = "NGO THI THUONG"   # Tên chủ tài khoản (Viết hoa không dấu)

PRICE_TABLE = {
    1: 7000,
    5: 25000,
    10: 40000,
    20: 70000,
    30: 100000
}

pending_orders = {}

def get_headers():
    return {
        "Content-Type": "application/json",
        "X-Ctv-Key": CTV_API_KEY,
        "User-Agent": "Mozilla/5.0"
    }

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ===== 3. KHỞI TẠO BYPASSER (SAU DÒNG bot = commands.Bot(...)) =====
MAX_SIZE_MB = 100
MAX_SIZE = MAX_SIZE_MB * 1024 * 1024

COOKIE_FILE = "cookies.txt"

#================= HELPER FUNCTIONS =================
def create_embed(title, description):
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x00ffcc
    )
    embed.set_footer(text="Komura BOT 🌸")
    return embed

async def auto_delete(message):
    await asyncio.sleep(30)
    try:
        await message.delete()
    except Exception:
        pass

def tao_user_wazue_qling(username, password, days, plan=2):
    if not username.startswith(CTV_PREFIX):
        username = f"{CTV_PREFIX}{username}"

    url_create = f"{QLING_BASE_URL}/api/ctv/users"
    res1 = requests.post(url_create, json={"username": username, "password": password}, headers=get_headers(), timeout=10)
    if not res1.ok:
        return False, res1.json().get("message", "Lỗi tạo tài khoản Qling")

    url_update = f"{QLING_BASE_URL}/api/ctv/users/{urllib.parse.quote(username)}"
    res2 = requests.put(url_update, json={"plan": plan, "extend_days": days}, headers=get_headers(), timeout=10)
    
    if res2.ok:
        return True, username
    return False, "Tạo user thành công nhưng lỗi cài đặt hạn dùng!"

# Bộ nhớ lưu các ID giao dịch SePAY đã được xử lý (tránh duyệt lại lần 2)
PROCESSED_SEPAY_IDS = set()

def check_sepay_payment(memo_code, amount, order_created_time_str):
    """
    Hàm kiểm tra giao dịch từ SePAY:
    - Bỏ qua ID đã duyệt.
    - Bỏ qua giao dịch diễn ra TRƯỚC thời điểm tạo đơn (order_created_time_str).
    """
    headers = {
        "Authorization": f"Bearer {SEPAY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get("https://my.sepay.vn/userapi/transactions/list", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            transactions = data.get("transactions", [])
            
            for tx in transactions:
                tx_id = str(tx.get("id"))
                tx_amount = float(tx.get("amount_in", 0))
                tx_content = str(tx.get("transaction_content", ""))
                tx_date = str(tx.get("transaction_date", "")) # Định dạng từ SePAY: YYYY-MM-DD HH:MM:SS

                # 1. Bỏ qua nếu giao dịch này đã từng được duyệt thành công
                if tx_id in PROCESSED_SEPAY_IDS:
                    continue

                # 2. Bỏ qua nếu giao dịch xảy ra TRƯỚC LÚC TẠO ĐƠN (chống dùng bill cũ)
                if tx_date < order_created_time_str:
                    continue

                # 3. Kiểm tra đúng Nội dung CK và Số tiền
                if memo_code in tx_content and tx_amount >= amount:
                    PROCESSED_SEPAY_IDS.add(tx_id) # Đánh dấu ID này đã xử lý
                    return True
                    
    except Exception as e:
        print(f"Lỗi kiểm tra SePAY: {e}")
        
    return False




# ================= WELCOME / GOODBYE =================
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return
    gif_file = discord.File("welcome.gif", filename="welcome.gif")
    embed = discord.Embed(
        title="🎉 Chào mừng!",
        description=f"👋 Xin chào {member.mention} đến với server!",
        color=0x00ffcc
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    embed.set_image(url="attachment://welcome.gif")
    embed.add_field(name="📌 Thông tin", value=f"👤 Tên: {member.name}\n🆔 ID: {member.id}", inline=False)
    embed.set_footer(text="Komura BOT 🌸")
    await channel.send(file=gif_file, embed=embed)

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return
    gif_file = discord.File("goodbye.gif", filename="goodbye.gif")
    embed = discord.Embed(
        title="😢 Tạm biệt!",
        description=f"{member.name} đã rời server...",
        color=0xff0000
    )
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    embed.set_image(url="attachment://goodbye.gif")
    embed.set_footer(text="Hẹn gặp lại 👋")
    await channel.send(file=gif_file, embed=embed)

@bot.event
async def on_ready():
    print(f"🔥 Bot đã online: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ================= TIKTOK CORE =================
async def process_tiktok(url, get_audio=False):
    api_url = f"https://www.tikwm.com/api/?url={url}"
    res = requests.get(api_url, timeout=15).json()

    if res.get("code") != 0:
        return None, [], False

    data = res["data"]
    title = data.get("title", "TikTok Media")
    author = data.get("author", {}).get("nickname", "TikTok User")
    likes = data.get("digg_count", 0)
    views = data.get("play_count", 0)

    desc = f"""
🎬 **Tiêu đề:** {title}
👤 **Kênh:** {author}
👍 **Lượt thích:** {likes:,}
👁 **Lượt xem:** {views:,}
🔗 **Link:** {url}
"""

    files_to_send = []
    is_slide = False

    if "images" in data and data["images"]:
        is_slide = True
        images = data["images"]
        for idx, img_url in enumerate(images[:10]):
            img_bytes = requests.get(img_url).content
            file_name = f"tt_img_{idx}.jpg"
            with open(file_name, "wb") as f:
                f.write(img_bytes)
            files_to_send.append(file_name)
    else:
        video_url = data.get("play")
        if video_url:
            v_bytes = requests.get(video_url).content
            file_name = "tt_video.mp4"
            with open(file_name, "wb") as f:
                f.write(v_bytes)
            files_to_send.append(file_name)

    if get_audio:
        music_url = data.get("music")
        if music_url:
            m_bytes = requests.get(music_url).content
            m_file_name = "tt_audio.mp3"
            with open(m_file_name, "wb") as f:
                f.write(m_file_name)
            files_to_send.append(m_file_name)

    return desc, files_to_send, is_slide

# ================= YOUTUBE CORE =================
def _yt_download_worker(url, v_file, get_audio):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
        'outtmpl': v_file,
        'quiet': True,
        'noplaylist': True,
    }

    if os.path.exists(COOKIE_FILE):
        ydl_opts['cookiefile'] = COOKIE_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    a_file = "yt_audio.mp3"
    if get_audio:
        ydl_audio_opts = {
            'format': 'bestaudio/best',
            'outtmpl': a_file,
            'quiet': True,
            'noplaylist': True,
            'overwrites': True,
        }
        if os.path.exists(COOKIE_FILE):
            ydl_audio_opts['cookiefile'] = COOKIE_FILE

        with yt_dlp.YoutubeDL(ydl_audio_opts) as ydl_a:
            ydl_a.extract_info(url, download=True)

    return info

async def process_youtube(url, get_audio=False):
    v_file = "yt_video.mp4"
    a_file = "yt_audio.mp3"

    for f_check in [v_file, a_file]:
        if os.path.exists(f_check):
            try:
                os.remove(f_check)
            except Exception:
                pass

    try:
        info = await asyncio.to_thread(_yt_download_worker, url, v_file, get_audio)
    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None, []

    if not info:
        return None, []

    title = info.get("title", "YouTube Video")
    uploader = info.get("uploader", "Unknown")
    likes = info.get("like_count", 0) or 0
    views = info.get("view_count", 0) or 0
    duration = info.get("duration", 0) or 0

    mins = duration // 60
    secs = duration % 60
    duration_text = f"{mins}:{secs:02d}" if duration else "Unknown"

    desc = f"""
🎬 **Tiêu đề:** {title}
👤 **Kênh:** {uploader}
👍 **Lượt thích:** {likes:,}
👁 **Lượt xem:** {views:,}
⏱ **Thời lượng:** {duration_text}
🔗 **Link:** {info.get('webpage_url', url)}
"""

    files_to_send = []
    if os.path.exists(v_file):
        files_to_send.append(v_file)
    if get_audio and os.path.exists(a_file):
        files_to_send.append(a_file)

    return desc, files_to_send

# ================= COMMANDS =================
@bot.command(name="tt")
async def tiktok_download(ctx, url: str):
    delete_task = asyncio.create_task(auto_delete(ctx.message))
    msg = await ctx.send("⏳ Đang tải TikTok...")

    try:
        desc, file_paths, is_slide = await process_tiktok(url, get_audio=False)
        if not desc or not file_paths:
            await msg.edit(content="❌ Không tải được TikTok này!")
            return

        embed = create_embed("🎉 Tải TikTok Thành Công", desc)
        discord_files = [discord.File(f) for f in file_paths if os.path.exists(f)]

        await ctx.send(embed=embed, files=discord_files)
        delete_task.cancel()
        try:
            await ctx.message.delete()
        except Exception:
            pass

    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")
    finally:
        for f in file_paths:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        try:
            await msg.delete()
        except Exception:
            pass

@bot.command(name="ttmp3")
async def tiktok_mp3_download(ctx, url: str):
    delete_task = asyncio.create_task(auto_delete(ctx.message))
    msg = await ctx.send("⏳ Đang tải TikTok + MP3...")

    try:
        desc, file_paths, is_slide = await process_tiktok(url, get_audio=True)
        if not desc or not file_paths:
            await msg.edit(content="❌ Không tải được TikTok này!")
            return

        embed = create_embed("🎉 Tải TikTok + MP3 Thành Công", desc)
        discord_files = [discord.File(f) for f in file_paths if os.path.exists(f)]

        await ctx.send(embed=embed, files=discord_files)
        delete_task.cancel()
        try:
            await ctx.message.delete()
        except Exception:
            pass

    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")
    finally:
        for f in file_paths:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        try:
            await msg.delete()
        except Exception:
            pass

@bot.command(name="yt")
async def youtube_download(ctx, url: str):
    delete_task = asyncio.create_task(auto_delete(ctx.message))
    msg = await ctx.send("⏳ Đang tải YouTube...")

    try:
        desc, file_paths = await process_youtube(url, get_audio=False)
        if not desc or not file_paths:
            await msg.edit(content="❌ Không tải được YouTube này!")
            return

        embed = create_embed("🎉 Tải YouTube Thành Công", desc)
        discord_files = [discord.File(f) for f in file_paths if os.path.exists(f)]

        await ctx.send(embed=embed, files=discord_files)
        delete_task.cancel()
        try:
            await ctx.message.delete()
        except Exception:
            pass

    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")
    finally:
        for f in file_paths:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        try:
            await msg.delete()
        except Exception:
            pass

@bot.command(name="ytmp3")
async def youtube_mp3_download(ctx, url: str):
    delete_task = asyncio.create_task(auto_delete(ctx.message))
    msg = await ctx.send("⏳ Đang tải YouTube + MP3...")

    try:
        desc, file_paths = await process_youtube(url, get_audio=True)
        if not desc or not file_paths:
            await msg.edit(content="❌ Không tải được YouTube này!")
            return

        embed = create_embed("🎉 Tải YouTube + MP3 Thành Công", desc)
        discord_files = [discord.File(f) for f in file_paths if os.path.exists(f)]

        await ctx.send(embed=embed, files=discord_files)
        delete_task.cancel()
        try:
            await ctx.message.delete()
        except Exception:
            pass

    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")
    finally:
        for f in file_paths:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        try:
            await msg.delete()
        except Exception:
            pass

@bot.command(name="mp3")
async def general_mp3_download(ctx, url: str):
    delete_task = asyncio.create_task(auto_delete(ctx.message))
    msg = await ctx.send("🎧 Đang tải âm thanh (Tốc độ cao)...")

    for file in os.listdir("."):
        if file.startswith("downloaded_audio"):
            try:
                os.remove(file)
            except Exception:
                pass

    try:
        if "tiktok.com" in url or "vt.tiktok.com" in url:
            api_url = f"https://www.tikwm.com/api/?url={url}"
            res = requests.get(api_url, timeout=15).json()

            if res.get("code") == 0:
                music_url = res["data"].get("music")
                if music_url:
                    m_bytes = requests.get(music_url).content
                    with open("downloaded_audio.mp3", "wb") as f:
                        f.write(m_bytes)

        file_found = None
        for file in os.listdir("."):
            if file.startswith("downloaded_audio"):
                file_found = file
                break

        if not file_found:
            target_url = url
            if "spotify.com" in url:
                target_url = f"ytsearch1:{url}"

            def _download_audio_fast():
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': 'downloaded_audio.%(ext)s',
                    'concurrent_fragment_downloads': 8,
                    'quiet': True,
                    'noplaylist': True,
                }
                if os.path.exists(COOKIE_FILE):
                    ydl_opts['cookiefile'] = COOKIE_FILE

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(target_url, download=True)

            await asyncio.to_thread(_download_audio_fast)

            for file in os.listdir("."):
                if file.startswith("downloaded_audio"):
                    file_found = file
                    break

        if not file_found or not os.path.exists(file_found):
            await msg.edit(content="❌ Không thể lấy file âm thanh từ liên kết này!")
            return

        size = os.path.getsize(file_found)
        if size <= MAX_SIZE:
            await ctx.send(file=discord.File(file_found))
        else:
            await ctx.send(f"⚠️ File quá lớn ({size // (1024*1024)}MB)!")

        delete_task.cancel()
        try:
            await ctx.message.delete()
        except Exception:
            pass

    except Exception as e:
        print(f"Lỗi MP3: {e}")
        await ctx.send(f"❌ Lỗi tải âm thanh: {e}")

    finally:
        for file in os.listdir("."):
            if file.startswith("downloaded_audio"):
                try:
                    os.remove(file)
                except Exception:
                    pass
        try:
            await msg.delete()
        except Exception:
            pass

# =================== CHANNEL CONTROL ===================
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lockrole(ctx, role: discord.Role):
    channel = ctx.channel
    await channel.set_permissions(role, send_messages=False, send_messages_in_threads=False)
    await ctx.send(f"🔒 Đã khóa role {role.mention} trong kênh này")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlockrole(ctx, role: discord.Role):
    channel = ctx.channel
    await channel.set_permissions(role, send_messages=True, send_messages_in_threads=True)
    await ctx.send(f"🔓 Đã mở khóa role {role.mention}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def locktime(ctx, minutes: int = 0):
    channel = ctx.channel
    role = ctx.guild.default_role
    if minutes > 0:
        await ctx.send(f"⏱ Kênh sẽ bị khóa sau {minutes} phút...")
        await asyncio.sleep(minutes * 60)
    await channel.set_permissions(role, send_messages=False, send_messages_in_threads=False)
    await ctx.send("🔒 Kênh đã bị khóa")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    channel = ctx.channel
    role = ctx.guild.default_role
    await channel.set_permissions(role, send_messages=True, send_messages_in_threads=True)
    await ctx.send("🔓 Kênh đã mở lại")

ANIME_API_POOL = [
    {"url": "https://api.waifu.im/search?included_tags=waifu", "parse": lambda r: r["images"][0]["url"]},
    {"url": "https://nekos.best/api/v2/waifu", "parse": lambda r: r["results"][0]["url"]},
    {"url": "https://nekos.life/api/v2/img/waifu", "parse": lambda r: r["url"]},
    {"url": "https://api.catboys.com/img", "parse": lambda r: r["url"]},
    {"url": "https://purrbot.site/api/img/sfw/background/img", "parse": lambda r: r["link"]},
    {"url": "https://nekos.best/api/v2/neko", "parse": lambda r: r["results"][0]["url"]},
    {"url": "https://nekos.life/api/v2/img/neko", "parse": lambda r: r["url"]},
    {"url": "https://nekos.best/api/v2/kitsune", "parse": lambda r: r["results"][0]["url"]},
    {"url": "https://api.otakugifs.xyz/gif?reaction=smile", "parse": lambda r: r["url"]}
]

@bot.command(name="waifu", aliases=["anime", "neko"])
async def get_random_anime_image(ctx):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    shuffled_apis = ANIME_API_POOL.copy()
    random.shuffle(shuffled_apis)
    
    img_url = None
    used_api_domain = ""

    for api_info in shuffled_apis:
        try:
            res = requests.get(api_info["url"], headers=headers, timeout=4).json()
            img_url = api_info["parse"](res)
            if img_url:
                used_api_domain = api_info["url"].split("/")[2]
                break
        except Exception:
            continue

    if not img_url:
        await ctx.send("❌ Đã thử tất cả API nhưng không kết nối được server nào!")
        return

    try:
        img_bytes = requests.get(img_url, headers=headers, timeout=8).content
        ext = img_url.split(".")[-1].split("?")[0]
        if len(ext) > 4 or "/" in ext: 
            ext = "png"
            
        file_name = f"anime_pic.{ext}"

        with open(file_name, "wb") as f:
            f.write(img_bytes)

        caption = f"🌸 **Ảnh Anime dành cho bạn!** *(Nguồn: `{used_api_domain}`)*"
        await ctx.send(content=caption, file=discord.File(file_name))
        
    except Exception as e:
        await ctx.send(f"❌ Lỗi gửi ảnh: {e}")
    finally:
        for f in os.listdir("."):
            if f.startswith("anime_pic."):
                try:
                    os.remove(f)
                except Exception:
                    pass

@bot.command(name="quote")
async def anime_quote(ctx):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        res = requests.get("https://catboys.com/api/bakagoto", headers=headers, timeout=5).json()
        quote = res.get("result")
        if quote:
            await ctx.send(f"💬 *\"{quote}\"* — 👤 **Catboys API**")
            return
    except Exception:
        pass

    quotes_database = [
        ("People die if they are killed...", "Emiya Shirou", "Fate/stay night"),
        ("If you don't take risks, you can't create a future.", "Monkey D. Luffy", "One Piece"),
        ("Whatever you lose, you'll find it again. But what you throw away you'll never get back.", "Kenshin Himura", "Rurouni Kenshin"),
        ("Fear is not evil. It tells you what your weakness is.", "Gildarts Clive", "Fairy Tail"),
        ("Push through the pain, giving up hurts more.", "Vegeta", "Dragon Ball Z")
    ]
    
    q, c, a = random.choice(quotes_database)
    await ctx.send(f"💬 *\"{q}\"*\n\n👤 **{c}** — 🎬 *{a}*")

# =============== List Nhapma =========

# ID Discord của bạn (để dùng lệnh được cả trong DM lẫn Server)
ADMIN_USER_IDS = [894935877833334894]  # Thay ID Discord của bạn vào đây

NHAPMA_TOKEN = "d4c38e3a-ade0-4ae2-9652-cec4aec4d71b"
DB_FILE = "links_history.json"

# ==============================================================================
# HÀM LƯU / ĐỌC DỮ LIỆU LINK ĐÃ TẠO
# ==============================================================================
def load_links():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_link_data(original_url, shortened_url, alias, creator_id):
    links = load_links()
    new_entry = {
        "shortenedUrl": shortened_url,
        "originalUrl": original_url,
        "alias": alias if alias else "Không có",
        "creator_id": creator_id
    }
    # Thêm vào đầu danh sách để link mới nhất lên trên
    links.insert(0, new_entry)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=4)

# ==============================================================================
# VIEW CHUYỂN TRANG (PAGINATION)
# ==============================================================================
class LinkPaginator(discord.ui.View):
    def __init__(self, links_data, author_id, per_page=5):
        super().__init__(timeout=120)
        self.links = links_data
        self.author_id = author_id
        self.per_page = per_page
        self.current_page = 0
        self.max_page = (len(links_data) - 1) // per_page + 1
        self.update_buttons()

    def update_buttons(self):
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page >= self.max_page - 1)

    def create_embed(self) -> discord.Embed:
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_items = self.links[start:end]

        embed = discord.Embed(
            title="🔗 DANH SÁCH LINK ĐÃ RÚT GỌN",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Trang {self.current_page + 1}/{self.max_page} • Tổng số: {len(self.links)} link")

        for item in page_items:
            short_link = item.get("shortenedUrl", "N/A")
            original_url = item.get("originalUrl", "N/A")
            alias = item.get("alias", "Không có")

            field_value = (
                f"🌐 **Link gốc (Full):** `{original_url}`\n"
                f"🏷️ **Alias:** `{alias}`"
            )
            embed.add_field(name=f"👉 `{short_link}`", value=field_value, inline=False)

        return embed


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Bạn không có quyền thao tác trên menu này!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Trang trước", style=discord.ButtonStyle.blurple, custom_id="prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Trang sau ▶", style=discord.ButtonStyle.blurple, custom_id="next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

# ==============================================================================
# LỆNH RÚT GỌN LINK (!nhapma / !nm) - TỰ LƯU DỮ LIỆU
# ==============================================================================
@bot.command(name="nhapma", aliases=["nm"])
async def shorten_nhapma(ctx, url: str, alias: str = None):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    encoded_url = urllib.parse.quote(url, safe="")
    api_url = f"https://service.nhapma.com/api?token={NHAPMA_TOKEN}&url={encoded_url}"
    if alias:
        api_url += f"&alias={urllib.parse.quote(alias)}"

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                res = await response.json(content_type=None)

                if res.get("status") == "error":
                    error_msg = res.get("message", "Lỗi không xác định từ Nhapma")
                    await ctx.send(f"❌ **Rút gọn thất bại:** {error_msg}")
                else:
                    shortened_url = res.get("shortenedUrl")
                    # Lưu link vừa rút gọn vào file cục bộ
                    save_link_data(url, shortened_url, alias, ctx.author.id)
                    await ctx.send(f"🔗 **Link Nhapma:** {shortened_url}")

    except Exception as e:
        await ctx.send(f"❌ **Lỗi kết nối API:** {e}")

# ==============================================================================
# LỆNH XEM DANH SÁCH LINK (!listnm / !listlinks)
# ==============================================================================
@bot.command(name="listnm", aliases=["listlinks", "ll"])
async def list_links(ctx):
    # Kiểm tra quyền: Hoặc là Admin Server, hoặc là ID Admin cài sẵn (dùng cho DM)
    is_server_admin = ctx.guild and ctx.author.guild_permissions.administrator
    is_bot_owner = ctx.author.id in ADMIN_USER_IDS

    if not (is_server_admin or is_bot_owner):
        return await ctx.send("🛑 **Quyền hạn không đủ:** Lệnh này chỉ dành cho **Administrator**!")

    links_data = load_links()

    if not links_data:
        return await ctx.send("📂 **Hiện chưa có link nào được rút gọn qua bot!**")

    paginator = LinkPaginator(links_data=links_data, author_id=ctx.author.id, per_page=5)
    await ctx.send(embed=paginator.create_embed(), view=paginator)

# ================= LỆNH NẠP GÓI WAZUE (ĐÃ FIX LỖI) =================
@bot.command(name="napgoi", aliases=["nap", "muagoi"])
async def nap_goi_wazue(ctx, days: int = None):
    if days is None or days not in PRICE_TABLE:
        embed = discord.Embed(
            title="💳 HƯỚNG DẪN NẠP GÓI WAZUE (SEPAY AUTOMATION)",
            description="Vui lòng chọn một trong các gói dịch vụ quy định bên dưới:",
            color=0x00ffcc
        )
        embed.add_field(
            name="📌 BẢNG GIÁ QUY ĐỊNH",
            value=(
                "• **Gói  1 Ngày**: `7,000` VNĐ  ➜ Cú pháp: `!napgoi 1`\n"
                "• **Gói  5 Ngày**: `25,000` VNĐ ➜ Cú pháp: `!napgoi 5`\n"
                "• **Gói 10 Ngày**: `40,000` VNĐ ➜ Cú pháp: `!napgoi 10`\n"
                "• **Gói 20 Ngày**: `70,000` VNĐ ➜ Cú pháp: `!napgoi 20`\n"
                "• **Gói 30 Ngày**: `100,000` VNĐ ➜ Cú pháp: `!napgoi 30`\n"
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️ LƯU Ý QUAN TRỌNG",
            value=(
                "1. Chuyển khoản **ĐÚNG SỐ TIỀN** của gói đã chọn.\n"
                "2. Nội dung chuyển tiền ghi đúng mã: `WAZUE<ID_Discord>`.\n"
                "3. Mã QR hóa đơn sẽ được gửi **trực tiếp qua Tin Nhắn Riêng (DM)**."
            ),
            inline=False
        )
        embed.set_footer(text="Komura BOT 🌸 | Powered by SePAY")
        await ctx.send(embed=embed)
        return

    user_id_str = str(ctx.author.id)

    # 1. Nếu user đã có đơn pending cũ -> Xóa đơn cũ đi để ghi nhận đơn mới
    if user_id_str in pending_orders:
        del pending_orders[user_id_str]

    so_tien = PRICE_TABLE[days]
    memo_code = f"WAZUE{user_id_str}"

    vietnam_tz = timezone(timedelta(hours=7))
    order_time_vn = datetime.now(vietnam_tz)
    order_time_str = order_time_vn.strftime("%Y-%m-%d %H:%M:%S")

    pending_orders[user_id_str] = {
        "days": days,
        "amount": so_tien,
        "channel_id": ctx.channel.id,
        "username_discord": ctx.author.name,
        "order_time": order_time_str
    }

    clean_name = " ".join(MB_ACCOUNT_NAME.split())
    encoded_name = urllib.parse.quote(clean_name)
    encoded_memo = urllib.parse.quote(memo_code)
    
    qr_url = f"https://img.vietqr.io/image/MB-{MB_STK}-compact2.png?amount={so_tien}&addInfo={encoded_memo}&accountName={encoded_name}"

    embed_bill = discord.Embed(
        title=f"📥 ĐƠN NẠP MUA WAZUE ({days} NGÀY)",
        description=f"Vui lòng quét mã QR bên dưới hoặc chuyển khoản chính xác thông tin:",
        color=0xffcc00
    )
    embed_bill.add_field(name="🏦 Ngân hàng", value="`MBBank`", inline=True)
    embed_bill.add_field(name="🔢 Số tài khoản", value=f"`{MB_STK}`", inline=True)
    embed_bill.add_field(name="👤 Chủ tài khoản", value=f"`{clean_name}`", inline=True)
    embed_bill.add_field(name="💰 Số tiền", value=f"`{so_tien:,} VNĐ`", inline=False)
    embed_bill.add_field(name="📝 Nội dung CK (Bắt buộc)", value=f"`{memo_code}`", inline=False)
    embed_bill.set_footer(text="Hệ thống tự động duyệt tiền sau 5 - 10 giây... Hạn thanh toán: 10 phút.")

    # Tạo tên file tạm riêng biệt cho từng User
    temp_qr_file = f"qr_temp_{user_id_str}.png"

    try:
        qr_bytes = requests.get(qr_url, timeout=10).content
        with open(temp_qr_file, "wb") as f:
            f.write(qr_bytes)
        file = discord.File(temp_qr_file, filename="qr_code.png")
        embed_bill.set_image(url="attachment://qr_code.png")
        
        await ctx.author.send(file=file, embed=embed_bill)
        
        if os.path.exists(temp_qr_file):
            os.remove(temp_qr_file)

        notify_embed = discord.Embed(
            title="📩 ĐÃ GỬI HÓA ĐƠN THANH TOÁN!",
            description=f"Chào {ctx.author.mention}, bot đã gửi **mã QR và thông tin nạp gói {days} ngày** vào **Tin nhắn riêng (DM)** của bạn. Vui lòng kiểm tra hộp thư tin nhắn nhé!",
            color=0x00ffcc
        )
        await ctx.send(embed=notify_embed)

    except discord.Forbidden:
        if user_id_str in pending_orders:
            del pending_orders[user_id_str]
        error_embed = discord.Embed(
            title="❌ KHÔNG THỂ GỬI TIN NHẮN RIÊNG!",
            description=f"{ctx.author.mention}, bạn đang **tắt tính năng nhận Tin nhắn riêng (DM)** từ thành viên Server!\nVui lòng vào **Cài đặt Discord ➔ Quyền riêng tư & An toàn ➔ Bật 'Cho phép tin nhắn trực tiếp từ thành viên máy chủ'** rồi thử lại.",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)
        return
    except Exception:
        embed_bill.set_image(url=qr_url)
        await ctx.author.send(embed=embed_bill)
        await ctx.send(f"📩 {ctx.author.mention}, vui lòng kiểm tra **Tin nhắn riêng (DM)** để lấy mã QR thanh toán!")

    # VÒNG LẶP CHECK TIỀN TỰ ĐỘNG (10 PHÚT)
    for _ in range(120):
        await asyncio.sleep(5)
        
        # Nếu đơn đã bị ghi đè/hủy bởi đơn mới của chính user này -> Thoát task cũ
        if user_id_str not in pending_orders or pending_orders[user_id_str].get("order_time") != order_time_str:
            return

        is_paid = await asyncio.to_thread(check_sepay_payment, memo_code, so_tien, order_time_str)
        
        if is_paid:
            acc_name = f"{ctx.author.name}{random.randint(100, 999)}"
            acc_pass = f"Wazue@{random.randint(100000, 999999)}"

            success, result_msg = tao_user_wazue_qling(acc_name, acc_pass, days, plan=1)

            if success:
                # Tính giờ hết hạn chuẩn theo thời điểm nạp tiền thành công
                success_now_vn = datetime.now(vietnam_tz)
                expire_date = success_now_vn + timedelta(days=days)
                expire_str = expire_date.strftime("%d/%m/%Y %H:%M")

                success_embed = discord.Embed(
                    title="🎉 THANH TOÁN THÀNH CÔNG - ĐÃ CẤP TÀI KHOẢN WAZUE",
                    color=0x00ffcc
                )
                success_embed.add_field(name="👤 Tài khoản (Username)", value=f"`{result_msg}`", inline=False)
                success_embed.add_field(name="🔑 Mật khẩu (Password)", value=f"`{acc_pass}`", inline=False)
                success_embed.add_field(name="⏳ Gói nạp", value=f"`{days} Ngày`", inline=True)
                success_embed.add_field(name="📅 Hết hạn vào", value=f"`{expire_str}`", inline=True)
                success_embed.add_field(name="🌐 Đăng nhập tại", value="`wazue.site`", inline=False)
                success_embed.set_footer(text="Cảm ơn bạn đã mua hàng! 🌸")

                try:
                    await ctx.author.send(embed=success_embed)
                except Exception:
                    await ctx.send(content=f"<@{user_id_str}>", embed=success_embed)

                pub_success = discord.Embed(
                    title="✅ GIAO DỊCH THÀNH CÔNG!",
                    description=f"Cảm ơn {ctx.author.mention}! Đơn nạp gói **{days} ngày** đã hoàn tất. Thông tin tài khoản WAZUE đã được gửi vào **Tin nhắn riêng (DM)** của bạn.",
                    color=0x00ffcc
                )
                await ctx.send(embed=pub_success)

            else:
                await ctx.send(f"⚠️ {ctx.author.mention} Đã nhận tiền thành công nhưng tạo user Qling thất bại: {result_msg}. Vui lòng báo Admin xử lý!")

            if user_id_str in pending_orders:
                del pending_orders[user_id_str]
            return

    # Nếu hết 10 phút chưa nạp
    if user_id_str in pending_orders and pending_orders[user_id_str].get("order_time") == order_time_str:
        del pending_orders[user_id_str]
        timeout_embed = discord.Embed(
            title="⏰ ĐƠN HÀNG HẾT HẠN",
            description=f"Đơn mua gói **{days} ngày** của <@{user_id_str}> đã bị hủy do quá thời gian 10 phút.",
            color=0xff0000
        )
        try:
            await ctx.author.send(embed=timeout_embed)
        except Exception:
            await ctx.send(embed=timeout_embed)



# ================== LỆNH HỦY ĐƠN NẠP ==================
@bot.command(name="huynap", aliases=["cancelnap", "huydon"])
async def huy_nap_wazue(ctx):
    user_id_str = str(ctx.author.id)

    if user_id_str in pending_orders:
        order_info = pending_orders.pop(user_id_str)
        embed = discord.Embed(
            title="🚫 HỦY ĐƠN NẠP THÀNH CÔNG",
            description=f"Đã hủy đơn nạp gói **{order_info['days']} ngày** (`{order_info['amount']:,} VNĐ`) của <@{user_id_str}>.",
            color=0xff0000
        )
        embed.set_footer(text="Komura BOT 🌸")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"⚠️ {ctx.author.mention}, bạn hiện **không có đơn nạp nào** đang chờ xử lý!")

# ================== LỆNH TẠO USER ==================
@bot.command(name="taouser")
async def create_user_qling(ctx, username: str, password: str, plan: int, days: int):
    if ctx.author.id != ADMIN_ID:
        await ctx.send("❌ **Bạn không có quyền sử dụng lệnh này!**")
        return

    if not username.startswith(CTV_PREFIX):
        username = f"{CTV_PREFIX}{username}"

    if len(password) < 6:
        await ctx.send("⚠️ **Mật khẩu phải từ 6 ký tự trở lên!**")
        return

    msg = await ctx.send(f"⏳ Đang khởi tạo tài khoản `{username}`...")

    try:
        url_create = f"{QLING_BASE_URL}/api/ctv/users"
        body_create = {
            "username": username,
            "password": password
        }
        
        res1 = requests.post(url_create, json=body_create, headers=get_headers(), timeout=10)
        res1_json = res1.json() if res1.status_code in [200, 201] else {}

        if not res1.ok:
            err_msg = res1_json.get("message", f"HTTP {res1.status_code}")
            await msg.edit(content=f"❌ **Lỗi tạo user:** {err_msg}")
            return

        url_update = f"{QLING_BASE_URL}/api/ctv/users/{urllib.parse.quote(username)}"
        body_update = {
            "plan": plan,
            "extend_days": days
        }
        
        res2 = requests.put(url_update, json=body_update, headers=get_headers(), timeout=10)

        expire_date = datetime.now() + timedelta(days=days)
        expire_str = expire_date.strftime("%H:%M:%S - %d/%m/%Y")

        embed = discord.Embed(
            title="🎉 TẠO USER THÀNH CÔNG",
            color=0x00ffcc
        )
        embed.add_field(name="👤 Tài khoản", value=f"`{username}`", inline=True)
        embed.add_field(name="🔑 Mật khẩu", value=f"`{password}`", inline=True)
        embed.add_field(name="📦 Plan", value=f"`Gói {plan}`", inline=True)
        embed.add_field(name="⏳ Số ngày cấp", value=f"`{days} ngày`", inline=True)
        embed.add_field(name="📅 Dự kiến hết hạn", value=f"`{expire_str}`", inline=True)
        embed.set_footer(text="Komura BOT 🌸 | Qling Portal")

        await msg.edit(content=None, embed=embed)

    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi kết nối API:** {e}")

# ================== LỆNH XEM DANH SÁCH USER ==================
@bot.command(name="listuser", aliases=["alluser"])
async def list_all_users(ctx):
    if ctx.author.id != ADMIN_ID:
        await ctx.send("❌ **Bạn không có quyền xem danh sách user!**")
        return

    msg = await ctx.send("⏳ Đang lấy danh sách user từ Qling Portal...")

    try:
        url = f"{QLING_BASE_URL}/api/ctv/users"
        res = requests.get(url, headers=get_headers(), timeout=10)

        if not res.ok:
            err_msg = res.json().get("message", f"HTTP {res.status_code}") if res.text else f"HTTP {res.status_code}"
            await msg.edit(content=f"❌ **Lỗi tải danh sách:** {err_msg}")
            return

        data = res.json()
        users_list = data.get("data", [])

        if not users_list:
            await msg.edit(content="⚠️ Chưa có user nào do bạn quản lý!")
            return

        total_users = len(users_list)

        if total_users > 50:
            file_path = "danh_sach_user.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"=== TỔNG SỐ USER: {total_users} ===\n\n")
                f.write(f"{'STT':<5} | {'USERNAME':<25} | {'PLAN':<6} | {'TRẠNG THÁI':<10} | {'HẾT HẠN'}\n")
                f.write("-" * 70 + "\n")
                for idx, u in enumerate(users_list, 1):
                    status = "Expired" if u.get("isExpired") else "Active"
                    f.write(f"{idx:<5} | {u.get('username','N/A'):<25} | {u.get('plan','N/A'):<6} | {status:<10} | {u.get('expiry_date','N/A')}\n")
            
            await ctx.send(content=f"📊 **Tổng số user:** `{total_users}`. Đã xuất danh sách ra file:", file=discord.File(file_path))
            await msg.delete()
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        lines = []
        for idx, u in enumerate(users_list, 1):
            status_icon = "🔴" if u.get("isExpired") else "🟢"
            exp_date = u.get("expiry_date", "N/A")
            if exp_date and "T" in str(exp_date):
                exp_date = exp_date.replace("T", " ")[:16]
            lines.append(f"`{idx}.` {status_icon} **{u.get('username')}** | Plan: `{u.get('plan')}` | Mode: `{u.get('mode', 'N/A')}` | Hạn: `{exp_date}`")

        chunk_size = 15
        chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]

        await msg.delete()
        for i, chunk in enumerate(chunks, 1):
            embed = discord.Embed(
                title=f"📋 DANH SÁCH USER ({total_users} users) - Trang {i}/{len(chunks)}",
                description="\n".join(chunk),
                color=0x00ffcc
            )
            embed.set_footer(text="Komura BOT 🌸 | Qling Portal")
            await ctx.send(embed=embed)

    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi khi truy xuất:** {e}")

# ================== LỆNH KIỂM TRA 1 HOẶC NHIỀU USER ==================
@bot.command(name="checkuser", aliases=["checklist"])
async def check_user_qling(ctx, *usernames: str):
    if not usernames:
        await ctx.send("⚠️ Cú pháp chuẩn: `!checkuser <username1> <username2>...`")
        return

    msg = await ctx.send(f"⏳ Đang tra cứu thông tin {len(usernames)} user...")

    try:
        url = f"{QLING_BASE_URL}/api/ctv/users"
        res = requests.get(url, headers=get_headers(), timeout=10)

        if not res.ok:
            await msg.edit(content="❌ **Lỗi tải dữ liệu từ Server!**")
            return

        all_users = res.json().get("data", [])
        user_dict = {u["username"].lower(): u for u in all_users}

        results = []
        for query_u in usernames:
            search_key = query_u if query_u.startswith(CTV_PREFIX) else f"{CTV_PREFIX}{query_u}"
            search_key = search_key.lower()

            if search_key in user_dict:
                u = user_dict[search_key]
                status = "🔴 Expired" if u.get("isExpired") else "🟢 Active"
                exp_date = u.get("expiry_date", "N/A")
                if exp_date and "T" in str(exp_date):
                    exp_date = exp_date.replace("T", " ")[:16]
                results.append(f"• **{u['username']}**: {status} | Plan: `{u.get('plan')}` | Mode: `{u.get('mode', 'N/A')}` | Hạn: `{exp_date}`")
            else:
                results.append(f"• **{query_u}**: ❌ Không tìm thấy user này")

        embed = discord.Embed(
            title=f"🔍 KẾT QUẢ KIỂM TRA USER ({len(usernames)})",
            description="\n".join(results),
            color=0x00ffcc
        )
        embed.set_footer(text="Komura BOT 🌸 | Qling Portal")
        await msg.edit(content=None, embed=embed)

    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi khi kiểm tra:** {e}")

# ================= CỬA SỔ BẮT LỖI SAI CÚ PHÁP LỆNH =================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        if ctx.command.name == "taouser":
            embed = discord.Embed(
                title="⚠️ Cú Pháp Lệnh Không Chính Xác!",
                description=(
                    "**Hướng dẫn sử dụng lệnh `!taouser`:**\n"
                    "👉 Cú pháp: `!taouser <username> <password> <plan> <ngày>`\n\n"
                    "💡 *Ví dụ chuẩn:* `!taouser khachhang01 pass123456 1 30`"
                ),
                color=0xffcc00
            )
            embed.set_footer(text="Komura BOT 🌸")
            await ctx.send(embed=embed)
            
        elif ctx.command.name in ["checkuser", "checklist"]:
            embed = discord.Embed(
                title="⚠️ Cú Pháp Lệnh Không Chính Xác!",
                description=(
                    "**Hướng dẫn sử dụng lệnh `!checkuser` / `!checklist`:**\n"
                    "👉 Cú pháp: `!checkuser <username1> <username2>...`\n\n"
                    "💡 *Ví dụ chuẩn:* `!checkuser khachhang01 khachhang02`"
                ),
                color=0xffcc00
            )
            embed.set_footer(text="Komura BOT 🌸")
            await ctx.send(embed=embed)

        elif ctx.command.name in ["napgoi", "nap", "muagoi"]:
            embed = discord.Embed(
                title="⚠️ Cú Pháp Lệnh Không Chính Xác!",
                description=(
                    "**Hướng dẫn sử dụng lệnh `!napgoi`:**\n"
                    "👉 Cú pháp: `!napgoi <số_ngày>`\n\n"
                    "💡 *Các gói hợp lệ:* `1`, `5`, `10`, `20`, `30` (Ví dụ: `!napgoi 30`)"
                ),
                color=0xffcc00
            )
            embed.set_footer(text="Komura BOT 🌸")
            await ctx.send(embed=embed)

    elif isinstance(error, commands.CheckFailure):
        await ctx.send("❌ **Bạn không có quyền thực hiện lệnh này!**")

# ====== Check Info FF=====
@bot.command(name="ff", help="Tra cứu thông tin Free Fire đầy đủ")
async def freefire_info(ctx, *, search_parameter: str = None):
    if not search_parameter:
        await ctx.send(
            "❌ Vui lòng nhập UID hoặc Tên nhân vật!\nVí dụ: `!ff"
            " 7998022758`"
        )
        return

    # Endpoint bù đắp dữ liệu Rank & Pet
    if search_parameter.isdigit():
        info_url = f"https://info.killersharmabot.online/player-info?uid={search_parameter}"
    else:
        info_url = f"https://info.killersharmabot.online/player-info?name={search_parameter}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(info_url, timeout=12) as response:
                if response.status != 200:
                    await ctx.send(
                        f"❌ Không tìm thấy dữ liệu hoặc API lỗi (Mã:"
                        f" {response.status})."
                    )
                    return

                data = await response.json()
                basic_info = data.get("basicInfo")
                if not basic_info:
                    await ctx.send("❌ Không tìm thấy người chơi này!")
                    return

                # Bóc tách thông tin cơ bản
                account_id = basic_info.get("accountId", "N/A")
                nickname = basic_info.get("nickname", "Không rõ")
                region = basic_info.get("region", "VN").upper()
                level = basic_info.get("level", "N/A")
                liked = basic_info.get("liked", "0")
                exp = basic_info.get("exp", "N/A")

                # Bóc tách Rank BR & CS (fallback từ maxRank / rank / points trong API)
                br_rank = (
                    basic_info.get("rank")
                    or basic_info.get("maxRank")
                    or "N/A"
                )
                br_points = basic_info.get("rankingPoints", 0)
                cs_rank = basic_info.get("csMaxRank") or "N/A"
                cs_points = basic_info.get("csRankingPoints", 0)

                # Bóc tách Pet
                pet_info = data.get("petInfo", {})
                pet_name = (
                    pet_info.get("name")
                    or pet_info.get("petName")
                    or "Chưa trang bị"
                )

                # Bóc tách Tiểu sử & Quân đoàn
                social_info = data.get("socialInfo", {})
                signature = social_info.get("signature") or "Không có"

                clan_info = data.get("clanBasicInfo", {})
                clan_name = clan_info.get("clanName") or "Chưa vào quân đoàn"

                # Lấy Banner & Outfit URL
                prime_level = basic_info.get("primeLevel", {}).get("level", 0)
                frame = "true" if prime_level == 8 else "false"
                encoded_name = urllib.parse.quote(nickname)
                encoded_guild = urllib.parse.quote(clan_name)

                banner_url = (
                    f"https://image.killersharmabot.online/banner-image?"
                    f"headPic={basic_info.get('headPic', '')}&"
                    f"bannerId={basic_info.get('bannerId', '')}&"
                    f"name={encoded_name}&"
                    f"level={basic_info.get('level', 2)}&"
                    f"guild={encoded_guild}&"
                    f"pinId={basic_info.get('pinId', '900000012')}&"
                    f"celebrity={basic_info.get('celebrityStatus', 0)}&"
                    f"primeLevel={prime_level}&"
                    f"frame={frame}"
                )

                profile_info = data.get("profileInfo", {})
                equipped_weapons = basic_info.get("weaponSkinShows", [])
                equipped_outfits = profile_info.get("clothes", [])
                character_id = profile_info.get("avatarId", "102000007")

                combined_items = equipped_outfits + equipped_weapons
                outfit_ids = (
                    ",".join(str(item) for item in combined_items)
                    if combined_items
                    else ""
                )

                outfit_url = (
                    f"https://image.killersharmabot.online/outfit-image?"
                    f"avatar_id={character_id}&"
                    f"clothes={outfit_ids}"
                )

                # Fetch Ảnh
                banner_file = None
                outfit_file = None
                files_to_send = []

                try:
                    async with session.get(banner_url, timeout=10) as b_resp:
                        if b_resp.status == 200:
                            banner_bytes = await b_resp.read()
                            banner_file = discord.File(
                                io.BytesIO(banner_bytes), filename="banner.png"
                            )
                            files_to_send.append(banner_file)
                except Exception:
                    pass

                try:
                    async with session.get(outfit_url, timeout=10) as o_resp:
                        if o_resp.status == 200:
                            outfit_bytes = await o_resp.read()
                            outfit_file = discord.File(
                                io.BytesIO(outfit_bytes), filename="outfit.png"
                            )
                            files_to_send.append(outfit_file)
                except Exception:
                    pass

                # Trình bày đúng chuẩn mẫu chung dòng
                description = (
                    f"👤 **Name:** {nickname}\n"
                    f"🆔 **UID:** {account_id} • **SV:** {region} • **Lv:** {level}\n"
                    f"❤️ **Likes:** {liked} • **EXP:** {exp}\n"
                    f"🏆 **BR:** {br_rank} ({br_points} RP)\n"
                    f"🎯 **CS:** {cs_rank} ({cs_points} RP)\n"
                    f"🛡️ **Clan:** {clan_name}\n"
                    f"🐾 **Pet:** {pet_name}\n"
                    f"💬 **Bio:** {signature}"
                )

                embed = discord.Embed(
                    title="🔥 FREE FIRE PROFILE",
                    description=description,
                    color=discord.Color.from_rgb(255, 69, 0),
                )

                if banner_file:
                    embed.set_image(url="attachment://banner.png")
                if outfit_file:
                    embed.set_thumbnail(url="attachment://outfit.png")

                embed.set_footer(
                    text=f"Yêu cầu bởi {ctx.author.display_name}",
                    icon_url=ctx.author.display_avatar.url,
                )

                await ctx.send(embed=embed, files=files_to_send)

        except Exception as e:
            await ctx.send(f"❌ Đã xảy ra lỗi: `{e}`")

# ======= Checkbanff ======
@bot.command(name="checkban", aliases=["cb"], help="Kiểm tra trạng thái Banned của UID Free Fire")
async def check_ban(ctx, uid: str = None):
    if not uid:
        await ctx.send("❌ Vui lòng nhập UID cần kiểm tra!\nVí dụ: `!checkban 12345678` hoặc `!cb 12345678`")
        return

    if not uid.isdigit():
        await ctx.send("❌ UID phải là một dãy số nguyên!")
        return

    ban_url = f"https://bancheck-xprince.onrender.com/checkban?uid={uid}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ban_url, timeout=60) as response:
                if response.status != 200:
                    await ctx.send(f"❌ Không thể kiểm tra UID này hoặc API bị lỗi (Mã: {response.status}).")
                    return

                data = await response.json()

                # Bóc tách dữ liệu từ API
                is_banned = data.get("banned", False)
                ban_message = data.get("ban_message", "Không rõ")
                ban_period = data.get("ban_period_months", 0)
                nickname = data.get("nickname", "Không rõ")
                region = data.get("region", "N/A")
                player_uid = data.get("uid", uid)

                # Cấu hình màu sắc và icon theo trạng thái
                if is_banned:
                    color = discord.Color.red()
                    status_text = "⛔ **ĐÃ BỊ BAN (KHÓA TÀI KHOẢN)**"
                else:
                    color = discord.Color.green()
                    status_text = "✅ **AN TOÀN (KHÔNG BỊ BAN)**"

                # Gom thông tin theo định dạng gọn gàng
                description = (
                    f"👤 **Name:** {nickname}\n"
                    f"🆔 **UID:** {player_uid} • **SV:** {region}\n"
                    f"🛡️ **Trạng thái:** {status_text}\n"
                    f"💬 **Chi tiết:** {ban_message}"
                )

                if is_banned and ban_period > 0:
                    description += f"\n⏳ **Thời hạn khóa:** {ban_period} tháng"

                embed = discord.Embed(
                    title="🔍 THÔNG TIN BAN CHECK FREE FIRE",
                    description=description,
                    color=color
                )

                embed.set_footer(
                    text=f"Yêu cầu bởi {ctx.author.display_name}",
                    icon_url=ctx.author.display_avatar.url
                )

                await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("⏳ **API Ban Check phản hồi quá lâu (Timeout)!** Vui lòng thử lại sau.")
        except aiohttp.ClientError as e:
            await ctx.send(f"📡 **Lỗi kết nối tới API Ban Check!** (`{type(e).__name__}`)")
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            await ctx.send(f"❌ Đã xảy ra lỗi: `{error_msg}`")

# ====== Check Lienquan =======

def load_random_proxy():
    file_path = "proxies.txt"
    if not os.path.exists(file_path):
        return None
        
    with open(file_path, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    if not proxies:
        return None

    raw_proxy = random.choice(proxies)
    parts = raw_proxy.split(":")
    
    # Chuyển user:pass:host:port -> host:port:user:pass cho PHP cURL
    if len(parts) == 4:
        user, password, host, port = parts
        return f"{host}:{port}:{user}:{password}"
    
    return raw_proxy


@bot.command(name="checklq", aliases=["lq", "lienquan"])
async def check_lienquan(ctx, username: str = None, password: str = None, mode: str = None):
    # Xóa tin nhắn chứa tài khoản/mật khẩu
    try:
        await ctx.message.delete()
    except Exception:
        pass

    # Kiểm tra cú pháp
    if not username or not password:
        err_msg = await ctx.send(
            f"⚠️ {ctx.author.mention} Sai cú pháp!\n"
            f"• Check thường (không proxy): `!checklq <tài_khoản> <mật_khẩu>`\n"
            f"• Check dùng proxy: `!checklq <tài_khoản> <mật_khẩu> proxy`"
        )
        await asyncio.sleep(10)
        try:
            await err_msg.delete()
        except Exception:
            pass
        return

    # Xác định có sử dụng proxy hay không
    use_proxy = (mode is not None and mode.lower() == "proxy")
    
    if use_proxy:
        msg = await ctx.send("⏳ Đang kiểm tra tài khoản (Chế độ: **Proxy ngẫu nhiên**)...")
    else:
        msg = await ctx.send("⏳ Đang kiểm tra tài khoản (Chế độ: **IP Trực tiếp / Thường**)...")

    api_url = "https://takatori-panel.onrender.com/"

    # Cấu hình tham số request
    selected_proxy = load_random_proxy() if use_proxy else None
    
    if use_proxy and not selected_proxy:
        await msg.edit(content="❌ **Lỗi:** Bạn chọn chế độ proxy nhưng file `proxies.txt` rỗng hoặc không tồn tại!")
        return

    payload = {
        "account": username,
        "password": password,
        "use_proxy": use_proxy,
        "proxy": selected_proxy if use_proxy else ""
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, timeout=60) as response:
                if response.status != 200:
                    await msg.edit(content=f"❌ **Lỗi HTTP API:** Mã phản hồi {response.status}")
                    return

                raw_data = await response.text()
                
                try:
                    data = json.loads(raw_data)
                except Exception:
                    await msg.edit(content=f"❌ **Lỗi Server PHP:**\n```{raw_data[:200]}```")
                    return

                # Kiểm tra trạng thái từ API PHP
                if not data.get("status"):
                    error_message = data.get("message", "Lỗi không xác định")
                    await msg.edit(content=f"❌ **Kiểm tra thất bại:** {error_message}")
                    return

                # Bóc tách dữ liệu khi thành công
                player_info = data.get("player", {})
                security = data.get("security", {})
                wallet = data.get("wallet", {})
                collection = data.get("collection", {}).get("summary", {})
                ban_info = data.get("ban_info", {})
                top_up = data.get("top_up", {})

                nickname = player_info.get("name", "Chưa tạo nhân vật")
                level = player_info.get("level", 0)
                rank_name = player_info.get("rank", {}).get("rank_name", "Không rõ")
                quan_huy = wallet.get("quan_huy", 0)
                heroes_count = collection.get("hero_count", 0)
                skins_count = collection.get("skin_count", 0)
                
                tier_counts = collection.get("tier_counts", {})
                sss_skins = tier_counts.get("sss", 0)
                ss_skins = tier_counts.get("ss", 0)
                anime_skins = collection.get("anime_skin_count", 0)
                collab_skins = collection.get("collab_skin_count", 0)

                acc_status = security.get("account_status", "Không rõ")
                is_banned = ban_info.get("banned", False)
                ban_text = "⛔ ĐÃ BỊ KHÓA" if is_banned else "✅ An toàn"
                mode_text = "⚡ Direct IP" if not use_proxy else "🌐 Proxy"

                # Trình bày sạch đẹp, không có dấu * thừa
                desc = (
                    f"👤 **Name:** `{nickname}` • **Lv:** `{level}`\n"
                    f"🏆 **Rank:** `{rank_name}`\n"
                    f"💰 **Quân Huy:** `{quan_huy}` | **Nạp 60 ngày:** `{top_up.get('total_60_days', 0):,}` VNĐ\n\n"
                    f"🎒 **BỘ SƯU TẬP**\n"
                    f"• Tướng: `{heroes_count}` | Trang phục: `{skins_count}`\n"
                    f"• Bậc SSS: `{sss_skins}` | Bậc SS: `{ss_skins}`\n"
                    f"• 🌸 Anime: `{anime_skins}` | ⚔️ Collab: `{collab_skins}`\n\n"
                    f"🔒 **BẢO MẬT ({acc_status})**\n"
                    f"• SĐT: `{'Có' if security.get('mobile_bound') == 'YES' else 'Không'}` | Email: `{'Có' if security.get('email_verified') == 'YES' else 'Không'}`\n"
                    f"• Facebook: `{security.get('fb_status', 'NO')}` | CMND: `{'Có' if security.get('cmnd') == 'YES' else 'Không'}`\n\n"
                    f"🛡️ **TRẠNG THÁI KHÓA:** {ban_text}"
                )

                embed = discord.Embed(
                    title="🎮 THÔNG TIN TÀI KHOẢN LIÊN QUÂN",
                    description=desc,
                    color=0xff0000 if is_banned else 0x00ffcc
                )
                
                if player_info.get("avatar"):
                    embed.set_thumbnail(url=player_info.get("avatar"))

                embed.set_footer(
                    text=f"Yêu cầu bởi {ctx.author.display_name} • Chế độ: {mode_text}",
                    icon_url=ctx.author.display_avatar.url
                )

                await msg.edit(content=None, embed=embed)

    except asyncio.TimeoutError:
        await msg.edit(content="❌ **Thất bại:** Kết nối tới API/Proxy bị quá thời gian (Timeout).")
    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi Hệ Thống:** `{e}`")

# ======= Check lq v2 ========

@bot.command(name="checklq2", aliases=["lq2"])
async def check_lienquan_full(ctx, username: str = None, password: str = None):
    # Tự động xóa tin nhắn chứa tài khoản/mật khẩu
    try:
        await ctx.message.delete()
    except Exception:
        pass

    # Kiểm tra cú pháp
    if not username or not password:
        err_msg = await ctx.send(
            f"⚠️ {ctx.author.mention} Sai cú pháp!\n"
            f"👉 Dùng: `!checklq2 <tài_khoản> <mật_khẩu>`"
        )
        await asyncio.sleep(10)
        try:
            await err_msg.delete()
        except Exception:
            pass
        return

    msg = await ctx.send("⏳ Đang bóc tách toàn bộ thông tin từ API...")

    base_api_url = "http://103.77.246.176:5000/check"
    params = {
        "user": username,
        "pass": password
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_api_url, params=params, timeout=60) as response:
                if response.status != 200:
                    await msg.edit(content=f"❌ **Lỗi HTTP API:** Mã phản hồi {response.status}")
                    return

                raw_text = await response.text()

                try:
                    data = json.loads(raw_text)
                except Exception:
                    await msg.edit(content=f"❌ **Lỗi dữ liệu trả về:**\n```{raw_text[:200]}```")
                    return

                if not data.get("ok"):
                    err_text = data.get("message") or data.get("error") or "Đăng nhập thất bại / Sai mật khẩu"
                    await msg.edit(content=f"❌ **Kiểm tra thất bại:** {err_text}")
                    return

                # ================= BÓC TÁCH TOÀN BỘ DỮ LIỆU =================
                res = data.get("result", {})
                
                # 1. Thông tin tài khoản & Hệ thống
                uid = res.get("uid", "N/A")
                acc_name = res.get("username", username)
                nickname = res.get("aov_name", "Chưa tạo nhân vật")
                level = res.get("aov_level", 0)
                rank_name = res.get("aov_rank", "Chưa xếp hạng")
                server = res.get("aov_server", "Không rõ")
                country = res.get("country", "VN")
                garena_created = res.get("garena_created", "Không rõ")
                aov_reg_time = res.get("aov_reg_time", "Không rõ")
                last_login = res.get("last_login", "Không rõ")

                # 2. Bộ sưu tập Tướng & Trang phục
                skins_data = res.get("aov_skins", {})
                heroes_count = skins_data.get("total_champs", 0)
                skins_count = skins_data.get("total_skins", 0)
                sss_skins = skins_data.get("sss", 0)
                ss_skins = skins_data.get("ss", 0)
                anime_skins = skins_data.get("anime", 0)
                cp_skins = skins_data.get("cp", 0)
                other_skins = skins_data.get("other", 0)

                # 3. Tài sản
                shells = res.get("shells", 0)
                topup_time = res.get("topup_time", 0)

                # 4. Bảo mật & Liên kết
                mobile_bound = "Có" if res.get("mobile_bound") else "Không"
                masked_phone = res.get("masked_phone", "Chưa liên kết")
                email_verified = "Có" if res.get("email_verified") else "Không"
                fb_linked = "Có" if res.get("fb_linked") else "Không"
                fb_uid = res.get("fb_uid", "Không")

                # 5. Trạng thái khóa & Chi tiết khóa
                aov_banned = res.get("aov_banned", "NO")
                is_banned = (aov_banned == "YES")
                ban_text = "⛔ ĐÃ BỊ KHÓA" if is_banned else "✅ An toàn"
                
                # Chi tiết Ban
                kt_player = res.get("_kt_player", {})
                ban_info = kt_player.get("banInfo", {})
                ban_detail = ""
                if is_banned and ban_info:
                    unban_time = ban_info.get("unbanTime", 0)
                    if unban_time > 0:
                        unban_date = datetime.fromtimestamp(unban_time).strftime("%d/%m/%Y %H:%M")
                        ban_detail = f"\n⏱️ **Mở khóa lúc:** `{unban_date}`"

                # Trình bày Embed chi tiết chuẩn đẹp
                desc = (
                    f"👤 **Name:** `{nickname}` • Lv: `{level}`\n"
                    f"🏆 **Rank:** `{rank_name}` • **Server:** `{server}`\n"
                    f"🆔 **UID:** `{uid}` | **User:** `{acc_name}`\n"
                    f"💰 **Sò Garena:** `{shells}` | **Topup:** `{topup_time}`\n\n"
                    
                    f"🎒 **BỘ SƯU TẬP TRANG PHỤC**\n"
                    f"• Tướng: `{heroes_count}` | Trang phục: `{skins_count}`\n"
                    f"• Bậc SSS: `{sss_skins}` | Bậc SS: `{ss_skins}`\n"
                    f"• 🌸 Anime: `{anime_skins}` | 💖 CP: `{cp_skins}` | Khác: `{other_skins}`\n\n"
                    
                    f"🔒 **THÔNG TIN BẢO MẬT**\n"
                    f"• SĐT: `{mobile_bound}` ({masked_phone})\n"
                    f"• Email: `{email_verified}` | Facebook: `{fb_linked}` (UID: `{fb_uid}`)\n\n"
                    
                    f"📅 **THỜI GIAN HỆ THỐNG**\n"
                    f"• Tạo Garena: `{garena_created}`\n"
                    f"• Tạo Game: `{aov_reg_time}`\n"
                    f"• Đăng nhập cuối: `{last_login}`\n\n"

                    f"🛡️ **TRẠNG THÁI TÀI KHOẢN:** {ban_text}{ban_detail}"
                )

                embed = discord.Embed(
                    title="🎮 TOÀN BỘ THÔNG TIN TÀI KHOẢN LIÊN QUÂN",
                    description=desc,
                    color=0xff0000 if is_banned else 0x00ffcc
                )
                
                # Thumbnail ảnh Rank
                rank_entry = res.get("aov_rank_entry", {})
                if rank_entry.get("image"):
                    embed.set_thumbnail(url=rank_entry.get("image"))

                embed.set_footer(
                    text=f"Yêu cầu bởi {ctx.author.display_name} • Full Data API",
                    icon_url=ctx.author.display_avatar.url
                )

                await msg.edit(content=None, embed=embed)

    except asyncio.TimeoutError:
        await msg.edit(content="❌ **Thất bại:** Kết nối tới API quá thời gian (Timeout).")
    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi Hệ Thống:** `{e}`")




# Biến toàn cục lưu ID phòng treo 24/7
TARGET_VOICE_CHANNEL_ID = None

# Task tự động kiểm tra và duy trì kết nối (chạy ngầm mỗi 30s)
@tasks.loop(seconds=30)
async def keep_voice_alive():
    global TARGET_VOICE_CHANNEL_ID
    if not TARGET_VOICE_CHANNEL_ID:
        return

    channel = bot.get_channel(TARGET_VOICE_CHANNEL_ID)
    if not channel:
        return

    vc = channel.guild.voice_client

    # Nếu chưa kết nối hoặc bị rớt mạng -> Tự vào lại
    if vc is None or not vc.is_connected():
        try:
            await channel.connect(reconnect=True, self_deaf=True)
            print(f"✅ [Voice 24/7] Đã kết nối lại vào kênh: {channel.name}")
        except Exception as e:
            print(f"❌ [Voice 24/7] Lỗi kết nối lại: {e}")

# Lệnh !join247 <idroom>
# 2. Cấu hình Danh sách nhạc & Biến trạng thái Voice 24/7
# -------------------------------------------------------------
MUSIC_PLAYLIST = [
    "music/song1.mp3",
    "music/song2.mp3",
    "music/song3.mp3",
    "music/song4.mp3",
    "music/song5.mp3",
]

voice_247_config = {
    "enabled": False,
    "channel_id": None,
    "guild_id": None,
    "track_index": 0,
}


# -------------------------------------------------------------
# 3. Hàm xử lý phát nhạc & chuyển bài tự động
# -------------------------------------------------------------
def play_next_track(error=None):
    if error:
        print(f"❌ Lỗi khi phát nhạc: {error}")

    if voice_247_config["enabled"]:
        # Tăng chỉ số bài hát (0 -> 1 -> 2 -> 3 -> 4 -> 0...)
        voice_247_config["track_index"] = (
            voice_247_config["track_index"] + 1
        ) % len(MUSIC_PLAYLIST)

        # Gọi phát bài tiếp theo trong Event Loop
        coro = play_current_song()
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"❌ Lỗi chuyển bài: {e}")


async def play_current_song():
    guild_id = voice_247_config["guild_id"]
    if not guild_id:
        return

    guild = bot.get_guild(guild_id)
    if not guild or not guild.voice_client:
        return

    vc = guild.voice_client

    if vc.is_playing() or vc.is_paused():
        vc.stop()

    track_idx = voice_247_config["track_index"]
    song_path = MUSIC_PLAYLIST[track_idx]

    if not song_path.startswith("http") and not os.path.exists(song_path):
        print(f"⚠️ Không tìm thấy file: {song_path}. Tự chuyển bài...")
        play_next_track()
        return

    audio_source = discord.FFmpegPCMAudio(song_path, options="-vn")
    vc.play(audio_source, after=play_next_track)
    print(
        f"🎵 [Voice 24/7] Đang phát bài [{track_idx + 1}/{len(MUSIC_PLAYLIST)}]: {song_path}"
    )


# -------------------------------------------------------------
# 4. Task ngầm duy trì kết nối (Anti-crash / Reconnect 24/7)
# -------------------------------------------------------------
@tasks.loop(seconds=15)
async def keep_alive_task():
    if not voice_247_config["enabled"] or not voice_247_config["guild_id"]:
        return

    guild = bot.get_guild(voice_247_config["guild_id"])
    if not guild:
        return

    channel = guild.get_channel(voice_247_config["channel_id"])
    if not channel:
        return

    vc = guild.voice_client

    # Trường hợp 1: Bị ngắt kết nối khỏi Voice
    if vc is None or not vc.is_connected():
        try:
            print("🔄 [Voice 24/7] Đang kết nối lại...")
            vc = await channel.connect(reconnect=True, self_deaf=True)
            await play_current_song()
        except Exception as e:
            print(f"❌ Lỗi tự động Reconnect: {e}")

    # Trường hợp 2: Vẫn ở trong Voice nhưng bị ngắt nhạc bất thường
    elif not vc.is_playing() and not vc.is_paused():
        print("🔄 [Voice 24/7] Khôi phục lại nhạc...")
        await play_current_song()


# -------------------------------------------------------------
# 5. Lệnh !join247 và !leave247
# -------------------------------------------------------------
@bot.command(name="join247")
async def join247(ctx, channel_input: str = None):
    target_channel = None

    # 1. Nhập ID kênh trực tiếp (!join247 123456789)
    if channel_input:
        try:
            channel_id = int(channel_input)
            target_channel = ctx.guild.get_channel(channel_id)
        except ValueError:
            return await ctx.send(
                "❌ ID kênh không hợp lệ! Vui lòng nhập chuỗi số ID."
            )

    # 2. Không nhập ID -> Lấy kênh thoại người gọi đang đứng
    if not target_channel and ctx.author.voice:
        target_channel = ctx.author.voice.channel

    # 3. Không tìm thấy kênh thoại nào
    if not target_channel or not isinstance(
        target_channel, discord.VoiceChannel
    ):
        return await ctx.send(
            "❌ Vui lòng vào một kênh thoại hoặc truyền ID kênh! Ví dụ: `!join247 123456789`"
        )

    # Cập nhật thông tin 24/7
    voice_247_config["enabled"] = True
    voice_247_config["channel_id"] = target_channel.id
    voice_247_config["guild_id"] = ctx.guild.id
    voice_247_config["track_index"] = 0

    # Vào kênh thoại
    if ctx.voice_client is None:
        await target_channel.connect(reconnect=True, self_deaf=True)
    else:
        await ctx.voice_client.move_to(target_channel)

    # Khởi chạy phát nhạc & Task 24/7
    await play_current_song()
    if not keep_alive_task.is_running():
        keep_alive_task.start()

    await ctx.send(
        f"✅ **Đã bật chế độ Voice 24/7!**\n"
        f"🔊 Kênh: **{target_channel.name}** (`{target_channel.id}`)\n"
        f"🎶 Đã nạp vòng lặp **{len(MUSIC_PLAYLIST)} bài hát**."
    )


@bot.command(name="leave247")
async def leave247(ctx):
    voice_247_config["enabled"] = False
    if keep_alive_task.is_running():
        keep_alive_task.stop()

    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Đã tắt Voice 24/7 và thoát kênh thoại.")
    else:
        await ctx.send("❌ Bot hiện không ở trong kênh thoại nào.")


# Bắt lỗi lệnh để in thông báo ra Console
@join247.error
@leave247.error
async def command_error(ctx, error):
    print(f"❌ Lỗi thực thi lệnh: {error}")
    await ctx.send(f"⚠️ Đã xảy ra lỗi: `{error}`")

# ======= xa mp3 war ========
@bot.command(name="xa")
async def play_specific_audio(ctx, filename: str = None, channel_id: int = None):
    # Kiểm tra cú pháp
    if not filename or not channel_id:
        return await ctx.send("⚠️ **Sai cú pháp!** Vui lòng nhập: `!xa <tên_file.mp3> <id_room>`\n👉 Ví dụ: `!xa song1.mp3 1234567890`")

    # Tự động thêm đuôi .mp3 nếu người dùng quên nhập
    if not filename.endswith(".mp3"):
        filename += ".mp3"

    # Kiểm tra file có tồn tại trên server không (tìm ở thư mục gốc hoặc thư mục music/)
    file_path = filename
    if not os.path.exists(file_path):
        file_path = os.path.join("music", filename)
        if not os.path.exists(file_path):
            return await ctx.send(f"❌ **Không tìm thấy file:** `{filename}` trên máy chủ!")

    # Lấy kênh thoại an toàn (tránh lỗi NoneType get_channel)
    target_channel = bot.get_channel(channel_id)
    if not target_channel:
        try:
            target_channel = await bot.fetch_channel(channel_id)
        except Exception:
            return await ctx.send(f"❌ **Không tìm thấy phòng thoại có ID:** `{channel_id}`")

    if not isinstance(target_channel, discord.VoiceChannel):
        return await ctx.send("❌ ID đã cung cấp không phải là một kênh thoại (Voice Channel)!")

    # Xử lý kết nối Voice
    vc = ctx.guild.voice_client
    try:
        if vc is None:
            vc = await target_channel.connect(reconnect=True, self_deaf=True)
        elif vc.channel.id != target_channel.id:
            await vc.move_to(target_channel)
    except Exception as e:
        return await ctx.send(f"❌ **Không thể kết nối vào phòng thoại:** `{e}`")

    # Dừng bài nhạc đang phát (nếu có) để phát file mới
    if vc.is_playing() or vc.is_paused():
        vc.stop()

    # Phát file MP3
    try:
        audio_source = discord.FFmpegPCMAudio(file_path, options="-vn")
        vc.play(audio_source)
        await ctx.send(f"🎶 **Đang phát:** `{filename}` tại kênh **{target_channel.name}**")
    except Exception as e:
        await ctx.send(f"❌ **Lỗi khi phát audio:** `{e}`")

# =========== listxa =======
@bot.command(name="listxa", aliases=["lxa"])
async def list_audio_files(ctx):
    mp3_files = []

    # 1. Quét file .mp3 ở thư mục gốc
    try:
        for file in os.listdir("."):
            if file.endswith(".mp3"):
                mp3_files.append(f"• `{file}`")
    except Exception:
        pass

    # 2. Quét file .mp3 trong thư mục music/ (nếu có)
    if os.path.exists("music"):
        try:
            for file in os.listdir("music"):
                if file.endswith(".mp3"):
                    mp3_files.append(f"• `music/{file}`")
        except Exception:
            pass

    # Nếu không tìm thấy file mp3 nào
    if not mp3_files:
        return await ctx.send("📂 **Không tìm thấy file `.mp3` nào trên máy chủ!**")

    # Tạo Embed hiển thị danh sách file
    desc = "\n".join(mp3_files)
    embed = discord.Embed(
        title="🎵 DANH SÁCH FILE MP3 TRÊN BOT",
        description=desc,
        color=0x00ffcc
    )
    embed.set_footer(
        text=f"Sử dụng: !xa <tên_file> <id_room>",
        icon_url=ctx.author.display_avatar.url
    )

    await ctx.send(embed=embed)

# kiểm tra ping ========

@bot.command(name="ping", aliases=["p", "latency"])
async def check_ping(ctx):
    # Tính độ trễ WebSocket (kết nối giữa Bot và Discord)
    websocket_latency = round(bot.latency * 1000)

    # Tính độ trễ phản hồi API (thời gian gửi và nhận tin nhắn)
    start_time = time.perf_counter()
    message = await ctx.send("🏓 **Pong!** Đang đo độ trễ...")
    end_time = time.perf_counter()
    
    api_latency = round((end_time - start_time) * 1000)

    # Tạo Embed hiển thị đẹp mắt
    embed = discord.Embed(
        title="🏓 THÔNG SỐ ĐỘ TRỄ (PING)",
        color=discord.Color.green()
    )
    embed.add_field(name="📶 WebSocket Latency:", value=f"`{websocket_latency} ms`", inline=True)
    embed.add_field(name="⚡ API Response Time:", value=f"`{api_latency} ms`", inline=True)
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

    # Cập nhật lại tin nhắn với Embed
    await message.edit(content=None, embed=embed)

def doithe_submit_card(card_type: str, card_amount: str, serial: str, pin: str) -> str:
    """
    Hàm gửi thẻ cào lên thegiare.vn qua web scraping
    Trả về: Chuỗi kết quả (thành công hoặc lỗi)
    """
    login_url = "https://thegiare.vn/login"
    card_url = "https://thegiare.vn/doithecao"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    session = requests.Session()
    
    try:
        print(f"🔐 Đang đăng nhập vào thegiare.vn với user: {THEGIARE_USERNAME}")
        
        # === BƯỚC 1: Lấy CSRF Token từ trang Login ===
        login_page = session.get(login_url, headers=headers, timeout=15)
        if login_page.status_code != 200:
            return f"❌ Không thể truy cập trang đăng nhập (Mã lỗi: {login_page.status_code})"
        
        soup = BeautifulSoup(login_page.text, 'html.parser')
        
        # Tìm token trong meta tag
        csrf_token = None
        meta_token = soup.find('meta', {'name': 'csrf-token'})
        if meta_token:
            csrf_token = meta_token.get('content')
        
        # Nếu không tìm thấy, tìm trong input hidden
        if not csrf_token:
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                csrf_token = token_input.get('value')
        
        if not csrf_token:
            return "❌ Không thể lấy token bảo mật từ trang web!"
        
        print(f"✅ Đã lấy được CSRF Token: {csrf_token[:20]}...")

        # === BƯỚC 2: Đăng nhập ===
        login_payload = {
            "_token": csrf_token,
            "username": THEGIARE_USERNAME,
            "password": THEGIARE_PASSWORD
        }

        login_headers = headers.copy()
        login_headers["Content-Type"] = "application/x-www-form-urlencoded"
        login_headers["Referer"] = login_url

        login_resp = session.post(login_url, data=login_payload, headers=login_headers, timeout=15)
        
        # Kiểm tra đăng nhập thành công (kiểm tra URL chuyển hướng)
        if "login" in login_resp.url.lower():
            # Kiểm tra nội dung để xác định lỗi
            if "sai" in login_resp.text.lower() or "không chính xác" in login_resp.text.lower():
                return "❌ Đăng nhập thất bại! Sai tài khoản hoặc mật khẩu thegiare.vn!"
            return "❌ Đăng nhập thất bại! Vui lòng kiểm tra tài khoản thegiare.vn."

        print(f"✅ Đăng nhập thành công! Session ID: {session.cookies.get('laravel_session', 'N/A')}")

        # === BƯỚC 3: Lấy token mới cho trang Đổi thẻ ===
        card_headers = headers.copy()
        card_headers["Referer"] = login_url
        
        card_page = session.get(card_url, headers=card_headers, timeout=15)
        if card_page.status_code != 200:
            return f"❌ Không thể truy cập trang đổi thẻ (Mã lỗi: {card_page.status_code})"
            
        soup_card = BeautifulSoup(card_page.text, 'html.parser')
        
        new_token = None
        meta_token_card = soup_card.find('meta', {'name': 'csrf-token'})
        if meta_token_card:
            new_token = meta_token_card.get('content')
        
        if not new_token:
            token_input_card = soup_card.find('input', {'name': '_token'})
            if token_input_card:
                new_token = token_input_card.get('value')

        # Sử dụng token mới hoặc token cũ
        final_token = new_token if new_token else csrf_token
        print(f"✅ Đã lấy token đổi thẻ: {final_token[:20]}...")

        # === BƯỚC 4: Gửi thẻ cào ===
        # Lưu ý: Form trong HTML sử dụng tên field là `telco[]`, `code[]`, `serial[]`, `amount[]`
        card_payload = {
            "_token": final_token,
            "telco[]": card_type,    # Phải có dấu [] như trong HTML
            "code[]": pin,           # Mã thẻ
            "serial[]": serial,      # Serial
            "amount[]": card_amount  # Mệnh giá
        }

        post_headers = headers.copy()
        post_headers["Referer"] = card_url
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Origin"] = "https://thegiare.vn"

        print(f"📤 Đang gửi thẻ {card_type} mệnh giá {card_amount}...")
        print(f"   Serial: {serial}")
        print(f"   PIN: {pin[:5]}...")

        post_resp = session.post(card_url, data=card_payload, headers=post_headers, timeout=15)

        # === BƯỚC 5: Phân tích phản hồi ===
        if post_resp.status_code == 200:
            response_text = post_resp.text
            soup_result = BeautifulSoup(response_text, 'html.parser')
            
            # Tìm thông báo kết quả từ các class thường dùng
            alert_messages = []
            
            # Kiểm tra các class alert thông dụng
            alert_selectors = [
                '.alert', '.toast', '.notification', 
                '.alert-success', '.alert-danger', 
                '.alert-info', '.alert-warning',
                '.message', '.flash-message', '.alert-message'
            ]
            
            for selector in alert_selectors:
                alerts = soup_result.select(selector)
                for alert in alerts:
                    text = alert.get_text(strip=True)
                    if text and len(text) > 5:  # Bỏ qua text quá ngắn
                        alert_messages.append(text)
            
            # Nếu tìm thấy thông báo
            if alert_messages:
                message = " | ".join(alert_messages[:3])  # Lấy 3 thông báo đầu
                print(f"📢 Phản hồi: {message}")
                return f"📢 {message}"
            
            # Kiểm tra nội dung HTML để tìm thông báo thành công
            lower_text = response_text.lower()
            success_keywords = ["thành công", "cộng", "đã cộng", "thực nhận", "nhận được"]
            for keyword in success_keywords:
                if keyword in lower_text:
                    print(f"✅ Đổi thẻ thành công: {keyword}")
                    return f"✅ Đổi thẻ thành công! Tiền đã được cộng vào tài khoản của bạn."
            
            # Kiểm tra lỗi
            error_keywords = ["lỗi", "thất bại", "không hợp lệ", "sai", "hết hạn", "trùng", "đã sử dụng", "không tồn tại"]
            for keyword in error_keywords:
                if keyword in lower_text:
                    print(f"❌ Lỗi: {keyword}")
                    return f"❌ Đổi thẻ thất bại: {keyword.title()}! Vui lòng kiểm tra lại thông tin."
            
            # Trường hợp không xác định
            print("⚠️ Không xác định được kết quả từ phản hồi")
            return "✅ Gửi thẻ thành công! Hệ thống đang xử lý. Vui lòng kiểm tra tài khoản sau ít phút."
        else:
            return f"❌ Lỗi kết nối máy chủ (Mã: {post_resp.status_code})"

    except requests.exceptions.Timeout:
        return "❌ Kết nối tới thegiare.vn bị timeout! Vui lòng thử lại sau ít phút."
    except requests.exceptions.ConnectionError:
        return "❌ Không thể kết nối tới thegiare.vn! Vui lòng kiểm tra kết nối internet."
    except requests.exceptions.TooManyRedirects:
        return "❌ Lỗi chuyển hướng trang! Vui lòng thử lại."
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Lỗi hệ thống: {error_msg}")
        return f"❌ Lỗi hệ thống: {error_msg[:100]}"

@bot.command(name="doithe", aliases=["dt"])
async def doithe_cmd(ctx, loai_the: str = None, menh_gia: str = None, serial: str = None, pin: str = None):
    """
    Lệnh đổi thẻ cào tự động - Sử dụng web scraping
    Cú pháp: !doithe <Loại_Thẻ> <Mệnh_Giá> <Serial> <Mã_PIN>
    Ví dụ: !doithe Viettel 100000 10001234567 9876543210123
    """
    # Xóa tin nhắn chứa thông tin thẻ cào để bảo mật
    try:
        await ctx.message.delete()
    except Exception as e:
        print(f"⚠️ Không thể xóa tin nhắn: {e}")

    # Kiểm tra cú pháp
    if not all([loai_the, menh_gia, serial, pin]):
        embed = discord.Embed(
            title="⚠️ HƯỚNG DẪN ĐỔI THẺ CÀO",
            description=(
                "**Cú pháp chuẩn:**\n"
                "`!doithe <Loại_Thẻ> <Mệnh_Giá> <Serial> <Mã_PIN>`\n\n"
                "**📌 Ví dụ:**\n"
                "`!doithe Viettel 100000 10001234567 9876543210123`\n\n"
                "**📱 Các loại thẻ hỗ trợ:**\n"
                f"`{'`, `'.join(VALID_CARD_TYPES)}`\n\n"
                "**💰 Các mệnh giá phổ biến:**\n"
                "`10,000` • `20,000` • `30,000` • `50,000` • `100,000` • `200,000` • `500,000`"
            ),
            color=0xffcc00
        )
        embed.set_footer(text="Komura BOT 🌸 | Mọi thông tin sẽ được bảo mật")
        return await ctx.send(embed=embed)

    # Xác thực loại thẻ
    card_type = loai_the.upper()
    if card_type not in VALID_CARD_TYPES:
        embed = discord.Embed(
            title="❌ LOẠI THẺ KHÔNG HỢP LỆ",
            description=f"**`{loai_the}` không được hỗ trợ!**\n\nCác loại thẻ hợp lệ:\n`{'`, `'.join(VALID_CARD_TYPES)}`",
            color=0xff0000
        )
        embed.set_footer(text="Komura BOT 🌸")
        return await ctx.send(embed=embed)

    # Xác thực mệnh giá (kiểm tra số)
    try:
        amount_int = int(menh_gia)
        if amount_int <= 0:
            raise ValueError
    except ValueError:
        embed = discord.Embed(
            title="❌ MỆNH GIÁ KHÔNG HỢP LỆ",
            description=f"**`{menh_gia}` không phải là số tiền hợp lệ!**\n\nVui lòng nhập số nguyên dương.\nVí dụ: `100000`",
            color=0xff0000
        )
        embed.set_footer(text="Komura BOT 🌸")
        return await ctx.send(embed=embed)

    # Gửi tin nhắn xử lý
    msg = await ctx.send(f"⏳ {ctx.author.mention} **Đang xử lý đổi thẻ...**")

    try:
        # Chạy hàm đổi thẻ (chạy trong thread để không block bot)
        result = await asyncio.to_thread(
            doithe_submit_card, 
            card_type, 
            str(amount_int), 
            serial.strip(), 
            pin.strip()
        )

        # Xác định kết quả thành công hay thất bại
        is_success = any(keyword in result.lower() for keyword in [
            "thành công", "cộng", "nhận", "xử lý", "đã gửi"
        ])
        is_error = any(keyword in result.lower() for keyword in [
            "lỗi", "thất bại", "không", "sai", "hết hạn", "trùng"
        ])

        # Tạo Embed kết quả
        if is_success and not is_error:
            color = 0x00ffcc
            title = "✅ ĐỔI THẺ THÀNH CÔNG"
        elif is_error:
            color = 0xff0000
            title = "❌ ĐỔI THẺ THẤT BẠI"
        else:
            color = 0xffaa00
            title = "⚠️ KẾT QUẢ ĐỔI THẺ"

        embed_result = discord.Embed(
            title=title,
            description=result,
            color=color
        )
        
        # Thêm thông tin chi tiết
        embed_result.add_field(
            name="💳 Thông tin thẻ",
            value=(
                f"**Loại:** `{card_type}`\n"
                f"**Mệnh giá:** `{amount_int:,} VNĐ`"
            ),
            inline=True
        )
        embed_result.add_field(
            name="🔑 Mã thẻ (Ẩn)",
            value=f"`{pin[:3]}***{pin[-3:] if len(pin) > 6 else ''}`" if len(pin) > 6 else "`****`",
            inline=True
        )
        
        embed_result.set_footer(
            text=f"Yêu cầu bởi {ctx.author.display_name} | Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            icon_url=ctx.author.display_avatar.url
        )

        await msg.edit(content=None, embed=embed_result)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Lỗi khi xử lý đổi thẻ: {error_msg}")
        await msg.edit(
            content=f"❌ **Đã xảy ra lỗi khi xử lý đổi thẻ:**\n```{error_msg[:200]}```"
        )

@bot.command(name="sodu", aliases=["balance"])
async def check_balance(ctx):
    """Kiểm tra số dư tài khoản thegiare.vn"""
    msg = await ctx.send("⏳ Đang kiểm tra số dư...")
    
    result = await asyncio.to_thread(get_balance_from_thegiare)
    
    embed = discord.Embed(
        title="💰 SỐ DƯ TÀI KHOẢN",
        description=result,
        color=0x00ffcc if "đ" in result else 0xff0000
    )
    embed.set_footer(text=f"Yêu cầu bởi {ctx.author.display_name}")
    
    await msg.edit(content=None, embed=embed)


def get_balance_from_thegiare() -> str:
    """Lấy số dư từ thegiare.vn"""
    login_url = "https://thegiare.vn/login"
    profile_url = "https://thegiare.vn/account/profile"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    session = requests.Session()
    
    try:
        # Lấy token
        login_page = session.get(login_url, headers=headers, timeout=10)
        soup = BeautifulSoup(login_page.text, 'html.parser')
        
        csrf_token = None
        meta_token = soup.find('meta', {'name': 'csrf-token'})
        if meta_token:
            csrf_token = meta_token.get('content')
        
        if not csrf_token:
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                csrf_token = token_input.get('value')
        
        if not csrf_token:
            return "❌ Không thể lấy token bảo mật!"
        
        # Đăng nhập
        login_payload = {
            "_token": csrf_token,
            "username": THEGIARE_USERNAME,
            "password": THEGIARE_PASSWORD
        }
        
        login_resp = session.post(login_url, data=login_payload, headers=headers, timeout=10)
        
        if "login" in login_resp.url.lower():
            return "❌ Đăng nhập thất bại! Vui lòng kiểm tra tài khoản."
        
        # Truy cập trang profile để lấy số dư
        profile_resp = session.get(profile_url, headers=headers, timeout=10)
        
        if profile_resp.status_code == 200:
            soup_profile = BeautifulSoup(profile_resp.text, 'html.parser')
            
            # Tìm số dư trong HTML (thường nằm trong element có class chứa 'balance' hoặc 'wallet')
            balance_patterns = [
                r'số dư[:\s]*([\d,]+)\s*đ',
                r'balance[:\s]*([\d,]+)',
                r'([\d,]+)\s*đ',
            ]
            
            import re
            for pattern in balance_patterns:
                match = re.search(pattern, profile_resp.text, re.IGNORECASE)
                if match:
                    balance = match.group(1).replace(',', '')
                    return f"✅ **Số dư hiện tại:** `{int(balance):,} VNĐ`"
            
            # Nếu không tìm thấy, thử tìm element
            for selector in ['.balance', '.wallet', '.money', '.so-du', '.sodu']:
                element = soup_profile.select_one(selector)
                if element:
                    text = element.get_text(strip=True)
                    return f"✅ **Số dư:** `{text}`"
            
            return "⚠️ Không tìm thấy thông tin số dư trên trang profile!"
        else:
            return f"❌ Không thể truy cập trang profile (Mã: {profile_resp.status_code})"
            
    except Exception as e:
        return f"❌ Lỗi: {str(e)}"

# ================= LỆNH BOT DISCORD =================
@bot.command(name="ask", aliases=["chat", "ai"])
async def ask_claude(ctx, *, prompt: str = None):
    # Kiểm tra nội dung câu hỏi
    if not prompt:
        return await ctx.send(
            f"⚠️ {ctx.author.mention} Vui lòng nhập câu hỏi!\n"
            f"👉 Cú pháp: `!ask <nội dung>`\n"
            f"👉 Ví dụ: `!ask Say hello in one sentence.`"
        )

    # Tin nhắn chờ
    msg = await ctx.send("🤔 **Claude đang suy nghĩ...**")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GOROUTER_API_KEY}"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        # Gọi API bất đồng bộ (Async HTTP Request)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GOROUTER_API_URL, 
                headers=headers, 
                json=payload, 
                timeout=120
            ) as response:
                
                if response.status != 200:
                    err_text = await response.text()
                    return await msg.edit(
                        content=f"❌ **Lỗi API (HTTP {response.status}):**\n```{err_text[:300]}```"
                    )

                data = await response.json()
                
                # Bóc tách câu trả lời từ JSON trả về
                choices = data.get("choices", [])
                if not choices:
                    return await msg.edit(content="❌ Không nhận được câu trả lời từ AI.")

                reply_text = choices[0].get("message", {}).get("content", "")

                # Discord giới hạn tối đa 2000 ký tự mỗi tin nhắn
                if len(reply_text) <= 2000:
                    await msg.edit(content=reply_text)
                else:
                    await msg.delete()
                    # Chia nhỏ tin nhắn nếu dài hơn 2000 ký tự
                    for i in range(0, len(reply_text), 1900):
                        await ctx.send(reply_text[i:i + 1900])

    except asyncio.TimeoutError:
        await msg.edit(content="❌ **Hết thời gian:** API phản hồi quá lâu (Timeout).")
    except Exception as e:
        await msg.edit(content=f"❌ **Lỗi hệ thống:** `{e}`")

# ================= HÀM GỌI API =================
async def send_ff_like(uid: str, server: str = DEFAULT_SERVER, key: str = DEFAULT_KEY):
    params = {
        "uid": uid,
        "server_name": server,
        "key": key
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(LIKE_API_BASE, params=params, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data, None
                else:
                    return None, f"Lỗi máy chủ API (Mã HTTP {resp.status})"
    except asyncio.TimeoutError:
        return None, "Hết thời gian chờ phản hồi từ máy chủ API."
    except Exception as e:
        return None, f"Lỗi kết nối: {e}"


# ================= LỆNH DISCORD BOT =================
@bot.command(name="like", aliases=["bufflike", "fflike"])
async def cmd_like(ctx, uid: str = None, server: str = DEFAULT_SERVER):
    # 1. Kiểm tra tham số UID
    if not uid:
        embed_help = discord.Embed(
            title="⚠️ Thiếu UID Free Fire",
            description=(
                f"**Cú pháp:** `!like <UID> [server]`\n"
                f"**Ví dụ:** `!like 7998022758 vn`\n"
                f"*(Mặc định server: `{DEFAULT_SERVER.upper()}`)*"
            ),
            color=0xffcc00
        )
        return await ctx.send(embed=embed_help)

    # 2. Gửi tin nhắn chờ
    msg = await ctx.send(f"⏳ Đang xử lý tăng like cho UID: `{uid}` (Server: `{server.upper()}`)...")

    # 3. Gọi API
    data, error = await send_ff_like(uid=uid, server=server)

    # 4. Xử lý khi có lỗi kết nối
    if error:
        embed_err = discord.Embed(
            title="❌ Thất Bại",
            description=f"Không thể buff like:\n```{error}```",
            color=0xff3333
        )
        return await msg.edit(content=None, embed=embed_err)

    # 5. Kiểm tra trạng thái trả về từ API
    status = data.get("status")
    if status != 1:
        embed_fail = discord.Embed(
            title="❌ Buff Like Thất Bại",
            description="API trả về lỗi hoặc UID/Server không hợp lệ.",
            color=0xff3333
        )
        return await msg.edit(content=None, embed=embed_fail)

    # 6. Bóc tách dữ liệu từ JSON
    nickname = data.get("PlayerNickname", "Không rõ")
    player_uid = data.get("UID", uid)
    likes_given = data.get("LikesGivenByAPI", 0)
    likes_before = data.get("LikesbeforeCommand", 0)
    likes_after = data.get("LikesafterCommand", 0)
    remains = data.get("remains", "N/A")

    # 7. Format hiển thị chung dòng vào Description
    desc = (
        f"👤 **Tên nhân vật:** `{nickname}`\n"
        f"🆔 **UID:** `{player_uid}`\n"
        f"🌐 **Server:** `{server.upper()}`\n\n"
        f"📈 **Like trước:** `{likes_before:,}`\n"
        f"➕ **Đã tăng:** `+{likes_given:,}` ❤️\n"
        f"🎯 **Like hiện tại:** `{likes_after:,}`\n\n"
        f"📊 **Lượt dùng còn lại:** `{remains}`"
    )

    embed_res = discord.Embed(
        title="✨ BUFF LIKE FREE FIRE THÀNH CÔNG ✨",
        description=desc,
        color=0x00ff88
    )

    embed_res.set_footer(
        text=f"Yêu cầu bởi {ctx.author.display_name} • Powered by API", 
        icon_url=ctx.author.display_avatar.url
    )

    await msg.edit(content=None, embed=embed_res)

# ================== RUN ==================
bot.run(TOKEN)
