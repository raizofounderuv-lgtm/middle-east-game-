"""
🗺️ لعبة الشرق الأوسط الجيوسياسية - النسخة 3.0
"""
import logging, random, string, json, os, io, time, asyncio
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
ADMIN_ID   = int(os.environ.get("ADMIN_ID", "0"))
DATA_FILE  = "game_data.json"
MAP_FILE   = "map_base.png"
FLAGS_DIR  = "flags"
os.makedirs(FLAGS_DIR, exist_ok=True)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

# ==================== رمز العملة ====================
CUR = "¥"   # مثقال

# ==================== توقيتات ====================
HOUR_REAL      = 180        # ثانية = ساعة لعبة
WEEK_REAL      = HOUR_REAL * 24 * 7
TAX_COOLDOWN        = 60 * 10   # 10 دقايق
STRAIT_TAX_COOLDOWN = 60 * 15   # 15 دقيقة لو مضيق مغلق
DISASTER_EVERY = WEEK_REAL       # 21 دقيقة
ATTACK_CD      = 60 * 5          # cooldown هجوم 5 دقائق
ALLY_REQ_TTL   = 60 * 30         # طلبات تحالف تنتهي بعد 30 دقيقة
WAR_EXPIRE     = HOUR_REAL * 48  # حرب تنتهي تلقائياً بعد 48 ساعة لعبة بدون هجوم
MARKET_TTL     = HOUR_REAL * 72  # عروض السوق تنتهي بعد 72 ساعة لعبة
MAX_MARKET_PER_PLAYER = 5        # حد أقصى عروض في السوق

FLAG_SIZE_MAIN  = 200
FLAG_SIZE_SMALL = 100

# ==================== قروض البنك الدولي ====================
LOAN_OPTIONS = [
    {"id":"small",  "name":"قرض صغير",  "amount":5000,  "interest":0.20, "due_cycles":3,  "emoji":"💵"},
    {"id":"medium", "name":"قرض متوسط", "amount":15000, "interest":0.25, "due_cycles":5,  "emoji":"💴"},
    {"id":"large",  "name":"قرض كبير",  "amount":40000, "interest":0.30, "due_cycles":8,  "emoji":"💶"},
]
# due_cycles = عدد دورات الحصاد قبل السداد
# ==================== إحداثيات ====================
REGION_COORDS = {
    "مصر":      [(378,1077)],
    "تركيا":    [(532,407),(192,306)],
    "ايران":    [(1267,642)],
    "الاردن":   [(662,906)],
    "قطر":      [(1331,1187)],
    "الامارات": [(1482,1288)],
    "عمان":     [(1610,1509),(1549,1149)],
    "فلسطين":   [(594,844)],
    "الكويت":   [(1130,948)],
    "العراق":   [(957,749)],
    "السعودية": [(1080,1246)],
    "اليمن":    [(1206,1703)],
    "لبنان":    [(614,692)],
    "سوريا":    [(726,618)],
    "البحرين":  [(1010,1080)],
    "ليبيا":    [(150,700)],
    "السودان":  [(350,1300)],
    "اسرائيل":  [(580,870)],
    "مصر_شمال": [(378,900)],  # موقع السويس
    "قبرص":     [(488,659)],
}
AVAILABLE_REGIONS = [r for r in REGION_COORDS if r != "مصر_شمال"]

# ==================== الخريطة تعمل بـ map_base.png فقط ====================
_COUNTRY_MASKS = {}  # لا يوجد masks — الأعلام تُوضع بالإحداثيات

# ==================== المضائق ====================
STRAITS = {
    "هرمز":       {"controller":["عمان","ايران"],  "affects":["السعودية","الكويت","العراق","قطر","الامارات","البحرين"], "blocked":False,"blocked_by":None},
    "باب المندب": {"controller":["اليمن"],          "affects":["مصر","الاردن"],                                         "blocked":False,"blocked_by":None},
    "السويس":     {"controller":["مصر"],            "affects":["الاردن","فلسطين","لبنان","سوريا","تركيا","قبرص"],       "blocked":False,"blocked_by":None},
    "البسفور":    {"controller":["تركيا"],          "affects":["سوريا","لبنان","قبرص","مصر"],                           "blocked":False,"blocked_by":None},
}

# ==================== الموارد ====================
REGION_RESOURCES = {
    "السعودية":["نفط","غاز","محطة_تحليه"],
    "الكويت": ["نفط","غاز","محطة_تحليه"],
    "العراق": ["نفط","غاز"],
    "قطر":    ["غاز","نفط","محطة_تحليه"],
    "ليبيا":  ["نفط"],
    "ايران":  ["نفط","غاز","صلب"],
    "الامارات":["ذهب","غاز","محطة_تحليه"],
    "البحرين": ["ذهب","محطة_تحليه"],
    "السودان": ["قمح","ذهب"],
    "اسرائيل": ["صلب","قمح"],
    "عمان":   ["نفط","غاز","محطة_تحليه"],
    "مصر":    ["قمح","ارز","فول"],
    "سوريا":  ["قمح","زيتون"],
    "اليمن":  ["بن","فول"],
    "تركيا":  ["قمح","بطاطس","صلب"],
    "الاردن": ["بطاطس","زيتون"],
    "فلسطين": ["زيتون","فول"],
    "لبنان":  ["زيتون","ذهب"],
    "قبرص":   ["زيتون","ذهب"],
}

RESOURCE_FACILITIES = {
    # ===== Lv.0 — متاح من البداية =====
    "نفط":        {"name":"🛢️ حقل نفط",       "base_cost":20000, "amount":10, "emoji":"🛢️", "infra_req":0},
    "غاز":        {"name":"⛽ محطة غاز",        "base_cost":18000, "amount":10, "emoji":"⛽",  "infra_req":0},
    # ===== Lv.1 =====
    "صلب":        {"name":"⚙️ مصنع صلب",       "base_cost":25000, "amount":8,  "emoji":"⚙️", "infra_req":1},
    "مصنع_اسلحه": {"name":"🔩 مصنع أسلحة",     "base_cost":35000, "amount":0,  "emoji":"🔩", "infra_req":1,
                   "special":"يخفض سعر التجنيد 10% لكل مصنع (حد أقصى 50%)"},
    # ===== Lv.2 =====
    "ذهب":        {"name":"🏦 بنك مركزي",      "base_cost":30000, "amount":6,  "emoji":"🏦", "infra_req":2},
    "محطة_تحليه": {"name":"🌊 محطة تحلية",      "base_cost":28000, "amount":0,  "emoji":"🌊", "infra_req":2,
                   "special":"يرفع الأمن الغذائي +15 لكل محطة",
                   "infra_desert":1, "infra_coastal":2, "infra_other":4},
    # ===== Lv.3 =====
    "مطار":       {"name":"✈️ مطار دولي",       "base_cost":50000, "amount":0,  "emoji":"✈️", "infra_req":3,
                   "special":"يخفض cooldown الهجوم 20%"},
    "ميناء":      {"name":"⚓ ميناء تجاري",     "base_cost":45000, "amount":0,  "emoji":"⚓", "infra_req":3,
                   "special":"يرفع ضرائب المستعمرات +15%"},
    # ===== Lv.4 =====
    "جامعه":      {"name":"🎓 جامعة",           "base_cost":60000, "amount":0,  "emoji":"🎓", "infra_req":4,
                   "special":"مضاعفة XP من كل الأنشطة"},
    # ===== Lv.5 =====
    "مفاعل":      {"name":"☢️ مفاعل نووي",      "base_cost":500000, "amount":0,  "emoji":"☢️", "infra_req":10,
                   "special":"يخفض سعر القنابل النووية 50% ويلغي الحظر بعد الاستخدام"},
}

FARM_CROPS = {
    "قمح":   {"name":"🌾 حقل قمح",     "base_cost":3000,  "amount":100,"emoji":"🌾"},
    "ارز":   {"name":"🍚 حقل ارز",     "base_cost":2500,  "amount":80, "emoji":"🍚"},
    "فول":   {"name":"🫘 حقل فول",     "base_cost":2000,  "amount":60, "emoji":"🫘"},
    "بن":    {"name":"☕ مزرعة بن",    "base_cost":4000,  "amount":40, "emoji":"☕"},
    "بطاطس": {"name":"🥔 حقل بطاطس",  "base_cost":1800,  "amount":120,"emoji":"🥔"},
    "زيتون": {"name":"🫒 بستان زيتون","base_cost":3500,  "amount":50, "emoji":"🫒"},
}

REGION_PREFERRED_CROPS = {
    "مصر":["قمح","ارز","فول"], "سوريا":["قمح","زيتون"],
    "السودان":["قمح","فول"],    "اليمن":["بن","فول"],
    "تركيا":["قمح","بطاطس"],   "الاردن":["بطاطس","زيتون"],
    "فلسطين":["زيتون","فول"],   "لبنان":["زيتون","بن"],
    "اسرائيل":["قمح","بطاطس"], "قبرص":["زيتون","بن"],
}
ALL_CROPS = list(FARM_CROPS.keys())

# أسعار البيع ثابتة لا تتغير (مثقال/طن)
CROP_SELL_PRICE = {
    "قمح":20,  "ارز":30,  "فول":35,  "بن":120, "بطاطس":15, "زيتون":80,
    "نفط":500, "غاز":400, "صلب":350, "ذهب":800,
}

# حد أقصى للمزارع حسب مستوى البنية التحتية
FARM_MAX_PER_INFRA = {0:3, 1:6, 2:12, 3:20, 4:30, 5:45}
def get_max_farms(infra):
    """إجمالي أقصى عدد مزارع مسموح بيه"""
    for lvl in sorted(FARM_MAX_PER_INFRA.keys(), reverse=True):
        if infra >= lvl:
            return FARM_MAX_PER_INFRA[lvl]
    return 3

# ==================== الكوارث ====================
DISASTERS = [
    # عسكرية/اقتصادية
    {"name":"زلزال مدمر",       "emoji":"🌍","effect":"army",        "loss":(0.2,0.4),  "msg":"ضرب زلزال مدمر! خسرت جزء من جيشك!"},
    {"name":"وباء",             "emoji":"🦠","effect":"army",        "loss":(0.1,0.3),  "msg":"وباء اجتاح جيشك!"},
    {"name":"فيضانات",          "emoji":"🌊","effect":"facilities",  "loss":(1,2),      "msg":"فيضانات دمرت بعض منشآتك!"},
    {"name":"حريق مصانع",       "emoji":"🔥","effect":"facilities",  "loss":(1,1),      "msg":"حريق دمر إحدى منشآتك!"},
    {"name":"انهيار اقتصادي",   "emoji":"📉","effect":"gold",        "loss":(0.1,0.2),  "msg":"انهيار اقتصادي! خسرت جزء من مثاقيلك!"},
    # زراعية — تصيب محصول عشوائي
    {"name":"جفاف شديد",        "emoji":"☀️","effect":"crops_one",   "loss":(0.4,0.7),  "msg":"جفاف أثّر على أحد محاصيلك!"},
    {"name":"غزو الجراد",       "emoji":"🦗","effect":"crops_all",   "loss":(0.2,0.5),  "msg":"أسراب الجراد التهمت محاصيلك!"},
    {"name":"صقيع مبكر",        "emoji":"🌨️","effect":"crops_one",  "loss":(0.3,0.6),  "msg":"الصقيع أتلف أحد محاصيلك!",
     "regions": {"مناطق_باردة":["تركيا","سوريا","الاردن","لبنان","فلسطين","اسرائيل","قبرص"]}},
    {"name":"عاصفة رملية",      "emoji":"🌪️","effect":"crops_all",  "loss":(0.1,0.3),  "msg":"عاصفة رملية غطّت حقولك!",
     "regions": {"مناطق_صحراوية":["السعودية","الكويت","العراق","قطر","الامارات","البحرين","عمان","ايران","ليبيا","السودان","اليمن","مصر"]}},
    {"name":"فطر المحاصيل",     "emoji":"🍄","effect":"crops_type",  "loss":(0.5,0.9),  "crop_types":["قمح","ارز","فول"],
     "msg":"فطر أصاب محاصيلك الحبوبية!"},
    {"name":"عفن الثمار",       "emoji":"🪲","effect":"crops_type",  "loss":(0.4,0.8),  "crop_types":["زيتون","بن"],
     "msg":"عفن أتلف مزارع الثمار!"},
    {"name":"فيضان الحقول",     "emoji":"💧","effect":"crops_all",   "loss":(0.15,0.35),"msg":"فيضان غمر حقولك!",
     "regions": {"مناطق_رطبة":["مصر","السودان","العراق","سوريا","تركيا","لبنان"]}},
]

# ==================== الكوارث الإقليمية ====================
# كل كارثة تضرب جميع الدول اللاعبة في القائمة
REGIONAL_DISASTERS = [
    {
        "name": "موجة جفاف خليجية",
        "emoji": "🏜️",
        "regions": ["السعودية","الكويت","قطر","الامارات","البحرين","عمان"],
        "effect": "crops_all", "loss": (0.3, 0.6),
        "msg_private": "موجة جفاف إقليمية أصابت منطقتك!",
        "msg_channel": "موجة جفاف حارقة تجتاح دول الخليج العربي!",
    },
    {
        "name": "عاصفة رملية كبرى",
        "emoji": "🌪️",
        "regions": ["السعودية","العراق","الكويت","الاردن","سوريا","مصر"],
        "effect": "crops_all", "loss": (0.2, 0.4),
        "msg_private": "عاصفة رملية إقليمية ضربت محاصيلك!",
        "msg_channel": "عاصفة رملية عاتية تجتاح المشرق العربي!",
    },
    {
        "name": "وباء إقليمي",
        "emoji": "🦠",
        "regions": ["مصر","السودان","اليمن","العراق","سوريا"],
        "effect": "army", "loss": (0.1, 0.25),
        "msg_private": "وباء إقليمي ضرب جيشك!",
        "msg_channel": "وباء خطير ينتشر في الهلال الخصيب وشمال أفريقيا!",
    },
    {
        "name": "زلازل البحر المتوسط",
        "emoji": "🌍",
        "regions": ["تركيا","سوريا","لبنان","فلسطين","اسرائيل","قبرص","مصر"],
        "effect": "facilities", "loss": (1, 2),
        "msg_private": "زلزال إقليمي دمّر بعض منشآتك!",
        "msg_channel": "سلسلة زلازل تضرب سواحل البحر المتوسط!",
    },
    {
        "name": "غزو الجراد الإقليمي",
        "emoji": "🦗",
        "regions": ["اليمن","السعودية","عمان","السودان","مصر","الاردن"],
        "effect": "crops_all", "loss": (0.25, 0.5),
        "msg_private": "أسراب الجراد الإقليمية التهمت محاصيلك!",
        "msg_channel": "أسراب جراد ضخمة تجتاح شبه الجزيرة العربية وشمال أفريقيا!",
    },
    {
        "name": "أزمة نفطية إقليمية",
        "emoji": "📉",
        "regions": ["السعودية","الكويت","العراق","ايران","قطر","الامارات","البحرين","عمان"],
        "effect": "gold", "loss": (0.08, 0.18),
        "msg_private": "انهيار أسعار النفط ضرب خزينتك!",
        "msg_channel": "انهيار حاد في أسعار النفط يضرب دول الخليج المنتجة!",
    },
    {
        "name": "فيضانات الأنهر",
        "emoji": "🌊",
        "regions": ["العراق","سوريا","مصر","السودان","تركيا"],
        "effect": "facilities", "loss": (1, 2),
        "msg_private": "فيضانات الأنهار دمّرت بعض منشآتك!",
        "msg_channel": "فيضانات ضخمة تغرق سهول الأنهار الكبرى!",
    },
]
# احتمال كارثة إقليمية من أصل كل disaster_loop cycle
REGIONAL_DISASTER_CHANCE = 0.25   # 25%

# ==================== الأسلحة ====================

WEAPONS = {
    # ===== أسلحة تجهيز الجيش (السعر حسب عدد الجنود المراد تجهيزهم) =====
    "بندقية_هجوم": {
        "name": "🔫 بنادق هجومية",  "emoji": "🔫",
        "cost_per_soldier": 10,   # ¥ لكل جندي
        "damage_bonus": 0.05,
        "desc": "تجهيز الجنود ببنادق هجومية — +5% ضرر", "category": "تقليدي",
        "army_scale": True,
    },
    "مدفعية": {
        "name": "💣 مدفعية ثقيلة",  "emoji": "💣",
        "cost_per_soldier": 25,
        "damage_bonus": 0.15,
        "desc": "مدفعية ثقيلة للجنود — +15% ضرر", "category": "تقليدي",
        "army_scale": True,
    },
    # ===== أسلحة عددية (تشتري عدد محدد) =====
    "دبابات": {
        "name": "🚛 دبابة",          "emoji": "🚛",
        "cost": 2000,               # سعر الوحدة الواحدة
        "army_bonus_each": 20,      # جنود لكل دبابة
        "damage_bonus_each": 0.002, # ضرر لكل دبابة
        "desc": "كل دبابة = +20 جندي +0.2% ضرر", "category": "تقليدي",
        "unit": True,
    },
    "صواريخ": {
        "name": "🚀 منظومة صواريخ", "emoji": "🚀",
        "cost": 60000,  "army_bonus": 0, "damage_bonus": 0.30,
        "desc": "تزيد ضرر المعارك +30%", "category": "متطور"
    },
    # ===== طيران (شراء عددي) =====
    "طائرات_مسيرة": {
        "name": "🛸 طائرة مسيّرة",  "emoji": "🛸",
        "cost": 8000,
        "army_bonus_each": 5,
        "damage_bonus_each": 0.003,
        "defense_reduce_each": 0.002,
        "desc": "كل مسيّرة = +5 جندي +0.3% ضرر +0.2% اختراق دفاع", "category": "طيران",
        "unit": True,
    },
    "طائرات_حربية": {
        "name": "✈️ طائرة حربية",   "emoji": "✈️",
        "cost": 40000,
        "army_bonus_each": 30,
        "damage_bonus_each": 0.008,
        "desc": "كل طائرة = +30 جندي +0.8% ضرر", "category": "طيران",
        "unit": True,
    },
    "طائرات_شبح": {
        "name": "🛩️ طائرة شبح",    "emoji": "🛩️",
        "cost": 150000,
        "army_bonus_each": 80,
        "damage_bonus_each": 0.015,
        "desc": "كل طائرة شبح = +80 جندي +1.5% ضرر — تتجاوز الدفاعات!", "category": "طيران",
        "unit": True,
    },
    # ===== أسلحة دمار شامل =====
    "قنبلة_ذرية": {
        "name": "☢️ قنبلة ذرية",       "emoji": "☢️",
        "cost": 8000000, "army_bonus": 0,  "damage_bonus": 0.0,
        "desc": "⚠️ تدمر 80% من جيش العدو في ضربة واحدة! تنبّه دولياً!",
        "category": "دمار_شامل", "one_use": True, "nuke_power": 0.80
    },
    "قنبلة_هيدروجينية": {
        "name": "💥 قنبلة هيدروجينية", "emoji": "💥",
        "cost": 25000000, "army_bonus": 0,  "damage_bonus": 0.0,
        "desc": "☠️ تدمر 99% من جيش العدو + تحتله فوراً! حظر دولي لـ3 هجمات!",
        "category": "دمار_شامل", "one_use": True, "nuke_power": 0.99, "occupy": True
    },
}

# شرط شراء الأسلحة
WEAPON_REQUIREMENTS = {
    "طائرات_شبح":       {"infra": 2},
    "قنبلة_ذرية":       {"infra": 3, "level": 5, "facility": "مفاعل"},
    "قنبلة_هيدروجينية": {"infra": 3, "level": 6, "facility": "مفاعل"},
}

# شروط بناء المنشآت الخاصة
# المناطق الجافة (خليجية): محطة تحلية متاحة من Lv.1 بنية
# المناطق الساحلية (بحر متوسط/أحمر): محطة تحلية تحتاج Lv.3 بنية
# مصنع الأسلحة: متاح لكل الدول من Lv.2 بنية
COASTAL_REGIONS = {"مصر","ليبيا","سوريا","لبنان","فلسطين","اسرائيل","تركيا","قبرص","الاردن","اليمن","عمان","السودان"}
DESERT_REGIONS  = {"السعودية","الامارات","قطر","الكويت","البحرين","ايران","العراق"}

# حدود برية/بحرية بين المناطق
NEIGHBORS = {
    "مصر":      {"ليبيا","السودان","فلسطين","اسرائيل","الاردن","سوريا","لبنان","قبرص","تركيا"},  # بحر متوسط + سويس
    "ليبيا":    {"مصر","السودان","تونس"},
    "السودان":  {"مصر","ليبيا","اثيوبيا","اريتريا","اليمن"},   # البحر الأحمر
    "فلسطين":   {"مصر","اسرائيل","الاردن","لبنان"},
    "اسرائيل":  {"مصر","فلسطين","الاردن","لبنان","سوريا"},
    "الاردن":   {"مصر","فلسطين","اسرائيل","سوريا","العراق","السعودية"},
    "لبنان":    {"مصر","فلسطين","اسرائيل","سوريا","قبرص","تركيا"},
    "سوريا":    {"مصر","لبنان","اسرائيل","الاردن","العراق","تركيا"},
    "قبرص":     {"مصر","لبنان","سوريا","تركيا"},
    "تركيا":    {"مصر","سوريا","لبنان","قبرص","العراق","ايران"},
    "العراق":   {"الاردن","سوريا","تركيا","ايران","الكويت","السعودية"},
    "ايران":    {"تركيا","العراق","الكويت","الامارات","عمان","قطر","البحرين"},  # الخليج
    "الكويت":   {"العراق","السعودية","ايران"},
    "السعودية": {"الاردن","العراق","الكويت","قطر","الامارات","عمان","اليمن"},
    "قطر":      {"السعودية","الامارات","ايران","البحرين"},
    "البحرين":  {"السعودية","قطر","ايران","الامارات"},
    "الامارات": {"السعودية","قطر","البحرين","ايران","عمان"},
    "عمان":     {"السعودية","الامارات","اليمن","ايران"},
    "اليمن":    {"السعودية","عمان","السودان","جيبوتي"},
}

def can_attack_region(data, attacker_p, defender_region):
    """هل المهاجم يقدر يهاجم هذه المنطقة؟"""
    my_region = attacker_p.get("region","")
    neighbors = NEIGHBORS.get(my_region, set())

    # 1. على حدودك مباشرة
    if defender_region in neighbors:
        return True, None

    # 2. دولة تحت احتلالك
    if attacker_p.get("occupied_by") is None:  # أنا حر
        for uid2, p2 in data["players"].items():
            if (p2.get("occupied_by") == attacker_p["country_name"] or
                p2.get("colony_of")   == attacker_p["country_name"]):
                if defender_region in NEIGHBORS.get(p2.get("region",""), set()):
                    return True, None

    # 3. عضو في حلف مشترك له حدود مع الهدف
    orgs_data = data.get("organizations", {})
    my_org_members = set()
    for ov in orgs_data.values():
        if attacker_p["country_name"] in ov["members"]:
            my_org_members.update(ov["members"])
    my_org_members.discard(attacker_p["country_name"])
    for uid2, p2 in data["players"].items():
        if p2.get("country_name") in my_org_members:
            if defender_region in NEIGHBORS.get(p2.get("region",""), set()):
                return True, None

    # 4. الهدف ساحلي (إطلالة بحرية)
    if defender_region in COASTAL_REGIONS and my_region in COASTAL_REGIONS:
        return True, None

    return False, f"❌ *{defender_region}* بعيدة عن حدودك!\nلازم تكون على حدودك أو حدود حليف أو مستعمرة ليك أو ساحلية."

# ترتيب عرض الأسلحة في السوق حسب الفئة
WEAPON_MARKET_CATEGORIES = {
    "تقليدي":    "🔫 أسلحة تقليدية",
    "متطور":     "🚀 أسلحة متطورة",
    "طيران":     "✈️ طيران حربي",
    "دمار_شامل": "☢️ أسلحة دمار شامل",
}

# ==================== المستويات ====================
LEVELS = [
    {"level":1,"name":"قرية",         "xp":0,    "emoji":"🏘️"},
    {"level":2,"name":"مدينة ناشئة",  "xp":500,  "emoji":"🏙️"},
    {"level":3,"name":"اماره",        "xp":1500, "emoji":"🏰"},
    {"level":4,"name":"مملكة",        "xp":3000, "emoji":"👑"},
    {"level":5,"name":"امبراطورية",   "xp":6000, "emoji":"🌟"},
    {"level":6,"name":"قوة عظمى",    "xp":12000,"emoji":"⚡"},
    {"level":7,"name":"حضارة متقدمة","xp":25000,"emoji":"🚀"},
]

def get_level(xp):
    cur = LEVELS[0]
    for l in LEVELS:
        if xp >= l["xp"]: cur = l
        else: break
    return cur

def get_next_level(xp):
    for l in LEVELS:
        if xp < l["xp"]: return l
    return None

# مزايا المستويات
LEVEL_PERKS = {
    1: [],
    2: ["تجنيد_مخفض"],        # تجنيد أرخص 5%
    3: ["وزير_دفاع"],         # +8% دفاع في المعارك
    4: ["دبلوماسية_متقدمة"],  # معاهدات سلام + إعلانات حرب
    5: ["مخابرات"],           # تجسس على دول أخرى
    6: ["هيمنة_اقتصادية"],   # ضرائب مستعمرات +10% إضافي
    7: ["قوة_عظمى"],          # كل المزايا + بونص 15% هجوم
}

def get_perks(xp):
    lvl = get_level(xp)["level"]
    perks = []
    for l in range(1, lvl+1):
        perks += LEVEL_PERKS.get(l, [])
    return perks

def check_sovereignty(p, action="هذا الأمر"):
    """
    يفحص هل الدولة تقدر تنفذ الأمر حسب حالتها.
    يرجع (مسموح: bool, رسالة_خطأ: str)
    """
    occ  = p.get("occupied_by")
    col  = p.get("colony_of")
    # قائمة الأوامر المحظورة على المحتلة
    OCCUPIED_BLOCKED = {"هجوم","بناء","منشأة","مزرعة","بنية","سوق","شراء","تجسس",
                        "تحالف","معاهدة","تحالف_دفاعي","احمي","اعلن_حرب","تحويل",
                        "مهرجان","استعمر","اهدي","مضيق","حلف"}
    # قائمة الأوامر المحظورة على المستعمرة
    COLONY_BLOCKED   = {"هجوم","تحالف","معاهدة","تحالف_دفاعي","اعلن_حرب",
                        "احمي","مضيق","حلف","استعمر"}
    if occ:
        for kw in OCCUPIED_BLOCKED:
            if kw in action:
                return False, (
                    f"🏴 *دولتك محتلة!*\n{sep()}\n"
                    f"تحت سيطرة *{occ}* — لا يمكن {action}\n\n"
                    f"✊ اكتب `ثورة` لمحاولة التحرر\n"
                    f"💰 أو اجمع الضرائب للبقاء"
                )
    if col:
        for kw in COLONY_BLOCKED:
            if kw in action:
                return False, (
                    f"🏴 *دولتك مستعمرة!*\n{sep()}\n"
                    f"تحت وصاية *{col}* — لا يمكن {action}\n\n"
                    f"⚔️ اكتب `استقلال` لمحاولة الاستقلال"
                )
    return True, ""

# عقوبات الخمول
INACTIVITY_WARNING  = 60 * 60 * 24 * 3   # 3 أيام — تحذير
INACTIVITY_DECAY    = 60 * 60 * 24 * 7   # 7 أيام — تآكل الجيش
INACTIVITY_RATE     = 0.05               # 5% من الجيش كل دورة خمول

def add_xp(data, uid, amount):
    p   = data["players"][str(uid)]
    old = p.get("xp", 0)
    # الجامعة تضاعف XP
    unis = p.get("facilities", {}).get("جامعه", 0)
    if unis > 0:
        amount = amount * (1 + unis)
    new = old + int(amount)
    data["players"][str(uid)]["xp"] = new
    return get_level(new)["level"] > get_level(old)["level"], get_level(new)

# ==================== السكان والاحوال ====================
def calc_population(p):
    base  = 1.0
    terr  = p.get("territories",1) * 0.3
    crops = sum(p.get("crops",{}).values()) * 0.5
    econ  = min(p.get("gold",0)/10000, 2.0)
    wars  = p.get("wars_lost",0) * 0.2
    dis   = p.get("disasters_hit",0) * 0.1
    return round(max(0.5, base+terr+crops+econ-wars-dis), 1)

def calc_food_security(p):
    crops = sum(p.get("crops",{}).values())
    pop   = calc_population(p)
    base  = min(100, int((crops*0.5/pop)*100)) if pop > 0 else 100
    # محطات التحلية: +15 لكل محطة
    desal = p.get("facilities",{}).get("محطة_تحليه", 0)
    return min(100, base + desal * 15)

def calc_health(p):
    return max(10, min(100,
        60 + min(20, p.get("gold",0)//500) +
        calc_food_security(p)//5 -
        p.get("wars_lost",0)*5 -
        p.get("disasters_hit",0)*3
    ))

def calc_happiness(p):
    """
    رضا الشعب الشامل:
    قاعدة 50
    + الأمن الغذائي    (0→+25)
    + المثاقيل            (0→+15)
    + البنية التحتية   (+3 لكل مستوى)
    + الانتصارات       (+4 لكل انتصار، حد +20)
    + مهرجانات         (مخزونة في happiness_bonus)
    - خسائر الحروب     (-6 لكل خسارة)
    - الكوارث          (-2 لكل كارثة)
    - المديونية        (-3 لكل قرض نشط)
    - الاحتلال         (-40 ثابت)
    - الخيانة          (-20 ثابت)
    """
    food_bonus   = calc_food_security(p) // 4          # 0 → +25
    gold_bonus   = min(15, p.get("gold", 0) // 2000)   # 0 → +15
    infra_bonus  = p.get("infrastructure", 0) * 3       # +3 لكل مستوى بنية
    wins_bonus   = min(20, p.get("wars_won", 0) * 4)   # +4 لكل انتصار، حد 20
    fest_bonus   = p.get("happiness_bonus", 0)          # مهرجانات وإنفاق
    war_penalty  = p.get("wars_lost", 0) * 6            # -6 لكل هزيمة
    dis_penalty  = p.get("disasters_hit", 0) * 2        # -2 لكل كارثة
    debt_penalty = len([l for l in p.get("loans", []) if not l.get("paid")]) * 3
    occ_penalty  = 40 if p.get("occupied_by") else 0   # احتلال = -40
    traitor_pen  = 20 if p.get("traitor") else 0
    return max(0, min(100,
        50 + food_bonus + gold_bonus + infra_bonus + wins_bonus + fest_bonus
        - war_penalty - dis_penalty - debt_penalty - occ_penalty - traitor_pen
    ))

def status_emoji(v):
    return "🟢" if v>=80 else "🟡" if v>=50 else "🟠" if v>=25 else "🔴"

# ==================== تنسيق ====================
def sep(c="─", n=30): return c*n
def sep2(): return "┄"*30
def box_title(e, t): return f"╔{'═'*28}╗\n║ {e} *{t}*\n╚{'═'*28}╝"
def section(title): return f"┌─ {title} ─"
def escape_md(t):
    """هروب من رموز Markdown الخاصة في أسماء الدول"""
    for ch in ['*','_','`','[',']','(',')','>','#','+','-','=','|','{','}','.',',','!']:
        t = t.replace(ch, f'\\{ch}')
    return t

import re as _re
async def safe_md(update_or_msg, text, is_message=True):
    """
    يبعت رسالة Markdown بأمان — لو فشل يحاول HTML، لو فشل plain.
    يتعامل مع الرسائل الطويلة بالتقطيع تلقائياً.
    """
    send_fn = update_or_msg.reply_text if is_message else update_or_msg.send_message
    parts = []
    if len(text) <= 4000:
        parts = [text]
    else:
        chunk = ""
        for line in text.split("\n"):
            if len(chunk) + len(line) + 1 > 4000:
                parts.append(chunk); chunk = line + "\n"
            else:
                chunk += line + "\n"
        if chunk.strip(): parts.append(chunk)
    for part in parts:
        try:
            await send_fn(part, parse_mode="Markdown")
        except Exception:
            try:
                html = _re.sub(r'\*([^*\n]+)\*', r'<b>\1</b>', part)
                html = _re.sub(r'_([^_\n]+)_',   r'<i>\1</i>', html)
                html = _re.sub(r'`([^`\n]+)`',    r'<code>\1</code>', html)
                await send_fn(html, parse_mode="HTML")
            except Exception:
                await send_fn(_re.sub(r'[*_`]', '', part))
def progress_bar(v, mx, n=10):
    f = int((v/mx)*n) if mx>0 else 0
    return "█"*f + "░"*(n-f)

# ==================== بيانات ====================

_data_lock = asyncio.Lock()

def save_data(d):
    """حفظ آمن — atomic write + backup تلقائي"""
    # backup قبل الحفظ
    if os.path.exists(DATA_FILE):
        try:
            import shutil
            shutil.copy2(DATA_FILE, DATA_FILE + ".bak")
        except: pass
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)  # atomic — مش ممكن يتقطع في النص

def load_data():
    """تحميل مع قراءة آمنة"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, IOError):
            # لو الملف اتخرب، رجّع نسخة احتياطية
            backup = DATA_FILE + ".bak"
            if os.path.exists(backup):
                with open(backup, "r", encoding="utf-8") as f:
                    d = json.load(f)
            else:
                d = {}
    else:
        d = {}
    d.setdefault("players", {})
    d.setdefault("pending_codes", {})
    d.setdefault("market", [])
    d.setdefault("shipments", [])
    d.setdefault("alliance_requests", {})
    d.setdefault("dissolve_requests", {})
    d.setdefault("last_disaster", 0)
    d.setdefault("wars_enabled", True)
    d.setdefault("straits", {k: {"blocked": False, "blocked_by": None} for k in STRAITS})
    d.setdefault("organizations", {})   # {"اسم الحلف": {"founder": "اسم الدولة", "members": [...], "created_at": timestamp}}
    d.setdefault("org_invites", {})      # دعوات الانضمام المعلقة
    d.setdefault("news_channel_id", 0)   # ID القناة/المجموعة للنشرة الإخبارية
    return d


def get_facility_infra_req(fac_id, region):
    """يرجع الـ infra المطلوب لبناء منشأة في منطقة معينة"""
    fc = RESOURCE_FACILITIES.get(fac_id, {})
    if not fc:
        return 0
    # محطة تحلية — لها متطلبات مختلفة حسب نوع المنطقة
    if "infra_desert" in fc:
        if region in DESERT_REGIONS:  return fc.get("infra_desert", 1)
        if region in COASTAL_REGIONS: return fc.get("infra_coastal", 2)
        return fc.get("infra_other", 4)
    return fc.get("infra_req", 0)


    """تطبيع النص — ة↔ه، همزات، ألف مقصورة"""
    t = t.strip()
    t = t.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    t = t.replace("ة","ه")
    t = t.replace("ى","ي")
    return t

def norm(t):
    """تطبيع النص — ة↔ه، همزات، ألف مقصورة"""
    t = t.strip()
    t = t.replace("أ","ا").replace("إ","ا").replace("آ","ا")
    t = t.replace("ة","ه")
    t = t.replace("ى","ي")
    return t

def generate_code():
    return "".join(random.choices(string.ascii_uppercase+string.digits, k=6))

def get_player(d, uid):
    p = d["players"].get(str(uid))
    if p:
        # تصحيح تلقائي للقيم السالبة
        for field in ["gold","army","territories","xp"]:
            if p.get(field,0) < 0:
                d["players"][str(uid)][field] = 0
        # إضافة حقول ناقصة للاعبين القدامى
        defaults = {
            "weapons": {},
            "occupied_by": None, "colony_of": None,
            "nuke_banned": 0, "colony_last_harvest": 0, "loans": [],
            "at_war": [], "allies": [], "traitor": False,
            "wars_lost": 0, "disasters_hit": 0, "last_attack": 0,
            "infrastructure": 0, "capital": "", "crops_amount": {},
            "protected_by": None, "protects": [],
            "war_declared": [], "peace_treaties": {}, "defensive_pacts": [],
            "last_active": 0,
            "wars_won": 0, "happiness_bonus": 0,
            "last_collapse": 0,
        }
        for k, v in defaults.items():
            if k not in p:
                d["players"][str(uid)][k] = v
    return p

def is_admin(uid):
    return uid == ADMIN_ID

def find_by_code(d, code):
    for uid, p in d["players"].items():
        if p.get("player_code") == code.upper():
            return uid, p
    return None, None

def find_by_name(d, name):
    name_norm = norm(name)
    for uid, p in d["players"].items():
        clean = norm(p["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)",""))
        if clean == name_norm or norm(p["country_name"]) == name_norm or norm(p.get("region","")) == name_norm:
            return uid, p
    return None, None

def transfer_conquest(data, winner_uid, loser_uid):
    """ينقل كل موارد الدولة المهزومة للمنتصر"""
    winner_uid = str(winner_uid)
    loser_uid  = str(loser_uid)
    w = data["players"][winner_uid]
    l = data["players"][loser_uid]

    # مثاقيل
    gold = l.get("gold", 0)
    data["players"][winner_uid]["gold"] += gold
    data["players"][loser_uid]["gold"]   = 0

    # مزارع
    lc  = l.get("crops", {})
    lca = l.get("crops_amount", {})
    wc  = w.get("crops", {})
    wca = w.get("crops_amount", {})
    for crop, cnt in lc.items():
        wc[crop] = wc.get(crop, 0) + cnt
        if crop in lca:
            wca[crop] = lca[crop]
    data["players"][winner_uid]["crops"]        = wc
    data["players"][winner_uid]["crops_amount"] = wca
    data["players"][loser_uid]["crops"]         = {}
    data["players"][loser_uid]["crops_amount"]  = {}

    # منشآت
    lf = l.get("facilities", {})
    wf = w.get("facilities", {})
    for res, cnt in lf.items():
        wf[res] = wf.get(res, 0) + cnt
    data["players"][winner_uid]["facilities"] = wf
    data["players"][loser_uid]["facilities"]  = {}

    # أسلحة
    lw = l.get("weapons", {})
    ww = w.get("weapons", {})
    for weap, cnt in lw.items():
        # القنابل لا تُنقل (one_use)
        if WEAPONS.get(weap, {}).get("one_use"):
            continue
        ww[weap] = ww.get(weap, 0) + cnt
    data["players"][winner_uid]["weapons"] = ww
    data["players"][loser_uid]["weapons"]  = {}

    # بنية تحتية — ينقل نصفها (الاحتلال يدمر نصف البنية)
    loser_infra = l.get("infrastructure", 0)
    if loser_infra > 0:
        transferred_infra = loser_infra // 2
        data["players"][winner_uid]["infrastructure"] = w.get("infrastructure", 0) + transferred_infra
        data["players"][loser_uid]["infrastructure"]  = loser_infra - transferred_infra

    return gold

def calc_colony_harvest(col_p):
    """يحسب دخل مستعمرة — يُعاد استخدامه في احصد مستعمرة"""
    region    = col_p.get("region", "")
    preferred = REGION_PREFERRED_CROPS.get(region, [])
    total     = 0
    lines     = []
    for crop, count in col_p.get("crops", {}).items():
        fc      = FARM_CROPS.get(crop, {})
        amt_per = col_p.get("crops_amount", {}).get(crop, fc.get("amount", 10))
        if crop in preferred:
            amt_per = int(amt_per * 1.5)
        qty    = amt_per * count
        price  = CROP_SELL_PRICE.get(crop, 20)
        earned = qty * price
        total += earned
        lines.append(f"  {fc.get('emoji','🌾')} {qty}طن {crop} ← {CUR}{earned:,}")
    for res, count in col_p.get("facilities", {}).items():
        fc     = RESOURCE_FACILITIES.get(res, {})
        qty    = fc.get("amount", 2) * count
        price  = CROP_SELL_PRICE.get(res, 400)
        earned = qty * price
        total += earned
        lines.append(f"  {fc.get('emoji','🏭')} {qty} {res} ← {CUR}{earned:,}")
    terr_income = col_p.get("territories", 1) * 50
    total += terr_income
    return total, terr_income, lines



def new_player(region, country_name, player_id):
    return {
        "country_name":    country_name,
        "region":          region,
        "gold":            5000,
        "army":            100,
        "territories":     1,
        "allies":          [],
        "at_war":          [],
        "last_tax":        0,
        "player_code":     generate_code(),
        "xp":              0,
        "facilities":      {},
        "crops":           {},
        "crops_amount":    {},
        "infrastructure":  0,
        "capital":         "",
        "traitor":         False,
        "wars_lost":       0,
        "disasters_hit":   0,
        "last_attack":     0,
        "loans":           [],
        "weapons":         {},
        "occupied_by":     None,
        "colony_of":       None,
        "nuke_banned":     0,
        "colony_last_harvest": 0,
        "protected_by":    None,
        "protects":        [],
        "war_declared":    [],
        "peace_treaties":  {},
        "defensive_pacts": [],
        "last_active":     time.time(),
        "wars_won":        0,
        "happiness_bonus": 0,
        "last_collapse":   0,
    }

def get_farm_cost(d, crop):
    """السعر ثابت لا يتغير"""
    return FARM_CROPS[crop]["base_cost"]

def get_strait_status(d):
    result = {}
    for name, info in STRAITS.items():
        saved = d["straits"].get(name, {})
        result[name] = {**info, "blocked":saved.get("blocked",False), "blocked_by":saved.get("blocked_by")}
    return result

def is_shipment_blocked(d, seller_reg, buyer_reg, seller_name=None, buyer_name=None):
    """يفحص لو الشحنة محجوبة — أعضاء الحلف المشترك مع صاحب المضيق لا يتأثرون"""
    orgs_d = d.get("organizations", {})
    for name, s in get_strait_status(d).items():
        if not s["blocked"]: continue
        blocker = s.get("blocked_by", "")
        if seller_reg in s["affects"] or buyer_reg in s["affects"]:
            # لو البائع أو المشتري في حلف مع صاحب المضيق — مش محجوب
            for party in [seller_name, buyer_name]:
                if not party: continue
                in_same_org = any(
                    party in ov["members"] and blocker in ov["members"]
                    for ov in orgs_d.values()
                )
                if in_same_org:
                    break
            else:
                return True, name
    return False, None

def get_tax_cooldown(d, region):
    """يرجع الـ cooldown الفعلي — 15 دقيقة لو مضيق مغلق يؤثر على المنطقة"""
    straits = get_strait_status(d)
    # اجيب اللاعب صاحب المنطقة
    player = next((pp for pp in d.get("players",{}).values() if pp.get("region") == region), None)
    for s in straits.values():
        if not s.get("blocked"): continue
        if region not in s.get("affects", []): continue
        # تحقق لو اللاعب وصاحب المضيق في حلف مشترك
        blocker_name = s.get("blocked_by","")
        if player:
            orgs_d = d.get("organizations", {})
            player_name = player.get("country_name","")
            in_same_org = any(
                player_name in ov["members"] and blocker_name in ov["members"]
                for ov in orgs_d.values()
            )
            if in_same_org: continue
        return STRAIT_TAX_COOLDOWN
    return TAX_COOLDOWN

def clean_old_requests(d):
    """امسح طلبات التحالف + حروب منتهية + عروض سوق قديمة"""
    now = time.time()

    try:
        # ── طلبات التحالف ──
        d["alliance_requests"] = {
            k: v for k, v in d.get("alliance_requests", {}).items()
            if now - v.get("time", 0) < ALLY_REQ_TTL
        }
    except Exception: pass

    try:
        # ── cleanup الحروب المنتهية ──
        for uid, p in list(d.get("players", {}).items()):
            wars = p.get("at_war", [])
            if not wars:
                continue
            still_at_war = []
            for enemy_name in wars:
                enemy_uid = next(
                    (eid for eid, ep in d["players"].items()
                     if ep.get("country_name") == enemy_name), None)
                if not enemy_uid:
                    continue
                last_atk = max(
                    p.get("last_attack", 0) or 0,
                    d["players"][enemy_uid].get("last_attack", 0) or 0
                )
                if now - last_atk < WAR_EXPIRE:
                    still_at_war.append(enemy_name)
            d["players"][uid]["at_war"] = still_at_war
    except Exception: pass

    try:
        # ── cleanup سوق الأسلحة ──
        market = d.get("weapon_market", [])
        valid_sellers = {p["country_name"] for p in d.get("players", {}).values()}
        d["weapon_market"] = [
            entry for entry in market
            if entry.get("seller") in valid_sellers
            and now - (entry.get("listed_at") or 0) < MARKET_TTL
        ]
    except Exception: pass

# ==================== الخريطة ====================
def generate_map(players, d):
    if not os.path.exists(MAP_FILE):
        # ارجع صورة فارغة لو الخريطة مش موجودة
        img = Image.new("RGBA", (800, 600), (240, 240, 240, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG"); buf.seek(0)
        return buf

    img     = Image.open(MAP_FILE).convert("RGBA")
    draw    = ImageDraw.Draw(img)
    straits = get_strait_status(d)

    # حمّل خط — fallback للخط الافتراضي لو مش موجود
    try:
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_label = ImageFont.load_default()
        font_small = font_label

    for uid, p in players.items():
        region    = p.get("region")
        if region not in REGION_COORDS: continue
        lvl   = get_level(p.get("xp", 0))
        tag   = " 🗡️" if p.get("traitor") else ""
        label = f"{lvl['emoji']}{p.get('country_name','')}{tag}"

        # لو محتلة أو مستعمرة — استخدم علم المحتل/المستعمِر
        controller_name = p.get("occupied_by") or p.get("colony_of")
        if controller_name:
            # ابحث عن منطقة المحتل
            ctrl_region = None
            for _, cp in players.items():
                if cp.get("country_name") == controller_name:
                    ctrl_region = cp.get("region"); break
            flag_path = os.path.join(FLAGS_DIR, f"{ctrl_region}.png") if ctrl_region else None
            # إذا مفيش علم للمحتل — رجّع للعلم الأصلي
            if not flag_path or not os.path.exists(flag_path):
                flag_path = os.path.join(FLAGS_DIR, f"{region}.png")
        else:
            flag_path = os.path.join(FLAGS_DIR, f"{region}.png")

        for i, (cx, cy) in enumerate(REGION_COORDS[region]):
            size = FLAG_SIZE_MAIN if i == 0 else FLAG_SIZE_SMALL
            # لون الإطار: أحمر للمحتلة، برتقالي للمستعمرة، أبيض عادي
            if p.get("occupied_by"):
                border_color = "red"
            elif p.get("colony_of"):
                border_color = "orange"
            else:
                border_color = "white"
            if flag_path and os.path.exists(flag_path):
                try:
                    flag = Image.open(flag_path).convert("RGBA")
                    f2   = flag.resize((size, int(size*0.6)), Image.LANCZOS)
                    fw, fh = f2.size
                    img.paste(f2, (cx-fw//2, cy-fh//2), f2)
                    draw.rectangle([cx-fw//2-2, cy-fh//2-2, cx+fw//2+2, cy+fh//2+2],
                                   outline=border_color, width=3)
                    # إشارة احتلال/استعمار صغيرة
                    if p.get("occupied_by"):
                        draw.ellipse([cx+fw//2-8, cy-fh//2-8, cx+fw//2+8, cy-fh//2+8],
                                     fill="red", outline="white", width=1)
                    elif p.get("colony_of"):
                        draw.ellipse([cx+fw//2-8, cy-fh//2-8, cx+fw//2+8, cy-fh//2+8],
                                     fill="orange", outline="white", width=1)
                    flag.close(); f2.close()
                except Exception as e:
                    logging.warning(f"Flag error {region}: {e}")
                    draw.ellipse([cx-30, cy-20, cx+30, cy+20], fill="royalblue", outline=border_color, width=2)
            else:
                draw.ellipse([cx-30, cy-20, cx+30, cy+20], fill="royalblue", outline=border_color, width=2)
            if i == 0:
                # ظل أسود ثم نص أبيض
                ty = cy + int(size*0.6)//2 + 8
                for ox, oy in [(-1,1),(1,1),(-1,-1),(1,-1)]:
                    draw.text((cx+ox, ty+oy), label, fill="black", anchor="mt", font=font_label)
                draw.text((cx, ty), label, fill="white", anchor="mt", font=font_label)

    # ===== المضائق =====
    strait_pos = {"هرمز":(1400,1050),"باب المندب":(1100,1550),"السويس":(500,950),"البسفور":(490,390)}
    for name, pos in strait_pos.items():
        s   = straits.get(name, {})
        col = "red" if s.get("blocked") else "cyan"
        cx, cy = pos
        draw.ellipse([cx-20,cy-20,cx+20,cy+20], fill=col, outline="black", width=2)
        sname = f"{'🔴' if s.get('blocked') else '🟢'}{name}"
        for ox, oy in [(-1,1),(1,1)]:
            draw.text((cx+ox, cy+26+oy), sname, fill="black", anchor="mt", font=font_small)
        draw.text((cx, cy+26), sname, fill="white", anchor="mt", font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG"); buf.seek(0)
    return buf

# ==================== جمع الضرائب يدوياً ====================
async def do_harvest(app, uid, p, data):
    """جمع الضرائب + حصاد المزارع + إنتاج المنشآت دفعة واحدة"""
    crops_p      = p.get("crops",{})
    crops_amount = p.get("crops_amount",{})
    region       = p.get("region","")
    preferred    = REGION_PREFERRED_CROPS.get(region,[])
    total        = 0
    total_tons   = 0
    lines        = []

    # --- المزارع ---
    for crop, count in crops_p.items():
        fc      = FARM_CROPS.get(crop, {})
        amt_per = crops_amount.get(crop, fc.get("amount",10))
        if crop in preferred:
            amt_per = int(amt_per * 1.5)
        qty         = amt_per * count
        price       = CROP_SELL_PRICE.get(crop, 20)   # ثابت
        earned      = qty * price
        total      += earned
        total_tons += qty
        lines.append(f"  {fc.get('emoji','🌾')} {qty}طن {crop} ← {CUR}{earned:,}")

    # --- المنشآت الصناعية ---
    facs = p.get("facilities",{})
    for res, count in facs.items():
        fc     = RESOURCE_FACILITIES.get(res,{})
        qty    = fc.get("amount",2) * count
        price  = CROP_SELL_PRICE.get(res, 400)        # ثابت
        earned = qty * price
        total += earned
        lines.append(f"  {fc.get('emoji','🏭')} {qty} {res} ← {CUR}{earned:,}")

    # --- دخل الأراضي الأساسي (يزيد مع المشاريع) ---
    num_projects = sum(facs.values()) + sum(crops_p.values())
    infra        = p.get("infrastructure", 0)
    base_tax     = p.get("territories", 1) * 500 + 1000
    project_bonus = num_projects * 300
    infra_bonus   = infra * 1500
    terr_income   = base_tax + project_bonus + infra_bonus
    total += terr_income

    # --- ضرائب المستعمرات التلقائية ---
    colony_lines = []
    colony_total = 0
    for col_uid_s, col_p in data["players"].items():
        if col_p.get("colony_of") != p["country_name"]:
            continue
        # احسب دخل المستعمرة
        col_crops = col_p.get("crops", {})
        col_facs  = col_p.get("facilities", {})
        col_region= col_p.get("region", "")
        col_pref  = REGION_PREFERRED_CROPS.get(col_region, [])
        col_income = 0
        for crop, count in col_crops.items():
            fc      = FARM_CROPS.get(crop, {})
            amt_per = fc.get("amount", 10)
            if crop in col_pref:
                amt_per = int(amt_per * 1.5)
            col_income += amt_per * count * CROP_SELL_PRICE.get(crop, 20)
        for res, count in col_facs.items():
            fc = RESOURCE_FACILITIES.get(res, {})
            col_income += fc.get("amount", 2) * count * CROP_SELL_PRICE.get(res, 400)
        col_terr = col_p.get("territories", 1) * 300 + 500  # ضرائب أقل من الدولة الأصلية
        col_income += col_terr
        # نسبة الضريبة — الميناء يرفعها +15% لكل ميناء (حد أقصى 70%)
        ports    = p.get("facilities", {}).get("ميناء", 0)
        tax_rate = min(0.80, 0.40 + ports * 0.15 + (0.10 if "هيمنة_اقتصادية" in get_perks(p.get("xp",0)) else 0))
        tax_cut  = int(col_income * tax_rate)
        if tax_cut > 0:
            colony_total += tax_cut
            col_name_clean = col_p["country_name"].replace(" (مستعمرة)","")
            colony_lines.append(f"  🏴 {col_name_clean}: +{CUR}{tax_cut:,} ({int(tax_rate*100)}% ضريبة)")
    total += colony_total

    # --- سداد القروض التلقائي ---
    loans     = p.get("loans",[])
    loan_msgs = []
    new_loans = []
    for loan in loans:
        loan["remaining_cycles"] = loan.get("remaining_cycles",1) - 1
        if loan["remaining_cycles"] <= 0:
            due = loan["due"]
            if data["players"][str(uid)]["gold"] + total >= due:
                total -= due
                loan_msgs.append(f"   🏦 سُدِّد {loan['name']}: -{CUR}{due:,} ✅")
            else:
                penalty = int(due * 0.5)
                data["players"][str(uid)]["gold"] = max(0, data["players"][str(uid)]["gold"] - penalty)
                loan_msgs.append(f"   ⚠️ {loan['name']} متأخر! عقوبة: -{CUR}{penalty:,}")
                loan["remaining_cycles"] = 2
                new_loans.append(loan)
        else:
            new_loans.append(loan)
    data["players"][str(uid)]["loans"]    = new_loans
    data["players"][str(uid)]["gold"]    += total
    # لو الدولة محتلة — 60% من الدخل يروح للمحتل
    occ_name = p.get("occupied_by")
    occ_cut_txt = ""
    if occ_name:
        cut = int(total * 0.60)
        remainder = total - cut
        data["players"][str(uid)]["gold"] = data["players"][str(uid)]["gold"] - total + remainder
        occ_uid2, occ_p2 = find_by_name(data, occ_name)
        if occ_p2:
            data["players"][occ_uid2]["gold"] = occ_p2.get("gold",0) + cut
        occ_cut_txt = f"\n🏴 {cut:,}¥ انتزعها {occ_name} (60% احتلال)"
        total = remainder
    data["players"][str(uid)]["last_tax"]    = time.time()
    data["players"][str(uid)]["last_active"] = time.time()
    leveled_up, new_lvl = add_xp(data, uid, 50 + p.get("territories",1)*10)

    # --- رسالة النتيجة ---
    new_balance = data["players"][str(uid)]["gold"]  # الرصيد الفعلي بعد كل العمليات
    if not lines and not loan_msgs:
        msg = (
            f"💰 *جمع الضرائب*\n{sep()}\n"
            f"🗺️ {p['territories']} منطقة: {CUR}{base_tax:,}\n"
            f"🏗️ بونص البنية التحتية: {CUR}{infra_bonus:,}\n"
            f"📦 لا يوجد مشاريع بعد\n"
            f"{sep()}\n"
            f"💰 المضاف: *+{CUR}{terr_income:,}*"
            f"{occ_cut_txt}\n"
            f"💰 الرصيد: *{CUR}{new_balance:,}*\n"
            f"⏳ القادم بعد 10 دقايق\n"
            f"💡 ابنِ مزارع أو منشآت لزيادة الدخل!"
        )
    else:
        prod_txt = "\n".join(lines) if lines else "  (لا يوجد إنتاج)"
        loan_txt = "\n".join(loan_msgs) if loan_msgs else ""
        colony_txt = "\n".join(colony_lines) if colony_lines else ""
        msg = (
            f"{box_title('💰','جمع الضرائب والحصاد')}\n\n"
            f"📦 *الإنتاج:*\n{prod_txt}\n"
            f"  🗺️ ضرائب الأراضي: {CUR}{base_tax:,}\n"
            f"  📈 بونص المشاريع ({num_projects}): {CUR}{project_bonus:,}\n"
            f"  🏗️ بونص البنية (Lv.{infra}): {CUR}{infra_bonus:,}\n"
        )
        if colony_txt:
            msg += f"  🏴 *ضرائب المستعمرات:*\n{colony_txt}\n  📊 إجمالي المستعمرات: +{CUR}{colony_total:,}\n"
        msg += (
            f"{sep()}\n"
            f"  🌾 كمية: ~{total_tons} طن\n"
            f"  💰 المضاف: *+{CUR}{total:,}*"
            f"{occ_cut_txt}\n"
            f"  💰 الرصيد: *{CUR}{new_balance:,}*"
        )
        if loan_txt:
            msg += f"\n{sep()}\n🏦 *القروض:*\n{loan_txt}"
    if leveled_up:
        msg += f"\n🎊 *ترقية!* {new_lvl['name']} {new_lvl['emoji']}"
    msg += f"\n{sep()}\n⏳ القادم بعد 10 دقايق"
    try:
        await app.bot.send_message(chat_id=int(uid), text=msg, parse_mode="Markdown")
    except: pass

# ==================== loops ====================

def _apply_disaster_to_player(data, uid, d):
    """تطبق تأثير كارثة على لاعب واحد، ترجع loss_desc"""
    p = data["players"][uid]
    loss_desc = ""

    if d["effect"] == "army":
        pct  = random.uniform(*d["loss"])
        loss = max(10, int(p["army"] * pct))
        data["players"][uid]["army"] = max(0, p["army"] - loss)
        loss_desc = f"{loss:,} جندي"

    elif d["effect"] == "gold":
        pct  = random.uniform(*d["loss"])
        loss = max(50, int(p["gold"] * pct))
        data["players"][uid]["gold"] = max(0, p["gold"] - loss)
        loss_desc = f"{CUR}{loss:,}"

    elif d["effect"] == "facilities":
        facs = p.get("facilities", {})
        if facs:
            res  = random.choice(list(facs.keys()))
            loss = random.randint(1, min(int(d["loss"][1]), facs[res]))
            data["players"][uid]["facilities"][res] = max(0, facs[res] - loss)
            if data["players"][uid]["facilities"][res] == 0:
                del data["players"][uid]["facilities"][res]
            fc_name = RESOURCE_FACILITIES.get(res, {}).get("name", res)
            loss_desc = f"{loss} × {fc_name}"

    elif d["effect"] == "crops_one":
        crops = {k: v for k, v in p.get("crops", {}).items() if v > 0}
        if crops:
            res = random.choice(list(crops.keys()))
            pct = random.uniform(*d["loss"])
            destroyed = max(1, int(crops[res] * pct))
            data["players"][uid]["crops"][res] = max(0, crops[res] - destroyed)
            loss_desc = f"{destroyed} حقل {res}"

    elif d["effect"] in ("crops_all", "crops_type"):
        target = d.get("crop_types") or None
        crops  = {k: v for k, v in p.get("crops", {}).items()
                  if v > 0 and (target is None or k in target)}
        if crops:
            pct = random.uniform(*d["loss"])
            destroyed_list = []
            for res, cnt in crops.items():
                destroyed = max(0, int(cnt * pct))
                data["players"][uid]["crops"][res] = max(0, cnt - destroyed)
                if destroyed > 0:
                    destroyed_list.append(f"{destroyed} {res}")
            loss_desc = "، ".join(destroyed_list[:3]) or "—"

    data["players"][uid]["disasters_hit"] = p.get("disasters_hit", 0) + 1
    return loss_desc


async def disaster_loop(app):
    await asyncio.sleep(DISASTER_EVERY)
    while True:
        try:
            data = load_data()
            channel_id = data.get("news_channel_id", 0)

            if data["players"]:
                # ──── كارثة إقليمية (25% احتمال) ────
                if random.random() < REGIONAL_DISASTER_CHANCE:
                    # اختر كارثة إقليمية عشوائية
                    rd = random.choice(REGIONAL_DISASTERS)
                    affected_regions = set(rd["regions"])

                    # ابحث عن اللاعبين في هذه المناطق
                    victims = [(uid, p) for uid, p in data["players"].items()
                               if p.get("region", "") in affected_regions]

                    if victims:
                        victim_names = []
                        for uid, p in victims:
                            loss_desc = _apply_disaster_to_player(data, uid, rd)
                            victim_names.append(p["country_name"])
                            # إشعار خاص لكل لاعب
                            private_msg = (
                                f"{box_title(rd['emoji'], 'كارثة إقليمية — ' + rd['name'])}\n"
                                f"📢 {rd['msg_private']}\n"
                                f"{sep()}\n"
                                f"💔 خسارتك: *{loss_desc or '—'}*"
                            )
                            try:
                                await app.bot.send_message(
                                    chat_id=int(uid), text=private_msg, parse_mode="Markdown")
                            except: pass

                        data["last_disaster"] = time.time()
                        save_data(data)

                        # إشعار القناة
                        if channel_id and victim_names:
                            names_txt = " | ".join(victim_names[:6])
                            if len(victim_names) > 6:
                                names_txt += f" و{len(victim_names)-6} آخرين"
                            channel_msg = (
                                f"{box_title(rd['emoji'], 'كارثة إقليمية!')}\n"
                                f"📢 *{rd['msg_channel']}*\n"
                                f"{sep()}\n"
                                f"🌍 الدول المتضررة ({len(victim_names)}):\n"
                                f"_{names_txt}_"
                            )
                            try:
                                await app.bot.send_message(
                                    chat_id=channel_id, text=channel_msg, parse_mode="Markdown")
                            except: pass
                        await asyncio.sleep(DISASTER_EVERY)
                        continue

                # ──── كارثة فردية (عادية) ────
                uids   = list(data["players"].keys())
                uid    = random.choice(uids)
                p      = data["players"][uid]
                region = p.get("region", "")

                # فلتر الكوارث المناسبة للمنطقة
                eligible = []
                for dis in DISASTERS:
                    regions_filter = dis.get("regions", {})
                    if regions_filter:
                        allowed = [r for rlist in regions_filter.values() for r in rlist]
                        if region not in allowed:
                            continue
                    eligible.append(dis)
                if not eligible:
                    eligible = DISASTERS
                d = random.choice(eligible)

                # تجاهل لو crops_type وما في محاصيل مناسبة
                if d["effect"] == "crops_type":
                    target = d.get("crop_types", [])
                    has_crops = any(v > 0 for k, v in p.get("crops", {}).items() if k in target)
                    if not has_crops:
                        await asyncio.sleep(DISASTER_EVERY)
                        continue

                loss_desc = _apply_disaster_to_player(data, uid, d)
                data["last_disaster"] = time.time()
                save_data(data)

                private_msg = (
                    f"{box_title(d['emoji'], 'كارثة — ' + d['name'])}\n"
                    f"ضربت *{p['country_name']}*!\n"
                    f"📢 {d['msg']}\n"
                    f"{sep()}\n"
                    f"💔 الخسارة: *{loss_desc or '—'}*"
                )
                try:
                    await app.bot.send_message(
                        chat_id=int(uid), text=private_msg, parse_mode="Markdown")
                except: pass

                if channel_id:
                    channel_msg = (
                        f"{box_title(d['emoji'], 'كارثة طبيعية!')}\n"
                        f"ضربت *{p['country_name']}* — _{p.get('region', '')}_\n"
                        f"📢 {d['msg']}\n"
                        f"{sep()}\n"
                        f"💔 الخسارة: *{loss_desc or '—'}*"
                    )
                    try:
                        await app.bot.send_message(
                            chat_id=channel_id, text=channel_msg, parse_mode="Markdown")
                    except: pass

        except Exception as e:
            logging.error(f"Disaster loop: {e}")
        await asyncio.sleep(DISASTER_EVERY)


_harvest_lock = asyncio.Lock()

# ==================== الأحداث السياسية ====================
POLITICAL_EVENTS = [
    {
        "id": "coup", "name": "انقلاب عسكري", "emoji": "🪖",
        "min_unhappy": 20,  # يحصل لما الرضا أقل من 20%
        "effect": "army", "loss": (0.3, 0.5),
        "msgs": [
            "قائد الجيش أعلن الانقلاب! الجيش انقسم على نفسه 💥",
            "دبابات في الشوارع والقصر محاصر! الجيش خسر جزءاً منه 🪖",
        ]
    },
    {
        "id": "revolution", "name": "ثورة شعبية", "emoji": "✊",
        "min_unhappy": 15,
        "effect": "gold", "loss": (0.2, 0.4),
        "msgs": [
            "الشعب نزل الشوارع! الخزينة نُهبت في الفوضى 💸",
            "ثورة اجتاحت العاصمة! جزء من المثاقيل ضاع 🔥",
        ]
    },
    {
        "id": "assassination", "name": "اغتيال وزراء", "emoji": "🗡️",
        "min_unhappy": 25,
        "effect": "xp", "loss": (0.1, 0.2),
        "msgs": [
            "اغتيال وزير الاقتصاد! التنمية تأخرت 🗡️",
            "مجلس الوزراء أصيب باغتيالات! فقدت خبرة وتقدماً ⚠️",
        ]
    },
    {
        "id": "strike", "name": "إضراب عام", "emoji": "🚫",
        "min_unhappy": 30,
        "effect": "production", "loss": (0, 0),
        "msgs": [
            "إضراب عام شلّ الإنتاج! لا حصاد هذه الجولة 🚫",
            "العمال أضربوا والمصانع توقفت! خسرت دورة حصاد 📉",
        ]
    },
]

POLITICAL_CHECK_INTERVAL = 60 * 15  # فحص كل 15 دقيقة

async def political_events_loop(app):
    """يفحص رضا الشعوب ويطلق أحداث سياسية عند انخفاضه"""
    await asyncio.sleep(120)
    while True:
        try:
            data    = load_data()
            changed = False
            for uid_s, p in data["players"].items():
                # تلاشي المهرجانات — -1 كل دورة فحص (15 دقيقة)
                if p.get("happiness_bonus", 0) > 0:
                    data["players"][uid_s]["happiness_bonus"] = max(0, p["happiness_bonus"] - 1)
                    changed = True

                happy = calc_happiness(data["players"][uid_s])

                # ===== انهيار كامل عند الرضا = 0 =====
                if happy == 0 and not p.get("occupied_by"):
                    last_collapse = p.get("last_collapse", 0)
                    if time.time() - last_collapse > 3600:  # مرة كل ساعة على الأكثر
                        # ثورة شعبية
                        army_loss = max(100, int(p["army"] * random.uniform(0.25, 0.45)))
                        gold_loss = max(500, int(p["gold"] * random.uniform(0.20, 0.35)))
                        data["players"][uid_s]["army"] = max(0, p["army"] - army_loss)
                        data["players"][uid_s]["gold"] = max(0, p["gold"] - gold_loss)
                        data["players"][uid_s]["last_collapse"] = time.time()
                        changed = True
                        try:
                            await app.bot.send_message(
                                chat_id=int(uid_s),
                                text=(
                                    f"{box_title('💥','انهيار شعبي!')}\n"
                                    f"رضا الشعب وصل *0%* — الفوضى تجتاح البلاد!\n\n"
                                    f"✊ *ثورة شعبية:* -{army_loss:,} جندي (فروا أو انضموا للثوار)\n"
                                    f"💸 *نهب الخزينة:* -{CUR}{gold_loss:,}\n\n"
                                    f"🆘 عليك رفع رضا الشعب فوراً!\n"
                                    f"اكتب `مهرجان شعبي` أو حسّن الأمن الغذائي"
                                ),
                                parse_mode="Markdown"
                            )
                        except: pass
                    continue  # لا أحداث سياسية إضافية لو انهار

                # فحص كل حدث
                for event in POLITICAL_EVENTS:
                    if happy >= event["min_unhappy"]:
                        continue
                    # احتمال 20% كل دورة فحص لو الشرط متحقق
                    if random.random() > 0.20:
                        continue
                    # منع تكرار نفس الحدث لنفس الدولة في آخر ساعة
                    last_key = f"last_event_{event['id']}"
                    if time.time() - p.get(last_key, 0) < 3600:
                        continue

                    msg_text = random.choice(event["msgs"])
                    loss_val = 0

                    if event["effect"] == "army":
                        pct = random.uniform(*event["loss"])
                        loss_val = max(50, int(p["army"] * pct))
                        data["players"][uid_s]["army"] = max(0, p["army"] - loss_val)
                        loss_txt = f"⚔️ خسرت *{loss_val:,}* جندي"

                    elif event["effect"] == "gold":
                        pct = random.uniform(*event["loss"])
                        loss_val = max(500, int(p["gold"] * pct))
                        data["players"][uid_s]["gold"] = max(0, p["gold"] - loss_val)
                        loss_txt = f"💸 خسرت *{CUR}{loss_val:,}*"

                    elif event["effect"] == "xp":
                        pct = random.uniform(*event["loss"])
                        loss_val = max(10, int(p.get("xp",0) * pct))
                        data["players"][uid_s]["xp"] = max(0, p.get("xp",0) - loss_val)
                        loss_txt = f"📉 خسرت *{loss_val:,}* XP"

                    elif event["effect"] == "production":
                        # حظر الحصاد مؤقتاً — يضع cooldown مزدوج
                        data["players"][uid_s]["last_tax"] = time.time() + TAX_COOLDOWN
                        loss_txt = f"⏳ *حصادك القادم ضاع!*"

                    data["players"][uid_s][last_key] = time.time()
                    changed = True

                    try:
                        await app.bot.send_message(
                            chat_id=int(uid_s),
                            text=(
                                f"{box_title(event['emoji'], event['name'] + '!')}\n"
                                f"📢 {msg_text}\n{sep()}\n"
                                f"{loss_txt}\n"
                                f"😡 رضا الشعب: *{happy}%* — حسّن أحوالهم قبل فوات الأوان!"
                            ),
                            parse_mode="Markdown"
                        )
                    except: pass
                    break  # حدث واحد فقط في كل دورة فحص للدولة

            if changed:
                save_data(data)
        except Exception as e:
            logging.error(f"Political events loop: {e}")
        await asyncio.sleep(POLITICAL_CHECK_INTERVAL)

async def harvest_loop(app):
    """loop التجارة فقط — يمسح الشحنات القديمة (+24 ساعة)
       الحصاد يدوي الآن بأمر جمع الضرائب كل 10 دقايق"""
    await asyncio.sleep(60)
    while True:
        try:
            async with _harvest_lock:
                data = load_data()
                now  = time.time()
                changed = False

                # مسح الشحنات المنتهية الصلاحية (+24 ساعة)
                old_len = len(data.get("shipments", []))
                data["shipments"] = [
                    s for s in data.get("shipments", [])
                    if now - s.get("sent_at", 0) < 86400
                ]
                if len(data["shipments"]) != old_len:
                    changed = True

                # مسح عروض السوق القديمة (+24 ساعة)
                old_mlen = len(data.get("market", []))
                data["market"] = [
                    m for m in data.get("market", [])
                    if now - m.get("created_at", now) < 86400
                ]
                if len(data["market"]) != old_mlen:
                    changed = True

                if changed:
                    save_data(data)
        except Exception as e:
            logging.error(f"Trade loop: {e}")
        await asyncio.sleep(300)  # كل 5 دقائق يتحقق

NEWS_CHANNEL_ID = int(os.environ.get("NEWS_CHANNEL_ID", "0"))  # ID القناة أو المجموعة
NEWS_INTERVAL   = 60 * 20   # كل 20 دقيقة

# تعليقات ساخرة على الدول الضعيفة
_WEAK_GOLD_COMMENTS = [
    "خزينتهم أفقر من جيب طالب ثانوي 💸",
    "الميزانية؟ أي ميزانية؟ 🦗",
    "يقدروا يشتروا فلافل بس 🧆",
    "اقتصادهم على وشك ما يتذكره أحد 📉",
    "حالتهم المالية تبكي بدون دموع 😢",
    "ما عندهم مصاري بس عندهم آمال 💫",
    "حساب الخزينة فيه صفر بس الفاصلة فاضية 🕳️",
    "لو باعوا الهوا ما كفّاهم 🌬️",
]
_WEAK_ARMY_COMMENTS = [
    "جيشهم يخوّف الحمام بس 🐦",
    "قواتهم المسلحة = هم + الجيران 👀",
    "يدافعون بالدعاء والأمل 🙏",
    "أمنهم القومي: 'إن شاء الله ما أحد يهاجمنا' 🤲",
    "جيشهم رقم نظري أكثر من كونه تهديد ⚠️",
    "خطتهم الدفاعية: الهروب بسرعة 🏃",
    "وزير الدفاع عنده جيش ورقي فقط 📄",
]
_HAPPY_HIGH = [
    "شعبهم راضي وفرحان — ربما لأنهم ما يعرفون الحقيقة 😅",
    "رضا الشعب عالي ومشبوه بعض الشيء 🕵️",
    "الناس سعيدة والحاكم نايم مرتاح 😴",
    "سعادة مشبوهة — مين يعطيهم البنج؟ 💉",
    "أسعد شعب في المنطقة، لحد دلوقتي 🌟",
]
_HAPPY_LOW = [
    "الشعب على وشك الثورة والحاكم يلعب ألعاب 🎮",
    "رضا الشعب في الحضيض — والحاكم مش داري 🙈",
    "لو كان في انتخابات ما فاز أحد 🗳️",
    "الناس في الشارع تتذمر والحاكم يبني قصور 🏰",
    "نسبة الرضا أقل من درجات امتحانات الفصل الأول 📝",
    "الحكومة تقول 'نعمل جهدنا'، والشعب يقول 'انتهى الجهد' 🤦",
]
_FOOD_LOW = [
    "الأمن الغذائي على الصفر — الأكل بيتوزع بالقرعة 🎰",
    "ناسهم جوعانة والمزارع فارغة 🌾😬",
    "القمح ما وصل والشعب بيأكل آمال 🍞❌",
    "وزارة التموين بتوزع وعود بدل طعام 📋",
    "الجوع وصل — والمزارع ما ردّت على الاتصالات 📵",
]

# ======= صيغ النشرات المتنوعة =======

def _news_classic(data, pvs, stats):
    """النشرة الكلاسيكية — مذيع رسمي ساخر"""
    anchor  = random.choice(["🎙️ أبو فراس الحربي","🎙️ الإعلامي كمال النشرة","🎙️ المذيع فيصل الخبر"])
    channel = random.choice(["📡 وكالة أنباء الشرق الأوسط","📺 قناة الخليج الساخرة","🗞️ جريدة الرمال","📻 إذاعة المنطقة"])
    sep = "─"*32
    richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting = stats

    intros = [
        "مساء الخير يا مشاهدين الكرام، وأنا عارف إنكم ما عندكم غيرنا 😤",
        "أهلاً بكم في النشرة اللي ما تفوتكم وإن فاتتكم ما خسرتوا شي 🙃",
        "تابعونا في نشرتنا المسائية، الأحداث كثيرة والعقل واحد 🧠",
        "هذي النشرة مدعومة من دموع الدول الضعيفة وضحكات القوية 😂",
        "عدنا إليكم بنشرة تتمنون ما سمعتوها — لكن ما في خيار 🎬",
    ]
    news = f"{sep}\n{channel}\n🎤 *{anchor}*\n{sep}\n\n_{random.choice(intros)}_\n\n"

    news += f"💰 *الاقتصاد:*\n"
    news += f"  🥇 {richest['country_name']}: {CUR}{richest['gold']:,} — 'ما قلنا ما قلنا 😎'\n"
    if poorest['country_name'] != richest['country_name']:
        news += f"  💀 {poorest['country_name']}: {CUR}{poorest['gold']:,} — {random.choice(_WEAK_GOLD_COMMENTS)}\n"
    news += f"\n⚔️ *الجيوش:*\n"
    news += f"  🦁 {strongest['country_name']}: {strongest['army']:,} جندي"
    news += f" {'— وهم في الميدان الآن 🔥' if strongest.get('at_war') else ' — بس ما استخدمهم لسه 💤'}\n"
    if weakest['country_name'] != strongest['country_name']:
        news += f"  🐣 {weakest['country_name']}: {weakest['army']:,} جندي — {random.choice(_WEAK_ARMY_COMMENTS)}\n"
    news += f"\n😤 *رضا الشعوب:*\n"
    if most_happy:
        news += f"  😊 {most_happy[0]} ({most_happy[1]}%) — {random.choice(_HAPPY_HIGH)}\n"
    if most_unhappy and most_unhappy[0] != (most_happy[0] if most_happy else ""):
        news += f"  😡 {most_unhappy[0]} ({most_unhappy[1]}%) — {random.choice(_HAPPY_LOW)}\n"
    if revolting:
        news += f"  🚨 على حافة الثورة: {', '.join(n for n,_ in revolting[:3])}\n"
    news += "\n"
    if hungry_states:
        news += f"🍽️ *تحذير غذائي:*\n  {', '.join(n for n,_ in hungry_states[:3])} — {random.choice(_FOOD_LOW)}\n\n"
    if at_war_list:
        news += f"🔥 *مناطق الصراع:*\n"
        w_cmts = ["المفاوضات فشلت، الرصاص ما فشل","السلام كان خياراً وما اختاروه","الكل خاسر بس ما أحد يعترف","ما في مفاوضات، في نيران فقط 🔥"]
        for name, enemies in at_war_list[:3]:
            news += f"  ⚔️ {name} تحارب {', '.join(enemies[:2])} — _{random.choice(w_cmts)}_\n"
        news += "\n"
    else:
        news += f"☮️ _{random.choice(['المنطقة هادية اليوم... مريبة الهدوء 🤔','لا حروب؟ هذا مشبوه 👁️','السلام سائد — إلى حين 🕊️','كل الجيوش في البيت تتأمل 🧘'])}_\n\n"
    if occupied:
        news += f"🏴 *دول تحت الاحتلال:*\n"
        for occ_name, by_who in occupied[:3]:
            news += f"  • {occ_name} تحت سيطرة {by_who} — _'ما نعلق'_ 😶\n"
        news += "\n"
    if orgs:
        news += f"🏛️ *الأحلاف:* {len(orgs)} حلف نشط — أبرزها: {', '.join(list(orgs.keys())[:2])}\n\n"
    news += f"{sep}\n📊 {total_players} دولة | {total_army:,} جندي | {CUR}{total_gold:,}\n"
    closings = [
        "🎙️ _'وهذا كان خبر آخر النهار — تصبحون على حرب'_",
        "🎙️ _'شكراً لمتابعتكم — وعذراً على الحقيقة'_",
        "🎙️ _'أبو فراس الحربي، وأنا لا أتحمل مسؤولية ما سمعتم'_",
        "🎙️ _'إلى اللقاء في النشرة القادمة — إن بقيت دولكم'_",
        "🎙️ _'نتمنى لكم ليلة هادئة — وهذا مجرد تمني'_",
    ]
    news += random.choice(closings)
    return news

def _news_gossip(data, pvs, stats):
    """صيغة نميمة وشائعات — مصدر مجهول"""
    richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting = stats
    sep = "─"*32

    sources = ["🤫 مصدر مطلع رفض الكشف عن هويته","👁️‍🗨️ شخصية مقربة من الدوائر الحاكمة","🕵️ محقق خاص طلب السرية التامة"]
    news = f"{sep}\n🗣️ *شائعات وهمسات — المنطقة الساخنة*\n{sep}\n"
    news += f"_المصدر: {random.choice(sources)}_\n\n"

    gossips = []

    # شائعة عن الأغنى
    gossips.append(random.choice([
        f"🤑 يُقال إن {richest['country_name']} تشتري جزيرة خاصة بـ{CUR}{richest['gold']//3:,}… مصادرنا لم تتأكد",
        f"💎 {richest['country_name']} وخزينتهم {CUR}{richest['gold']:,} — قيل إنهم لا ينامون من الخوف على فلوسهم",
        f"🏦 مصادر: {richest['country_name']} ترفض نشر ميزانيتها 'خوفاً من الحسد'",
    ]))

    # شائعة عن الأقوى عسكرياً
    if strongest['army'] > 500:
        gossips.append(random.choice([
            f"🪖 {strongest['country_name']} تجند كل يوم — الجيران يتساءلون: ليه؟ 👀",
            f"⚔️ {strongest['country_name']} لديها {strongest['army']:,} جندي — 'للدفاع فقط' بحسب بيانهم الرسمي",
            f"🛡️ قائد جيش {strongest['country_name']} قيل إنه ما ينام منذ أسبوع",
        ]))

    # شائعة عن الأضعف
    if poorest['country_name'] != richest['country_name']:
        gossips.append(random.choice([
            f"💸 {poorest['country_name']} يبحثون عن مستثمرين — الرد كان الصمت حتى الآن",
            f"📉 مسؤول في {poorest['country_name']} قال سراً: 'لو كان في تقاعد دولي كنا تقاعدنا'",
            f"🆘 {poorest['country_name']} تقدمت بطلب قرض جديد — رُفض للمرة الثالثة",
        ]))

    # شائعة عن حرب أو سلام
    if at_war_list:
        name, enemies = random.choice(at_war_list)
        gossips.append(random.choice([
            f"🔥 الحرب بين {name} و{enemies[0] if enemies else '؟'} — 'مفاوضات سرية على وشك الانهيار' حسب مصادرنا",
            f"💣 طرف في حرب {name} يطلب وساطة — لكنه يطلب السلاح في نفس الوقت 🤦",
            f"🕊️ مصدر: {name} تدرس وقف إطلاق النار — 'بعد معركة واحدة أخيرة'",
        ]))
    else:
        gossips.append("🕊️ المنطقة كلها هادئة اليوم — مصادرنا قلقة من هذا الهدوء المريب 😰")

    # شائعة عن محتلة
    if occupied:
        occ_name, by_who = random.choice(occupied)
        gossips.append(random.choice([
            f"🏴 {occ_name} تحت {by_who} — مصادر: 'الأهالي يتساءلون متى ينتهي هذا'",
            f"😶 ممثل {occ_name} السابق رفض التعليق على وضع بلده 'حفاظاً على سلامته'",
        ]))

    # اختار 3-4 شائعات عشوائية
    random.shuffle(gossips)
    for i, g in enumerate(gossips[:4], 1):
        news += f"*{i}.* {g}\n\n"

    closings = [
        "_'المصدر طلب عدم الإفصاح — وأبو فراس يحترم الخصوصية أحياناً'_ 🤫",
        "_'هذه الشائعات غير مؤكدة — لكنها ممتعة جداً'_ 😄",
        "_'نتحفظ على صحة هذه المعلومات — لكننا ننشرها على أي حال'_ 📢",
    ]
    news += f"{sep}\n{random.choice(closings)}"
    return news

def _news_report(data, pvs, stats):
    """صيغة تقرير إحصائي جاف ساخر"""
    richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting = stats
    sep = "─"*32

    news = f"{sep}\n📊 *التقرير الإحصائي الدوري — وكالة الأرقام الصادمة*\n{sep}\n\n"

    # إحصائيات مرتبة
    news += f"🌍 *إجمالي المنطقة:*\n"
    news += f"  👥 الدول: {total_players} | 💰 الثروة: {CUR}{total_gold:,} | ⚔️ الجنود: {total_army:,}\n"
    avg_gold = total_gold // total_players if total_players else 0
    avg_army = total_army // total_players if total_players else 0
    news += f"  📈 متوسط الثروة/دولة: {CUR}{avg_gold:,} | متوسط الجيش: {avg_army:,}\n\n"

    # ترتيب الثروة
    news += f"💰 *ترتيب الثروة (أعلى 3):*\n"
    ranked_gold = sorted(pvs, key=lambda x: x.get("gold",0), reverse=True)
    medals = ["🥇","🥈","🥉"]
    for i, p in enumerate(ranked_gold[:3]):
        pct = int(p['gold']/total_gold*100) if total_gold else 0
        news += f"  {medals[i]} {p['country_name']}: {CUR}{p['gold']:,} ({pct}% من ثروة المنطقة)\n"
    news += "\n"

    # أكبر الجيوش
    ranked_army = sorted(pvs, key=lambda x: x.get("army",0), reverse=True)
    news += f"⚔️ *أكبر الجيوش (أعلى 3):*\n"
    for i, p in enumerate(ranked_army[:3]):
        status = "🔥 في حرب" if p.get("at_war") else "💤 خامل"
        news += f"  {medals[i]} {p['country_name']}: {p['army']:,} جندي — {status}\n"
    news += "\n"

    # مقارنة الأمن الغذائي
    if happy_data:
        news += f"🌾 *الأمن الغذائي:*\n"
        food_sorted = sorted(pvs, key=lambda x: calc_food_security(x), reverse=True)
        best_food  = food_sorted[0]
        worst_food = food_sorted[-1]
        news += f"  ✅ الأفضل: {best_food['country_name']} ({calc_food_security(best_food)}%)\n"
        if worst_food['country_name'] != best_food['country_name']:
            news += f"  ❌ الأسوأ: {worst_food['country_name']} ({calc_food_security(worst_food)}%)"
            news += f" — {random.choice(_FOOD_LOW)}\n"
        news += "\n"

    # الحروب بأرقام
    if at_war_list:
        news += f"🔥 *إحصاء الصراعات:*\n"
        news += f"  {len(at_war_list)} دولة في حالة حرب — ما يعادل {int(len(at_war_list)/total_players*100)}% من المنطقة 😬\n\n"

    # المحتلة
    if occupied:
        news += f"🏴 *دول محتلة:* {len(occupied)} ({', '.join(n for n,_ in occupied[:3])})\n\n"

    closings = [
        "📊 _'الأرقام لا تكذب — الكذب للسياسيين'_",
        "📋 _'هذا التقرير أعدّه فريق لا ينام ولا يتقاضى راتباً منذ شهرين'_",
        "📈 _'للاستفسار عن منهجية التقرير: لا أحد يرد'_",
    ]
    news += f"{sep}\n{random.choice(closings)}"
    return news

def _news_interview(data, pvs, stats):
    """صيغة مقابلة مباشرة مفبركة مع زعيم عشوائي"""
    richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting = stats
    sep = "─"*32

    # اختار شخصية للمقابلة
    subject = random.choice(pvs)
    is_rich    = subject["country_name"] == richest["country_name"]
    is_poor    = subject["country_name"] == poorest["country_name"]
    is_strong  = subject["country_name"] == strongest["country_name"]
    is_war     = bool(subject.get("at_war"))
    is_occ     = bool(subject.get("occupied_by"))

    interviewers = ["🎤 مراسلنا أمجد الديك","🎤 الصحفية رنا الخبر","🎤 المراسل الميداني سامي الجبهة"]
    news = f"{sep}\n🎙️ *مقابلة خاصة — {subject['country_name']}*\n{sep}\n"
    news += f"_{random.choice(interviewers)} يلتقي بممثل {subject['country_name']}_\n\n"

    qa_pairs = []

    if is_rich:
        qa_pairs += [
            ("❓ سر ثروتكم؟", f"*الممثل:* 'العمل الجاد والتوفيق... والجيران الضعاف 😅'"),
            ("❓ كيف تشعر بامتلاك {CUR}{gold:,}؟".format(CUR=CUR, gold=subject['gold']), "*الممثل:* 'ثقيل على الكتف، لكن نتحمل'"),
        ]
    if is_poor:
        qa_pairs += [
            ("❓ ما خططكم الاقتصادية؟", f"*الممثل:* 'نعمل على... نعمل على... الأمر قيد الدراسة 📋'"),
            ("❓ متى ستتحسن الأوضاع؟", "*الممثل:* 'قريباً إن شاء الله — وهذا وعد رسمي' 🤞"),
        ]
    if is_strong:
        qa_pairs += [
            ("❓ لماذا هذا الجيش الضخم؟", f"*الممثل:* 'للدفاع فقط، والدفاع أحياناً يكون هجوماً' 😏"),
            ("❓ هل تخطط للتوسع؟", "*الممثل:* 'كلمة توسع قاسية — نقول: نشر الاستقرار'"),
        ]
    if is_war:
        enemy = subject['at_war'][0] if subject.get('at_war') else "أحد"
        qa_pairs += [
            (f"❓ ما موقفكم من الحرب مع {enemy}؟", f"*الممثل:* 'هم بدأوا — هذا موقفنا الثابت والنهائي'"),
            ("❓ هل تفكرون في السلام؟", "*الممثل:* 'السلام جميل... بعد الانتصار 😤'"),
        ]
    if is_occ:
        qa_pairs += [
            ("❓ كيف أوضاعكم في ظل الاحتلال؟", "*الممثل:* '...' _(صمت طويل)_"),
        ]
    if not qa_pairs:
        qa_pairs = [
            ("❓ كيف أحوالكم؟", f"*الممثل:* 'تمام، والحمد لله، وسائرون على الخطة'"),
            ("❓ ما رأيكم في المنطقة؟", "*الممثل:* 'المنطقة فيها طاقات كبيرة... وتوترات أكبر 😬'"),
            ("❓ رسالة للجيران؟", f"*الممثل:* 'السلام عليكم — وعليكم السلام' _(ابتسامة دبلوماسية)_"),
        ]

    random.shuffle(qa_pairs)
    for q, a in qa_pairs[:3]:
        news += f"{q}\n{a}\n\n"

    closings = [
        "🎤 _'شكراً لممثل {name}... الذي غادر قبل انتهاء المقابلة'_".format(name=subject['country_name']),
        "🎤 _'انتهت المقابلة فجأة بعد السؤال الأخير'_",
        "🎤 _'الممثل رفض الإجابة على 4 أسئلة إضافية'_",
    ]
    news += f"{sep}\n{random.choice(closings)}"
    return news

def _news_flash(data, pvs, stats):
    """صيغة أخبار عاجلة متعددة — بريق وإثارة"""
    richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting = stats
    sep = "─"*32

    news = f"{sep}\n🚨 *عاجل || عاجل || عاجل*\n📡 _شريط أخبار المنطقة — لحظة بلحظة_\n{sep}\n\n"

    flashes = []

    # اقتصادية
    flashes.append(random.choice([
        f"💰 *عاجل:* {richest['country_name']} تسجل رقماً قياسياً في الثروة — المواطنون لم يلاحظوا فرقاً",
        f"📉 *عاجل:* وزير مالية {poorest['country_name']} يعقد مؤتمراً صحفياً 'للتفاؤل' — الخزينة لم تتعاون",
        f"🏦 *عاجل:* البنك الدولي يصدر تحذيراً جديداً بشأن المنطقة — المعنيون تجاهلوه",
    ]))

    # عسكرية
    flashes.append(random.choice([
        f"⚔️ *عاجل:* {strongest['country_name']} تجري مناورات عسكرية 'دفاعية' — الجيران يحملون حقائبهم",
        f"🪖 *عاجل:* {weakest['country_name']} تعلن رفع جاهزية جيشها — من 0% إلى 3%",
        f"🛡️ *عاجل:* وزير دفاع مجهول يؤكد: 'جيشنا جاهز لأي طارئ' — دون تحديد ما هو الطارئ",
    ]))

    # حروب أو سلام
    if at_war_list:
        name, enemies = random.choice(at_war_list)
        flashes.append(random.choice([
            f"🔥 *عاجل:* اشتباكات مستمرة بين {name} و{enemies[0] if enemies else '؟'} — لا إشارة لوقف النار",
            f"💣 *عاجل:* {name} تؤكد 'تقدماً ميدانياً' — الطرف الآخر يقول نفس الشيء",
            f"🕊️ *عاجل:* وسيط دولي يحاول التفاوض في أزمة {name} — فقد هاتفه منذ ساعة",
        ]))
    else:
        flashes.append(random.choice([
            "🕊️ *عاجل:* لا حروب مسجلة — المراسلون الحربيون يلعبون ورق في الفندق",
            "😴 *عاجل:* هدوء تام في المنطقة — المحللون قلقون من هذا الهدوء",
        ]))

    # اجتماعية
    if most_unhappy and most_unhappy[1] < 30:
        flashes.append(f"😡 *عاجل:* رضا شعب {most_unhappy[0]} وصل {most_unhappy[1]}% — مصادر: 'الحكومة تتجاهل'")
    elif most_happy:
        flashes.append(f"😊 *عاجل:* {most_happy[0]} الأسعد في المنطقة — خبراء يتساءلون عن السبب")

    # محتلة
    if occupied:
        occ_name, by_who = random.choice(occupied)
        flashes.append(f"🏴 *عاجل:* {occ_name} لا تزال تحت سيطرة {by_who} — لم يتغير شيء")

    # إضافي عشوائي
    extras = [
        f"🌾 *عاجل:* تقرير: {int(sum(calc_food_security(p) for p in pvs)/len(pvs))}% متوسط الأمن الغذائي — الخبراء يعلقون بـ'مقبول للأسف'",
        f"📊 *عاجل:* إجمالي الجنود في المنطقة: {total_army:,} — لا أحد يعرف لماذا كل هذا العدد",
        f"🏛️ *عاجل:* {len(orgs)} أحلاف نشطة في المنطقة — الولاء يتغير كل فترة",
    ]
    flashes.append(random.choice(extras))

    random.shuffle(flashes)
    for f in flashes[:5]:
        news += f"▪️ {f}\n\n"

    closings = [
        "📡 _'متابعة مستمرة — شريط الأخبار لا ينام'_",
        "🚨 _'نعود بالمستجدات فور وقوعها أو اختراعها'_",
        "📺 _'هذه الأخبار دقيقة حسب علمنا الناقص'_",
    ]
    news += f"{sep}\n{random.choice(closings)}"
    return news

def _build_news(data):
    """يبني نشرة إخبارية من صيغ متنوعة عشوائياً"""
    players = data.get("players", {})
    if not players:
        return None

    pvs = list(players.values())
    ranked_gold  = sorted(pvs, key=lambda x: x.get("gold",0),        reverse=True)
    ranked_army  = sorted(pvs, key=lambda x: x.get("army",0),        reverse=True)
    ranked_terr  = sorted(pvs, key=lambda x: x.get("territories",1), reverse=True)
    ranked_xp    = sorted(pvs, key=lambda x: x.get("xp",0),          reverse=True)
    richest   = ranked_gold[0];  poorest   = ranked_gold[-1]
    strongest = ranked_army[0];  weakest   = ranked_army[-1]
    biggest   = ranked_terr[0];  advanced  = ranked_xp[0]
    at_war_list = [(p["country_name"], p["at_war"]) for p in pvs if p.get("at_war")]
    occupied    = [(p["country_name"], p.get("occupied_by","؟")) for p in pvs if p.get("occupied_by")]
    orgs        = data.get("organizations", {})
    total_gold  = sum(p.get("gold",0)  for p in pvs)
    total_army  = sum(p.get("army",0)  for p in pvs)
    total_players = len(pvs)
    happy_data  = sorted([(p["country_name"], calc_happiness(p), calc_food_security(p)) for p in pvs], key=lambda x: x[1])
    most_unhappy  = happy_data[0]  if happy_data else None
    most_happy    = happy_data[-1] if happy_data else None
    hungry_states = [(n,f) for n,h,f in happy_data if f < 30]
    revolting     = [(n,h) for n,h,_ in happy_data if h < 25]

    stats = (richest,poorest,strongest,weakest,biggest,advanced,at_war_list,occupied,orgs,
             total_gold,total_army,total_players,happy_data,most_unhappy,most_happy,hungry_states,revolting)

    # اختار صيغة عشوائية مع أوزان
    formats = [
        (_news_classic,   35),   # الكلاسيكية — الأكثر شيوعاً
        (_news_gossip,    25),   # شائعات
        (_news_report,    15),   # تقرير إحصائي
        (_news_interview, 15),   # مقابلة
        (_news_flash,     10),   # أخبار عاجلة
    ]
    funcs   = [f for f,w in formats]
    weights = [w for f,w in formats]
    chosen  = random.choices(funcs, weights=weights, k=1)[0]
    return chosen(data, pvs, stats)

async def inactivity_loop(app):
    """كل 6 ساعات — يعاقب الدول الخاملة"""
    await asyncio.sleep(300)
    while True:
        try:
            data = load_data()
            now  = time.time()
            changed = False
            for uid_s, p in data["players"].items():
                # تجاهل الدول المحتلة
                if p.get("occupied_by"): continue
                last = p.get("last_active", p.get("last_tax", 0))
                inactive_secs = now - last
                if inactive_secs < INACTIVITY_DECAY: continue
                army = p.get("army", 0)
                if army <= 10: continue
                # تآكل 5% كل دورة (6 ساعات)
                decay = max(1, int(army * INACTIVITY_RATE))
                data["players"][uid_s]["army"] = max(10, army - decay)
                changed = True
                # تحذير لو أول مرة تتجاوز 3 أيام
                if INACTIVITY_WARNING < inactive_secs < INACTIVITY_WARNING + 21600:
                    try:
                        days = int(inactive_secs // 86400)
                        await app.bot.send_message(chat_id=int(uid_s),
                            text=f"⚠️ *تحذير خمول — {p['country_name']}*\n{sep()}\n"
                                 f"غايب منذ *{days} أيام*!\n"
                                 f"جيشك بيتآكل {int(INACTIVITY_RATE*100)}% كل 6 ساعات\n"
                                 f"الجنود يفرون والفساد ينتشر 🪖💸\n"
                                 f"ارجع للعبة قبل ما تخسر كل شيء!", parse_mode="Markdown")
                    except: pass
            if changed:
                save_data(data)
        except Exception as e:
            logging.error(f"Inactivity loop: {e}")
        await asyncio.sleep(60 * 60 * 6)  # كل 6 ساعات

async def news_loop(app):
    """نشرة إخبارية كل 20 دقيقة — القناة تُحدَّد بأمر 'تفعيل النشرة'"""
    await asyncio.sleep(60)
    while True:
        try:
            data       = load_data()
            channel_id = data.get("news_channel_id", 0)
            if channel_id != 0:
                text = _build_news(data)
                if text:
                    await app.bot.send_message(
                        chat_id=channel_id,
                        text=text,
                        parse_mode="Markdown"
                    )
        except Exception as e:
            logging.error(f"News loop: {e}")
        await asyncio.sleep(NEWS_INTERVAL)

# ==================== معالج الرسائل ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text:
        text = update.message.text.strip()
    elif update.message.caption:
        text = update.message.caption.strip()
    else:
        return  # صورة بدون كابشن — تجاهل

    uid   = update.effective_user.id
    uname = update.effective_user.first_name
    data  = load_data()
    clean_old_requests(data)
    ntext = norm(text)  # نسخة منقحة للمقارنة

    # ======= فحص التجميد — الأدمن مستثنى =======
    if not is_admin(uid):
        player_data = data.get("players", {}).get(str(uid), {})
        if player_data.get("frozen"):
            await update.message.reply_text(
                "🧊 *دولتك مجمّدة من الإدارة*\n"
                "لا يمكنك استخدام أي أوامر حالياً.\n"
                "تواصل مع الأدمن للاستفسار.", parse_mode="Markdown")
            return

    # ======= منع الأوامر في الخاص =======
    chat_type = update.effective_chat.type  # "private" | "group" | "supergroup" | "channel"
    PRIVATE_ALLOWED = {
        "حاله دولتي", "دولتي", "وضعي",
        "جيشي", "قواتي", "تسليحي", "عتادي",
        "كودي", "الكود",
        "ديوني", "قروضي", "ديون",
        "امبراطوريتي", "دولي", "اراضيي", "ممتلكاتي",
        "مساعده", "اوامر", "help", "meg", "meg!",
        "احصائيات اللعبه", "احصائيات", "إحصائيات اللعبه", "إحصائيات",
        "المتصدرين", "الترتيب",
        "قائمه الدول", "الدول",
        "المضائق", "حاله المضائق",
    }
    if chat_type == "private" and not is_admin(uid) and ntext not in PRIVATE_ALLOWED:
        await update.message.reply_text(
            "⚠️ الأوامر تشتغل في الجروب فقط!\n"
            "هذا الخاص للإشعارات فقط 🔔\n\n"
            "💡 يمكنك هنا: `دولتي` | `جيشي` | `ديوني` | `دولي`",
            parse_mode="Markdown")
        return

    # ======= أدمن: انشاء دولة بعلم =======
    if is_admin(uid) and update.message.photo and ntext.startswith("دوله "):
        parts = text.split()
        if len(parts) < 4:
            await update.message.reply_text("الصيغة:\n`دولة [المنطقة] [اسم] [الكود]`", parse_mode="Markdown"); return
        code   = parts[-1].upper()
        region = parts[1]
        cname  = " ".join(parts[2:-1])
        if code not in data["pending_codes"]:
            await update.message.reply_text(f"الكود `{code}` مش موجود.", parse_mode="Markdown"); return
        if region not in AVAILABLE_REGIONS:
            await update.message.reply_text(f"'{region}' مش في القائمة."); return
        for _, p in data["players"].items():
            if p["region"] == region:
                await update.message.reply_text(f"'{region}' محجوزة."); return
        photo  = update.message.photo[-1]
        ff     = await context.bot.get_file(photo.file_id)
        await ff.download_to_drive(os.path.join(FLAGS_DIR, f"{region}.png"))
        pid    = data["pending_codes"].pop(code)
        pl     = new_player(region, cname, pid)
        res    = REGION_RESOURCES.get(region, [])
        data["players"][str(pid)] = pl
        save_data(data)
        await update.message.reply_text(
            f"✅ تم!\n🏳️ *{cname}* ← {region}\n🔑 `{pl['player_code']}`", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=pid,
                text=f"{box_title('🎊','مرحباً بك في اللعبة!')}\n"
                     f"🏳️ *{cname}* | 🗺️ {region}\n"
                     f"🌍 الموارد: {', '.join(res) if res else 'لا يوجد'}\n{sep()}\n"
                     f"💰 مثاقيل: 1,000 | ⚔️ جيش: 100\n📖 اكتب *مساعدة*", parse_mode="Markdown")
        except: pass
        return

    # ======= تعديل العلم — اللاعب يرفع علمه الجديد =======
    if update.message.photo and ntext in ["تعديل علمي","غير علمي","تحديث علمي","علم جديد"]:
        p = get_player(data, uid)
        if not p:
            await update.message.reply_text("❌ مش مسجل — انشئ دولة أولاً."); return
        region    = p["region"]
        flag_path = os.path.join(FLAGS_DIR, f"{region}.png")
        backup    = os.path.join(FLAGS_DIR, f"{region}_original.png")
        try:
            import shutil
            if os.path.exists(flag_path) and not os.path.exists(backup):
                shutil.copy2(flag_path, backup)
            photo = update.message.photo[-1]
            ff    = await context.bot.get_file(photo.file_id)
            await ff.download_to_drive(flag_path)
            save_data(data)
            # ابحث عن المستعمرات والمحتلات — الخريطة بتعرض علم المحتل عليهم
            my_name = p["country_name"]
            affected = []
            for _, op in data["players"].items():
                ctrl = op.get("occupied_by") or op.get("colony_of")
                if ctrl == my_name:
                    affected.append(op["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)",""))
            extra_txt = ""
            if affected:
                extra_txt = f"\n🏴 علمك يظهر أيضاً على: {', '.join(affected[:5])}"
            await update.message.reply_text(
                f"🏳️ *تم تحديث علم {p['country_name']}!*\n{sep()}\n"
                f"علمك الجديد سيظهر على الخريطة ✅"
                f"{extra_txt}",
                parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Flag update error: {e}")
            await update.message.reply_text("❌ حصل خطأ أثناء رفع العلم، جرب مرة ثانية.")
        return

    # ======= انشاء دولة =======
    if ntext == "انشاء دوله":
        if get_player(data, uid):
            await update.message.reply_text(f"⚠️ عندك دولة بالفعل."); return
        existing = next((c for c,v in data["pending_codes"].items() if v==uid), None)
        if existing:
            await update.message.reply_text(f"⏳ كودك: `{existing}`", parse_mode="Markdown"); return
        code = generate_code()
        while code in data["pending_codes"]: code = generate_code()
        data["pending_codes"][code] = uid; save_data(data)
        await update.message.reply_text(
            f"{box_title('🎮','طلب انشاء دولة')}\n\nاهلاً *{uname}*! ✅\n\n"
            f"🔑 كودك:\n┌─────────────┐\n│  `{code}`  │\n└─────────────┘\n\n"
            f"ابعت الكود للادمن!", parse_mode="Markdown")
        return

    # ======= كودي =======
    if ntext in ["كودي","الكود"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        await update.message.reply_text(f"🔑 كودك:\n```\n{p['player_code']}```", parse_mode="Markdown")
        return

    # ======= كوده — رداً على رسالة شخص =======
    if ntext in ["كوده","كودها","كودهم"]:
        replied = update.message.reply_to_message
        if not replied:
            await update.message.reply_text("↩️ ردّ على رسالة الشخص اللي تريد كوده."); return
        target_uid = replied.from_user.id
        tp = get_player(data, target_uid)
        if not tp:
            await update.message.reply_text(f"❌ *{replied.from_user.first_name}* مش عنده دولة.", parse_mode="Markdown"); return
        await update.message.reply_text(
            f"🔑 *كود {tp['country_name']}*\n```\n{tp['player_code']}```\n"
            f"💡 استخدمه في التحويل والمستعمرات والهدايا",
            parse_mode="Markdown")
        return

    # ======= دولته — رداً على رسالة شخص =======
    if ntext in ["دولته","دولتها","دولتهم","حالته","وضعه"]:
        replied = update.message.reply_to_message
        if not replied:
            await update.message.reply_text("↩️ ردّ على رسالة الشخص اللي تريد بيانات دولته."); return
        target_uid = replied.from_user.id
        tp = get_player(data, target_uid)
        if not tp:
            await update.message.reply_text(f"❌ *{replied.from_user.first_name}* مش عنده دولة.", parse_mode="Markdown"); return
        # بيانات الدولة المستهدفة
        xp   = tp.get("xp", 0)
        lvl  = get_level(xp)
        nxt  = get_next_level(xp)
        nxt_txt = f"{nxt['xp']-xp:,} XP للمستوى القادم" if nxt else "🏆 أعلى مستوى!"
        facs = tp.get("facilities", {})
        crops_p = tp.get("crops", {})
        infra   = tp.get("infrastructure", 0)
        capital = tp.get("capital", "غير محددة")
        traitor = " 🗡️خائن" if tp.get("traitor") else ""
        # أعضاء الأحلاف المشتركة بدل allies
        orgs_tmp = data.get("organizations", {})
        allies_list = list({m for ov in orgs_tmp.values() if tp["country_name"] in ov["members"] for m in ov["members"] if m != tp["country_name"]})
        allies_txt  = (", ".join(allies_list[:3]) + (f" (+{len(allies_list)-3})" if len(allies_list)>3 else "")) if allies_list else "—"
        wars_list   = tp.get("at_war", [])
        wars_txt    = (", ".join(wars_list[:3])) if wars_list else "سلام ☮️"
        status_txt  = ""
        if tp.get("occupied_by"):    status_txt = f"🏴 محتلة بواسطة: {tp['occupied_by']}"
        elif tp.get("colony_of"):    status_txt = f"🏴 مستعمرة لـ: {tp['colony_of']}"
        elif tp.get("protected_by"): status_txt = f"🛡️ محمية بواسطة: {tp['protected_by']}"
        pop   = calc_population(tp)
        happy = calc_happiness(tp)
        food  = calc_food_security(tp)
        xp_bar = progress_bar(xp - lvl["xp"], (nxt["xp"] - lvl["xp"]) if nxt else 1)
        msg = (
            f"{box_title(lvl['emoji'], tp['country_name'] + traitor)}\n"
            f"🏅 *{lvl['name']}* — Lv.{lvl['level']}\n"
            f"⭐ `{xp_bar}` {xp:,} XP  ↳ {nxt_txt}\n"
            f"{sep()}\n"
            f"📍 *{tp['region']}*  🏛️ {capital}  🏗️ Lv.{infra}\n"
            f"💰 الخزينة: *{CUR}{tp['gold']:,}*\n"
            f"⚔️ الجيش:  *{tp['army']:,}* جندي\n"
            f"🗺️ الأراضي: *{tp['territories']}* منطقة\n"
            f"🏭 منشآت: {len(facs)}  🌾 مزارع: {len(crops_p)}\n"
            f"{sep()}\n"
            f"👥 {pop}M نسمة  😊 {happy}%  🍽️ {food}%\n"
            f"🤝 الأحلاف: {allies_txt}\n"
            f"⚔️ الحروب: {wars_txt}\n"
        )
        if status_txt:
            msg += f"{sep()}\n{status_txt}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return


    if ntext in ["حاله دولتي","دولتي","وضعي"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        xp   = p.get("xp",0)
        lvl  = get_level(xp)
        nxt  = get_next_level(xp)
        nxt_txt = f"{nxt['xp']-xp:,} XP للمستوى القادم" if nxt else "🏆 اعلى مستوى!"
        cooldown = get_tax_cooldown(data, p.get("region",""))
        left = cooldown - (time.time()-p.get("last_tax",0))
        if left <= 0:
            tax = "✅ جاهزة"
        elif cooldown == STRAIT_TAX_COOLDOWN:
            strait_name = next((sn for sn,s in get_strait_status(data).items()
                                if s.get("blocked") and p.get("region","") in s.get("affects",[])
                                and not any(
                                    p.get("country_name","") in ov["members"] and s.get("blocked_by","") in ov["members"]
                                    for ov in data.get("organizations",{}).values()
                                )), "")
            tax = f"🔴 مضيق {strait_name} مغلق — {int(left//60):02d}:{int(left%60):02d}" if strait_name else f"⏳ {int(left//60):02d}:{int(left%60):02d}"
        else:
            tax = f"⏳ {int(left//60):02d}:{int(left%60):02d}"
        facs = p.get("facilities",{})
        crops_p = p.get("crops",{})
        res     = REGION_RESOURCES.get(p["region"],[])
        capital = p.get("capital","غير محددة")
        infra   = p.get("infrastructure",0)
        traitor = " 🗡️خائن" if p.get("traitor") else ""
        xp_bar  = progress_bar(xp-lvl["xp"], (nxt["xp"]-lvl["xp"]) if nxt else 1)

        # حساب الاقتصاد
        num_proj_s = sum(facs.values()) + sum(crops_p.values())
        base_t     = p.get("territories",1)*500 + 1000
        econ       = base_t + num_proj_s*300 + infra*1500 + sum(
            RESOURCE_FACILITIES.get(r,{}).get("amount",0)*c*CROP_SELL_PRICE.get(r,0)
            for r,c in facs.items()
        ) + sum(
            FARM_CROPS.get(cr,{}).get("amount",0)*cn*CROP_SELL_PRICE.get(cr,0)
            for cr,cn in crops_p.items()
        )
        total_tons = sum(
            FARM_CROPS.get(c,{}).get("amount",0)*n*(1.5 if c in REGION_PREFERRED_CROPS.get(p["region"],[]) else 1)
            for c,n in crops_p.items()
        )
        pop   = calc_population(p)
        food  = calc_food_security(p)
        health= calc_health(p)
        happy = calc_happiness(p)

        # ===== بناء النصوص بحد أقصى =====
        # المنشآت — كل منشأة في سطر (تجاهل المفاتيح غير الموجودة)
        fac_lines = [
            f"  {RESOURCE_FACILITIES[r]['emoji']} {RESOURCE_FACILITIES[r]['name']}: ×{c}"
            for r, c in facs.items() if r in RESOURCE_FACILITIES
        ]
        fac_txt = "\n".join(fac_lines) or "  لا يوجد"

        # المزارع
        crop_lines = [
            f"  {FARM_CROPS[c]['emoji']} {FARM_CROPS[c]['name']}: ×{n}"
            for c, n in crops_p.items() if c in FARM_CROPS
        ]
        crops_txt = "\n".join(crop_lines) or "  لا يوجد"

        # القروض
        loans_active = p.get("loans",[])
        loans_txt = "\n".join(
            f"  🏦 {ln['name']}: {CUR}{ln['due']:,} بعد {ln['remaining_cycles']} دورة"
            for ln in loans_active
        ) or "  لا يوجد"

        # التحالفات والحروب — اختصار لو كثيرة
        orgs_tmp2 = data.get("organizations", {})
        allies_list = list({m for ov in orgs_tmp2.values() if p["country_name"] in ov["members"] for m in ov["members"] if m != p["country_name"]})
        wars_list   = p.get("at_war",[])
        allies_txt  = (", ".join(allies_list[:5]) + (f" (+{len(allies_list)-5})" if len(allies_list)>5 else "")) if allies_list else "—"
        wars_txt    = (", ".join(wars_list[:5])   + (f" (+{len(wars_list)-5})"   if len(wars_list)>5   else "")) if wars_list   else "سلام ☮️"

        msg1 = (
            f"{box_title(lvl['emoji'], p['country_name'] + traitor)}\n"
            f"🏅 *{lvl['name']}* — المستوى {lvl['level']}\n"
            f"⭐ `{xp_bar}` {xp:,} XP\n"
            f"   ↳ {nxt_txt}\n"
            f"{sep()}\n"
            f"📍 *{p['region']}*  🏛️ {capital}  🏗️ بنية Lv.{infra}\n"
            f"🌍 الموارد: {', '.join(res) or '—'}\n"
            f"{sep()}\n"
            f"💰 الخزينة:   *{CUR}{p['gold']:,}*\n"
            f"📈 دخل/دورة: ~*{CUR}{econ:,}*\n"
            f"⚔️ الجيش:    *{p['army']:,}* جندي\n"
            f"🗺️ الأراضي:  *{p['territories']}* منطقة\n"
            f"{sep()}\n"
            f"⏱️ الحصاد: {tax}\n"
            f"🏦 القروض:\n{loans_txt}"
        )
        # مزايا المستوى
        my_perks = get_perks(xp)
        PERK_NAMES = {
            "تجنيد_مخفض":      "💰 تجنيد مخفض 5%",
            "وزير_دفاع":        "🛡️ وزير دفاع (+8% دفاع)",
            "دبلوماسية_متقدمة": "📜 دبلوماسية متقدمة",
            "مخابرات":          "🕵️ جهاز مخابرات",
            "هيمنة_اقتصادية":   "💎 هيمنة اقتصادية (+10% ضرائب)",
            "قوة_عظمى":         "⚡ قوة عظمى (+15% هجوم ودفاع)",
        }
        if my_perks:
            perks_txt = " | ".join(PERK_NAMES.get(pk, pk) for pk in my_perks)
            msg1 += f"\n{sep()}\n✨ *مزايا المستوى:*\n{perks_txt}"

        msg2 = (
            f"{box_title('🏭', 'المنشآت والمزارع')}\n"
            f"*{p['country_name']}*\n"
            f"{sep()}\n"
            f"🏭 المنشآت — {len(facs)} نوع:\n{fac_txt}\n"
            f"{sep()}\n"
            f"🌾 المزارع — {len(crops_p)} نوع | إنتاج: {int(total_tons)} طن/دورة:\n{crops_txt}"
        )

        msg3 = (
            f"{box_title('👥', 'السكان والأحوال')}\n"
            f"*{p['country_name']}* — 🧑‍🤝‍🧑 *{pop}M* نسمة\n"
            f"{sep()}\n"
            f"🌾 الأمن الغذائي:\n"
            f"   {status_emoji(food)} `{pbar(food)}` {food}%\n"
            f"❤️ الصحة:\n"
            f"   {status_emoji(health)} `{pbar(health)}` {health}%\n"
            f"😊 رضا الشعب:\n"
            f"   {status_emoji(happy)} `{pbar(happy)}` {happy}%\n"
        )
        # تفاصيل الرضا
        food_b  = calc_food_security(p) // 4
        gold_b  = min(15, p.get("gold",0) // 2000)
        infra_b = p.get("infrastructure",0) * 3
        wins_b  = min(20, p.get("wars_won",0) * 4)
        fest_b  = p.get("happiness_bonus",0)
        war_pen = p.get("wars_lost",0) * 6
        dis_pen = p.get("disasters_hit",0) * 2
        debt_pen= len([l for l in p.get("loans",[]) if not l.get("paid")]) * 3
        occ_pen = 40 if p.get("occupied_by") else 0
        details = []
        if food_b:   details.append(f"🌾 غذاء +{food_b}")
        if gold_b:   details.append(f"💰 ثروة +{gold_b}")
        if infra_b:  details.append(f"🏗️ بنية +{infra_b}")
        if wins_b:   details.append(f"⚔️ انتصارات +{wins_b}")
        if fest_b:   details.append(f"🎉 مهرجانات +{fest_b}")
        if war_pen:  details.append(f"😔 هزائم -{war_pen}")
        if dis_pen:  details.append(f"🌍 كوارث -{dis_pen}")
        if debt_pen: details.append(f"🏦 ديون -{debt_pen}")
        if occ_pen:  details.append(f"🏴 احتلال -{occ_pen}")
        if details:
            msg3 += "   _(" + " | ".join(details) + ")_\n"
        if happy <= 20:
            msg3 += f"   ⚠️ *خطر! الشعب على وشك الثورة!*\n"
        elif happy <= 40:
            msg3 += f"   ⚠️ الشعب غير راضٍ — اكتب `مهرجان شعبي`\n"
        msg3 += (
            f"{sep()}\n"
            f"🤝 الأحلاف:  {allies_txt}\n"
            f"⚔️ الحروب:   {wars_txt}"
        )
        if p.get("protected_by"):
            msg3 += f"\n🛡️ محمية بواسطة: *{p['protected_by']}*"
        if p.get("protects"):
            protects_txt = "، ".join(p["protects"][:3])
            msg3 += f"\n🛡️ تحمي: *{protects_txt}*"

        # إرسال آمن
        for msg in [msg1, msg2, msg3]:
            await safe_md(update.message, msg)
        return

    # ======= بناء منشاة صناعية =======
    if ntext in ["بناء منشاه","بناء منشأة","انشئ منشاه","انشئ منشأة"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "بناء منشأة")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        region = p["region"]
        infra  = p.get("infrastructure", 0)

        # كل المنشآت — مرتبة حسب infra_req
        all_facs = sorted(RESOURCE_FACILITIES.items(), key=lambda x: x[1].get("infra_req",0))

        table = ""
        kbd   = []
        prev_tier = -1
        for fac_id, fc in all_facs:
            infra_req = get_facility_infra_req(fac_id, region)
            locked    = infra < infra_req
            tier      = fc.get("infra_req", 0)
            if tier != prev_tier:
                tier_label = f"🔓 مجاني" if tier == 0 else f"🏗️ بنية Lv.{tier}"
                table += f"\n{sep('-',20)}\n{tier_label}\n"
                prev_tier = tier
            owned = p.get("facilities", {}).get(fac_id, 0)
            owned_txt = f" (عندك {owned})" if owned else ""
            if fc.get("amount", 0) > 0:
                prod_txt = f"+{fc['amount']} {fac_id}/دورة"
            else:
                prod_txt = fc.get("special", "")[:35]
            if locked:
                table += f"  🔒 {fc['emoji']} {fc['name']}: {fc['base_cost']:,}¥ — يحتاج Lv.{infra_req}\n"
                kbd.append([InlineKeyboardButton(f"🔒 {fc['name']} (بنية Lv.{infra_req})", callback_data="cancel")])
            else:
                table += f"  ✅ {fc['emoji']} {fc['name']}{owned_txt}: {fc['base_cost']:,}¥ ← {prod_txt}\n"
                kbd.append([InlineKeyboardButton(f"{fc['emoji']} {fc['name']} {fc['base_cost']:,}¥", callback_data=f"build_{fac_id}")])

        kbd.append([InlineKeyboardButton("❌ الغاء", callback_data="cancel")])
        await update.message.reply_text(
            f"🏗️ *بناء منشأة — {p['country_name']}*\n"
            f"🏗️ بنيتك التحتية: Lv.*{infra}*\n"
            f"{table}",
            reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
        return

    # ======= بناء مزرعة =======
    if ntext in ["بناء مزرعه","ابني مزرعه","انشئ مزرعه"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "بناء مزرعة")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        region    = p["region"]
        infra     = p.get("infrastructure", 0)
        preferred = REGION_PREFERRED_CROPS.get(region,[])
        sorted_c  = preferred + [c for c in ALL_CROPS if c not in preferred]

        # حساب الحد الأقصى
        max_farms   = get_max_farms(infra)
        total_farms = sum(p.get("crops",{}).values())

        table = ""
        kbd   = []
        row   = []
        for crop in sorted_c:
            fc   = FARM_CROPS[crop]
            cost = get_farm_cost(data, crop)
            star = "⭐" if crop in preferred else ""
            real_amt = int(fc["amount"]*1.5) if crop in preferred else fc["amount"]
            table += f"{fc['emoji']}{star} {crop}: {cost:,}¥ → {real_amt}طن/حقل/دورة\n"
            row.append(InlineKeyboardButton(f"{fc['emoji']}{star}{crop} {cost:,}¥", callback_data=f"farm_{crop}"))
            if len(row)==2: kbd.append(row); row=[]
        if row: kbd.append(row)
        kbd.append([InlineKeyboardButton("❌ الغاء", callback_data="cancel")])
        pref_txt  = f"⭐ أنسب لمنطقتك: {', '.join(preferred)}" if preferred else "تقدر تزرع أي محصول"
        limit_txt = f"🌾 مزارعك: *{total_farms}/{max_farms}*"
        if total_farms >= max_farms:
            await update.message.reply_text(
                f"❌ وصلت الحد الأقصى!\n{limit_txt}\n\n💡 ابن *بنية تحتية* عشان تزيد الحد\n"
                f"Lv.{infra+1} ← {get_max_farms(infra+1)} مزرعة",
                parse_mode="Markdown"); return
        await update.message.reply_text(
            f"🌾 *اختار المحصول:*\n{limit_txt}\n{pref_txt}\n{sep()}\n{table}\n⭐ = إنتاج أعلى 50%",
            reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
        return

    # ======= جمع الحصاد يدوياً =======
    if ntext in ["جمع الضرائب","اجمع الضرائب","حصاد","جمع موارد","احصد"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        cooldown = get_tax_cooldown(data, p.get("region",""))
        left = cooldown - (time.time()-p.get("last_tax",0))
        if left > 0:
            mins = int(left // 60)
            secs = int(left % 60)
            if cooldown == STRAIT_TAX_COOLDOWN:
                # اكتشف أي مضيق
                strait_name = ""
                for sn, s in get_strait_status(data).items():
                    if s.get("blocked") and p.get("region","") in s.get("affects",[]):
                        strait_name = sn; break
                await update.message.reply_text(
                    f"🔴 مضيق *{strait_name}* مغلق — انتظر *{mins:02d}:{secs:02d}* دقيقة",
                    parse_mode="Markdown"); return
            else:
                await update.message.reply_text(
                    f"⏳ استنى *{mins:02d}:{secs:02d}* دقيقة!", parse_mode="Markdown"); return
        async with _harvest_lock:
            data2 = load_data()
            p2    = get_player(data2, uid)
            cooldown2 = get_tax_cooldown(data2, p2.get("region",""))
            left2 = cooldown2 - (time.time()-p2.get("last_tax",0))
            if left2 > 0:
                await update.message.reply_text("⏳ تم الحصاد للتو!"); return
            await do_harvest(context.application, uid, p2, data2)
            save_data(data2)
        return

    # ======= حصاد مستعمرة =======
    if ntext.startswith("احصد مستعمره ") or ntext.startswith("حصاد مستعمره "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        col_name = ntext.split("مستعمره",1)[1].strip()
        col_uid, col_p = None, None
        for tuid, tp in data["players"].items():
            clean = norm(tp.get("country_name","").replace(" (مستعمرة)","").replace(" (محتلة)",""))
            if clean == norm(col_name) or norm(tp.get("region","")) == norm(col_name):
                col_uid, col_p = tuid, tp; break
        if not col_p:
            await update.message.reply_text(f"❌ مش لاقي مستعمرة اسمها '{col_name}'."); return
        if col_p.get("colony_of") != p["country_name"]:
            await update.message.reply_text(f"❌ *{col_name}* مش مستعمرتك.", parse_mode="Markdown"); return
        col_last = col_p.get("colony_last_harvest",0)
        col_cooldown = get_tax_cooldown(data, col_p.get("region",""))
        col_left = col_cooldown - (time.time()-col_last)
        if col_left > 0:
            await update.message.reply_text(f"⏳ حصاد المستعمرة جاهز بعد *{int(col_left//60):02d}:{int(col_left%60):02d}*", parse_mode="Markdown"); return
        total_gold, terr_income, prod_lines = calc_colony_harvest(col_p)
        data["players"][str(uid)]["gold"] += total_gold
        data["players"][col_uid]["colony_last_harvest"] = time.time()
        save_data(data)
        prod_txt = "\n".join(prod_lines) if prod_lines else "  لا يوجد إنتاج"
        await update.message.reply_text(
            f"🏴 *حصاد مستعمرة {col_p['country_name']}*\n{sep()}\n"
            f"{prod_txt}\n  🗺️ دخل الأراضي: +{terr_income:,}¥\n{sep()}\n"
            f"💰 المضاف: *+{CUR}{total_gold:,}*\n"
            f"💰 رصيدك: *{CUR}{p['gold']+total_gold:,}*",
            parse_mode="Markdown"); return

    # ======= تحويل محتلة → مستعمرة =======
    if ntext.startswith("استعمر "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        col_name = ntext.replace("استعمر","").strip()
        col_uid, col_p = None, None
        for tuid, tp in data["players"].items():
            clean = norm(tp.get("country_name","").replace(" (محتلة)",""))
            if clean == norm(col_name) or norm(tp.get("region","")) == norm(col_name):
                col_uid, col_p = tuid, tp; break
        if not col_p:
            await update.message.reply_text(f"❌ مش لاقي دولة '{col_name}'."); return
        if col_p.get("occupied_by") != p["country_name"]:
            await update.message.reply_text(f"❌ *{col_name}* مش محتلة بواسطتك.", parse_mode="Markdown"); return
        if col_p.get("colony_of"):
            await update.message.reply_text(f"❌ *{col_name}* مستعمرة بالفعل!", parse_mode="Markdown"); return
        original_name = col_p["country_name"].replace(" (محتلة)","")
        data["players"][col_uid]["country_name"]        = f"{original_name} (مستعمرة)"
        data["players"][col_uid]["colony_of"]           = p["country_name"]
        data["players"][col_uid]["occupied_by"]         = None  # مش محتلة بعد الآن
        data["players"][col_uid]["colony_last_harvest"] = 0
        save_data(data)
        await update.message.reply_text(
            f"🏴 *تم الاستعمار!*\n{sep()}\n"
            f"*{original_name}* أصبحت مستعمرة لـ *{p['country_name']}*\n"
            f"🌾 `احصد مستعمرة {original_name}` — لحصاد مواردها\n"
            f"🕊️ `تحرير {original_name}` — لتحريرها\n"
            f"🎁 `اهدي مستعمرة {original_name} الى [كود]` — لنقلها",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(col_uid),
                text=f"🏴 *دولتك أصبحت مستعمرة!*\n{sep()}\n"
                     f"*{p['country_name']}* استعمر *{original_name}*\n"
                     f"كل مواردك ومزارعك تحت سيطرتهم!", parse_mode="Markdown")
        except: pass
        return

    # ======= إهداء مستعمرة =======
    if ntext.startswith("اهدي مستعمره "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        rest = ntext.replace("اهدي مستعمره","").strip()
        if " الى " not in rest:
            await update.message.reply_text("❌ الصيغة:\n`اهدي مستعمرة [اسم] الى [كود]`", parse_mode="Markdown"); return
        parts      = rest.split(" الى ",1)
        col_name   = parts[0].strip()
        target_code= parts[1].strip()
        col_uid, col_p = None, None
        for tuid, tp in data["players"].items():
            clean = norm(tp.get("country_name","").replace(" (مستعمرة)",""))
            if clean == norm(col_name) or norm(tp.get("region","")) == norm(col_name):
                col_uid, col_p = tuid, tp; break
        if not col_p:
            await update.message.reply_text(f"❌ مش لاقي مستعمرة '{col_name}'."); return
        if col_p.get("colony_of") != p["country_name"]:
            await update.message.reply_text(f"❌ *{col_name}* مش مستعمرتك.", parse_mode="Markdown"); return
        recv_uid, recv_p = find_by_code(data, target_code)
        if not recv_p:
            await update.message.reply_text(f"❌ مش لاقي لاعب بالكود `{target_code}`.", parse_mode="Markdown"); return
        if recv_uid == str(uid):
            await update.message.reply_text("❌ مينفعش تهدي لنفسك!"); return
        original_name = col_p["country_name"].replace(" (مستعمرة)","")
        col_terr = col_p.get("territories", 1)
        # نقل الأراضي
        data["players"][str(uid)]["territories"]  = max(1, p.get("territories",1) - col_terr)
        data["players"][recv_uid]["territories"]  = recv_p.get("territories",1) + col_terr
        data["players"][col_uid]["colony_of"]     = recv_p["country_name"]
        data["players"][col_uid]["country_name"]  = f"{original_name} (مستعمرة)"
        save_data(data)
        await update.message.reply_text(
            f"🎁 *تم الإهداء!*\n{sep()}\nأهديت مستعمرة *{original_name}* لـ *{recv_p['country_name']}*",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(recv_uid),
                text=f"🎁 *هدية!*\n{sep()}\n*{p['country_name']}* أهداك مستعمرة *{original_name}*!",
                parse_mode="Markdown")
        except: pass
        return

    # ======= سوق الأسلحة =======
    if ntext in ["سوق", "سوق الاسلحه", "متجر الاسلحه", "السلاح", "اسلحه"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        infra = p.get("infrastructure", 0)
        lvl   = get_level(p.get("xp", 0))
        weaps = p.get("weapons", {})
        msg   = f"{box_title('🏪','سوق الأسلحة')}\n💰 خزينتك: *{CUR}{p['gold']:,}*\n{sep()}\n\n"
        prev_cat = None
        for wid, w in WEAPONS.items():
            if w.get("basic"): continue
            req    = WEAPON_REQUIREMENTS.get(wid, {})
            fac_req = req.get("facility")
            fac_locked = fac_req and not p.get("facilities",{}).get(fac_req, 0)
            locked = (req.get("infra", 0) > infra or req.get("level", 0) > lvl["level"] or fac_locked)
            owned  = weaps.get(wid, 0)
            cat    = w.get("category", "")
            cat_label = WEAPON_MARKET_CATEGORIES.get(cat, cat)
            if cat != prev_cat:
                msg += f"\n{cat_label}\n{sep('-',24)}\n"
                prev_cat = cat
            if locked:
                lock_why = ""
                if req.get("infra", 0) > infra:        lock_why += f"بنية Lv.{req['infra']} "
                if req.get("level", 0) > lvl["level"]: lock_why += f"مستوى {req['level']} "
                if fac_locked:
                    fc_name = RESOURCE_FACILITIES.get(fac_req,{}).get("name", fac_req)
                    lock_why += f"{fc_name}"
                msg += f"  🔒 {w['emoji']} {w['name']}\n     _{lock_why.strip()}_\n"
            else:
                owned_txt = f" ✅({owned:,})" if owned else ""
                if w.get("army_scale"):
                    army      = max(1, p.get("army", 1))
                    cost_est  = army * w["cost_per_soldier"]
                    owned_txt = f" ✅(مجهز)" if weaps.get(wid, 0) else ""
                    cost_fmt  = f"{w['cost_per_soldier']}¥/جندي ≈ {cost_est:,}¥ لجيشك ({army:,})"
                    buy_hint  = f"`شراء {wid}`"
                elif w.get("unit"):
                    cost_fmt = f"{w['cost']:,}¥/وحدة"
                    buy_hint = f"`شراء {wid} [عدد]`"
                elif w.get("one_use"):
                    base_cost = w['cost']
                    has_reactor = bool(p.get("facilities",{}).get("مفاعل",0))
                    if wid in ("قنبلة_ذرية","قنبلة_هيدروجينية") and has_reactor:
                        cost_fmt = f"~~{base_cost:,}~~ {base_cost//2:,}¥ (خصم 50% ☢️)"
                    else:
                        cost_fmt = f"{base_cost:,}¥"
                    buy_hint = f"`شراء {wid}`"
                else:
                    cost_fmt = f"{w.get('cost',0):,}¥"
                    buy_hint = f"`شراء {wid}`"
                msg += f"  {w['emoji']} *{w['name']}*{owned_txt}\n"
                msg += f"     💰 {CUR}{cost_fmt} | _{w['desc']}_\n"
                msg += f"     🛒 {buy_hint}\n"
        msg += f"\n{sep()}\n💡 مثال: `شراء بندقية_هجوم` | `شراء دبابات 50` | `شراء قنبلة_ذرية`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= شراء أسلحة =======
    if ntext.startswith("شراء "):
        if ntext == "شراء اسلحه":
            await update.message.reply_text("🏪 اكتب `سوق` لعرض سوق الأسلحة الكامل!", parse_mode="Markdown")
            return
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return

        # استخراج السلاح والعدد من النص الأصلي (مش ntext) للحفاظ على ة و_
        parts_orig = text.strip().split()
        # أزل كلمة "شراء" الأولى
        parts_orig = parts_orig[1:] if parts_orig else []
        wid = parts_orig[0] if parts_orig else ""
        qty = 1
        if len(parts_orig) >= 2:
            try: qty = max(1, int(parts_orig[1]))
            except: pass

        # لو wid مش موجود — جرب norm() للبحث
        if wid not in WEAPONS:
            wid_norm = norm(wid)
            for k in WEAPONS:
                if norm(k) == wid_norm:
                    wid = k
                    break

        if wid not in WEAPONS:
            await update.message.reply_text(
                f"❌ سلاح '{wid}' مش موجود.\n💡 اكتب `سوق` لعرض سوق الأسلحة",
                parse_mode="Markdown"); return

        w     = WEAPONS[wid]
        infra = p.get("infrastructure", 0)
        lvl   = get_level(p.get("xp", 0))
        req   = WEAPON_REQUIREMENTS.get(wid, {})
        if req.get("infra", 0) > infra:
            await update.message.reply_text(
                f"🔒 محتاج بنية تحتية مستوى *{req['infra']}*\nعندك: {infra}",
                parse_mode="Markdown"); return
        if req.get("level", 0) > lvl["level"]:
            await update.message.reply_text(
                f"🔒 محتاج مستوى *{req['level']}*\nأنت مستوى: {lvl['level']}",
                parse_mode="Markdown"); return
        if req.get("facility"):
            fac_needed = req["facility"]
            if not p.get("facilities", {}).get(fac_needed, 0):
                fc_name = RESOURCE_FACILITIES.get(fac_needed, {}).get("name", fac_needed)
                await update.message.reply_text(
                    f"🔒 محتاج *{fc_name}* عشان تشتري {w['name']}!\n"
                    f"ابن المفاعل النووي أولاً (بنية Lv.10)",
                    parse_mode="Markdown"); return

        # ===== أسلحة الجيش (army_scale) — تجهيز كل الجيش =====
        if w.get("army_scale"):
            army = max(1, p.get("army", 1))
            cost = army * w["cost_per_soldier"]
            if p["gold"] < cost:
                await update.message.reply_text(
                    f"❌ تجهيز جيشك ({army:,} جندي) يكلف *{CUR}{cost:,}*\nعندك *{CUR}{p['gold']:,}*",
                    parse_mode="Markdown"); return
            data["players"][str(uid)]["gold"] -= cost
            data["players"][str(uid)].setdefault("weapons", {})[wid] = army
            leveled_up, new_lvl = add_xp(data, uid, 100)
            save_data(data)
            msg = (f"{w['emoji']} *تجهيز الجيش!*\n{sep()}\n"
                   f"*{w['name']}* لـ {army:,} جندي\n"
                   f"_{w['desc']}_\n{sep()}\n"
                   f"💰 -{CUR}{cost:,} | الرصيد: *{CUR}{p['gold']-cost:,}*\n"
                   f"💡 لو جيشك كبر اشتر مرة ثانية لتحديث التجهيز")
            if leveled_up: msg += f"\n🎊 {new_lvl['name']} {new_lvl['emoji']}"
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # ===== أسلحة عددية (unit) =====
        if w.get("unit"):
            cost_total  = w["cost"] * qty
            army_gain   = w.get("army_bonus_each", 0) * qty
            dmg_gain    = w.get("damage_bonus_each", 0) * qty
            def_gain    = w.get("defense_reduce_each", 0) * qty
            if p["gold"] < cost_total:
                await update.message.reply_text(
                    f"❌ {qty} × {w['emoji']} {w['name']} = *{CUR}{cost_total:,}*\nعندك *{CUR}{p['gold']:,}*",
                    parse_mode="Markdown"); return
            cur = p.get("weapons", {}).get(wid, 0)
            data["players"][str(uid)]["gold"] -= cost_total
            data["players"][str(uid)].setdefault("weapons", {})[wid] = cur + qty
            if army_gain:
                data["players"][str(uid)]["army"] += army_gain
            leveled_up, new_lvl = add_xp(data, uid, qty * 10)
            save_data(data)
            msg = (f"{w['emoji']} *تم الشراء!*\n{sep()}\n"
                   f"{qty} × {w['name']} (إجمالي: {cur+qty})\n"
                   f"_{w['desc']}_\n{sep()}\n"
                   f"💰 -{CUR}{cost_total:,} | الرصيد: *{CUR}{p['gold']-cost_total:,}*")
            if army_gain:  msg += f"\n⚔️ +{army_gain:,} جندي"
            if dmg_gain:   msg += f"\n💥 +{dmg_gain*100:.1f}% ضرر"
            if def_gain:   msg += f"\n🛡️ +{def_gain*100:.1f}% اختراق دفاع"
            if leveled_up: msg += f"\n🎊 {new_lvl['name']} {new_lvl['emoji']}"
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        # ===== أسلحة عادية (مرة واحدة) =====
        if w.get("one_use") and p.get("weapons", {}).get(wid, 0) >= 1:
            await update.message.reply_text(
                f"⚠️ عندك {w['emoji']} {w['name']} بالفعل!",
                parse_mode="Markdown"); return
        cost = w["cost"]
        # المفاعل النووي يخفض سعر القنابل 50%
        if wid in ("قنبلة_ذرية","قنبلة_هيدروجينية"):
            reactors = p.get("facilities",{}).get("مفاعل", 0)
            if reactors > 0:
                cost = cost // 2
        if p["gold"] < cost:
            await update.message.reply_text(
                f"❌ محتاج *{CUR}{cost:,}*. عندك *{CUR}{p['gold']:,}*.",
                parse_mode="Markdown"); return
        cur = p.get("weapons", {}).get(wid, 0)
        data["players"][str(uid)]["gold"] -= cost
        data["players"][str(uid)].setdefault("weapons", {})[wid] = cur + 1
        if w.get("army_bonus", 0):
            data["players"][str(uid)]["army"] += w["army_bonus"]
        leveled_up, new_lvl = add_xp(data, uid, 100)
        save_data(data)
        msg = (f"{w['emoji']} *تم الشراء!*\n{sep()}\n"
               f"*{w['name']}*\n_{w['desc']}_\n{sep()}\n"
               f"💰 -{CUR}{cost:,} | الرصيد: *{CUR}{p['gold']-cost:,}*")
        if w.get("army_bonus", 0): msg += f"\n⚔️ +{w['army_bonus']:,} جندي"
        if leveled_up: msg += f"\n🎊 {new_lvl['name']} {new_lvl['emoji']}"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= استخدام أسلحة نووية =======
    if ntext.startswith("اضرب "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        nuke_type = None
        if "قنبلة_هيدروجينية" in text or "هيدروجينية" in text:
            nuke_type = "قنبلة_هيدروجينية"
        elif "قنبلة_ذرية" in text or "ذرية" in text:
            nuke_type = "قنبلة_ذرية"
        if not nuke_type:
            await update.message.reply_text(
                "❌ الصيغة:\n`اضرب [دولة] بقنبلة_ذرية`\n`اضرب [دولة] بقنبلة_هيدروجينية`",
                parse_mode="Markdown"); return
        tname = (ntext.replace("اضرب", "")
                     .replace("بقنبلة_هيدروجينية", "").replace("بقنبلة_ذرية", "")
                     .replace("بهيدروجينية", "").replace("بذرية", "").strip())
        if not p.get("weapons", {}).get(nuke_type, 0):
            w = WEAPONS[nuke_type]
            await update.message.reply_text(
                f"❌ مش عندك {w['emoji']} {w['name']}!\n💡 اشتريها من `شراء اسلحة`",
                parse_mode="Markdown"); return
        if p.get("nuke_banned", 0) > 0:
            await update.message.reply_text(
                f"🚫 محظور دولياً! استنى *{p['nuke_banned']}* معركة قبل النووي.",
                parse_mode="Markdown"); return
        tuid, tp = find_by_name(data, tname)
        if not tp:
            await update.message.reply_text(f"❌ مش لاقي دولة '{tname}'."); return
        if tuid == str(uid):
            await update.message.reply_text("❌ مينفعش تضرب نفسك!"); return
        # فحص الأحلاف المشتركة
        shared_org = None
        for org_name, org in data.get("organizations",{}).items():
            if p["country_name"] in org["members"] and tp["country_name"] in org["members"]:
                shared_org = org_name
                break
        if shared_org:
            await update.message.reply_text(
                f"🏛️ *لا يمكن الضرب!*\n{sep()}\n"
                f"أنت و*{tp['country_name']}* أعضاء في حلف *{shared_org}* 🤝",
                parse_mode="Markdown"); return
        w           = WEAPONS[nuke_type]
        destroyed   = int(tp["army"] * w["nuke_power"])
        new_army    = max(0, tp["army"] - destroyed)
        data["players"][tuid]["army"] = new_army
        data["players"][str(uid)]["weapons"][nuke_type] = 0
        # الحظر — إلا لو عنده مفاعل نووي
        has_reactor = bool(p.get("facilities", {}).get("مفاعل", 0))
        ban_turns = 0
        if not has_reactor:
            if nuke_type == "قنبلة_هيدروجينية":
                ban_turns = 5
            else:
                ban_turns = 3
            data["players"][str(uid)]["nuke_banned"] = ban_turns
        occupied_txt = ""
        if w.get("occupy") and new_army == 0:
            clean_name = tp['country_name'].replace(" (محتلة)","").replace(" (مستعمرة)","")
            data["players"][tuid]["country_name"] = f"{clean_name} (محتلة)"
            data["players"][tuid]["occupied_by"]  = p["country_name"]
            data["players"][str(uid)]["territories"] += tp.get("territories", 1)
            data["players"][tuid]["territories"]   = 0
            looted_gold = transfer_conquest(data, uid, tuid)
            occupied_txt = (
                f"\n🏴 *احتللت {tp['country_name']} بالكامل!*\n"
                f"💰 نهبت: {looted_gold:,}¥\n"
                f"🌾 مزارعها ومنشآتها صارت لك!"
            )
        leveled_up, new_lvl = add_xp(data, uid, 500)
        save_data(data)
        if has_reactor:
            ban_txt = "\n☢️ مفاعلك النووي منع الحظر الدولي!"
        elif ban_turns > 0:
            ban_txt = f"\n⚠️ محظور دولياً لـ{ban_turns} معارك!"
        else:
            ban_txt = ""
        await update.message.reply_text(
            f"{box_title(w['emoji'],'ضربة نووية!')}\n"
            f"أطلقت *{w['name']}* على *{tp['country_name']}*!\n"
            f"💀 دُمِّر: *{destroyed:,}* جندي ({int(w['nuke_power']*100)}%)\n"
            f"🏳️ جيش العدو المتبقي: *{new_army:,}*"
            f"{occupied_txt}{ban_txt}",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=int(tuid),
                text=f"☢️ *هجوم نووي!*\n{sep()}\n"
                     f"*{p['country_name']}* ضربك بـ{w['name']}!\n"
                     f"💀 خسرت *{destroyed:,}* جندي!",
                parse_mode="Markdown")
        except: pass
        return

    # ======= بناء بنية تحتية =======
    if ntext in ["بناء بنيه تحتيه","بنيه تحتيه"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "بناء بنية")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        infra = p.get("infrastructure",0)
        cost  = 10000 + infra*8000
        if p["gold"] < cost:
            await update.message.reply_text(f"❌ محتاج {cost:,}¥. عندك {p['gold']:,}."); return
        data["players"][str(uid)]["gold"]           -= cost
        data["players"][str(uid)]["infrastructure"]  = infra+1
        leveled_up, new_lvl = add_xp(data, uid, 150)
        save_data(data)
        benefits = {1:"تقدر تبني مصنع صلب ⚙️",2:"تقدر تبني مصافي نفط/غاز 🛢️",3:"تقدر تبني بنك مركزي 🏦"}
        msg = (f"🏗️ *البنية التحتية Lv.{infra+1}!*\n{sep()}\n"
               f"💰 {cost:,}¥ | ✅ {benefits.get(infra+1,'انتاج +1 لكل المنشآت')}\n⭐+150 XP")
        if leveled_up: msg += f"\n🎊 *ترقية!* {new_lvl['name']} {new_lvl['emoji']}"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= العاصمة =======
    if ntext.startswith("العاصمه "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        capital = ntext.replace("العاصمه","").strip()
        if not capital: await update.message.reply_text("❌ مثال: العاصمة القاهرة"); return
        data["players"][str(uid)]["capital"] = capital; save_data(data)
        await update.message.reply_text(f"🏛️ *{capital}* عاصمة *{p['country_name']}* ✅", parse_mode="Markdown")
        return

    # ======= المضائق =======
    if ntext in ["المضائق","حاله المضائق"]:
        straits = get_strait_status(data)
        msg = f"{box_title('⚓','حالة المضائق')}\n\n"
        for name, s in straits.items():
            if s.get("blocked"):
                status = f"🔴 *مغلق* — {s['blocked_by']}"
            else:
                status = "🟢 *مفتوح*"
            controllers = STRAITS[name]["controller"]
            affects_txt = " | ".join(s["affects"])
            msg += (
                f"🌊 *{name}*\n"
                f"   {status}\n"
                f"   🎮 المتحكمون: {', '.join(controllers)}\n"
                f"   ⚠️ المتأثرون: {affects_txt}\n"
                f"{sep2()}\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    for action in ["اغلق","افتح"]:
        if ntext.startswith(f"{action} مضيق "):
            p = get_player(data, uid)
            if not p: await update.message.reply_text("❌ مش مسجل."); return
            sname = ntext.replace(f"{action} مضيق","").strip()
            if sname not in STRAITS:
                await update.message.reply_text(f"❌ المضائق: {', '.join(STRAITS.keys())}"); return

            controllers = STRAITS[sname]["controller"]
            if p["region"] not in controllers:
                await update.message.reply_text(f"❌ دولتك مش من المتحكمين في مضيق {sname}."); return

            # لو في أكثر من متحكم — الأقوى عسكرياً هو المسيطر
            if len(controllers) > 1:
                # دور على اللاعبين اللي عندهم نفس المنطقة
                armies = {}
                for puid, pp in data["players"].items():
                    if pp.get("region") in controllers:
                        armies[pp["region"]] = (pp.get("army", 0), pp["country_name"])

                # أقوى جيش
                dominant_region = max(armies, key=lambda r: armies[r][0]) if armies else p["region"]
                if p["region"] != dominant_region:
                    dom_name = armies[dominant_region][1]
                    await update.message.reply_text(
                        f"❌ *{dom_name}* تسيطر على مضيق {sname} بجيش أقوى!\n"
                        f"جيشك: {p['army']:,} | جيشهم: {armies[dominant_region][0]:,}",
                        parse_mode="Markdown"); return

            blocked = (action == "اغلق")
            data["straits"][sname] = {"blocked": blocked, "blocked_by": p["country_name"] if blocked else None}
            save_data(data)

            # أرسل إشعار للدول المتأثرة فقط (ماعدا أعضاء الحلف)
            affected_regions = STRAITS[sname]["affects"]
            blocker_orgs = {on for on, ov in data.get("organizations",{}).items()
                            if p["country_name"] in ov["members"]}
            if blocked:
                affected_names = []
                for puid, pp in data["players"].items():
                    if pp.get("region") not in affected_regions: continue
                    # عضو في حلف مشترك — ما يتأثرش
                    in_same_org = any(
                        pp["country_name"] in data["organizations"].get(on,{}).get("members",[])
                        for on in blocker_orgs
                    )
                    if in_same_org:
                        try:
                            await context.bot.send_message(
                                chat_id=int(puid),
                                text=f"🟡 *مضيق {sname} أُغلق*\n{sep()}\n"
                                     f"أغلقه حليفك *{p['country_name']}*\n"
                                     f"✅ أنت في حلف مشترك — ضرائبك غير متأثرة",
                                parse_mode="Markdown")
                        except: pass
                        continue
                    affected_names.append(pp["country_name"])
                    try:
                        await context.bot.send_message(
                            chat_id=int(puid),
                            text=f"🔴 *مضيق {sname} أُغلق!*\n{sep()}\n"
                                 f"أغلقه *{p['country_name']}*\n"
                                 f"⏳ جمع ضرائبك أصبح *15 دقيقة* بدل 10",
                            parse_mode="Markdown")
                    except: pass
                effect = (f"⏳ الدول المتأثرة ({len(affected_names)}): "
                          f"{', '.join(affected_names[:5]) or 'لا يوجد'}\n"
                          f"ضرائبهم أصبحت 15 دقيقة!")
            else:
                # إشعار بفتح المضيق
                for puid, pp in data["players"].items():
                    if pp.get("region") in affected_regions:
                        try:
                            await context.bot.send_message(
                                chat_id=int(puid),
                                text=f"🟢 *مضيق {sname} فُتح!*\n{sep()}\n"
                                     f"فتحه *{p['country_name']}*\n"
                                     f"⏳ جمع ضرائبك عاد لـ *10 دقايق*",
                                parse_mode="Markdown")
                        except: pass
                effect = "✅ حركة الشحن والضرائب عادت للطبيعي (10 دقايق)."

            icon = "🔴" if blocked else "🟢"
            await update.message.reply_text(
                f"{icon} *مضيق {sname} {'مغلق' if blocked else 'مفتوح'}!*\n{sep()}\n{effect}",
                parse_mode="Markdown")
            return

    # ======= تحرير دولة محتلة (يرجعها لصاحبها) =======
    if ntext.startswith("تحرير "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        target_name = ntext.replace("تحرير","").strip()
        # دور على الدولة المحتلة
        found_uid, found_p = None, None
        for tuid, tp in data["players"].items():
            if (norm(tp.get("country_name","").replace(" (محتلة)","").replace(" (مستعمرة)","")) == norm(target_name) or
                norm(tp.get("region","")) == norm(target_name)):
                found_uid, found_p = tuid, tp
                break
        if not found_p:
            await update.message.reply_text(f"❌ مش لاقي دولة اسمها '{target_name}'."); return
        my_name    = p["country_name"]
        is_colony  = found_p.get("colony_of")  == my_name
        is_occupied = found_p.get("occupied_by") == my_name
        # fallback — قارن بالاسم النظيف لو الاسم اتغير
        if not is_colony and not is_occupied:
            my_clean = norm(my_name.replace(" (محتلة)","").replace(" (مستعمرة)",""))
            is_colony   = norm((found_p.get("colony_of")  or "").replace(" (محتلة)","").replace(" (مستعمرة)","")) == my_clean
            is_occupied = norm((found_p.get("occupied_by") or "").replace(" (محتلة)","").replace(" (مستعمرة)","")) == my_clean
        if not is_colony and not is_occupied:
            owner = found_p.get("occupied_by") or found_p.get("colony_of") or "لا أحد"
            await update.message.reply_text(
                f"❌ *{target_name}* مش تحت سيطرتك.\n"
                f"تحت سيطرة: {owner}", parse_mode="Markdown"); return
        # استرداد الأراضي من المنتصر
        occupied_terr = found_p.get("territories", 0)
        data["players"][str(uid)]["territories"] = max(1,
            data["players"][str(uid)]["territories"] - occupied_terr)
        # تحرير الدولة
        original_name = found_p["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        data["players"][found_uid]["country_name"] = original_name
        data["players"][found_uid]["occupied_by"]  = None
        data["players"][found_uid]["colony_of"]    = None
        data["players"][found_uid]["territories"]  = max(1, occupied_terr)
        # استرداد العلم الأصلي لو في backup
        orig_flag = os.path.join(FLAGS_DIR, f"{found_p['region']}_original.png")
        curr_flag = os.path.join(FLAGS_DIR, f"{found_p['region']}.png")
        if os.path.exists(orig_flag):
            try:
                import shutil; shutil.copy2(orig_flag, curr_flag)
            except: pass
        save_data(data)
        status_word = "الاستعمار" if is_colony else "الاحتلال"
        await update.message.reply_text(
            f"🕊️ *تم التحرير!*\n{sep()}\n"
            f"حررت *{original_name}* من {status_word}\n"
            f"الدولة رجعت لصاحبها بحرية كاملة!",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(found_uid),
                text=f"🎊 *دولتك تحررت!*\n{sep()}\n"
                     f"*{p['country_name']}* حرر *{original_name}*!\n"
                     f"عدت حرة مستقلة 🕊️", parse_mode="Markdown")
        except: pass
        return

    # ======= إهداء دولة محتلة لدولة أخرى =======
    if ntext.startswith("اهدي دوله "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        # الصيغة: اهدي دولة [اسم الدولة المحتلة] الى [كود اللاعب]
        rest = ntext.replace("اهدي دوله","").strip()
        if " الى " not in rest:
            await update.message.reply_text(
                "❌ الصيغة:\n`اهدي دولة [اسم الدولة المحتلة] الى [كود اللاعب]`",
                parse_mode="Markdown"); return
        parts      = rest.split(" الى ", 1)
        occ_name   = parts[0].strip()
        target_code= parts[1].strip()
        # دور على الدولة المحتلة
        occ_uid, occ_p = None, None
        for tuid, tp in data["players"].items():
            if (norm(tp.get("country_name","").replace(" (محتلة)","")) == norm(occ_name) or
                norm(tp.get("region","")) == norm(occ_name)):
                occ_uid, occ_p = tuid, tp; break
        if not occ_p:
            await update.message.reply_text(f"❌ مش لاقي دولة '{occ_name}'."); return
        if occ_p.get("occupied_by") != p["country_name"]:
            await update.message.reply_text(
                f"❌ *{occ_name}* مش في احتلالك."); return
        # دور على المستفيد
        recv_uid, recv_p = find_by_code(data, target_code)
        if not recv_p:
            await update.message.reply_text(f"❌ مش لاقي لاعب بالكود `{target_code}`."); return
        if recv_uid == str(uid):
            await update.message.reply_text("❌ مينفعش تهدي لنفسك!"); return
        # نقل الاحتلال
        occupied_terr = occ_p.get("territories", 1)
        # شيل الأراضي من المحتل الحالي
        data["players"][str(uid)]["territories"] = max(1,
            data["players"][str(uid)]["territories"] - occupied_terr)
        # نقل الاحتلال للمستفيد
        original_name = occ_p["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        data["players"][occ_uid]["occupied_by"]   = recv_p["country_name"]
        data["players"][occ_uid]["country_name"]  = f"{original_name} (محتلة)"
        data["players"][recv_uid]["territories"]  = recv_p.get("territories",1) + occupied_terr
        # انقل العلم
        winner_flag = os.path.join(FLAGS_DIR, f"{recv_p['region']}.png")
        loser_flag  = os.path.join(FLAGS_DIR, f"{occ_p['region']}.png")
        if os.path.exists(winner_flag):
            try:
                import shutil; shutil.copy2(winner_flag, loser_flag)
            except: pass
        save_data(data)
        await update.message.reply_text(
            f"🎁 *تم الإهداء!*\n{sep()}\n"
            f"أهديت *{original_name}* لـ *{recv_p['country_name']}*\n"
            f"علمهم يرفرف عليها الآن!",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(recv_uid),
                text=f"🎁 *هدية!*\n{sep()}\n"
                     f"*{p['country_name']}* أهداك دولة *{original_name}*!\n"
                     f"تحت سيطرتك الآن 🏳️", parse_mode="Markdown")
            await context.bot.send_message(chat_id=int(occ_uid),
                text=f"🔄 *تغيّر المحتل!*\n{sep()}\n"
                     f"*{original_name}* انتقلت من *{p['country_name']}*\n"
                     f"إلى *{recv_p['country_name']}* 🏳️", parse_mode="Markdown")
        except: pass
        return

    # ======= جيشي =======
    if ntext in ["جيشي","قواتي","تسليحي","عتادي"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        weaps = p.get("weapons", {})

        # تصنيف الأسلحة
        infantry_txt  = ""
        armored_txt   = ""
        aviation_txt  = ""
        nuke_txt      = ""
        total_dmg     = 0
        total_def_red = 0

        # المشاة (army_scale)
        for wid2, cnt in weaps.items():
            if wid2 not in WEAPONS or cnt == 0: continue
            w2 = WEAPONS[wid2]
            if w2.get("army_scale"):
                dmg = w2.get("damage_bonus", 0)
                total_dmg += dmg
                infantry_txt += f"  {w2['emoji']} {w2['name']}: {cnt:,} جندي (+{dmg*100:.0f}% ضرر)\n"

        # أسلحة عددية
        for wid2, cnt in weaps.items():
            if wid2 not in WEAPONS or cnt == 0: continue
            w2 = WEAPONS[wid2]
            if w2.get("army_scale"): continue
            if w2.get("unit"):
                dmg = w2.get("damage_bonus_each", 0) * cnt
                total_dmg     += dmg
                total_def_red += w2.get("defense_reduce_each", 0) * cnt
                cat  = w2["category"]
                line = f"  {w2['emoji']} {w2['name']}: ×{cnt:,} (+{dmg*100:.1f}% ضرر)\n"
                if cat == "تقليدي":  armored_txt  += line
                elif cat == "طيران": aviation_txt += line
            elif w2.get("one_use"):
                nuke_txt += f"  {w2['emoji']} {w2['name']}: ×{cnt}\n"

        total_dmg     = min(total_dmg, 2.0)
        total_def_red = min(total_def_red, 0.5)

        msg = f"{box_title('⚔️','القوة العسكرية')}\n*{p['country_name']}*\n{sep()}\n"
        msg += f"👥 *الجنود:* {p['army']:,}\n{sep()}\n"
        if infantry_txt:
            msg += f"🔫 *تسليح المشاة:*\n{infantry_txt}"
        else:
            msg += f"⚔️ المشاة بلا تسليح — اكتب `سوق`\n"
        if armored_txt:
            msg += f"🚛 *المدرعات:*\n{armored_txt}"
        if aviation_txt:
            msg += f"✈️ *الطيران:*\n{aviation_txt}"
        if nuke_txt:
            msg += f"☢️ *أسلحة دمار شامل:*\n{nuke_txt}"
        msg += f"{sep()}\n"
        msg += f"💥 بونص الضرر الإجمالي: *+{total_dmg*100:.1f}%*\n"
        if total_def_red > 0:
            msg += f"🛡️ اختراق الدفاع: *+{total_def_red*100:.1f}%*\n"
        msg += f"\n💡 `سوق` لشراء المزيد | `شراء دبابات [عدد]`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= تجنيد =======
    if ntext.startswith("تجنيد "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        try:
            amount = int(ntext.replace("تجنيد","").strip())
            assert amount > 0
            # المحتلة: حد أقصى 200 جندي إجمالي (مقاومة)
            if p.get("occupied_by"):
                max_occ = 200
                cur_army = p.get("army", 0)
                if cur_army >= max_occ:
                    await update.message.reply_text(
                        f"⛔ *حد المقاومة!*\n{sep()}\n"
                        f"الدولة المحتلة لا تقدر تتجاوز *{max_occ} جندي*\n"
                        f"✊ اكتب `ثورة` لو عندك {max_occ//3*2}+ جندي", parse_mode="Markdown"); return
                amount = min(amount, max_occ - cur_army)
            # خصم مصانع الأسلحة: 10% لكل مصنع، حد أقصى 50%
            factories = p.get("facilities",{}).get("مصنع_اسلحه", 0)
            discount  = min(0.50, factories * 0.10)
            # ميزة المستوى: تجنيد مخفض 5%
            if "تجنيد_مخفض" in get_perks(p.get("xp",0)):
                discount = min(0.55, discount + 0.05)
            base_cost = 50
            cost_per  = int(base_cost * (1 - discount))
            cost      = amount * cost_per
            discount_txt = f" (خصم {int(discount*100)}% 🔩)" if discount > 0 else ""
            if p["gold"] < cost:
                await update.message.reply_text(
                    f"❌ يكلف {CUR}{cost:,}{discount_txt}\nعندك {CUR}{p['gold']:,}."); return
            data["players"][str(uid)]["gold"] -= cost
            data["players"][str(uid)]["army"] += amount
            leveled_up, new_lvl = add_xp(data, uid, amount//10)
            save_data(data)
            new_army = p['army'] + amount
            occ_note = f"\n⚔️ جيش المقاومة: {new_army}/{200}" if p.get("occupied_by") else ""
            msg = (f"⚔️ *تجنيد ناجح!*\n{sep()}\n+{amount:,} جندي\n"
                   f"السعر: {CUR}{cost_per}/جندي{discount_txt}\n"
                   f"الجيش: {new_army:,} | المثاقيل: {CUR}{p['gold']-cost:,}\n⭐+{amount//10}"
                   f"{occ_note}")
            if leveled_up: msg += f"\n🎊 *ترقية!* {new_lvl['name']}"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except: await update.message.reply_text("❌ مثال: تجنيد 100")
        return

    # ======= هجوم =======
    if ntext.startswith("هجوم علي "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "هجوم")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        # هل الحروب مفتوحة؟
        if not data.get("wars_enabled", True):
            await update.message.reply_text(
                f"🕊️ *الحروب موقوفة حالياً*\n{sep()}\n"
                f"الأدمن أوقف الحروب مؤقتاً. انتظر إعادة الفتح.", parse_mode="Markdown"); return
        # cooldown الهجوم
        last_atk = p.get("last_attack",0)
        # المطار يخفض cooldown 20%
        airports  = p.get("facilities",{}).get("مطار", 0)
        attack_cd = int(ATTACK_CD * (0.8 ** min(airports, 3)))
        if time.time()-last_atk < attack_cd:
            rem = int(attack_cd-(time.time()-last_atk))
            await update.message.reply_text(f"⏳ استنى {rem//60}:{rem%60:02d} قبل الهجوم التالي!"); return
        tname = ntext.replace("هجوم علي","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp: await update.message.reply_text(f"❌ مش لاقي '{tname}'."); return
        if tuid == str(uid): await update.message.reply_text("❌ مينفعش تهاجم نفسك!"); return
        # منع الهجوم على أعضاء الحلف المشترك
        orgs_check = data.get("organizations", {})
        in_same_org_attack = any(
            p["country_name"] in ov["members"] and tp["country_name"] in ov["members"]
            for ov in orgs_check.values()
        )
        if in_same_org_attack:
            await update.message.reply_text(f"❌ *{tp['country_name']}* عضو في حلفك! مينفعش تهاجم حليف.", parse_mode="Markdown"); return
        # فحص معاهدة السلام
        peace = p.get("peace_treaties", {})
        tp_clean = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        for pname, pexpiry in list(peace.items()):
            if norm(pname) == norm(tp_clean):
                if time.time() < pexpiry:
                    rem_h = int((pexpiry - time.time()) // 3600)
                    await update.message.reply_text(
                        f"🕊️ *معاهدة سلام سارية!*\n{sep()}\n"
                        f"معاهدتك مع *{tp_clean}* تنتهي بعد *{rem_h}* ساعة\n"
                        f"لا يمكن الهجوم قبل انتهائها.",
                        parse_mode="Markdown"); return
                else:
                    data["players"][str(uid)]["peace_treaties"].pop(pname, None)
        # فحص الأحلاف المشتركة — أعضاء نفس الحلف لا يهاجموا بعض
        shared_org = None
        for org_name, org in data.get("organizations",{}).items():
            if p["country_name"] in org["members"] and tp["country_name"] in org["members"]:
                shared_org = org_name
                break
        if shared_org:
            await update.message.reply_text(
                f"🏛️ *لا يمكن الهجوم!*\n{sep()}\n"
                f"أنت و*{tp['country_name']}* أعضاء في حلف *{shared_org}*\n"
                f"أعضاء نفس الحلف لا يهاجموا بعض! 🤝",
                parse_mode="Markdown"); return
        if p.get("army", 0) == 0:
            await update.message.reply_text("❌ جيشك 0! جند جنوداً أولاً."); return
        # فحص الحدود الجغرافية
        can_atk, border_err = can_attack_region(data, p, tp.get("region",""))
        if not can_atk:
            await update.message.reply_text(border_err, parse_mode="Markdown"); return
        # بونص الأسلحة
        weap_dmg   = 0
        def_reduce = 0
        for wname, cnt in p.get("weapons", {}).items():
            if wname not in WEAPONS: continue
            wd = WEAPONS[wname]
            if wd.get("one_use"): continue
            if wd.get("unit"):
                weap_dmg   += wd.get("damage_bonus_each", 0) * cnt
                def_reduce += wd.get("defense_reduce_each", 0) * cnt
            elif wd.get("army_scale"):
                weap_dmg += wd.get("damage_bonus", 0)
        weap_dmg   = min(weap_dmg, 2.0)
        def_reduce = min(def_reduce, 0.5)
        att  = p["army"]*random.uniform(0.7,1.3)*(1+weap_dmg)
        # بونص المستوى — قوة عظمى +15% هجوم
        att_perks = get_perks(p.get("xp",0))
        if "قوة_عظمى" in att_perks:   att  *= 1.15
        if "وزير_دفاع" in att_perks:  att  *= 1.05
        # بونص إعلان الحرب الرسمي +15% هجوم
        war_decl_bonus = ""
        tp_clean2 = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        if any(norm(w) == norm(tp_clean2) for w in p.get("war_declared", [])):
            att *= 1.15
            war_decl_bonus = "\n⚔️ *إعلان حرب رسمي* +15% هجوم"  # هجوم أفضل قليلاً
        # دفاع الهدف
        base_defense = tp["army"]*random.uniform(0.7,1.3)*(1-def_reduce)
        def_perks = get_perks(tp.get("xp",0))
        if "وزير_دفاع" in def_perks:  base_defense *= 1.08
        if "قوة_عظمى"  in def_perks:  base_defense *= 1.15
        # لو الدولة محتلة أو مستعمرة، جيش المحتل/المستعمِر يدافع عنها
        extra_defense_txt = ""
        deff = base_defense
        occupier_uid = None
        occupier_p = None
        if tp.get("occupied_by") or tp.get("colony_of"):
            owner_name = tp.get("occupied_by") or tp.get("colony_of")
            is_occupied = bool(tp.get("occupied_by"))
            for ouid, op in data["players"].items():
                op_name_clean = op.get("country_name","").replace(" (محتلة)","").replace(" (مستعمرة)","")
                if op_name_clean == owner_name or op.get("country_name") == owner_name:
                    occupier_uid = ouid
                    occupier_p = op
                    break
            if occupier_p and occupier_uid != str(uid):
                # المحتل يدافع بـ 60-90% من جيشه (دفاع أقوى من الحليف)
                owner_defense = occupier_p["army"] * random.uniform(0.60, 0.90)
                deff += owner_defense
                rel_word = "محتلته" if is_occupied else "مستعمرته"
                extra_defense_txt = f"\n🛡️ *{owner_name}* دافع عن {rel_word}! (+{int(owner_defense):,} جندي)"
                # إشعار المحتل
                try:
                    await context.bot.send_message(chat_id=int(occupier_uid),
                        text=f"⚠️ *هجوم على {rel_word}!*\n{sep()}\n"
                             f"*{p['country_name']}* هاجم *{tp['country_name']}*\n"
                             f"جيشك يدافع عنها بـ *{int(owner_defense):,}* جندي 🛡️",
                        parse_mode="Markdown")
                except: pass
        # لو الدولة محمية، جيش الحامي يدافع عنها
        protector_name = tp.get("protected_by")
        if protector_name:
            prot_uid2, prot_p2 = find_by_name(data, protector_name)
            if prot_p2 and prot_uid2 != str(uid):
                prot_defense = prot_p2["army"] * random.uniform(0.4, 0.8)
                deff += prot_defense
                extra_defense_txt += f"\n🛡️ *{protector_name}* دافع عن المحمية! (+{int(prot_defense):,} جندي)"
                # إشعار الحامي
                try:
                    await context.bot.send_message(chat_id=int(prot_uid2),
                        text=f"⚔️ *{p['country_name']}* هاجم *{tp['country_name']}* المحمية بواسطتك!\n"
                             f"جيشك دافع عنهم بـ {int(prot_defense):,} جندي 🛡️", parse_mode="Markdown")
                except: pass
        # التحالف الدفاعي — الحلفاء يدافعون تلقائياً
        for def_ally_name in tp.get("defensive_pacts", []):
            def_ally_uid, def_ally_p = find_by_name(data, def_ally_name)
            if def_ally_p and def_ally_uid != str(uid):
                ally_def = def_ally_p["army"] * random.uniform(0.3, 0.6)
                deff += ally_def
                extra_defense_txt += f"\n🤝 *{def_ally_name}* (تحالف دفاعي) +{int(ally_def):,} جندي"
                try:
                    await context.bot.send_message(chat_id=int(def_ally_uid),
                        text=f"🛡️ *التحالف الدفاعي فُعِّل!*\n{sep()}\n"
                             f"*{p['country_name']}* هاجم حليفك *{tp['country_name']}*\n"
                             f"جيشك دافع عنهم بـ {int(ally_def):,} جندي", parse_mode="Markdown")
                except: pass
        data["players"][str(uid)]["last_attack"] = time.time()
        data["players"][str(uid)]["last_active"]  = time.time()
        # تحديث قوائم الحرب
        if tp["country_name"] not in p.get("at_war",[]):
            data["players"][str(uid)].setdefault("at_war",[]).append(tp["country_name"])
        if p["country_name"] not in tp.get("at_war",[]):
            data["players"][tuid].setdefault("at_war",[]).append(p["country_name"])
        if att > deff:
            # خسائر نسبية — المهاجم يخسر 5-15%، المدافع 15-30% من جيشه
            atk_loss_pct = random.uniform(0.05, 0.15)
            def_loss_pct = random.uniform(0.15, 0.30) * (1 + weap_dmg)  # الأسلحة تزيد خسائر العدو
            la = max(1, int(p["army"]  * atk_loss_pct))
            ld = max(1, int(tp["army"] * def_loss_pct))
            loot = min(tp["gold"] // 3, max(500, tp["gold"] // 5))
            loser_army_after = max(0, tp["army"] - ld)
            # الاحتلال: جيش المهزوم أقل من 20% من جيش المنتصر أو وصل صفر
            conquered = loser_army_after == 0 or loser_army_after < (p["army"] - la) * 0.2

            data["players"][str(uid)]["gold"]        += loot
            data["players"][str(uid)]["territories"] += 1
            data["players"][str(uid)]["army"]         = max(0, p["army"]-la)
            data["players"][tuid]["gold"]             = max(0, tp["gold"]-loot)
            data["players"][tuid]["territories"]      = max(1, tp["territories"]-1)
            data["players"][tuid]["army"]             = loser_army_after
            data["players"][tuid]["wars_lost"]        = tp.get("wars_lost",0)+1
            data["players"][str(uid)]["wars_won"]     = p.get("wars_won",0)+1
            # تقليل حظر النووي بعد كل معركة
            if data["players"][str(uid)].get("nuke_banned",0) > 0:
                data["players"][str(uid)]["nuke_banned"] -= 1
            leveled_up, new_lvl = add_xp(data, uid, 200)

            conquest_txt = ""
            if conquered:
                # نقل علم المهزوم للمنتصر
                loser_flag = os.path.join(FLAGS_DIR, f"{tp['region']}.png")
                winner_flag = os.path.join(FLAGS_DIR, f"{p['region']}.png")
                if os.path.exists(winner_flag):
                    try:
                        import shutil
                        orig_backup = os.path.join(FLAGS_DIR, f"{tp['region']}_original.png")
                        if os.path.exists(loser_flag) and not os.path.exists(orig_backup):
                            shutil.copy2(loser_flag, orig_backup)
                        shutil.copy2(winner_flag, loser_flag)
                    except: pass
                # نقل الدولة — غيّر الـ owner
                clean_name = tp['country_name'].replace(" (محتلة)","").replace(" (مستعمرة)","")
                data["players"][tuid]["country_name"] = f"{clean_name} (محتلة)"
                data["players"][tuid]["occupied_by"]  = p["country_name"]
                data["players"][str(uid)]["territories"] += tp["territories"]
                data["players"][tuid]["territories"]   = 0
                looted_gold = transfer_conquest(data, uid, tuid)
                conquest_txt = (
                    f"\n🏳️ *احتللت {tp['country_name']} بالكامل!*\n"
                    f"💰 نهبت: {looted_gold:,}¥\n"
                    f"🌾 مزارعها ومنشآتها صارت لك!\n"
                    f"علمك يرفرف على أراضيهم!"
                )

            save_data(data)
            weap_txt = f"\n   🔫 بونص أسلحة: +{weap_dmg*100:.0f}%" if weap_dmg > 0 else ""
            msg = (
                f"{box_title('⚔️','نتيجة المعركة')}\n"
                f"🏆 *انتصار!*{weap_txt}\n"
                f"{sep()}\n"
                f"🗡️ *{p['country_name']}*  vs  🛡️ *{tp['country_name']}*\n"
                f"{sep()}\n"
                f"💰 غنيمة:     +{CUR}{loot:,}\n"
                f"🗺️ أرض جديدة: +1 منطقة\n"
                f"💀 خسائرك:   {la:,} ({int(atk_loss_pct*100)}%)\n"
                f"💀 خسائر العدو: {ld:,} ({int(def_loss_pct*100)}%)\n"
                f"⭐ +200 XP"
                f"{war_decl_bonus}{extra_defense_txt}"
                f"{conquest_txt}"
            )
            if leveled_up: msg += f"\n\n🎊 *ترقية!* {new_lvl['name']} {new_lvl['emoji']}"
            await update.message.reply_text(msg, parse_mode="Markdown")
            try:
                defeat_msg = (
                    f"{box_title('🚨','تنبيه حرب!')}\n"
                    f"*{p['country_name']}* هاجمك!\n"
                    f"{sep()}\n"
                    f"💸 خسرت:  {CUR}{loot:,}\n"
                    f"💀 خسائر: {ld:,} جندي\n"
                    f"⚔️ رد بـ: `هجوم على {p['country_name']}`"
                )
                if conquered:
                    defeat_msg += f"\n\n🏴 *دولتك محتلة!*\nاكتب `ثورة` لمحاولة التحرر"
                await context.bot.send_message(chat_id=int(tuid), text=defeat_msg, parse_mode="Markdown")
            except: pass
        else:
            # هزيمة — المهاجم يخسر أكثر
            atk_loss_pct = random.uniform(0.15, 0.30)
            def_loss_pct = random.uniform(0.05, 0.15)
            la = max(1, int(p["army"]  * atk_loss_pct))
            ld = max(1, int(tp["army"] * def_loss_pct))
            data["players"][str(uid)]["army"]      = max(0, p["army"]-la)
            data["players"][str(uid)]["wars_lost"] = p.get("wars_lost",0)+1
            if data["players"][str(uid)].get("nuke_banned",0) > 0:
                data["players"][str(uid)]["nuke_banned"] -= 1
            data["players"][tuid]["army"] = max(0, tp["army"]-ld)
            save_data(data)
            await update.message.reply_text(
                f"{box_title('⚔️','نتيجة المعركة')}\n"
                f"❌ *هزيمة!*\n"
                f"{sep()}\n"
                f"💀 خسائرك:    {la:,} ({int(atk_loss_pct*100)}%)\n"
                f"💀 خسائر العدو: {ld:,} ({int(def_loss_pct*100)}%)\n"
                f"{extra_defense_txt}\n"
                f"💡 جنّد أكثر وأعد المحاولة!",
                parse_mode="Markdown")
        return

    # ======= البنك الدولي - القروض =======
    if ntext in ["البنك الدولي","بنك","قرض","اخد قرض"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        active = p.get("loans",[])
        if len(active) >= 2:
            await update.message.reply_text(
                f"❌ *عندك {len(active)} قروض نشطة*\n{sep()}\n"
                f"لازم تسدد القروض الحالية قبل قرض جديد.",
                parse_mode="Markdown"); return
        rows = []
        for l in LOAN_OPTIONS:
            total = int(l["amount"]*(1+l["interest"]))
            rows.append([InlineKeyboardButton(
                f"{l['emoji']} {l['name']}: {l['amount']:,}¥ → يُسدَّد {total:,}¥ في {l['due_cycles']} دورات",
                callback_data=f"loan_{l['id']}")])
        rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])
        loans_txt = ""
        for loan in active:
            loans_txt += f"  • {loan['name']}: يُسدَّد بعد {loan['remaining_cycles']} دورات\n"
        msg = (
            f"{box_title('🏦','البنك الدولي')}\n\n"
            f"اقترض الآن وسدّد تلقائياً من الحصاد!\n"
            f"⚠️ عدم السداد = عقوبة 50% إضافية\n"
        )
        if loans_txt:
            msg += f"\n📋 *قروضك الحالية:*\n{loans_txt}"
        msg += f"\n{sep()}\n*اختار نوع القرض:*"
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")
        return

    # ======= ديوني - التحقق من القروض وسدادها =======
    if ntext in ["ديوني","قروضي","ديون","سداد"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        loans = p.get("loans", [])
        if not loans:
            await update.message.reply_text(
                f"🏦 *ديونك*\n{sep()}\n✅ لا يوجد قروض!\nخزينتك: *{CUR}{p['gold']:,}*",
                parse_mode="Markdown"); return

        msg  = f"{box_title('🏦','ديونك وقروضك')}\n\n"
        msg += f"💰 خزينتك الآن: *{CUR}{p['gold']:,}*\n{sep()}\n"
        rows = []
        total_debt = 0
        for idx, loan in enumerate(loans):
            due              = loan["due"]
            remaining        = loan["remaining_cycles"]
            total_debt      += due
            can_afford       = p["gold"] >= due
            urgency          = "🔴" if remaining <= 1 else ("🟡" if remaining <= 3 else "🟢")
            afford_icon      = "✅" if can_afford else "❌"
            msg += (
                f"{urgency} *{loan['name']}*\n"
                f"  💸 المبلغ الواجب: *{CUR}{due:,}*\n"
                f"  ⏳ متبقي: *{remaining}* دورة حصاد\n"
                f"  {afford_icon} {'تقدر تسدد' if can_afford else 'رصيد غير كافٍ'}\n"
            )
            if can_afford:
                rows.append([InlineKeyboardButton(
                    f"💳 سداد {loan['name']} — {CUR}{due:,}",
                    callback_data=f"loan_repay_{idx}"
                )])
            msg += sep() + "\n"

        msg += f"📊 *إجمالي الديون: {CUR}{total_debt:,}*\n"
        if total_debt > p["gold"]:
            msg += f"⚠️ الديون أكبر من رصيدك بـ {CUR}{total_debt - p['gold']:,}"
        rows.append([InlineKeyboardButton("❌ إغلاق", callback_data="cancel")])
        await update.message.reply_text(
            msg, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")
        return

    # ======= ثورة — تحرر من الاحتلال =======
    if ntext in ["ثوره", "ثورة", "انتفاضه", "انتفاضة"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        occupier_name = p.get("occupied_by")
        if not occupier_name:
            await update.message.reply_text("❌ دولتك مش محتلة!"); return
        occ_uid, occ_p = find_by_name(data, occupier_name)
        if not occ_p:
            # المحتل اختفى — تحرر تلقائي
            data["players"][str(uid)]["occupied_by"] = None
            orig = p["country_name"].replace(" (محتلة)","")
            data["players"][str(uid)]["country_name"] = orig
            save_data(data)
            await update.message.reply_text(f"🎉 تحررت تلقائياً — المحتل اختفى!"); return
        my_army  = p.get("army", 0)
        occ_army = occ_p.get("army", 0)
        min_needed = max(50, int(occ_army * 0.30))
        if my_army < min_needed:
            await update.message.reply_text(
                f"✊ *الثورة تحتاج استعداداً!*\n{sep()}\n"
                f"جيشك: *{my_army:,}* | جيش {occupier_name}: *{occ_army:,}*\n"
                f"تحتاج على الأقل *{min_needed:,} جندي* (30% من جيش المحتل)\n\n"
                f"💡 جند أكثر — الحد الأقصى للمحتلة 200 جندي",
                parse_mode="Markdown"); return
        cost = 15000
        if p["gold"] < cost:
            await update.message.reply_text(
                f"✊ الثورة تحتاج *{CUR}{cost:,}* لتمويل المقاومة\n"
                f"عندك {CUR}{p['gold']:,}", parse_mode="Markdown"); return
        # حساب نسبة النجاح
        ratio = my_army / max(1, occ_army)
        success_chance = min(0.70, ratio)
        data["players"][str(uid)]["gold"] -= cost
        success = random.random() < success_chance
        if success:
            orig = p["country_name"].replace(" (محتلة)","")
            army_lost = max(10, int(my_army * random.uniform(0.20, 0.35)))
            occ_army_lost = max(100, int(occ_army * random.uniform(0.25, 0.40)))
            data["players"][str(uid)]["occupied_by"]   = None
            data["players"][str(uid)]["country_name"]  = orig
            data["players"][str(uid)]["army"]          = max(1, my_army - army_lost)
            data["players"][str(uid)]["wars_won"]      = p.get("wars_won",0) + 1
            data["players"][str(uid)]["happiness_bonus"] = min(30, p.get("happiness_bonus",0) + 20)
            if occ_uid:
                data["players"][occ_uid]["army"] = max(0, occ_army - occ_army_lost)
                data["players"][occ_uid]["wars_lost"] = occ_p.get("wars_lost",0) + 1
            save_data(data)
            await update.message.reply_text(
                f"{box_title('🎉','الثورة نجحت!')}\n"
                f"✊ *{orig}* حرة من الاحتلال!\n\n"
                f"⚔️ خسائرك: *{army_lost:,}* جندي\n"
                f"💥 خسائر {occupier_name}: *{occ_army_lost:,}* جندي\n"
                f"😊 رضا الشعب ارتفع فرحاً بالتحرر! +20%",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(occ_uid),
                    text=f"✊ *ثورة شعبية!*\n{sep()}\n"
                         f"*{orig}* ثارت وانتزعت حريتها!\n"
                         f"💀 خسرت *{occ_army_lost:,}* جندي في قمع الثورة", parse_mode="Markdown")
            except: pass
        else:
            army_lost = max(20, int(my_army * random.uniform(0.35, 0.55)))
            fine = 10000
            data["players"][str(uid)]["army"] = max(0, my_army - army_lost)
            data["players"][occ_uid]["gold"]  = occ_p.get("gold",0) + fine
            save_data(data)
            await update.message.reply_text(
                f"💔 *الثورة فشلت!*\n{sep()}\n"
                f"قمع {occupier_name} الثورة بالقوة\n\n"
                f"⚔️ خسرت: *{army_lost:,}* جندي\n"
                f"💸 غرامة: *{CUR}{fine:,}* دفعها المحتل\n\n"
                f"⏳ أعد بناء جيشك وحاول مجدداً",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(occ_uid),
                    text=f"🛡️ *قمعت الثورة!*\n{sep()}\n"
                         f"أخمدت ثورة *{p['country_name']}*\n"
                         f"💰 غنمت *{CUR}{fine:,}* غرامة", parse_mode="Markdown")
            except: pass
        return

    # ======= استقلال — تحرر من الاستعمار =======
    if ntext in ["استقلال", "اعلن الاستقلال", "اعلن استقلال"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        master_name = p.get("colony_of")
        if not master_name:
            await update.message.reply_text("❌ دولتك مش مستعمرة!"); return
        master_uid, master_p = find_by_name(data, master_name)
        if not master_p:
            # المستعمِر اختفى — استقلال تلقائي
            data["players"][str(uid)]["colony_of"] = None
            orig = p["country_name"].replace(" (مستعمرة)","")
            data["players"][str(uid)]["country_name"] = orig
            save_data(data)
            await update.message.reply_text(f"🎉 استقلال تلقائي — المستعمِر اختفى!"); return
        my_army     = p.get("army", 0)
        master_army = master_p.get("army", 0)
        min_needed  = max(100, int(master_army * 0.60))
        if my_army < min_needed:
            await update.message.reply_text(
                f"⚔️ *الاستقلال يحتاج قوة!*\n{sep()}\n"
                f"جيشك: *{my_army:,}* | جيش {master_name}: *{master_army:,}*\n"
                f"تحتاج *{min_needed:,} جندي* (60% من جيش المستعمِر)\n\n"
                f"💡 لديك حرية البناء والتجنيد — استغلها!",
                parse_mode="Markdown"); return
        cost = 25000
        if p["gold"] < cost:
            await update.message.reply_text(
                f"⚔️ الاستقلال يحتاج *{CUR}{cost:,}* لتمويل الحملة\n"
                f"عندك {CUR}{p['gold']:,}", parse_mode="Markdown"); return
        ratio = my_army / max(1, master_army)
        success_chance = min(0.70, ratio * 0.85)
        data["players"][str(uid)]["gold"] -= cost
        success = random.random() < success_chance
        if success:
            orig = p["country_name"].replace(" (مستعمرة)","")
            army_lost  = max(50, int(my_army * random.uniform(0.15, 0.30)))
            master_lost= max(200, int(master_army * random.uniform(0.20, 0.35)))
            data["players"][str(uid)]["colony_of"]     = None
            data["players"][str(uid)]["country_name"]  = orig
            data["players"][str(uid)]["army"]          = max(1, my_army - army_lost)
            data["players"][str(uid)]["wars_won"]      = p.get("wars_won",0) + 1
            data["players"][str(uid)]["happiness_bonus"] = min(30, p.get("happiness_bonus",0) + 15)
            if master_uid:
                data["players"][master_uid]["army"]      = max(0, master_army - master_lost)
                data["players"][master_uid]["wars_lost"] = master_p.get("wars_lost",0) + 1
                # أزل من قائمة المستعمرات إن وجدت
            save_data(data)
            await update.message.reply_text(
                f"{box_title('🏳️','إعلان الاستقلال!')}\n"
                f"🎉 *{orig}* دولة مستقلة من الآن!\n\n"
                f"⚔️ خسائرك: *{army_lost:,}* جندي\n"
                f"💥 خسائر {master_name}: *{master_lost:,}* جندي\n"
                f"😊 الشعب يحتفل بالاستقلال! +15%",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(master_uid),
                    text=f"🏳️ *استقلال المستعمرة!*\n{sep()}\n"
                         f"*{orig}* أعلنت استقلالها بالقوة!\n"
                         f"💀 خسرت *{master_lost:,}* جندي", parse_mode="Markdown")
            except: pass
        else:
            army_lost = max(30, int(my_army * random.uniform(0.25, 0.40)))
            fine = 20000
            data["players"][str(uid)]["army"] = max(0, my_army - army_lost)
            data["players"][master_uid]["gold"] = master_p.get("gold",0) + fine
            save_data(data)
            await update.message.reply_text(
                f"💔 *فشل إعلان الاستقلال!*\n{sep()}\n"
                f"*{master_name}* أخمد المحاولة\n\n"
                f"⚔️ خسرت: *{army_lost:,}* جندي\n"
                f"💸 غرامة: *{CUR}{fine:,}*\n\n"
                f"⏳ جند أكثر وحاول مجدداً",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(master_uid),
                    text=f"🛡️ *أخمدت محاولة الاستقلال!*\n{sep()}\n"
                         f"*{p['country_name']}* فشلت في الاستقلال\n"
                         f"💰 غنمت *{CUR}{fine:,}* غرامة", parse_mode="Markdown")
            except: pass
        return

    # ======= مهرجان شعبي / رفع الرضا =======
    if ntext in ["مهرجان شعبي", "مهرجان", "ارضي الشعب", "رضا الشعب"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        happy_now = calc_happiness(p)
        FESTIVALS = [
            {"name": "مهرجان شعبي صغير",  "cost": 5_000,  "bonus": 5,  "emoji": "🎪", "desc": "أفراح وموسيقى في الساحات"},
            {"name": "حفلة وطنية",        "cost": 15_000, "bonus": 12, "emoji": "🎆", "desc": "ألعاب نارية واحتفالات رسمية"},
            {"name": "عيد وطني كبير",     "cost": 40_000, "bonus": 25, "emoji": "🎊", "desc": "يوم إجازة وطنية وعطايا"},
            {"name": "توزيع إعانات",      "cost": 25_000, "bonus": 18, "emoji": "🏥", "desc": "توزيع مساعدات على المحتاجين"},
        ]
        kbd = []
        row = []
        for i, f in enumerate(FESTIVALS):
            avail = "✅" if p["gold"] >= f["cost"] else "❌"
            row.append(InlineKeyboardButton(
                f"{f['emoji']} {f['name']} {f['cost']:,}¥ (+{f['bonus']}%)",
                callback_data=f"festival_{i}"))
            if len(row) == 2: kbd.append(row); row = []
        if row: kbd.append(row)
        kbd.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])
        msg = (f"🎉 *رفع رضا الشعب*\n{sep()}\n"
               f"😊 الرضا الحالي: *{happy_now}%* {status_emoji(happy_now)}\n\n"
               f"اختار نوع الإنفاق:\n")
        for f in FESTIVALS:
            avail = "✅" if p["gold"] >= f["cost"] else "❌"
            msg += f"{avail} {f['emoji']} *{f['name']}* — {f['desc']}\n"
            msg += f"   💰 {f['cost']:,}¥ → +{f['bonus']}% رضا\n"
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kbd), parse_mode="Markdown")
        return





    # ======= إعلان حرب رسمي =======
    if ntext.startswith("اعلن حرب على ") or ntext.startswith("اعلان حرب على "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        if 4 not in [get_level(p.get("xp",0))["level"]] and get_level(p.get("xp",0))["level"] < 4:
            await update.message.reply_text("🔒 إعلان الحرب يتطلب مستوى *4 (مملكة)* على الأقل.", parse_mode="Markdown"); return
        tname = ntext.replace("اعلن حرب على","").replace("اعلان حرب على","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp: await update.message.reply_text(f"❌ مش لاقي دولة '{tname}'."); return
        if tuid == str(uid): await update.message.reply_text("❌ مينفعش تعلن حرب على نفسك!"); return
        already = any(norm(w) == norm(tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")) for w in p.get("war_declared",[]))
        if already:
            await update.message.reply_text(f"⚔️ إعلان الحرب على *{tp['country_name']}* سارٍ بالفعل.", parse_mode="Markdown"); return
        data["players"][str(uid)].setdefault("war_declared",[]).append(tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)",""))
        save_data(data)
        await update.message.reply_text(
            f"📜 *إعلان حرب رسمي!*\n{sep()}\n"
            f"أعلنت الحرب رسمياً على *{tp['country_name']}*\n"
            f"⚔️ هجماتك عليهم +15% قوة\n"
            f"⚠️ العالم لاحظ هذا الإعلان!", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"📜 *إعلان حرب!*\n{sep()}\n"
                     f"*{p['country_name']}* أعلنت الحرب عليك رسمياً!\n"
                     f"استعد للمواجهة ⚔️", parse_mode="Markdown")
        except: pass
        return

    # ======= معاهدة سلام =======
    if ntext.startswith("معاهده سلام مع ") or ntext.startswith("معاهدة سلام مع "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "معاهدة")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        if get_level(p.get("xp",0))["level"] < 4:
            await update.message.reply_text("🔒 معاهدة السلام تتطلب مستوى *4 (مملكة)*.", parse_mode="Markdown"); return
        tname = ntext.replace("معاهده سلام مع","").replace("معاهدة سلام مع","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp: await update.message.reply_text(f"❌ مش لاقي دولة '{tname}'."); return
        if tuid == str(uid): await update.message.reply_text("❌ مينفعش!"); return
        cost = 5000
        if p["gold"] < cost: await update.message.reply_text(f"❌ محتاج {cost:,}¥ رسوم المعاهدة."); return
        duration_h = 24
        expiry = time.time() + duration_h * 3600
        tp_clean = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        data["players"][str(uid)]["gold"] -= cost
        data["players"][str(uid)].setdefault("peace_treaties",{})[tp_clean] = expiry
        data["players"][tuid].setdefault("peace_treaties",{})[p["country_name"]] = expiry
        # أزل من قوائم الحرب
        data["players"][str(uid)]["at_war"] = [x for x in p.get("at_war",[]) if norm(x) != norm(tp_clean)]
        data["players"][tuid]["at_war"]     = [x for x in tp.get("at_war",[]) if norm(x) != norm(p["country_name"])]
        # أزل إعلانات الحرب
        data["players"][str(uid)]["war_declared"] = [x for x in p.get("war_declared",[]) if norm(x) != norm(tp_clean)]
        save_data(data)
        await update.message.reply_text(
            f"🕊️ *معاهدة سلام!*\n{sep()}\n"
            f"سلام مع *{tp_clean}* لمدة *{duration_h} ساعة*\n"
            f"💸 رسوم: {cost:,}¥\n"
            f"لا يمكن الهجوم عليهم خلال هذه المدة.", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"🕊️ *معاهدة سلام!*\n{sep()}\n"
                     f"*{p['country_name']}* عرض معاهدة سلام لـ{duration_h} ساعة\n"
                     f"لا يمكنهم مهاجمتك خلالها ✅", parse_mode="Markdown")
        except: pass
        return

    # ======= تحالف دفاعي =======
    if ntext.startswith("تحالف دفاعي مع "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "تحالف_دفاعي")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        tname = ntext.replace("تحالف دفاعي مع","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp: await update.message.reply_text(f"❌ مش لاقي '{tname}'."); return
        if tuid == str(uid): await update.message.reply_text("❌ مينفعش!"); return
        if p["country_name"] in tp.get("defensive_pacts",[]):
            await update.message.reply_text("✅ التحالف الدفاعي موجود بالفعل."); return
        # لازم يكونوا في حلف مشترك
        orgs = data.get("organizations", {})
        shared_org = next((on for on, ov in orgs.items()
                           if p["country_name"] in ov["members"] and tp["country_name"] in ov["members"]), None)
        if not shared_org:
            await update.message.reply_text(
                "❌ لازم تكونوا في *حلف مشترك* أولاً.\n"
                "أنشئ حلفاً وادعُ الدولة: `انشاء حلف [اسم]`", parse_mode="Markdown"); return
        data["players"][str(uid)].setdefault("defensive_pacts",[]).append(tp["country_name"])
        data["players"][tuid].setdefault("defensive_pacts",[]).append(p["country_name"])
        save_data(data)
        await update.message.reply_text(
            f"🛡️ *تحالف دفاعي!*\n{sep()}\n"
            f"لو هاجم أحد *{tp['country_name']}*، جيشك يدخل تلقائياً!\n"
            f"والعكس بالعكس 🤝", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"🛡️ *تحالف دفاعي مع {p['country_name']}!*\n"
                     f"لو هوجمت، جيشهم يدافع عنك تلقائياً ✅", parse_mode="Markdown")
        except: pass
        return

    # ======= إلغاء تحالف دفاعي =======
    if ntext.startswith("الغاء تحالف دفاعي مع ") or ntext.startswith("إلغاء تحالف دفاعي مع "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        tname = ntext.replace("الغاء تحالف دفاعي مع","").replace("إلغاء تحالف دفاعي مع","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp:
            await update.message.reply_text(f"❌ مش لاقي '{tname}'."); return
        my_pacts  = data["players"][str(uid)].get("defensive_pacts", [])
        his_pacts = data["players"][tuid].get("defensive_pacts", [])
        if tp["country_name"] not in my_pacts:
            await update.message.reply_text(
                f"❌ مفيش تحالف دفاعي بينك وبين *{tp['country_name']}*.",
                parse_mode="Markdown"); return
        # احذف من الطرفين
        data["players"][str(uid)]["defensive_pacts"] = [x for x in my_pacts  if x != tp["country_name"]]
        data["players"][tuid]["defensive_pacts"]      = [x for x in his_pacts if x != p["country_name"]]
        save_data(data)
        await update.message.reply_text(
            f"🛡️ *إلغاء التحالف الدفاعي*\n{sep()}\n"
            f"تم إلغاء التحالف الدفاعي مع *{tp['country_name']}*.",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"⚠️ *{p['country_name']}* ألغى التحالف الدفاعي معك.", parse_mode="Markdown")
        except: pass
        return

    # ======= تجسس =======
    if ntext.startswith("تجسس على ") or ntext.startswith("جاسوس على "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        if "مخابرات" not in get_perks(p.get("xp",0)):
            await update.message.reply_text("🔒 التجسس يتطلب مستوى *5 (إمبراطورية)*.", parse_mode="Markdown"); return
        tname = ntext.replace("تجسس على","").replace("جاسوس على","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp: await update.message.reply_text(f"❌ مش لاقي '{tname}'."); return
        if tuid == str(uid): await update.message.reply_text("❌ تجسس على نفسك؟ 🤦"); return
        cost = 3000
        if p["gold"] < cost: await update.message.reply_text(f"❌ التجسس يكلف {cost:,}¥."); return
        # احتمال الانكشاف 25%
        caught = random.random() < 0.25
        data["players"][str(uid)]["gold"] -= cost
        if caught:
            save_data(data)
            await update.message.reply_text(
                f"🚨 *جاسوسك انكشف!*\n{sep()}\n"
                f"تم اعتقاله في *{tp['country_name']}*\n💸 {cost:,}¥ ضاعت", parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🕵️ *جاسوس مكشوف!*\n{sep()}\n"
                         f"اعتقلنا جاسوساً من *{p['country_name']}*! 🚔", parse_mode="Markdown")
            except: pass
            return
        # نجح التجسس
        save_data(data)
        tp_perks = get_perks(tp.get("xp",0))
        nuke_txt = ""
        nukes = [w for w in tp.get("weapons",{}) if "قنبلة" in w and tp["weapons"][w] > 0]
        if nukes: nuke_txt = f"\n☢️ أسلحة نووية: {', '.join(nukes)}"
        await update.message.reply_text(
            f"🕵️ *تقرير المخابرات — {tp['country_name']}*\n{sep()}\n"
            f"⚔️ الجيش: *{tp['army']:,}* جندي\n"
            f"💰 الخزينة: *{CUR}{tp['gold']:,}*\n"
            f"🏗️ البنية: Lv.*{tp.get('infrastructure',0)}*\n"
            f"🏅 المستوى: *{get_level(tp.get('xp',0))['name']}*\n"
            f"🏛️ الأحلاف: {sum(1 for ov in data.get('organizations',{}).values() if tp['country_name'] in ov.get('members',[]))}"
            f"{nuke_txt}\n{sep()}\n_💸 كلف {cost:,}¥_",
            parse_mode="Markdown")
        return

    # ======= سوق الأسلحة الدولي =======
    if ntext in ["سوق الاسلحه الدولي", "اسلحه للبيع", "عرض سلاح"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        market = [m for m in data.get("market",[]) if m.get("type") == "weapons"]
        if not market:
            await update.message.reply_text(
                f"🏪 *سوق الأسلحة الدولي*\n{sep()}\n"
                f"لا توجد عروض حالياً.\n"
                f"💡 `بيع سلاح [اسم] [كمية] [سعر]` لعرض سلاحك", parse_mode="Markdown"); return
        msg = f"🏪 *سوق الأسلحة الدولي*\n{sep()}\n"
        for i, m in enumerate(market[:10], 1):
            w = WEAPONS.get(m["weapon_id"], {})
            msg += f"{i}. {w.get('emoji','🔫')} *{w.get('name', m['weapon_id'])}* ×{m['qty']}\n"
            msg += f"   💰 {CUR}{m['price']:,} | 🏳️ {m['seller_name']}\n"
            msg += f"   🛒 `شراء من سوق {i}`\n"
        msg += f"\n{sep()}\n💡 `بيع سلاح [اسم] [كمية] [سعر]` لعرض سلاحك"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    if ntext.startswith("بيع سلاح "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        parts = text.split()
        if len(parts) < 4: await update.message.reply_text("❌ الصيغة: `بيع سلاح [اسم] [كمية] [سعر]`", parse_mode="Markdown"); return
        wid_raw = parts[2]; qty_s = parts[3]; price_s = parts[4] if len(parts)>4 else parts[3]
        # norm للبحث
        wid = wid_raw
        for k in WEAPONS:
            if norm(k) == norm(wid_raw): wid = k; break
        if wid not in WEAPONS: await update.message.reply_text(f"❌ سلاح '{wid_raw}' مش موجود."); return
        w = WEAPONS[wid]
        if w.get("one_use"):
            await update.message.reply_text("❌ القنابل لا تُباع في السوق الدولي."); return
        try: qty = int(qty_s); assert qty > 0
        except: await update.message.reply_text("❌ الكمية لازم رقم موجب."); return
        try: price = int(price_s); assert price > 0
        except: await update.message.reply_text("❌ السعر لازم رقم موجب."); return
        owned = p.get("weapons",{}).get(wid, 0)
        if owned < qty:
            await update.message.reply_text(f"❌ عندك {owned} فقط من {w['name']}."); return
        # اخصم من المخزون وضع في السوق
        data["players"][str(uid)]["weapons"][wid] = owned - qty
        data.setdefault("market",[]).append({
            "type": "weapons", "weapon_id": wid, "qty": qty, "price": price,
            "seller_uid": str(uid), "seller_name": p["country_name"],
            "created_at": time.time(),
        })
        save_data(data)
        await update.message.reply_text(
            f"✅ *تم عرض السلاح!*\n{sep()}\n"
            f"{w['emoji']} {w['name']} ×{qty}\n"
            f"💰 السعر: {CUR}{price:,}\n"
            f"⏳ العرض يُلغى تلقائياً بعد 24 ساعة", parse_mode="Markdown")
        return

    if ntext.startswith("شراء من سوق "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        try: idx = int(ntext.replace("شراء من سوق","").strip()) - 1
        except: await update.message.reply_text("❌ رقم غير صحيح."); return
        market = [m for m in data.get("market",[]) if m.get("type") == "weapons"]
        if idx < 0 or idx >= len(market):
            await update.message.reply_text("❌ رقم العرض مش موجود."); return
        offer = market[idx]
        if offer["seller_uid"] == str(uid):
            await update.message.reply_text("❌ مينفعش تشتري عرضك الخاص!"); return
        if p["gold"] < offer["price"]:
            await update.message.reply_text(f"❌ محتاج {offer['price']:,}¥. عندك {p['gold']:,}."); return
        w = WEAPONS.get(offer["weapon_id"],{})
        # نقل المال والسلاح
        data["players"][str(uid)]["gold"] -= offer["price"]
        data["players"][offer["seller_uid"]]["gold"] = data["players"][offer["seller_uid"]].get("gold",0) + offer["price"]
        cur_weap = data["players"][str(uid)].get("weapons",{}).get(offer["weapon_id"],0)
        data["players"][str(uid)].setdefault("weapons",{})[offer["weapon_id"]] = cur_weap + offer["qty"]
        # إزالة من السوق
        data["market"] = [m for m in data.get("market",[]) if m is not offer]
        save_data(data)
        await update.message.reply_text(
            f"✅ *تم الشراء!*\n{sep()}\n"
            f"{w.get('emoji','🔫')} {w.get('name', offer['weapon_id'])} ×{offer['qty']}\n"
            f"💰 -{CUR}{offer['price']:,}", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(offer["seller_uid"]),
                text=f"💰 *بيعت!*\n{sep()}\n{w.get('emoji','🔫')} {w.get('name','')} ×{offer['qty']}\n"
                     f"+{CUR}{offer['price']:,} في خزينتك", parse_mode="Markdown")
        except: pass
        return

    # ======= احمي دولة =======
    if ntext.startswith("احمي "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        tname = ntext.replace("احمي","").strip()
        tuid, tp = find_by_name(data, tname)
        if not tp:
            await update.message.reply_text(f"❌ مش لاقي دولة '{tname}'."); return
        if tuid == str(uid):
            await update.message.reply_text("❌ مينفعش تحمي نفسك!"); return
        if tp.get("protected_by"):
            await update.message.reply_text(
                f"❌ *{tp['country_name']}* محمية بالفعل بواسطة *{tp['protected_by']}*.",
                parse_mode="Markdown"); return
        if p["country_name"] in tp.get("protects", []):
            await update.message.reply_text(f"❌ بتحمي *{tp['country_name']}* بالفعل.", parse_mode="Markdown"); return

        # لو الدولة تحت احتلالك — حماية فورية بدون موافقة
        is_my_occupied = tp.get("occupied_by") == p["country_name"] or tp.get("colony_of") == p["country_name"]
        if is_my_occupied:
            data["players"][tuid]["protected_by"] = p["country_name"]
            data["players"][str(uid)].setdefault("protects", []).append(tp["country_name"])
            save_data(data)
            await update.message.reply_text(
                f"🛡️ *حماية مفعّلة!*\n{sep()}\n"
                f"جيشك يحمي *{tp['country_name']}* فوراً\n"
                f"أي هجوم عليها = مواجهة جيشك أنت!",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🛡️ *دولتك تحت الحماية!*\n{sep()}\n"
                         f"*{p['country_name']}* وفّر حماية عسكرية لدولتك.", parse_mode="Markdown")
            except: pass
        else:
            # دولة مستقلة — أرسل طلب موافقة
            data.setdefault("pending_protection", {})[str(tuid)] = {
                "from_uid": str(uid),
                "from_name": p["country_name"],
                "target_name": tp["country_name"],
                "time": time.time(),
            }
            save_data(data)
            await update.message.reply_text(
                f"📨 *تم إرسال طلب الحماية!*\n{sep()}\n"
                f"انتظر موافقة *{tp['country_name']}*\n"
                f"⏳ الطلب ينتهي بعد 10 دقائق",
                parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🛡️ *طلب حماية!*\n{sep()}\n"
                         f"*{p['country_name']}* يعرض حماية دولتك عسكرياً\n"
                         f"✅ `قبول الحماية` | ❌ `رفض الحماية`", parse_mode="Markdown")
            except: pass
        return

    # ======= قبول / رفض الحماية =======
    if ntext in ["قبول الحمايه", "قبول الحماية"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        req = data.get("pending_protection", {}).get(str(uid))
        if not req:
            await update.message.reply_text("❌ مفيش طلب حماية معلق ليك."); return
        if time.time() - req["time"] > 600:
            data["pending_protection"].pop(str(uid), None)
            save_data(data)
            await update.message.reply_text("❌ الطلب انتهت مدته."); return
        prot_uid = req["from_uid"]
        prot_p   = data["players"].get(prot_uid)
        if not prot_p:
            data["pending_protection"].pop(str(uid), None); save_data(data)
            await update.message.reply_text("❌ الدولة الحامية مش موجودة."); return
        data["players"][str(uid)]["protected_by"] = req["from_name"]
        data["players"][prot_uid].setdefault("protects", []).append(p["country_name"])
        data["pending_protection"].pop(str(uid), None)
        save_data(data)
        await update.message.reply_text(
            f"🛡️ *قبلت الحماية!*\n{sep()}\n"
            f"جيش *{req['from_name']}* يحمي دولتك الآن\n"
            f"أي هجوم عليك = مواجهة جيشهم!", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(prot_uid),
                text=f"✅ *{p['country_name']}* قبل حمايتك!\nجيشك يدافع عنهم الآن 🛡️", parse_mode="Markdown")
        except: pass
        return

    if ntext in ["رفض الحمايه", "رفض الحماية"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        req = data.get("pending_protection", {}).get(str(uid))
        if not req:
            await update.message.reply_text("❌ مفيش طلب حماية معلق ليك."); return
        prot_uid = req["from_uid"]
        data["pending_protection"].pop(str(uid), None)
        save_data(data)
        await update.message.reply_text("❌ رفضت طلب الحماية.")
        try:
            await context.bot.send_message(chat_id=int(prot_uid),
                text=f"❌ *{req['target_name']}* رفض طلب حمايتك.", parse_mode="Markdown")
        except: pass
        return

    # ======= الغاء الحماية =======
    if ntext.startswith("الغاء الحمايه") or ntext.startswith("الغاء الحماية"):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        rest = ntext.replace("الغاء الحمايه","").replace("الغاء الحماية","").strip()
        # لو المُحمَى هو اللي بيلغي
        if not rest:
            protector_name = p.get("protected_by")
            if not protector_name:
                await update.message.reply_text("❌ دولتك مش محمية."); return
            prot_uid, prot_p = find_by_name(data, protector_name)
            data["players"][str(uid)]["protected_by"] = None
            if prot_p:
                data["players"][prot_uid]["protects"] = [x for x in prot_p.get("protects",[]) if norm(x) != norm(p["country_name"])]
            save_data(data)
            await update.message.reply_text(f"🚫 ألغيت حماية *{protector_name}* لدولتك.", parse_mode="Markdown")
            try:
                if prot_p:
                    await context.bot.send_message(chat_id=int(prot_uid),
                        text=f"🚫 *{p['country_name']}* ألغى حمايتك لهم.", parse_mode="Markdown")
            except: pass
            return
        # لو الحامي هو اللي بيلغي
        tuid, tp = find_by_name(data, rest)
        if not tp:
            await update.message.reply_text(f"❌ مش لاقي دولة '{rest}'."); return
        if norm(tp.get("protected_by","")) != norm(p["country_name"]):
            await update.message.reply_text(f"❌ مش بتحمي *{tp['country_name']}*.", parse_mode="Markdown"); return
        data["players"][tuid]["protected_by"] = None
        data["players"][str(uid)]["protects"] = [x for x in p.get("protects",[]) if norm(x) != norm(tp["country_name"])]
        save_data(data)
        await update.message.reply_text(f"🚫 ألغيت حمايتك لـ *{tp['country_name']}*.", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"🚫 *{p['country_name']}* ألغى حمايته لدولتك.", parse_mode="Markdown")
        except: pass
        return

    # ======= تحويل مثاقيل =======
    if ntext.startswith("تحويل "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        parts = text.split()
        if len(parts)!=3: await update.message.reply_text("❌ الصيغة: تحويل [مبلغ] [كود]", parse_mode="Markdown"); return
        try: amount=int(parts[1]); assert amount>0
        except: await update.message.reply_text("❌ المبلغ لازم رقم موجب."); return
        if p["gold"]<amount: await update.message.reply_text(f"❌ عندك {p['gold']:,} بس."); return
        tuid, tp = find_by_code(data, parts[2])
        if not tp: await update.message.reply_text("❌ مش لاقي لاعب."); return
        if tuid==str(uid): await update.message.reply_text("❌ مينفعش تحول لنفسك!"); return
        data["players"][str(uid)]["gold"] -= amount
        data["players"][tuid]["gold"]     += amount
        save_data(data)
        await update.message.reply_text(
            f"💸 *تحويل ناجح!*\n{sep()}\nالى: *{tp['country_name']}*\n{amount:,}¥\nرصيدك: {p['gold']-amount:,}",
            parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(tuid),
                text=f"💰 *تحويل وارد!*\n{sep()}\nمن: *{p['country_name']}*\n+{amount:,}¥", parse_mode="Markdown")
        except: pass
        return

    # ======= دولي — إمبراطوريتي كاملة =======
    if ntext in ["دولي", "امبراطوريتي", "اراضيي", "ممتلكاتي"]:
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        my_name = p["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")

        # الدولة الأم
        total_army = p.get("army", 0)
        total_gold = p.get("gold", 0)
        total_terr = p.get("territories", 1)

        msg = f"{box_title('🌍', 'إمبراطورية ' + my_name)}\n"

        # حالة الدولة الأم
        if p.get("occupied_by"):
            msg += f"🏴 *الدولة الأم:* {my_name}\n   _(محتلة بواسطة {p['occupied_by']})_\n"
        elif p.get("colony_of"):
            msg += f"🏴 *الدولة الأم:* {my_name}\n   _(مستعمرة لـ {p['colony_of']})_\n"
        else:
            lvl = get_level(p.get("xp",0))
            msg += (
                f"{lvl['emoji']} *{my_name}* | 📍 {p['region']}\n"
                f"   ⚔️ {p['army']:,}  💰 {CUR}{p['gold']:,}  🗺️ {p['territories']}\n"
            )

        # الدول المحتلة
        occupied_list = [(uid2, p2) for uid2, p2 in data["players"].items()
                         if p2.get("occupied_by") == my_name]
        # الدول المستعمرة
        colony_list   = [(uid2, p2) for uid2, p2 in data["players"].items()
                         if p2.get("colony_of") == my_name]

        if occupied_list:
            msg += f"\n{sep()}\n🔴 *محتلات — {len(occupied_list)} دولة:*\n"
            for _, op in occupied_list:
                oname = op["country_name"].replace(" (محتلة)","")
                happy  = calc_happiness(op)
                msg += (
                    f"  🏴 *{oname}* | 📍 {op.get('region','')}\n"
                    f"     ⚔️ {op.get('army',0):,}  💰 {CUR}{op.get('gold',0):,}"
                    f"  🗺️ {op.get('territories',1)}  😊 {happy}%\n"
                )
                total_army += op.get("army",0)
                total_gold += op.get("gold",0)
                total_terr += op.get("territories",1)

        if colony_list:
            msg += f"\n{sep()}\n🟠 *مستعمرات — {len(colony_list)} دولة:*\n"
            for _, cp in colony_list:
                cname = cp["country_name"].replace(" (مستعمرة)","")
                happy  = calc_happiness(cp)
                ports  = p.get("facilities",{}).get("ميناء",0)
                tax_r  = min(0.80, 0.40 + ports*0.15 + (0.10 if "هيمنة_اقتصادية" in get_perks(p.get("xp",0)) else 0))
                est_income, _, _ = calc_colony_harvest(cp)
                msg += (
                    f"  🏴 *{cname}* | 📍 {cp.get('region','')}\n"
                    f"     ⚔️ {cp.get('army',0):,}  💰 {CUR}{cp.get('gold',0):,}"
                    f"  🗺️ {cp.get('territories',1)}  😊 {happy}%\n"
                    f"     📥 دخل: ~{CUR}{int(est_income*tax_r):,}/دورة\n"
                )
                total_army += cp.get("army",0)
                total_gold += cp.get("gold",0)
                total_terr += cp.get("territories",1)

        if not occupied_list and not colony_list and not p.get("occupied_by") and not p.get("colony_of"):
            msg += f"\n{sep()}\n💡 _لا توجد أراضٍ تابعة بعد_\n_احتل دولة واستعمرها لتوسيع نفوذك!_\n"

        # الإجمالي
        if occupied_list or colony_list:
            n_countries = 1 + len(occupied_list) + len(colony_list)
            msg += (
                f"\n{sep()}\n"
                f"📊 *إجمالي الإمبراطورية*\n"
                f"🏳️ {n_countries} دولة  ⚔️ {total_army:,}  💰 {CUR}{total_gold:,}  🗺️ {total_terr}\n"
            )

        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= المتصدرين =======
    if ntext in ["المتصدرين","الترتيب"]:
        if not data["players"]: await update.message.reply_text("لا يوجد لاعبين."); return
        sorted_p = sorted(data["players"].items(), key=lambda x:x[1].get("xp",0), reverse=True)
        msg = f"{box_title('🏆','المتصدرين')}\n\n"
        medals = ["🥇","🥈","🥉"]
        for i,(puid,pp) in enumerate(sorted_p[:10]):
            m    = medals[i] if i<3 else f"  {i+1}."
            lvl  = get_level(pp.get("xp",0))
            bar_xp = progress_bar(pp.get("xp",0), 25000, 8)
            tag  = " 🗡️" if pp.get("traitor") else ""
            occ  = " 🏴" if pp.get("occupied_by") else ""
            army = pp.get("army",0)
            gold = pp.get("gold",0)
            msg += (
                f"{m} {lvl['emoji']} *{pp['country_name']}*{tag}{occ}\n"
                f"     `{bar_xp}` {pp.get('xp',0):,} XP — Lv.{lvl['level']} {lvl['name']}\n"
                f"     ⚔️ {army:,}  💰 {CUR}{gold:,}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= قائمة الدول =======
    if ntext in ["قائمه الدول","الدول"]:
        if not data["players"]: await update.message.reply_text("لا يوجد دول."); return
        sorted_countries = sorted(data["players"].items(), key=lambda x:x[1].get("xp",0), reverse=True)
        msg = f"{box_title('🗺️','الدول')} — {len(data['players'])} دولة\n\n"
        for i,(puid,pp) in enumerate(sorted_countries, 1):
            lvl  = get_level(pp.get("xp",0))
            tag  = " 🗡️" if pp.get("traitor") else ""
            occ  = f" _(محتلة)_" if pp.get("occupied_by") else ""
            col  = f" _(مستعمرة)_" if pp.get("colony_of") else ""
            msg += (
                f"{i}. {lvl['emoji']} *{pp['country_name']}*{tag}{occ}{col}\n"
                f"   📍 {pp['region']} | ⚔️ {pp.get('army',0):,} | 💰 {CUR}{pp.get('gold',0):,} | 🗺️ {pp.get('territories',1)}\n\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= خريطة =======
    if ntext in ["خريطه","الخريطه"]:
        if not data["players"]: await update.message.reply_text("لا يوجد دول."); return
        await update.message.reply_text("🗺️ جاري التوليد...")
        try:
            buf = generate_map(data["players"], data)
            cap = "🗺️ *خريطة الشرق الاوسط*\n"
            for pp in data["players"].values():
                lvl = get_level(pp.get("xp",0))
                cap += f"{lvl['emoji']} *{pp['country_name']}* ← {pp['region']}\n"
            await update.message.reply_photo(photo=buf, caption=cap, parse_mode="Markdown")
        except Exception as e: await update.message.reply_text(f"❌ خطا: {e}")
        return

    # ======= انشاء حلف/منظمة =======
    if ntext.startswith("انشاء حلف ") or ntext.startswith("انشاء حلف "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        org_name = ntext.replace("انشاء حلف","").replace("إنشاء حلف","").strip()
        if not org_name:
            await update.message.reply_text("❌ لازم تكتب اسم الحلف.\n مثال: `انشاء حلف حلف الشمال`", parse_mode="Markdown"); return
        if len(org_name) > 30:
            await update.message.reply_text("❌ اسم الحلف طويل جداً (أقصاه 30 حرف)."); return
        orgs = data.get("organizations", {})
        if org_name in orgs:
            await update.message.reply_text(f"❌ حلف باسم *{org_name}* موجود بالفعل!", parse_mode="Markdown"); return
        # تحقق إن اللاعب مش مؤسس حلف آخر
        for on, ov in orgs.items():
            if ov["founder"] == p["country_name"]:
                await update.message.reply_text(
                    f"❌ أنت مؤسس حلف *{on}* بالفعل!\nلازم تحله أول: `حل حلف {on}`",
                    parse_mode="Markdown"); return
        orgs[org_name] = {
            "founder":    p["country_name"],
            "members":    [p["country_name"]],
            "created_at": time.time(),
        }
        data["organizations"] = orgs
        save_data(data)
        await update.message.reply_text(
            f"{box_title('🏛️','تم تأسيس الحلف!')}\n"
            f"🏳️ الاسم: *{org_name}*\n"
            f"👑 المؤسس: *{p['country_name']}*\n"
            f"{sep()}\n"
            f"📨 لدعوة دولة: `دعوة {org_name} [اسم الدولة]`\n"
            f"📋 لعرض الأحلاف: `قائمة الاحلاف`",
            parse_mode="Markdown")
        return

    # ======= دعوة دولة لحلف =======
    if ntext.startswith("دعوه "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        rest = ntext.replace("دعوه","",1).strip()
        # البحث عن أطول اسم حلف يطابق البداية
        orgs     = data.get("organizations", {})
        matched_org  = None
        matched_country = None
        for org_name in sorted(orgs.keys(), key=len, reverse=True):
            if rest.startswith(org_name):
                matched_org     = org_name
                matched_country = rest[len(org_name):].strip()
                break
        if not matched_org or not matched_country:
            await update.message.reply_text(
                "❌ الصيغة:\n`دعوة [اسم الحلف] [اسم الدولة]`", parse_mode="Markdown"); return
        org = orgs[matched_org]
        if org["founder"] != p["country_name"]:
            await update.message.reply_text(f"❌ فقط مؤسس الحلف يقدر يدعو دول."); return
        tuid, tp = find_by_name(data, matched_country)
        if not tp:
            await update.message.reply_text(f"❌ مش لاقي دولة اسمها *{matched_country}*.", parse_mode="Markdown"); return
        if tuid == str(uid):
            await update.message.reply_text("❌ أنت أصلاً عضو!"); return
        if tp["country_name"] in org["members"]:
            await update.message.reply_text(f"❌ *{tp['country_name']}* عضو بالفعل!", parse_mode="Markdown"); return
        # حفظ طلب الدعوة
        req_key = f"org_{matched_org}_{tuid}"
        data.setdefault("org_invites", {})[req_key] = {
            "org_name":   matched_org,
            "from_name":  p["country_name"],
            "to_uid":     str(tuid),
            "to_name":    tp["country_name"],
            "time":       time.time(),
        }
        save_data(data)
        await update.message.reply_text(
            f"📨 *تم إرسال الدعوة!*\n{sep()}\n"
            f"دعوة لـ *{tp['country_name']}* للانضمام لـ *{matched_org}*\n"
            f"⏳ في انتظار القبول...", parse_mode="Markdown")
        try:
            kbd = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ قبول", callback_data=f"org_accept_{req_key}"),
                InlineKeyboardButton("❌ رفض",  callback_data=f"org_reject_{req_key}"),
            ]])
            await context.bot.send_message(chat_id=int(tuid),
                text=f"🏛️ *دعوة لحلف!*\n{sep()}\n"
                     f"*{p['country_name']}* يدعوك للانضمام لحلف *{matched_org}*!\n"
                     f"هل توافق؟",
                reply_markup=kbd, parse_mode="Markdown")
        except: pass
        return

    # ======= طرد دولة من الحلف =======
    if ntext.startswith("طرد من حلف "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        rest = ntext.replace("طرد من حلف","",1).strip()
        orgs = data.get("organizations", {})
        matched_org = None
        matched_country = None
        for org_name in sorted(orgs.keys(), key=len, reverse=True):
            if rest.startswith(org_name):
                matched_org     = org_name
                matched_country = rest[len(org_name):].strip()
                break
        if not matched_org or not matched_country:
            await update.message.reply_text("❌ الصيغة:\n`طرد من حلف [اسم الحلف] [اسم الدولة]`", parse_mode="Markdown"); return
        org = orgs[matched_org]
        if org["founder"] != p["country_name"]:
            await update.message.reply_text("❌ فقط المؤسس يقدر يطرد."); return
        if matched_country == p["country_name"]:
            await update.message.reply_text("❌ مينفعش تطرد نفسك! استخدم `حل حلف [اسم]` لحل الحلف."); return
        if matched_country not in org["members"]:
            await update.message.reply_text(f"❌ *{matched_country}* مش عضو في الحلف.", parse_mode="Markdown"); return
        data["organizations"][matched_org]["members"].remove(matched_country)
        save_data(data)
        await update.message.reply_text(
            f"🚪 *تم الطرد!*\n{sep()}\n*{matched_country}* طُرد من حلف *{matched_org}*.",
            parse_mode="Markdown")
        # إبلاغ المطرود
        tuid, tp = find_by_name(data, matched_country)
        if tp:
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🚪 *تم طردك!*\n{sep()}\nطُردت من حلف *{matched_org}* بواسطة *{p['country_name']}*.",
                    parse_mode="Markdown")
            except: pass
        return

    # ======= مغادرة حلف =======
    if ntext.startswith("مغادره حلف "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        org_name = ntext.replace("مغادره حلف","",1).strip()
        orgs = data.get("organizations", {})
        if org_name not in orgs:
            await update.message.reply_text(f"❌ مش لاقي حلف اسمه *{org_name}*.", parse_mode="Markdown"); return
        org = orgs[org_name]
        if p["country_name"] not in org["members"]:
            await update.message.reply_text("❌ أنت مش عضو في هذا الحلف."); return
        if org["founder"] == p["country_name"]:
            await update.message.reply_text(
                f"❌ أنت المؤسس! لازم تحل الحلف: `حل حلف {org_name}`", parse_mode="Markdown"); return
        data["organizations"][org_name]["members"].remove(p["country_name"])
        save_data(data)
        await update.message.reply_text(
            f"🚪 *غادرت الحلف!*\n{sep()}\nغادرت حلف *{org_name}* ✅", parse_mode="Markdown")
        return

    # ======= حل حلف =======
    if ntext.startswith("حل حلف "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        org_name = ntext.replace("حل حلف","",1).strip()
        orgs = data.get("organizations", {})
        if org_name not in orgs:
            await update.message.reply_text(f"❌ مش لاقي حلف *{org_name}*.", parse_mode="Markdown"); return
        org = orgs[org_name]
        if org["founder"] != p["country_name"]:
            await update.message.reply_text("❌ فقط المؤسس يقدر يحل الحلف."); return
        members = org["members"].copy()
        del data["organizations"][org_name]
        save_data(data)
        await update.message.reply_text(
            f"🏴 *تم حل الحلف!*\n{sep()}\nحلف *{org_name}* حُلّ رسمياً.", parse_mode="Markdown")
        for m in members:
            if m == p["country_name"]: continue
            tuid, tp = find_by_name(data, m)
            if tp:
                try:
                    await context.bot.send_message(chat_id=int(tuid),
                        text=f"🏴 *حلف انتهى!*\n{sep()}\nحلف *{org_name}* حُلّ بواسطة المؤسس *{p['country_name']}*.",
                        parse_mode="Markdown")
                except: pass
        return

    # ======= قائمة الأحلاف =======
    if ntext in ["قائمه الاحلاف","قائمة الاحلاف","الاحلاف","المنظمات","الاحلاف والمنظمات"]:
        orgs = data.get("organizations", {})
        if not orgs:
            await update.message.reply_text(
                f"{box_title('🏛️','الأحلاف والمنظمات')}\n\nلا يوجد أحلاف حالياً.\n"
                f"💡 `انشاء حلف [الاسم]` لتأسيس حلف جديد!", parse_mode="Markdown"); return
        msg = f"{box_title('🏛️','الأحلاف والمنظمات')}\n\n"
        for i, (org_name, org) in enumerate(orgs.items(), 1):
            members_txt = "\n".join(f"    {'👑' if m==org['founder'] else '🔹'} {m}" for m in org["members"])
            msg += (
                f"*{i}. {org_name}*\n"
                f"  👑 المؤسس: {org['founder']}\n"
                f"  👥 الأعضاء ({len(org['members'])}):\n{members_txt}\n"
                f"{sep()}\n"
            )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= تفاصيل حلف =======
    if ntext.startswith("حلف "):
        org_name = ntext.replace("حلف","",1).strip()
        orgs = data.get("organizations", {})
        if org_name not in orgs:
            await update.message.reply_text(f"❌ مش لاقي حلف اسمه *{org_name}*.", parse_mode="Markdown"); return
        org = orgs[org_name]
        p   = get_player(data, uid)
        is_member  = p and p["country_name"] in org["members"]
        is_founder = p and p["country_name"] == org["founder"]
        members_lines = "\n".join(
            f"  {'👑' if m==org['founder'] else '🔹'} *{m}*"
            for m in org["members"]
        )
        created = time.strftime("%Y/%m/%d", time.localtime(org["created_at"]))
        actions = ""
        if is_founder:
            actions = f"\n{sep()}\n🔧 *أوامرك كمؤسس:*\n`دعوة {org_name} [اسم الدولة]`\n`طرد من حلف {org_name} [اسم]`\n`حل حلف {org_name}`"
        elif is_member:
            actions = f"\n{sep()}\n🚪 `مغادرة حلف {org_name}`"
        msg = (
            f"{box_title('🏛️', org_name)}\n"
            f"👑 المؤسس: *{org['founder']}*\n"
            f"📅 التأسيس: {created}\n"
            f"👥 الأعضاء ({len(org['members'])}):\n{members_lines}"
            f"{actions}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # ======= جيش الحلف — تشكيل الجيش الموحد =======
    if ntext.startswith("جيش الحلف ") or ntext.startswith("جيش حلف "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        org_name = ntext.replace("جيش الحلف","").replace("جيش حلف","").strip()
        orgs = data.get("organizations", {})
        if org_name not in orgs:
            await update.message.reply_text(f"❌ مش لاقي حلف *{org_name}*.", parse_mode="Markdown"); return
        org = orgs[org_name]
        if p["country_name"] not in org["members"]:
            await update.message.reply_text("❌ أنت مش عضو في هذا الحلف."); return
        members = org["members"]
        total_army = 0
        total_gold = 0
        lines = []
        for m in members:
            muid, mp = find_by_name(data, m)
            if not mp: continue
            army = mp.get("army", 0)
            gold = mp.get("gold", 0)
            lvl  = get_level(mp.get("xp",0))
            tag  = "👑" if m == org["founder"] else "🔹"
            total_army += army
            total_gold += gold
            lines.append(f"  {tag} *{m}*\n    ⚔️ {army:,} | 💰 {CUR}{gold:,} | {lvl['emoji']} Lv.{lvl['level']}")
        members_txt = "\n".join(lines)
        await update.message.reply_text(
            f"{box_title('⚔️','جيش حلف ' + org_name)}\n"
            f"{members_txt}\n"
            f"{sep()}\n"
            f"⚔️ *إجمالي الجيش:* {total_army:,} جندي\n"
            f"💰 *إجمالي الخزائن:* {CUR}{total_gold:,}\n"
            f"👥 الأعضاء: {len(members)}\n"
            f"{sep()}\n"
            f"💡 `هجوم جماعي {org_name} على [دولة]` للهجوم الموحد",
            parse_mode="Markdown")
        return

    # ======= هجوم جماعي — الحلف كله يهاجم دولة =======
    if ntext.startswith("هجوم جماعي "):
        p = get_player(data, uid)
        if not p: await update.message.reply_text("❌ مش مسجل."); return
        ok, err = check_sovereignty(p, "هجوم")
        if not ok: await update.message.reply_text(err, parse_mode="Markdown"); return
        rest = ntext.replace("هجوم جماعي","",1).strip()
        if " على " not in rest:
            await update.message.reply_text(
                "❌ الصيغة:\n`هجوم جماعي [اسم الحلف] على [اسم الدولة]`", parse_mode="Markdown"); return
        parts = rest.split(" على ", 1)
        org_name   = parts[0].strip()
        target_name= parts[1].strip()
        orgs = data.get("organizations", {})
        if org_name not in orgs:
            await update.message.reply_text(f"❌ مش لاقي حلف *{org_name}*.", parse_mode="Markdown"); return
        org = orgs[org_name]
        if p["country_name"] not in org["members"]:
            await update.message.reply_text("❌ أنت مش عضو في هذا الحلف."); return
        if org["founder"] != p["country_name"]:
            await update.message.reply_text(
                f"❌ فقط المؤسس *{org['founder']}* يقدر يأمر بالهجوم الجماعي.", parse_mode="Markdown"); return
        if not data.get("wars_enabled", True):
            await update.message.reply_text("🕊️ الحروب موقوفة حالياً."); return
        tuid, tp = find_by_name(data, target_name)
        if not tp: await update.message.reply_text(f"❌ مش لاقي دولة '{target_name}'."); return
        if tuid == str(uid):
            await update.message.reply_text("❌ مينفعش تهاجم نفسك!"); return
        if tp["country_name"] in org["members"]:
            await update.message.reply_text("❌ مينفعش تهاجم عضو في حلفك!"); return
        # فحص معاهدة السلام
        tp_clean = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
        peace = p.get("peace_treaties", {})
        if tp_clean in peace and peace[tp_clean] > time.time():
            remaining = int((peace[tp_clean] - time.time()) / 60)
            await update.message.reply_text(
                f"🕊️ معاهدة سلام سارية مع *{tp_clean}* لمدة {remaining} دقيقة أخرى.", parse_mode="Markdown"); return
        # احسب إجمالي جيش الحلف
        members   = org["members"]
        total_att = 0
        contributions = []
        active_members = []
        for m in members:
            muid, mp = find_by_name(data, m)
            if not mp or mp.get("army", 0) == 0: continue
            # نسبة المشاركة: 70-95% من كل عضو
            contrib = int(mp.get("army", 0) * random.uniform(0.70, 0.95))
            contrib = max(1, contrib)
            total_att += contrib
            contributions.append((muid, m, contrib, mp))
            active_members.append(m)
        if total_att == 0:
            await update.message.reply_text("❌ جيش الحلف صفر!"); return
        # بونص التنسيق الجماعي +20%
        coalition_bonus = 1.20
        total_att_final = int(total_att * coalition_bonus * random.uniform(0.85, 1.15))
        # دفاع الهدف
        base_def = tp.get("army", 0) * random.uniform(0.7, 1.3)
        def_perks = get_perks(tp.get("xp", 0))
        if "وزير_دفاع" in def_perks: base_def *= 1.08
        if "قوة_عظمى"  in def_perks: base_def *= 1.15
        # دفاع المحتل/المستعمِر
        occ_defense_txt = ""
        owner_name = tp.get("occupied_by") or tp.get("colony_of")
        if owner_name:
            o_uid, o_p = find_by_name(data, owner_name)
            if o_p and o_uid not in [c[0] for c in contributions]:
                owner_def = o_p.get("army", 0) * random.uniform(0.60, 0.90)
                base_def += owner_def
                occ_defense_txt = f"\n🛡️ *{owner_name}* دافع (+{int(owner_def):,})"
                try:
                    await context.bot.send_message(chat_id=int(o_uid),
                        text=f"⚠️ *حلف {org_name}* هاجم {tp['country_name']} المحمية بواسطتك!\n"
                             f"جيشك دافع بـ {int(owner_def):,} جندي 🛡️", parse_mode="Markdown")
                except: pass
        victory = total_att_final > base_def
        result_lines = []
        total_losses = 0
        if victory:
            # خسائر الحلف
            for muid2, mname, contrib2, mp2 in contributions:
                loss_pct = random.uniform(0.08, 0.20)
                loss = max(1, int(mp2.get("army",0) * loss_pct))
                data["players"][muid2]["army"] = max(0, mp2["army"] - loss)
                data["players"][muid2]["wars_won"] = mp2.get("wars_won",0) + 1
                total_losses += loss
                result_lines.append(f"  🔹 *{mname}*: -{loss:,} جندي")
            # خسائر المدافع — نفس نسب الهجوم الفردي بس أشد
            def_loss_pct = random.uniform(0.25, 0.50)
            def_loss = max(10, int(tp.get("army",0) * def_loss_pct))
            loot = min(tp.get("gold",0) // 2, max(1000, tp.get("gold",0) // 3))
            loser_army_after = max(0, tp["army"] - def_loss)
            # الاحتلال: نفس شرط الهجوم الفردي
            founder_army_after = data["players"][str(uid)].get("army", p.get("army",0))
            conquered = loser_army_after == 0 or loser_army_after < founder_army_after * 0.2
            data["players"][tuid]["army"]      = loser_army_after
            data["players"][tuid]["gold"]      = max(0, tp.get("gold",0) - loot)
            data["players"][tuid]["wars_lost"] = tp.get("wars_lost",0) + 1
            # المؤسس يأخذ أرض واحدة (زي الهجوم الفردي)
            data["players"][str(uid)]["territories"] = p.get("territories",1) + 1
            data["players"][tuid]["territories"]     = max(1, tp.get("territories",1) - 1)
            # وزّع الغنيمة على الأعضاء بالتساوي
            share = loot // len(contributions) if contributions else 0
            for muid2, mname, contrib2, mp2 in contributions:
                data["players"][muid2]["gold"] = data["players"][muid2].get("gold",0) + share
            # XP للمؤسس
            add_xp(data, uid, 300)
            # تحديث قوائم الحرب
            if tp_clean not in p.get("at_war",[]):
                data["players"][str(uid)].setdefault("at_war",[]).append(tp_clean)
            if p["country_name"] not in tp.get("at_war",[]):
                data["players"][tuid].setdefault("at_war",[]).append(p["country_name"])
            # ======= احتلال — نفس منطق الهجوم الفردي =======
            conquest_txt = ""
            if conquered:
                # نقل علم المؤسس على أراضي المهزوم
                loser_flag  = os.path.join(FLAGS_DIR, f"{tp['region']}.png")
                winner_flag = os.path.join(FLAGS_DIR, f"{p['region']}.png")
                if os.path.exists(winner_flag):
                    try:
                        import shutil
                        orig_backup = os.path.join(FLAGS_DIR, f"{tp['region']}_original.png")
                        if os.path.exists(loser_flag) and not os.path.exists(orig_backup):
                            shutil.copy2(loser_flag, orig_backup)
                        shutil.copy2(winner_flag, loser_flag)
                    except: pass
                clean_name = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
                data["players"][tuid]["country_name"] = f"{clean_name} (محتلة)"
                data["players"][tuid]["occupied_by"]  = p["country_name"]
                data["players"][str(uid)]["territories"] += tp.get("territories", 0)
                data["players"][tuid]["territories"]   = 0
                looted_gold = transfer_conquest(data, str(uid), tuid)
                conquest_txt = (
                    f"\n{sep()}\n🏳️ *احتلال جماعي!*\n"
                    f"*{clean_name}* محتلة بواسطة *{p['country_name']}* (مؤسس الحلف)\n"
                    f"💰 نُهبت: {looted_gold:,}¥ إضافية للمؤسس\n"
                    f"⚔️ يمكن التحرر عبر `ثورة`"
                )
                for muid2, mname, contrib2, mp2 in contributions:
                    if muid2 == str(uid): continue
                    try:
                        await context.bot.send_message(chat_id=int(muid2),
                            text=f"🏳️ *احتلال جماعي!*\n{sep()}\n"
                                 f"*{clean_name}* احتُلت وضُمت لأراضي المؤسس *{p['country_name']}*",
                            parse_mode="Markdown")
                    except: pass
            save_data(data)
            contributions_txt = "\n".join(result_lines)
            msg = (
                f"⚔️ *هجوم جماعي — {org_name}*\n{sep()}\n"
                f"🎯 الهدف: *{tp['country_name']}*\n\n"
                f"🏆 *انتصار الحلف!*\n{sep()}\n"
                f"⚔️ جيش الحلف: *{total_att_final:,}* (+20% تنسيق)\n"
                f"🛡️ دفاع العدو: *{int(base_def):,}*\n"
                f"{occ_defense_txt}\n"
                f"{sep()}\n"
                f"💀 خسائر الحلف:\n{contributions_txt}\n"
                f"💀 خسائر العدو: *{def_loss:,}*\n"
                f"{sep()}\n"
                f"💰 غنيمة: *{CUR}{loot:,}* ({CUR}{share:,}/عضو)\n"
                f"⭐ +300 XP للقائد"
                f"{conquest_txt}"
            )
            # إشعار الأعضاء
            for muid2, mname, contrib2, mp2 in contributions:
                if muid2 == str(uid): continue
                try:
                    await context.bot.send_message(chat_id=int(muid2),
                        text=f"⚔️ *الحلف انتصر!*\n{sep()}\n"
                             f"هجوم *{org_name}* على *{tp['country_name']}* نجح!\n"
                             f"💰 نصيبك: +{CUR}{share:,}\n"
                             f"💀 خسائرك: -{next((c for m,c in [(x[1],x[2]) for x in contributions] if m==mname), 0):,} جندي",
                        parse_mode="Markdown")
                except: pass
            # إشعار المهزوم
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🚨 *هجوم جماعي!*\n{sep()}\n"
                         f"حلف *{org_name}* هاجمك بـ {len(contributions)} دول!\n"
                         f"💸 خسرت: *{CUR}{loot:,}* | 💀 *{def_loss:,}* جندي",
                    parse_mode="Markdown")
            except: pass
        else:
            # هزيمة الحلف
            for muid2, mname, contrib2, mp2 in contributions:
                loss_pct = random.uniform(0.15, 0.30)
                loss = max(1, int(mp2.get("army",0) * loss_pct))
                data["players"][muid2]["army"] = max(0, mp2["army"] - loss)
                data["players"][muid2]["wars_lost"] = mp2.get("wars_lost",0) + 1
                total_losses += loss
                result_lines.append(f"  🔹 *{mname}*: -{loss:,} جندي")
            def_loss = max(1, int(tp.get("army",0) * random.uniform(0.05, 0.15)))
            data["players"][tuid]["army"] = max(0, tp["army"] - def_loss)
            save_data(data)
            contributions_txt = "\n".join(result_lines)
            msg = (
                f"⚔️ *هجوم جماعي — {org_name}*\n{sep()}\n"
                f"🎯 الهدف: *{tp['country_name']}*\n\n"
                f"❌ *الحلف هُزم!*\n{sep()}\n"
                f"⚔️ جيش الحلف: *{total_att_final:,}*\n"
                f"🛡️ دفاع العدو: *{int(base_def):,}*\n"
                f"{occ_defense_txt}\n"
                f"{sep()}\n"
                f"💀 خسائر الحلف:\n{contributions_txt}\n"
                f"💡 أعيدوا تنظيم الجيش وحاولوا مجدداً"
            )
            for muid2, mname, contrib2, mp2 in contributions:
                if muid2 == str(uid): continue
                try:
                    await context.bot.send_message(chat_id=int(muid2),
                        text=f"❌ *الهجوم الجماعي فشل*\n{sep()}\n"
                             f"هجوم *{org_name}* على *{tp['country_name']}* فشل!\n"
                             f"💀 جيشك خسر بعض الجنود.",
                        parse_mode="Markdown")
                except: pass
        await safe_md(update.message, msg)
        return

    # ======= إحصائيات اللعبة =======
    if ntext in ["احصائيات اللعبة","احصائيات","إحصائيات اللعبة","إحصائيات"]:
        players = data.get("players", {})
        if not players:
            await update.message.reply_text("📊 لا يوجد لاعبين بعد."); return

        now = time.time()

        # ── أرقام أساسية ──
        total_players = len(players)
        total_gold    = sum(p.get("gold", 0)  for p in players.values())
        total_army    = sum(p.get("army", 0)  for p in players.values())
        total_wars    = sum(len(p.get("at_war", [])) for p in players.values()) // 2
        total_occ     = sum(1 for p in players.values() if p.get("occupied_by"))
        total_col     = sum(1 for p in players.values() if p.get("colony_of"))

        # ── أغنى / أقوى / أكبر ──
        richest   = max(players.values(), key=lambda p: p.get("gold", 0))
        strongest = max(players.values(), key=lambda p: p.get("army", 0))
        biggest   = max(players.values(), key=lambda p: p.get("territories", 1))
        most_xp   = max(players.values(), key=lambda p: p.get("xp", 0))

        # ── أكثر دولة تعرضت للاحتلال ──
        most_conquered = max(players.values(), key=lambda p: p.get("wars_lost", 0))

        # ── الدول في حرب الآن ──
        at_war_now = [(p["country_name"], p["at_war"])
                      for p in players.values() if p.get("at_war")]

        # ── الأحلاف ──
        orgs = data.get("organizations", {})
        biggest_org = max(orgs.items(), key=lambda x: len(x[1]["members"])) if orgs else None

        # ── رضا الشعب ──
        happiness_list = [(p["country_name"], calc_happiness(p)) for p in players.values()]
        happiest  = max(happiness_list, key=lambda x: x[1])
        unhappiest= min(happiness_list, key=lambda x: x[1])

        # ── آخر كارثة ──
        last_dis_ago = now - data.get("last_disaster", 0)
        if last_dis_ago < 3600:
            last_dis_txt = f"منذ {int(last_dis_ago//60)} دقيقة"
        else:
            last_dis_txt = f"منذ {int(last_dis_ago//3600)} ساعة"

        msg = (
            f"{box_title('📊','إحصائيات اللعبة')}\n\n"
            f"━━ 🌍 *عام* ━━\n"
            f"👥 الدول: *{total_players}*\n"
            f"💰 إجمالي المثاقيل: *{CUR}{total_gold:,}*\n"
            f"⚔️ إجمالي الجيوش: *{total_army:,}* جندي\n"
            f"🔥 حروب نشطة: *{total_wars}*\n"
            f"🏴 محتلات: *{total_occ}*  |  مستعمرات: *{total_col}*\n"
            f"🏛️ الأحلاف: *{len(orgs)}*\n\n"
            f"━━ 🏆 *السجلات* ━━\n"
            f"💰 أغنى دولة:    *{richest['country_name']}* — {CUR}{richest.get('gold',0):,}\n"
            f"⚔️ أقوى جيش:    *{strongest['country_name']}* — {strongest.get('army',0):,}\n"
            f"🗺️ أكبر أراضي:  *{biggest['country_name']}* — {biggest.get('territories',1)} منطقة\n"
            f"⭐ أعلى XP:      *{most_xp['country_name']}* — {most_xp.get('xp',0):,} XP\n"
            f"😔 أكثر هزائم:  *{most_conquered['country_name']}* — {most_conquered.get('wars_lost',0)} هزيمة\n\n"
            f"━━ 😊 *الرضا الشعبي* ━━\n"
            f"🟢 الأسعد: *{happiest[0]}* — {happiest[1]}%\n"
            f"🔴 الأتعس: *{unhappiest[0]}* — {unhappiest[1]}%\n\n"
        )

        if at_war_now:
            msg += f"━━ ⚔️ *الحروب النشطة* ━━\n"
            for name, enemies in at_war_now[:5]:
                msg += f"🔥 *{name}* ↔ {', '.join(enemies[:2])}\n"
            if len(at_war_now) > 5:
                msg += f"  _و{len(at_war_now)-5} حروب أخرى..._\n"
            msg += "\n"

        if biggest_org:
            org_name, org_data = biggest_org
            msg += (
                f"━━ 🏛️ *أكبر حلف* ━━\n"
                f"*{org_name}* — {len(org_data['members'])} أعضاء\n"
                f"المؤسس: {org_data['founder']}\n\n"
            )

        msg += f"{sep()}\n🌪️ آخر كارثة: {last_dis_txt}"

        await safe_md(update.message, msg)
        return

    # ======= MEG — شرح مفصل للعبة =======
    if ntext in ["meg", "meg!"]:
        await update.message.reply_text(
            f"{box_title('🌍','Middle East Game — دليل اللاعب')}\n\n"
            f"*لعبة الشرق الأوسط* هي لعبة جيوسياسية استراتيجية تدور في "
            f"منطقة الشرق الأوسط. تبني دولتك من الصفر وتطورها عبر الاقتصاد "
            f"والجيش والدبلوماسية.\n",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('🎮','كيف تبدأ؟')}\n\n"
            f"1️⃣ اكتب `انشاء دولة` — سيصلك كود\n"
            f"2️⃣ ابعت الكود للأدمن لتفعيل دولتك\n"
            f"3️⃣ اختار منطقتك من خريطة الشرق الأوسط\n"
            f"4️⃣ ابدأ باللعب!\n\n"
            f"*المناطق المتاحة:*\n"
            f"السعودية | الكويت | العراق | إيران | قطر\n"
            f"الإمارات | عمان | البحرين | اليمن | مصر\n"
            f"سوريا | لبنان | الأردن | فلسطين | تركيا\n"
            f"ليبيا | السودان | إسرائيل | قبرص",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('💰','الاقتصاد')}\n\n"
            f"*الضرائب:* كل 10 دقايق اكتب `جمع الضرائب`\n"
            f"الدخل = عدد الأراضي × بونص البنية التحتية\n\n"
            f"*المزارع:* `بناء مزرعة` — تنتج محاصيل تُباع تلقائياً\n"
            f"كل منطقة لها محاصيل خاصة (قمح، نفط، مثاقيل...)\n\n"
            f"*المنشآت:* `بناء منشاة` — تزيد الدخل والمزايا\n"
            f"مستشفى | مطار | ميناء | بنك | مصنع | محطة تحلية...\n\n"
            f"*البنية التحتية:* `بناء بنية تحتية`\n"
            f"تزيد سقف المزارع والمنشآت وتزيد دخل الضرائب\n\n"
            f"*القروض:* `البنك الدولي` — 3 أحجام بفوائد مختلفة\n"
            f"*التحويل:* `تحويل [مبلغ] [كود]` — أرسل مثاقيل لدولة أخرى",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('⚔️','الجيش والحرب')}\n\n"
            f"*التجنيد:* `تجنيد [عدد]` — كل جندي بـ 10¥\n\n"
            f"*الهجوم:* `هجوم على [اسم الدولة]`\n"
            f"• لازم تكون على حدود الهدف أو ساحلياً\n"
            f"• الانتصار = غنيمة مثاقيل + أرض جديدة\n"
            f"• لو جيش العدو وصل 0 → *احتلال كامل*\n\n"
            f"*إعلان الحرب:* `اعلن حرب على [دولة]` — Lv.4+\n"
            f"يعطيك +15% قوة هجوم\n\n"
            f"*الأسلحة:* `شراء اسلحة`\n"
            f"سيف → بندقية → مدفع → صاروخ → قنبلة ذرية ☢️\n"
            f"كل سلاح يزيد قوة هجومك في المعارك\n\n"
            f"*cooldown الهجوم:* 5 دقايق (يقل بالمطارات)",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('🏴','الاحتلال والاستعمار')}\n\n"
            f"*الاحتلال:* لما تصفّر جيش دولة → تصير _(محتلة)_\n"
            f"• تجمع ضرائبها تلقائياً\n"
            f"• المحتَلة تقدر تعمل `ثورة` للتحرر\n\n"
            f"*الاستعمار:* `استعمر [دولة]` — بعد الاحتلال\n"
            f"• تقدر تحصد مواردها: `احصد مستعمرة [اسم]`\n"
            f"• تقدر تهديها: `اهدي مستعمرة [اسم] الى [كود]`\n"
            f"• المستعمَرة تقدر `استقلال` بتكلفة كبيرة\n\n"
            f"*التحرر:*\n"
            f"🗡️ `ثورة` — تكلف 30% من جيش المحتل + 15,000¥\n"
            f"✊ `استقلال` — تكلف 60% من جيش المستعمِر + 25,000¥",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('🤝','الدبلوماسية والأحلاف')}\n\n"
            f"*الأحلاف:* `انشاء حلف [اسم]` ثم `دعوة [حلف] [دولة]`\n"
            f"• أعضاء الحلف يتوسعون معاً\n"
            f"• لا يهاجمون بعض\n"
            f"• مضائقهم لا تؤثر عليهم\n\n"
            f"*الهجوم الجماعي:* `هجوم جماعي [حلف] على [دولة]`\n"
            f"• للمؤسس فقط\n"
            f"• كل الأعضاء يشاركون بـ 70-95% من جيشهم\n"
            f"• بونص +20% تنسيق جماعي\n"
            f"• الغنيمة توزع بالتساوي\n"
            f"• الاحتلال يروح للمؤسس\n\n"
            f"*التحالف الدفاعي:* `تحالف دفاعي مع [دولة]`\n"
            f"• يتطلب حلف مشترك\n"
            f"• لو هوجمت، جيش حليفك يدافع تلقائياً\n\n"
            f"*معاهدة السلام:* `معاهدة سلام مع [دولة]` — 5,000¥\n"
            f"• 24 ساعة لا هجوم",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('⚓','المضائق الاستراتيجية')}\n\n"
            f"4 مضائق تتحكم في التجارة والضرائب:\n\n"
            f"🌊 *هرمز* — عمان/إيران\n"
            f"   يؤثر على: السعودية، الكويت، العراق، قطر، الإمارات، البحرين\n\n"
            f"🌊 *باب المندب* — اليمن\n"
            f"   يؤثر على: مصر، الأردن\n\n"
            f"🌊 *السويس* — مصر\n"
            f"   يؤثر على: الأردن، فلسطين، لبنان، سوريا، تركيا، قبرص\n\n"
            f"🌊 *البسفور* — تركيا\n"
            f"   يؤثر على: سوريا، لبنان، قبرص، مصر\n\n"
            f"لما مضيق مغلق → الدول المتأثرة تنتظر 15 دقيقة بدل 10\n"
            f"أعضاء حلف المُغلِق لا يتأثرون ✅\n\n"
            f"`اغلق مضيق [اسم]` | `افتح مضيق [اسم]`",
            parse_mode="Markdown")
        await update.message.reply_text(
            f"{box_title('📈','المستويات والتطور')}\n\n"
            f"🏘️ Lv.1 — *قرية* (0 XP)\n"
            f"🏙️ Lv.2 — *مدينة ناشئة* (500 XP) — تجنيد مخفض\n"
            f"🏰 Lv.3 — *إمارة* (1,500 XP) — وزير دفاع\n"
            f"👑 Lv.4 — *مملكة* (3,000 XP) — دبلوماسية متقدمة\n"
            f"🌟 Lv.5 — *إمبراطورية* (6,000 XP) — مخابرات، تجسس\n"
            f"⚡ Lv.6 — *قوة عظمى* (12,000 XP) — هيمنة اقتصادية\n"
            f"🚀 Lv.7 — *حضارة متقدمة* (25,000 XP) — قوة عظمى\n\n"
            f"تكسب XP من: الهجوم ✅ | جمع الضرائب ✅ | الاستعمار ✅\n\n"
            f"{box_title('⚠️','أحداث تلقائية')}\n\n"
            f"🌪️ *كوارث طبيعية* — تضرب الدول عشوائياً\n"
            f"🗳️ *أحداث سياسية* — تحدث لو رضا الشعب منخفض\n"
            f"📰 *النشرة الإخبارية* — كل 20 دقيقة أخبار اللعبة\n"
            f"😴 *عقوبة الخمول* — لو ما لعبت 7 أيام تخسر موارد\n\n"
            f"{sep()}\n"
            f"💡 اكتب `مساعدة` لقائمة الأوامر الكاملة",
            parse_mode="Markdown")
        return

    # ======= مساعدة =======
    if ntext in ["مساعده","اوامر","help"]:
        wars_status = "⚔️ الحروب مفتوحة" if data.get("wars_enabled", True) else "🕊️ الحروب موقوفة"
        await update.message.reply_text(
            f"{box_title('📖','دليل اللعبة')}\n\n"
            f"━━ 🎮 *البداية* ━━\n"
            f"`انشاء دولة` — طلب تسجيل\n"
            f"`كودي` — عرض كودك\n\n"
            f"━━ 📊 *المعلومات* ━━\n"
            f"`حالة دولتي` — الاقتصاد والجيش\n"
            f"`دولتي` — السكان والأحوال\n"
            f"`دولي` — الإمبراطورية كاملة\n"
            f"`قائمة الدول` | `خريطة` | `المتصدرين` | `المضائق`\n"
            f"`إحصائيات اللعبة` — أرقام وسجلات اللعبة\n\n"
            f"━━ 💰 *الاقتصاد* ━━\n"
            f"`جمع الضرائب` — كل 10 دقايق\n"
            f"`بناء مزرعة` | `بناء منشاة` | `بناء بنية تحتية`\n"
            f"`العاصمة [اسم]` | `تحويل [مبلغ] [كود]`\n"
            f"`البنك الدولي` | `ديوني` | `مهرجان شعبي`\n"
            f"`تعديل علمي` ← ارفق صورة\n\n"
            f"━━ ⚔️ *الجيش والحرب* ━━\n"
            f"`تجنيد [عدد]` | `جيشي`\n"
            f"`هجوم على [دولة]`\n"
            f"`اعلن حرب على [دولة]` — Lv.4+ (+15% هجوم)\n"
            f"`اضرب [دولة] بقنبلة_ذرية` — ☢️\n\n"
            f"━━ 🔫 *الأسلحة* ━━\n"
            f"`شراء اسلحة` | `شراء [سلاح] [عدد]`\n"
            f"`سوق الاسلحه الدولي` | `بيع سلاح [اسم] [كمية] [سعر]`\n"
            f"`شراء من سوق [رقم]`\n\n"
            f"━━ 🏴 *الاحتلال والاستعمار* ━━\n"
            f"`استعمر [اسم]` — حوّل محتلة → مستعمرة\n"
            f"`احصد مستعمرة [اسم]` | `تحرير [اسم]`\n"
            f"`اهدي مستعمرة [اسم] الى [كود]`\n"
            f"`ثورة` — تحرر من احتلال\n"
            f"`استقلال` — تحرر من استعمار\n\n"
            f"━━ 🤝 *الدبلوماسية* ━━\n"
            f"`معاهدة سلام مع [دولة]` — Lv.4+ (5000¥)\n"
            f"`تحالف دفاعي مع [دولة]` — يتطلب حلف مشترك\n"
            f"`إلغاء تحالف دفاعي مع [دولة]`\n"
            f"`احمي [دولة]`\n\n"
            f"━━ 🕵️ *المخابرات* ━━\n"
            f"`تجسس على [دولة]` — Lv.5+ (3000¥)\n\n"
            f"━━ ⚓ *المضائق* ━━\n"
            f"`اغلق مضيق [اسم]` | `افتح مضيق [اسم]`\n"
            f"هرمز | باب المندب | السويس | البسفور\n\n"
            f"━━ 🏛️ *الأحلاف* ━━\n"
            f"`انشاء حلف [اسم]` | `دعوة [حلف] [دولة]`\n"
            f"`قائمة الاحلاف` | `حلف [اسم]`\n"
            f"`جيش الحلف [اسم]` — قوة الحلف الكاملة\n"
            f"`هجوم جماعي [حلف] على [دولة]` — للمؤسس فقط\n"
            f"`مغادرة حلف [اسم]` | `طرد من حلف [حلف] [دولة]`\n"
            f"`حل حلف [اسم]`\n\n"
            f"{sep()}\n"
            f"{wars_status}",
            parse_mode="Markdown")
        return

    # ======= اوامر الادمن =======
    if is_admin(uid):
        # انشاء دولة نصي (بدون علم)
        if ntext.startswith("دوله "):
            parts = text.split()
            if len(parts)<4:
                await update.message.reply_text("الصيغة: دولة [المنطقة] [الاسم] [الكود]"); return
            code=parts[-1].upper(); region=parts[1]; cname=" ".join(parts[2:-1])
            if code not in data["pending_codes"]: await update.message.reply_text(f"الكود {code} مش موجود."); return
            if region not in AVAILABLE_REGIONS: await update.message.reply_text(f"'{region}' مش في القائمة."); return
            for _,pp in data["players"].items():
                if pp["region"]==region: await update.message.reply_text(f"'{region}' محجوزة."); return
            pid = data["pending_codes"].pop(code)
            pl  = new_player(region, cname, pid)
            data["players"][str(pid)] = pl; save_data(data)
            await update.message.reply_text(f"✅ *{cname}* ← {region} | كود: `{pl['player_code']}`", parse_mode="Markdown")
            try: await context.bot.send_message(chat_id=pid, text=f"🎊 *دولتك اتفعّلت!*\n🏳️ *{cname}*\nاكتب *مساعدة*", parse_mode="Markdown")
            except: pass
            return

        # حذف دولة
        if ntext.startswith("حذف دوله "):
            cname = ntext.replace("حذف دوله","").strip()
            for puid,pp in list(data["players"].items()):
                if pp["country_name"]==cname:
                    del data["players"][puid]; save_data(data)
                    await update.message.reply_text(f"✅ تم حذف {cname}."); return
            await update.message.reply_text(f"❌ مش لاقي '{cname}'."); return

        # تحويل ملكية دولة
        if ntext.startswith("تحويل ملكيه "):
            # الصيغة: تحويل ملكية [اسم الدولة] الى [كود اللاعب الجديد]
            parts = ntext.replace("تحويل ملكيه","").strip().split(" الى ")
            if len(parts) != 2:
                await update.message.reply_text("الصيغة: `تحويل ملكية [اسم الدولة] الى [كود اللاعب]`", parse_mode="Markdown"); return
            cname = parts[0].strip()
            target_ref = parts[1].strip()
            # ابحث عن الدولة
            found_uid, found_p = find_by_name(data, cname)
            if not found_p:
                await update.message.reply_text(f"❌ مش لاقي دولة '{cname}'."); return
            # ابحث عن المالك الجديد — بالكود أو بالاسم
            new_uid, new_p = find_by_code(data, target_ref)
            if not new_p:
                new_uid, new_p = find_by_name(data, target_ref)
            # لو رقم مباشر
            if not new_p and target_ref.isdigit():
                new_uid = target_ref
            if not new_uid:
                await update.message.reply_text(f"❌ مش لاقي لاعب '{target_ref}'.\nاستخدم كود اللاعب (مثل: ABC123)"); return
            data["players"][str(new_uid)] = data["players"].pop(str(found_uid))
            save_data(data)
            new_name = new_p["country_name"] if new_p else f"ID:{new_uid}"
            await update.message.reply_text(
                f"✅ ملكية *{found_p['country_name']}* تحولت لـ *{new_name}*",
                parse_mode="Markdown"); return

        # اختبار النشرة الإخبارية
        if ntext in ["نشره","اخبار","تجربه النشره"]:
            news_text = _build_news(data)
            if news_text:
                await update.message.reply_text(news_text, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ لا يوجد لاعبين بعد.")
            return

        # تفعيل النشرة في هذه القناة/المجموعة
        if ntext in ["تفعيل النشره","فعّل النشره","فعل النشره"]:
            chat_id = update.effective_chat.id
            data["news_channel_id"] = chat_id
            save_data(data)
            await update.message.reply_text(
                f"📡 *تم تفعيل النشرة الإخبارية!*\n"
                f"القناة: `{chat_id}`\n"
                f"ستصلك نشرة كل *20 دقيقة* تلقائياً ✅\n\n"
                f"لإيقافها: `إيقاف النشرة`",
                parse_mode="Markdown")
            return

        # إيقاف النشرة
        if ntext in ["ايقاف النشره","ايقاف النشرة","وقف النشره","وقف النشرة","إيقاف النشرة","إيقاف النشره"]:
            data["news_channel_id"] = 0
            save_data(data)
            await update.message.reply_text("🔕 *تم إيقاف النشرة الإخبارية.*", parse_mode="Markdown")
            return

        # فتح/قفل الحروب
        if ntext in ["اقفل الحروب","وقف الحروب"]:
            data["wars_enabled"] = False
            save_data(data)
            await update.message.reply_text("🕊️ *تم إيقاف الحروب!* لا أحد يستطيع الهجوم الآن.", parse_mode="Markdown"); return

        if ntext in ["افتح الحروب","شغّل الحروب","شغل الحروب"]:
            data["wars_enabled"] = True
            save_data(data)
            await update.message.reply_text("⚔️ *تم فتح الحروب!* يمكن للدول الهجوم الآن.", parse_mode="Markdown"); return

        # ======= إعادة تشغيل اللعبة =======
        if ntext in ["اعاده اللعبه","اعادة اللعبة","ريست","reset اللعبه"]:
            await update.message.reply_text(
                f"⚠️ *تأكيد إعادة التشغيل*\n{sep()}\n"
                f"سيتم:\n"
                f"• حذف جميع الدول والبيانات\n"
                f"• الإبقاء على القناة الإخبارية\n"
                f"• الإبقاء على العلامات في مجلد flags\n\n"
                f"اكتب `تأكيد الريست` للمتابعة.",
                parse_mode="Markdown"); return

        if ntext == "تاكيد الريست":
            # احفظ الإعدادات المهمة قبل التصفير
            news_ch  = data.get("news_channel_id", 0)
            wars_on  = data.get("wars_enabled", True)
            straits  = data.get("straits", {})

            # ابنِ تقرير الفائزين قبل التصفير
            players = data.get("players", {})
            report  = ""
            if players:
                by_xp   = sorted(players.values(), key=lambda x: x.get("xp",0),    reverse=True)
                by_gold = sorted(players.values(), key=lambda x: x.get("gold",0),  reverse=True)
                by_army = sorted(players.values(), key=lambda x: x.get("army",0),  reverse=True)
                by_terr = sorted(players.values(), key=lambda x: x.get("territories",1), reverse=True)
                report  = (
                    f"{box_title('🏆','نتائج الموسم المنتهي')}\n\n"
                    f"⭐ *الأكثر تقدماً:* {by_xp[0]['country_name']} — {by_xp[0].get('xp',0):,} XP\n"
                    f"💰 *الأغنى:* {by_gold[0]['country_name']} — {CUR}{by_gold[0].get('gold',0):,}\n"
                    f"⚔️ *الأقوى جيشاً:* {by_army[0]['country_name']} — {by_army[0].get('army',0):,} جندي\n"
                    f"🗺️ *الأوسع:* {by_terr[0]['country_name']} — {by_terr[0].get('territories',1)} منطقة\n"
                    f"{sep()}\n🎮 *اللعبة أُعيدت — موسم جديد بدأ!*"
                )

            # التصفير الكامل
            fresh = {
                "players":         {},
                "pending_codes":   {},
                "market":          [],
                "shipments":       [],
                "alliance_requests": {},
                "dissolve_requests": {},
                "last_disaster":   0,
                "wars_enabled":    wars_on,
                "straits":         straits,
                "organizations":   {},
                "org_invites":     {},
                "news_channel_id": news_ch,
            }
            # احفظ نسخة احتياطية من القديم
            import shutil
            if os.path.exists(DATA_FILE):
                shutil.copy(DATA_FILE, DATA_FILE + ".season_backup")
            # اكتب البيانات الجديدة
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(fresh, f, ensure_ascii=False, indent=2)

            await update.message.reply_text(
                f"✅ *تمت إعادة تشغيل اللعبة!*\n{sep()}\n"
                f"جميع البيانات صُفِّرت 🔄\n"
                f"نسخة احتياطية حُفظت ✅",
                parse_mode="Markdown")

            # ابعت تقرير الفائزين للقناة الإخبارية لو موجودة
            if report and news_ch:
                try:
                    await context.bot.send_message(chat_id=news_ch, text=report, parse_mode="Markdown")
                except: pass

            # بلّغ كل اللاعبين السابقين
            for uid_str, p in players.items():
                try:
                    await context.bot.send_message(
                        chat_id=int(uid_str),
                        text=f"🔄 *انتهى الموسم!*\n{sep()}\n"
                             f"اللعبة أُعيدت من جديد.\n"
                             f"اكتب *انشاء دولة* للانضمام من جديد! 🎮",
                        parse_mode="Markdown")
                except: pass
            return

        # الطلبات المعلقة
        if ntext == "الطلبات":
            if not data["pending_codes"]: await update.message.reply_text("✅ مفيش طلبات."); return
            msg = f"{box_title('📋','طلبات الانضمام')}\n\n"
            for c,v in data["pending_codes"].items():
                msg += f"• `{c}` — ID: `{v}`\n"
            await update.message.reply_text(msg, parse_mode="Markdown"); return

        # اوامر الادمن
        if ntext in ["اوامر الادمن","ادمن"]:
            await update.message.reply_text(
                f"{box_title('🔧','اوامر الادمن')}\n\n"
                f"*إدارة اللاعبين:*\n"
                f"• `دولة [منطقة] [اسم] [كود]` — انشاء دولة\n"
                f"• `حذف دولة [اسم]` — حذف دولة\n"
                f"• `تحويل ملكية [اسم] الى [كود]` — تغيير الملكية\n"
                f"• `منح مثاقيل [دولة] [مبلغ]` — منح مثاقيل\n"
                f"• `منح جيش [دولة] [عدد]` — منح جنود\n"
                f"• `منح xp [دولة] [عدد]` — منح XP\n"
                f"• `تحرير ادمن [دولة]` — تحرير قسري من احتلال\n"
                f"• `تجميد [دولة]` — تجميد/رفع تجميد\n\n"
                f"*مراقبة:*\n"
                f"• `إحصائيات` — نظرة عامة على اللعبة\n"
                f"• `سجل [دولة]` — بيانات كاملة للدولة\n"
                f"• `الطلبات` — طلبات الانضمام\n\n"
                f"*تحكم:*\n"
                f"• `اعلان [نص]` — إرسال لكل اللاعبين\n"
                f"• `اقفل الحروب` / `افتح الحروب`\n"
                f"• `تفعيل النشرة` / `إيقاف النشرة`\n"
                f"• `نشرة` — اختبار النشرة فوراً\n"
                f"• `تسريع الكوارث` — تشغيل كارثة فوراً\n"
                f"• `اعادة اللعبة` — تصفير كامل\n"
                f"• ارسل صورة + `دولة [منطقة] [اسم] [كود]` لاضافة علم",
                parse_mode="Markdown"); return

        # ======= منح مثاقيل =======
        if ntext.startswith("منح مثاقيل "):
            parts = ntext.replace("منح مثاقيل","").strip().split()
            if len(parts) < 2:
                await update.message.reply_text("❌ الصيغة: `منح مثاقيل [دولة] [مبلغ]`", parse_mode="Markdown"); return
            amount_s = parts[-1]
            country_q = " ".join(parts[:-1])
            try: amount = int(amount_s); assert amount != 0
            except: await update.message.reply_text("❌ المبلغ لازم رقم (ممكن سالب للخصم)."); return
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            data["players"][tuid]["gold"] = max(0, tp.get("gold",0) + amount)
            save_data(data)
            action = f"+{amount:,}" if amount > 0 else f"{amount:,}"
            await update.message.reply_text(
                f"✅ *منح مثاقيل*\n{sep()}\n{tp['country_name']}: {action}{CUR}\n"
                f"الرصيد الجديد: {CUR}{data['players'][tuid]['gold']:,}", parse_mode="Markdown")
            try:
                sign = "+" if amount > 0 else ""
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🎁 *منحة من الإدارة!*\n{sep()}\n{sign}{amount:,}{CUR} أُضيفت لخزينتك",
                    parse_mode="Markdown")
            except: pass
            return

        # ======= منح جيش =======
        if ntext.startswith("منح جيش "):
            parts = ntext.replace("منح جيش","").strip().split()
            if len(parts) < 2:
                await update.message.reply_text("❌ الصيغة: `منح جيش [دولة] [عدد]`", parse_mode="Markdown"); return
            amount_s = parts[-1]
            country_q = " ".join(parts[:-1])
            try: amount = int(amount_s); assert amount != 0
            except: await update.message.reply_text("❌ العدد لازم رقم (ممكن سالب للخصم)."); return
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            data["players"][tuid]["army"] = max(0, tp.get("army",0) + amount)
            save_data(data)
            action = f"+{amount:,}" if amount > 0 else f"{amount:,}"
            await update.message.reply_text(
                f"✅ *منح جيش*\n{sep()}\n{tp['country_name']}: {action} جندي\n"
                f"الجيش الجديد: {data['players'][tuid]['army']:,}", parse_mode="Markdown")
            try:
                sign = "+" if amount > 0 else ""
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🎖️ *تعزيز من الإدارة!*\n{sep()}\n{sign}{amount:,} جندي أُضيفوا لجيشك",
                    parse_mode="Markdown")
            except: pass
            return

        # ======= منح XP =======
        if ntext.startswith("منح xp ") or ntext.startswith("منح ايكس بي "):
            clean = ntext.replace("منح xp","").replace("منح ايكس بي","").strip()
            parts = clean.split()
            if len(parts) < 2:
                await update.message.reply_text("❌ الصيغة: `منح xp [دولة] [عدد]`", parse_mode="Markdown"); return
            amount_s = parts[-1]
            country_q = " ".join(parts[:-1])
            try: amount = int(amount_s); assert amount != 0
            except: await update.message.reply_text("❌ العدد لازم رقم."); return
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            old_xp  = tp.get("xp", 0)
            new_xp  = max(0, old_xp + amount)
            old_lvl = get_level(old_xp)["level"]
            data["players"][tuid]["xp"] = new_xp
            new_lvl = get_level(new_xp)
            save_data(data)
            lvl_change = f" → Lv.{new_lvl['level']} {new_lvl['emoji']}" if new_lvl["level"] != old_lvl else ""
            action = f"+{amount:,}" if amount > 0 else f"{amount:,}"
            await update.message.reply_text(
                f"✅ *منح XP*\n{sep()}\n{tp['country_name']}: {action} XP{lvl_change}\n"
                f"إجمالي XP: {new_xp:,}", parse_mode="Markdown")
            if new_lvl["level"] != old_lvl:
                try:
                    await context.bot.send_message(chat_id=int(tuid),
                        text=f"🎊 *ترقية من الإدارة!*\n{sep()}\nأصبحت {new_lvl['emoji']} *{new_lvl['name']}*",
                        parse_mode="Markdown")
                except: pass
            return

        # ======= تحرير ادمن — تحرير قسري =======
        if ntext.startswith("تحرير ادمن ") or ntext.startswith("تحرير admin "):
            country_q = ntext.replace("تحرير ادمن","").replace("تحرير admin","").strip()
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            occ  = tp.get("occupied_by")
            col  = tp.get("colony_of")
            if not occ and not col:
                await update.message.reply_text(f"❌ {tp['country_name']} مش محتلة أو مستعمرة."); return
            orig = tp["country_name"].replace(" (محتلة)","").replace(" (مستعمرة)","")
            data["players"][tuid]["country_name"] = orig
            data["players"][tuid]["occupied_by"]  = None
            data["players"][tuid]["colony_of"]    = None
            save_data(data)
            status = f"محتلة بواسطة {occ}" if occ else f"مستعمرة لـ {col}"
            await update.message.reply_text(
                f"✅ *تحرير قسري*\n{sep()}\n{orig} كانت {status}\nحرة الآن ✅", parse_mode="Markdown")
            try:
                await context.bot.send_message(chat_id=int(tuid),
                    text=f"🎉 *قرار إداري*\n{sep()}\nتم تحرير *{orig}* بقرار من الإدارة!", parse_mode="Markdown")
            except: pass
            return

        # ======= تجميد دولة =======
        if ntext.startswith("تجميد "):
            country_q = ntext.replace("تجميد","").strip()
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            currently_frozen = tp.get("frozen", False)
            data["players"][tuid]["frozen"] = not currently_frozen
            save_data(data)
            if not currently_frozen:
                await update.message.reply_text(
                    f"🧊 *تم تجميد {tp['country_name']}*\n{sep()}\nلا يستطيع اللاعب استخدام أي أوامر\n"
                    f"اكتب `تجميد {country_q}` مرة ثانية لرفع التجميد", parse_mode="Markdown")
                try:
                    await context.bot.send_message(chat_id=int(tuid),
                        text=f"🧊 *دولتك مجمّدة مؤقتاً من الإدارة*\nتواصل مع الأدمن للاستفسار.",
                        parse_mode="Markdown")
                except: pass
            else:
                await update.message.reply_text(
                    f"✅ *رُفع التجميد عن {tp['country_name']}*", parse_mode="Markdown")
                try:
                    await context.bot.send_message(chat_id=int(tuid),
                        text=f"✅ *رُفع التجميد عن دولتك*\nيمكنك اللعب مجدداً!", parse_mode="Markdown")
                except: pass
            return

        # ======= إحصائيات =======
        if ntext in ["إحصائيات","احصائيات","stats","إحصاء"]:
            players_all = data.get("players", {})
            n = len(players_all)
            if n == 0:
                await update.message.reply_text("❌ لا يوجد لاعبين بعد."); return
            total_gold  = sum(p.get("gold",0) for p in players_all.values())
            total_army  = sum(p.get("army",0) for p in players_all.values())
            total_terr  = sum(p.get("territories",1) for p in players_all.values())
            at_war_n    = sum(1 for p in players_all.values() if p.get("at_war"))
            occupied_n  = sum(1 for p in players_all.values() if p.get("occupied_by"))
            colony_n    = sum(1 for p in players_all.values() if p.get("colony_of"))
            frozen_n    = sum(1 for p in players_all.values() if p.get("frozen"))
            avg_gold    = total_gold // n
            avg_army    = total_army // n
            avg_lvl     = sum(get_level(p.get("xp",0))["level"] for p in players_all.values()) / n
            richest     = max(players_all.values(), key=lambda p: p.get("gold",0))
            strongest   = max(players_all.values(), key=lambda p: p.get("army",0))
            top_xp      = max(players_all.values(), key=lambda p: p.get("xp",0))
            market_n    = len([m for m in data.get("market",[]) if m.get("type")=="weapons"])
            await update.message.reply_text(
                f"{box_title('📊','إحصائيات اللعبة')}\n\n"
                f"👥 اللاعبين: *{n}*\n"
                f"⚔️ في حرب: *{at_war_n}* | 🏴 محتلين: *{occupied_n}* | 🔗 مستعمرات: *{colony_n}*\n"
                f"🧊 مجمّدين: *{frozen_n}*\n"
                f"{sep()}\n"
                f"💰 إجمالي المثاقيل: *{CUR}{total_gold:,}*\n"
                f"💰 متوسط/لاعب: *{CUR}{avg_gold:,}*\n"
                f"⚔️ إجمالي الجيوش: *{total_army:,}*\n"
                f"⚔️ متوسط/لاعب: *{avg_army:,}*\n"
                f"🗺️ إجمالي الأراضي: *{total_terr}*\n"
                f"📈 متوسط المستوى: *{avg_lvl:.1f}*\n"
                f"{sep()}\n"
                f"💰 الأغنى: *{richest['country_name']}* ({CUR}{richest.get('gold',0):,})\n"
                f"⚔️ الأقوى: *{strongest['country_name']}* ({strongest.get('army',0):,} جندي)\n"
                f"⭐ الأعلى: *{top_xp['country_name']}* (Lv.{get_level(top_xp.get('xp',0))['level']})\n"
                f"🛒 عروض السوق: *{market_n}*\n"
                f"{'⚔️ الحروب مفتوحة' if data.get('wars_enabled',True) else '🕊️ الحروب موقوفة'}",
                parse_mode="Markdown"); return

        # ======= سجل دولة — debug =======
        if ntext.startswith("سجل "):
            country_q = ntext.replace("سجل","").strip()
            tuid, tp = find_by_name(data, country_q)
            if not tp: await update.message.reply_text(f"❌ مش لاقي '{country_q}'."); return
            lvl = get_level(tp.get("xp",0))
            happy = calc_happiness(tp)
            facs_txt  = ", ".join(f"{k}×{v}" for k,v in tp.get("facilities",{}).items()) or "—"
            crops_txt = ", ".join(f"{k}×{v}" for k,v in tp.get("crops",{}).items()) or "—"
            weap_txt  = ", ".join(f"{k}×{v}" for k,v in tp.get("weapons",{}).items()) or "—"
            orgs_tmp3 = data.get("organizations", {})
            allies_set = {m for ov in orgs_tmp3.values() if tp["country_name"] in ov["members"] for m in ov["members"] if m != tp["country_name"]}
            allies_txt = ", ".join(allies_set) or "—"
            wars_txt   = ", ".join(tp.get("at_war",[])) or "—"
            pacts_txt  = ", ".join(tp.get("defensive_pacts",[])) or "—"
            msg = (
                f"{box_title('🔍','سجل: ' + tp['country_name'])}\n"
                f"🆔 UID: `{tuid}`\n"
                f"📍 المنطقة: {tp.get('region','—')}\n"
                f"🏅 Lv.{lvl['level']} | ⭐ {tp.get('xp',0):,} XP\n"
                f"💰 مثاقيل: {CUR}{tp.get('gold',0):,}\n"
                f"⚔️ جيش: {tp.get('army',0):,}\n"
                f"🗺️ أراضي: {tp.get('territories',1)}\n"
                f"🏗️ بنية: Lv.{tp.get('infrastructure',0)}\n"
                f"😊 رضا: {happy}%\n"
                f"{sep()}\n"
                f"🏭 منشآت: {facs_txt}\n"
                f"🌾 مزارع: {crops_txt}\n"
                f"🔫 أسلحة: {weap_txt}\n"
                f"{sep()}\n"
                f"🤝 حلفاء: {allies_txt}\n"
                f"⚔️ حروب: {wars_txt}\n"
                f"🛡️ أحلاف دفاعية: {pacts_txt}\n"
                f"{sep()}\n"
                f"🏴 محتلة بواسطة: {tp.get('occupied_by') or '—'}\n"
                f"🔗 مستعمرة لـ: {tp.get('colony_of') or '—'}\n"
                f"☢️ نووي محظور: {tp.get('nuke_banned',0)} دورة\n"
                f"🧊 مجمّد: {'نعم' if tp.get('frozen') else 'لا'}\n"
                f"🕐 آخر نشاط: {int((time.time()-tp.get('last_active',0))//3600)} ساعة"
            )
            await safe_md(update.message, msg); return

        # ======= إعلان لكل اللاعبين =======
        if ntext.startswith("اعلان "):
            announcement = text[text.lower().find("اعلان")+len("اعلان"):].strip()
            if not announcement:
                await update.message.reply_text("❌ الصيغة: `اعلان [النص]`", parse_mode="Markdown"); return
            players_all = data.get("players", {})
            sent = 0; failed = 0
            msg_out = (
                f"{box_title('📢','إعلان رسمي')}\n"
                f"{announcement}"
            )
            for puid in players_all:
                try:
                    await context.bot.send_message(chat_id=int(puid), text=msg_out, parse_mode="Markdown")
                    sent += 1
                except: failed += 1
            # أرسله للقناة كمان
            ch = data.get("news_channel_id", 0)
            if ch:
                try: await context.bot.send_message(chat_id=ch, text=msg_out, parse_mode="Markdown")
                except: pass
            await update.message.reply_text(
                f"✅ الإعلان أُرسل!\n📨 وصل: {sent} | ❌ فشل: {failed}"); return

        # ======= تسريع الكوارث — للاختبار =======
        if ntext in ["تسريع الكوارث","كارثة فورية","test كارثة","اختبار كارثة"]:
            players_all = data.get("players", {})
            if not players_all:
                await update.message.reply_text("❌ لا يوجد لاعبين."); return
            import random as _rnd
            uid_t = _rnd.choice(list(players_all.keys()))
            pt    = players_all[uid_t]
            eligible = []
            for dis in DISASTERS:
                regions_filter = dis.get("regions", {})
                if regions_filter:
                    allowed = []
                    for rlist in regions_filter.values(): allowed += rlist
                    if pt.get("region","") not in allowed: continue
                eligible.append(dis)
            if not eligible: eligible = DISASTERS
            dis   = _rnd.choice(eligible)
            loss_desc = "—"
            if dis["effect"] == "army":
                pct  = _rnd.uniform(*dis["loss"])
                loss = max(10, int(pt["army"]*pct))
                data["players"][uid_t]["army"] = max(0, pt["army"]-loss)
                loss_desc = f"{loss:,} جندي"
            elif dis["effect"] == "gold":
                pct  = _rnd.uniform(*dis["loss"])
                loss = max(50, int(pt["gold"]*pct))
                data["players"][uid_t]["gold"] = max(0, pt["gold"]-loss)
                loss_desc = f"{loss:,}¥"
            data["players"][uid_t]["disasters_hit"] = pt.get("disasters_hit",0)+1
            save_data(data)
            dis_msg = (
                f"{dis['emoji']} *كارثة — {dis['name']}!*\n{sep()}\n"
                f"ضربت *{pt['country_name']}*!\n📢 {dis['msg']}\n"
                f"{sep()}\n💔 الخسارة: *{loss_desc}*"
            )
            try: await context.bot.send_message(chat_id=int(uid_t), text=dis_msg, parse_mode="Markdown")
            except: pass
            ch = data.get("news_channel_id", 0)
            if ch:
                try: await context.bot.send_message(chat_id=ch, text=dis_msg, parse_mode="Markdown")
                except: pass
            await update.message.reply_text(
                f"✅ *كارثة اختبارية!*\n{sep()}\n"
                f"{dis['emoji']} {dis['name']} ضربت *{pt['country_name']}*\n"
                f"💔 {loss_desc}", parse_mode="Markdown"); return

# ==================== Callbacks ====================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id
    data  = load_data()
    p     = get_player(data, uid)

    if query.data == "cancel":
        await query.edit_message_text("❌ تم الالغاء."); return

    # ---- سداد مبكر للقرض ----
    if query.data.startswith("loan_repay_"):
        if not p: await query.edit_message_text("❌ مش مسجل."); return
        try:
            idx = int(query.data.replace("loan_repay_",""))
        except:
            await query.edit_message_text("❌ خطأ في البيانات."); return
        loans = data["players"][str(uid)].get("loans", [])
        if idx >= len(loans):
            await query.edit_message_text("❌ القرض غير موجود أو سُدِّد بالفعل."); return
        loan = loans[idx]
        due  = loan["due"]
        if p["gold"] < due:
            await query.edit_message_text(
                f"❌ *رصيد غير كافٍ!*\n{sep()}\n"
                f"المطلوب: *{CUR}{due:,}*\n"
                f"رصيدك:  *{CUR}{p['gold']:,}*\n"
                f"الناقص: *{CUR}{due-p['gold']:,}*",
                parse_mode="Markdown"); return
        # سداد القرض
        data["players"][str(uid)]["gold"] -= due
        loans.pop(idx)
        data["players"][str(uid)]["loans"] = loans
        save_data(data)
        remaining_loans = loans
        extra = ""
        if remaining_loans:
            extra = f"\n{sep()}\n📋 *قروض متبقية: {len(remaining_loans)}*"
            for ln in remaining_loans:
                extra += f"\n  • {ln['name']}: {CUR}{ln['due']:,} بعد {ln['remaining_cycles']} دورة"
        await query.edit_message_text(
            f"✅ *تم السداد المبكر!*\n{sep()}\n"
            f"🏦 {loan['name']}\n"
            f"💸 سُدِّد: *{CUR}{due:,}*\n"
            f"💰 رصيدك الآن: *{CUR}{p['gold']-due:,}*"
            f"{extra}",
            parse_mode="Markdown"); return

    # ---- القرض ----
    if query.data.startswith("loan_"):
        loan_id = query.data.replace("loan_","")
        if not p: await query.edit_message_text("❌ مش مسجل."); return
        loan_def = next((l for l in LOAN_OPTIONS if l["id"]==loan_id), None)
        if not loan_def: await query.edit_message_text("❌ قرض غير معروف."); return
        active = p.get("loans",[])
        if len(active) >= 2:
            await query.edit_message_text("❌ عندك 2 قروض بالفعل. سدّد أولاً."); return
        total_due = int(loan_def["amount"] * (1+loan_def["interest"]))
        new_loan  = {
            "id": loan_id,
            "name": loan_def["name"],
            "amount": loan_def["amount"],
            "due": total_due,
            "remaining_cycles": loan_def["due_cycles"],
        }
        data["players"][str(uid)]["gold"]  = p["gold"] + loan_def["amount"]
        data["players"][str(uid)]["loans"] = active + [new_loan]
        save_data(data)
        await query.edit_message_text(
            f"🏦 *تم صرف القرض!*\n{sep()}\n"
            f"{loan_def['emoji']} {loan_def['name']}\n"
            f"💵 المبلغ: +{loan_def['amount']:,}¥\n"
            f"💰 رصيدك الآن: {p['gold']+loan_def['amount']:,}¥\n"
            f"{sep()}\n"
            f"📅 السداد: {total_due:,}¥ خلال {loan_def['due_cycles']} دورات حصاد\n"
            f"⚠️ عدم السداد = عقوبة 50% إضافية!",
            parse_mode="Markdown")
        return

    # ---- قبول التحالف ----




    if query.data.startswith("build_"):
        resource = query.data.replace("build_","")
        if not p: await query.edit_message_text("❌ مش مسجل."); return
        if resource not in RESOURCE_FACILITIES: await query.edit_message_text("❌ مورد غير معروف."); return
        f         = RESOURCE_FACILITIES[resource]
        infra     = p.get("infrastructure", 0)
        region    = p.get("region", "")
        infra_req = get_facility_infra_req(resource, region)
        if infra < infra_req:
            await query.edit_message_text(
                f"🔒 *{f['name']}* تحتاج بنية تحتية *Lv.{infra_req}*\n"
                f"بنيتك الحالية: Lv.{infra}\n"
                f"طور بنيتك أولاً بأمر `بناء بنية تحتية`",
                parse_mode="Markdown"); return
        cost = f["base_cost"]
        if p["gold"] < cost:
            await query.edit_message_text(f"❌ محتاج {cost:,}¥. عندك {p['gold']:,}."); return
        data["players"][str(uid)]["gold"] -= cost
        facs = data["players"][str(uid)].get("facilities",{})
        facs[resource] = facs.get(resource,0)+1
        data["players"][str(uid)]["facilities"] = facs
        leveled_up, new_lvl = add_xp(data, uid, 120)
        save_data(data)
        special_txt = f"\n✨ {f['special']}" if f.get("special") else f"\n📦 +{f['amount']} {resource}/دورة"
        msg = (f"🏭 *تم البناء!*\n{'─'*28}\n{f['emoji']} *{f['name']}*"
               f"{special_txt}\n💰 {p['gold']-cost:,}¥ متبقي\n⭐+120")
        if leveled_up: msg += f"\n🎊 {new_lvl['name']} {new_lvl['emoji']}"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    # ---- مهرجان شعبي ----
    if query.data.startswith("festival_"):
        if not p: await query.edit_message_text("❌ مش مسجل."); return
        try: idx = int(query.data.replace("festival_",""))
        except: await query.edit_message_text("❌ خطأ."); return
        FESTIVALS = [
            {"name": "مهرجان شعبي صغير", "cost": 5_000,  "bonus": 5,  "emoji": "🎪"},
            {"name": "حفلة وطنية",       "cost": 15_000, "bonus": 12, "emoji": "🎆"},
            {"name": "عيد وطني كبير",    "cost": 40_000, "bonus": 25, "emoji": "🎊"},
            {"name": "توزيع إعانات",     "cost": 25_000, "bonus": 18, "emoji": "🏥"},
        ]
        if idx >= len(FESTIVALS): await query.edit_message_text("❌ خيار غير صحيح."); return
        f = FESTIVALS[idx]
        if p["gold"] < f["cost"]:
            await query.edit_message_text(f"❌ محتاج {f['cost']:,}¥. عندك {p['gold']:,}¥."); return
        # الحد الأقصى للـ bonus مخزون = 30 نقطة
        cur_bonus = p.get("happiness_bonus", 0)
        if cur_bonus >= 30:
            await query.edit_message_text("❌ الشعب مبسوط بما يكفي دلوقتي، انتظر شوية."); return
        new_bonus = min(30, cur_bonus + f["bonus"])
        data["players"][str(uid)]["gold"] -= f["cost"]
        data["players"][str(uid)]["happiness_bonus"] = new_bonus
        save_data(data)
        new_happy = calc_happiness(data["players"][str(uid)])
        await query.edit_message_text(
            f"{f['emoji']} *{f['name']}!*\n{sep()}\n"
            f"💸 -{f['cost']:,}¥\n"
            f"😊 الرضا: *{new_happy}%* {status_emoji(new_happy)}\n"
            f"✨ تأثير المهرجان: +{f['bonus']}% (يتلاشى تدريجياً)",
            parse_mode="Markdown")
        return

    # ---- زراعة محصول ----
    if query.data.startswith("farm_"):
        crop = query.data.replace("farm_","")
        if not p: await query.edit_message_text("❌ مش مسجل."); return
        if crop not in FARM_CROPS: await query.edit_message_text("❌ محصول غير معروف."); return
        # فحص الحد الأقصى
        infra       = p.get("infrastructure", 0)
        max_farms   = get_max_farms(infra)
        total_farms = sum(p.get("crops",{}).values())
        if total_farms >= max_farms:
            await query.edit_message_text(
                f"❌ وصلت الحد الأقصى ({max_farms} مزرعة)!\n"
                f"💡 ابن بنية تحتية Lv.{infra+1} عشان تزيد الحد → {get_max_farms(infra+1)} مزرعة"); return
        fc   = FARM_CROPS[crop]
        cost = get_farm_cost(data, crop)
        if p["gold"] < cost:
            await query.edit_message_text(f"❌ محتاج {cost:,}¥. عندك {p['gold']:,}."); return
        preferred = REGION_PREFERRED_CROPS.get(p.get("region",""),[])
        amount    = int(fc["amount"]*1.5) if crop in preferred else fc["amount"]
        bonus_txt = " (+50% ⭐)" if crop in preferred else ""
        data["players"][str(uid)]["gold"] -= cost
        crops_inv = data["players"][str(uid)].get("crops",{})
        crops_inv[crop] = crops_inv.get(crop,0)+1
        data["players"][str(uid)]["crops"] = crops_inv
        ca = data["players"][str(uid)].get("crops_amount",{})
        ca[crop] = amount
        data["players"][str(uid)]["crops_amount"] = ca
        leveled_up, new_lvl = add_xp(data, uid, 70)
        save_data(data)
        remaining = max_farms - (total_farms + 1)
        msg = (f"🌾 *تمت الزراعة!*\n{'─'*28}\n{fc['emoji']} *{fc['name']}*{bonus_txt}\n"
               f"📦 {amount}طن/دورة | يُباع تلقائياً\n💰 {p['gold']-cost:,}¥ متبقي\n"
               f"🌾 مزارعك: {total_farms+1}/{max_farms} (متبقي {remaining})\n⭐+70")
        if leveled_up: msg += f"\n🎊 {new_lvl['name']} {new_lvl['emoji']}"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    # ---- قبول دعوة حلف ----
    if query.data.startswith("org_accept_"):
        req_key = query.data.replace("org_accept_","")
        req = data.get("org_invites",{}).get(req_key)
        if not req:
            await query.edit_message_text("❌ انتهت صلاحية الدعوة."); return
        org_name = req["org_name"]
        orgs = data.get("organizations",{})
        if org_name not in orgs:
            await query.edit_message_text("❌ الحلف لم يعد موجوداً."); return
        country_name = req["to_name"]
        if country_name not in orgs[org_name]["members"]:
            data["organizations"][org_name]["members"].append(country_name)
        del data["org_invites"][req_key]
        save_data(data)
        await query.edit_message_text(
            f"🏛️ *انضممت لحلف {org_name}!*\n{sep()}\n"
            f"مرحباً بك في *{org_name}* 🎉\n"
            f"💡 `حلف {org_name}` لعرض التفاصيل",
            parse_mode="Markdown")
        try:
            founder_name = orgs[org_name]["founder"]
            for fuid, fp in data["players"].items():
                if fp.get("country_name") == founder_name:
                    await context.bot.send_message(chat_id=int(fuid),
                        text=f"🎉 *عضو جديد!*\n{sep()}\n*{country_name}* انضم لحلف *{org_name}*!",
                        parse_mode="Markdown")
                    break
        except: pass
        return

    # ---- رفض دعوة حلف ----
    if query.data.startswith("org_reject_"):
        req_key = query.data.replace("org_reject_","")
        req = data.get("org_invites",{}).get(req_key)
        if not req:
            await query.edit_message_text("❌ انتهت صلاحية الدعوة."); return
        org_name    = req["org_name"]
        from_name   = req["from_name"]
        country_name = req["to_name"]
        del data["org_invites"][req_key]
        save_data(data)
        await query.edit_message_text(f"❌ رفضت الانضمام لحلف *{org_name}*.", parse_mode="Markdown")
        try:
            for fuid, fp in data["players"].items():
                if fp.get("country_name") == from_name:
                    await context.bot.send_message(chat_id=int(fuid),
                        text=f"❌ *{country_name}* رفض دعوة حلف *{org_name}*.",
                        parse_mode="Markdown")
                    break
        except: pass
        return

# ==================== /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"{box_title('🌍','لعبة الشرق الأوسط')}\n\n"
        f"👋 أهلاً *{name}*!\n\n"
        f"🎮 ابنِ دولتك من قرية إلى إمبراطورية\n"
        f"⚔️ جنّد جيوشك واحتل الأراضي\n"
        f"🤝 أسّس أحلافاً وشنّ هجمات جماعية\n"
        f"🌾 زرع وحصد واستثمر في البنية التحتية\n"
        f"⚓ تحكّم في مضائق هرمز، السويس، باب المندب، البسفور\n\n"
        f"{sep()}\n"
        f"▶️ `انشاء دولة`   📖 `مساعدة`",
        parse_mode="Markdown")

# ==================== main ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, handle_message))

    loop = asyncio.get_event_loop()
    loop.create_task(disaster_loop(app))
    loop.create_task(harvest_loop(app))
    loop.create_task(news_loop(app))
    loop.create_task(political_events_loop(app))
    loop.create_task(inactivity_loop(app))

    print("✅ البوت شغال!")
    app.run_polling()

if __name__ == "__main__":
    main()
