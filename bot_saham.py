import os
import json
import logging
import yfinance as yf
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

# --- Konfigurasi Logging ---
# Ini akan membantu melihat apa yang terjadi pada bot di log Railway
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Konfigurasi Penyimpanan Data ---
# File ini akan menyimpan semua data pengguna (portofolio dan alert)
DATA_FILE = "bot_data.json"

# --- Fungsi Helper untuk Data ---
def load_data():
    """Memuat data pengguna dari file JSON. Mengembalikan dictionary kosong jika file tidak ada."""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning("File data tidak ditemukan atau rusak. Membuat file baru.")
    return {"portfolios": {}, "alerts": {}}

def save_data(data):
    """Menyimpan data pengguna ke file JSON."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- Fungsi Helper untuk yfinance ---
def get_stock_price_info(ticker_symbol):
    """Mengambil data harga penting dari sebuah saham."""
    if not ticker_symbol.upper().endswith('.JK'):
        ticker_symbol += '.JK'
    ticker = yf.Ticker(ticker_symbol)
    # Gunakan history() untuk data yang lebih andal daripada .info
    hist = ticker.history(period="1d")
    if hist.empty:
        return None
    return {
        'harga_terakhir': hist['Close'].iloc[-1],
        'nama_perusahaan': ticker.info.get('longName', ticker_symbol.upper().replace('.JK', ''))
    }

def get_stock_info_formatted(ticker_symbol):
    """Mengambil data lengkap dan memformatnya untuk pesan balasan."""
    if not ticker_symbol.upper().endswith('.JK'):
        ticker_symbol += '.JK'
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    hist = ticker.history(period="2d")

    if hist.empty or 'regularMarketPrice' not in info:
        return f"❌ Kode saham '{ticker_symbol.upper().replace('.JK','')}' tidak ditemukan."

    harga_terakhir = info.get('regularMarketPrice', 0)
    harga_sebelumnya = hist['Close'].iloc[-2] if len(hist) > 1 else info.get('previousClose', 0)
    perubahan = harga_terakhir - harga_sebelumnya
    persentase_perubahan = (perubahan / harga_sebelumnya) * 100 if harga_sebelumnya else 0
    emoji = "📈" if perubahan >= 0 else "📉"

    pesan = (
        f"{emoji} *{info.get('longName', 'N/A')} ({ticker_symbol.upper().replace('.JK','')})*\n\n"
        f"Harga Terakhir: *Rp {harga_terakhir:,.0f}*\n"
        f"Perubahan: *{'+' if perubahan >= 0 else ''}{perubahan:,.0f} ({'+' if persentase_perubahan >= 0 else ''}{persentase_perubahan:.2f}%)*\n\n"
        f"Tertinggi Hari Ini: Rp {info.get('dayHigh', 0):,.0f}\n"
        f"Terendah Hari Ini: Rp {info.get('dayLow', 0):,.0f}\n"
        f"Volume: {info.get('volume', 0):,}"
    )
    return pesan

# --- Handler Perintah Telegram ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_markdown(
        "Selamat datang di Bot Saham!\n\n"
        "Gunakan perintah berikut:\n"
        "📈 `/cek [KODE]` - Cek harga saham.\n"
        "➕ `/tambah [KODE] [LOT] [HARGA]` - Tambah saham ke portfolio.\n"
        "📒 `/portfolio` - Lihat isi portfolio Anda.\n"
        "🔔 `/alert [KODE] [diatas/dibawah] [HARGA]` - Pasang notifikasi harga.\n"
        "🗑️ `/hapus_alert [KODE]` - Hapus notifikasi untuk saham."
    )

async def cek_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Format: `/cek [KODE_SAHAM]` (Contoh: /cek BBCA)")
        return
    ticker = context.args[0].upper()
    info_saham = get_stock_info_formatted(ticker)
    await update.message.reply_markdown(info_saham)

async def tambah_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = str(update.effective_user.id)
        kode, lot, harga_beli = context.args[0].upper(), int(context.args[1]), float(context.args[2])
        
        data = load_data()
        if user_id not in data["portfolios"]:
            data["portfolios"][user_id] = []
        
        data["portfolios"][user_id].append({'kode': kode, 'lot': lot, 'harga_beli': harga_beli})
        save_data(data)
        await update.message.reply_text(f"✅ Berhasil ditambahkan: {kode} {lot} lot @ Rp {harga_beli:,.0f}")
    except (IndexError, ValueError):
        await update.message.reply_text("Format salah. Gunakan: `/tambah [KODE] [LOT] [HARGA_BELI]`")

async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()
    if user_id not in data["portfolios"] or not data["portfolios"][user_id]:
        await update.message.reply_text("Portfolio Anda masih kosong. Tambahkan saham dengan perintah `/tambah`.")
        return
    
    await update.message.reply_text("📊 Menganalisis portfolio Anda, mohon tunggu...")
    pesan = "*📒 Portfolio Anda*\n\n"
    total_modal, total_nilai_sekarang = 0, 0
    
    for saham in data["portfolios"][user_id]:
        kode, lot, harga_beli = saham['kode'], saham['lot'], saham['harga_beli']
        modal = lot * 100 * harga_beli
        total_modal += modal
        info_harga = get_stock_price_info(kode)
        
        if info_harga:
            harga_sekarang = info_harga['harga_terakhir']
            nilai_sekarang = lot * 100 * harga_sekarang
            total_nilai_sekarang += nilai_sekarang
            profit_loss = nilai_sekarang - modal
            persen_pl = (profit_loss / modal) * 100 if modal else 0
            emoji_pl = "🟢" if profit_loss >= 0 else "🔴"
            pesan += f"*{kode}* - {lot} Lot\n" \
                     f"Avg. Beli: Rp {harga_beli:,.0f}\n" \
                     f"Harga Skrg: Rp {harga_sekarang:,.0f}\n" \
                     f"{emoji_pl} P/L: *{persen_pl:+.2f}%* (Rp {profit_loss:,.0f})\n\n"
        else:
            pesan += f"*{kode}* - {lot} Lot\n Gagal mengambil harga terkini.\n\n"
            total_nilai_sekarang += modal

    total_pl = total_nilai_sekarang - total_modal
    total_persen_pl = (total_pl / total_modal) * 100 if total_modal else 0
    emoji_total = "🔼" if total_pl >= 0 else "🔽"
    pesan += f"------------------------------\n*Ringkasan Portfolio:*\n" \
             f"Total Modal: Rp {total_modal:,.0f}\n" \
             f"Nilai Aset Kini: Rp {total_nilai_sekarang:,.0f}\n" \
             f"{emoji_total} Total P/L: *{total_persen_pl:+.2f}%* (Rp {total_pl:,.0f})"
    await update.message.reply_markdown(pesan)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = str(update.effective_user.id)
        kode, kondisi, harga_target = context.args[0].upper(), context.args[1].lower(), float(context.args[2])

        if kondisi not in ["diatas", "dibawah"]:
            raise ValueError("Kondisi harus 'diatas' atau 'dibawah'.")
        
        data = load_data()
        if user_id not in data["alerts"]:
            data["alerts"][user_id] = []
        
        # Hapus alert lama untuk kode yang sama agar tidak tumpang tindih
        data["alerts"][user_id] = [a for a in data["alerts"][user_id] if a['kode'] != kode]
        
        data["alerts"][user_id].append({"kode": kode, "kondisi": kondisi, "harga_target": harga_target})
        save_data(data)
        await update.message.reply_text(f"🔔 Alert terpasang! Saya akan memberitahu jika {kode} bergerak {kondisi} Rp {harga_target:,.0f}.")
    except (IndexError, ValueError):
        await update.message.reply_text("Format salah. Gunakan: `/alert [KODE] [diatas/dibawah] [HARGA]`")

async def hapus_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = str(update.effective_user.id)
        kode_to_delete = context.args[0].upper()
        
        data = load_data()
        if user_id in data["alerts"]:
            original_count = len(data["alerts"][user_id])
            data["alerts"][user_id] = [a for a in data["alerts"][user_id] if a['kode'] != kode_to_delete]
            
            if len(data["alerts"][user_id]) < original_count:
                save_data(data)
                await update.message.reply_markdown(f"🗑️ Semua alert untuk *{kode_to_delete}* telah dihapus.")
            else:
                await update.message.reply_markdown(f"Tidak ada alert aktif untuk *{kode_to_delete}*.")
        else:
            await update.message.reply_text("Anda tidak memiliki alert aktif.")
    except IndexError:
        await update.message.reply_text("Format: `/hapus_alert [KODE_SAHAM]`")

# --- Mesin Pemindai Alert Otomatis ---
async def check_alerts_job(context: ContextTypes.DEFAULT_TYPE):
    """Fungsi yang dijalankan secara periodik oleh JobQueue untuk memeriksa semua alert."""
    logger.info("Memulai tugas pemeriksaan alert...")
    data = load_data()
    alerts_to_remove = {}

    all_alert_codes = set()
    for user_alerts in data.get("alerts", {}).values():
        for alert in user_alerts:
            all_alert_codes.add(alert["kode"])

    if not all_alert_codes:
        logger.info("Tidak ada alert aktif untuk diperiksa. Tugas selesai.")
        return

    for user_id, user_alerts in data.get("alerts", {}).items():
        if not user_alerts: continue
        
        for alert in user_alerts:
            kode, kondisi, harga_target = alert["kode"], alert["kondisi"], alert["harga_target"]
            info_harga = get_stock_price_info(kode)
            
            if info_harga:
                harga_sekarang = info_harga["harga_terakhir"]
                alert_terpicu = False
                if kondisi == "diatas" and harga_sekarang >= harga_target:
                    alert_terpicu = True
                elif kondisi == "dibawah" and harga_sekarang <= harga_target:
                    alert_terpicu = True
                
                if alert_terpicu:
                    pesan = f"🔔 *ALERT HARGA* 🔔\nSaham *{kode}* telah mencapai target Anda ({kondisi} Rp {harga_target:,.0f}).\n\nHarga saat ini: *Rp {harga_sekarang:,.0f}*"
                    try:
                        await context.bot.send_message(chat_id=user_id, text=pesan, parse_mode='Markdown')
                        logger.info(f"Mengirim notifikasi alert {kode} ke user {user_id}")
                        if user_id not in alerts_to_remove: alerts_to_remove[user_id] = []
                        alerts_to_remove[user_id].append(alert)
                    except Exception as e:
                        logger.error(f"Gagal mengirim alert ke {user_id}: {e}")

    if alerts_to_remove:
        for user_id, alerts in alerts_to_remove.items():
            if user_id in data.get("alerts", {}):
                for alert in alerts:
                    if alert in data["alerts"][user_id]:
                        data["alerts"][user_id].remove(alert)
        save_data(data)
        logger.info(f"Menghapus {sum(len(v) for v in alerts_to_remove.values())} alert yang sudah terpicu.")
    logger.info("Pemeriksaan alert selesai.")

# --- Fungsi Utama untuk Menjalankan Bot ---
def main() -> None:
    """Fungsi utama untuk menginisialisasi dan menjalankan bot."""
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        logger.critical("Variabel TELEGRAM_TOKEN tidak ditemukan! Bot tidak bisa berjalan.")
        return

    # Inisialisasi Application
    application = Application.builder().token(TOKEN).build()
    
    # Menambahkan tugas terjadwal (job) untuk memeriksa alert setiap 5 menit (300 detik)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_alerts_job, interval=300, first=10)

    # Mendaftarkan semua handler perintah
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cek", cek_command))
    application.add_handler(CommandHandler("tambah", tambah_command))
    application.add_handler(CommandHandler("portfolio", portfolio_command))
    application.add_handler(CommandHandler("alert", alert_command))
    application.add_handler(CommandHandler("hapus_alert", hapus_alert_command))

    logger.info("Bot interaktif dengan pemindai alert sedang berjalan...")
    # Jalankan bot
    application.run_polling()

if __name__ == "__main__":
    main()

