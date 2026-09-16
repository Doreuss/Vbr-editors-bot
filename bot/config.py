import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_GROUP_ID = int(os.environ["ADMIN_GROUP_ID"])
ADMIN_USER_IDS = {
    int(x) for x in os.environ.get("ADMIN_USER_IDS", "").split(",") if x.strip()
}
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# --- Бизнес-правила (меняются здесь, без правки логики хендлеров) ---
COOLDOWN_DAYS = 14  # 2 недели между отказом/резервом и предложением новой попытки
REMINDER_AFTER_HOURS = 24
REVIEW_SLA_DAYS = 3  # срок проверки, который видит кандидат

TEST_REFERENCES = [
    "https://www.tiktok.com/@edits/video/7677310807947988232",
    "https://www.tiktok.com/@edits/video/7676064935285247250",
]
TEST_SOUND_URL = "https://tiktok.com/music/OMNISCIENT-SLOWED-683206697/80004880"
