import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data/app.db"
RECORDS = 3000

# 🇺🇦 Українські ПІБ
last_names = ["Іваненко", "Шевченко", "Ковальчук", "Мельник", "Кравчук", "Романюк", "Бондар", "Сидоренко"]
first_names_m = ["Іван", "Петро", "Андрій", "Олексій", "Сергій", "Микола"]
first_names_f = ["Олена", "Марія", "Наталія", "Ірина", "Світлана", "Галина"]
patronymics_m = ["Іванович", "Петрович", "Андрійович", "Сергійович"]
patronymics_f = ["Іванівна", "Петрівна", "Андріївна", "Сергіївна"]

departments = ["Терапевтичне", "Хірургічне", "Кардіологічне", "Неврологічне", "Реанімаційне", "Травматологічне"]
doctors = ["Зелік О.О.", "Ковальчук М.С.", "Бондар Л.І.", "Сидоренко П.П.", "Романюк В.В.", "Іванчук А.М."]
histories = ["Планове лікування", "Госпіталізація в ургентному порядку", "Стаціонарне лікування", "Післяопераційне спостереження"]
comments = ["", "Стан стабільний", "Рекомендовано амбулаторне лікування", "Потребує подальшого спостереження"]
discharge_statuses = ["Виписаний", "Переведений", "Помер"]

def random_full_name():
    is_male = random.choice([True, False])
    if is_male:
        return f"{random.choice(last_names)} {random.choice(first_names_m)} {random.choice(patronymics_m)}"
    else:
        return f"{random.choice(last_names)} {random.choice(first_names_f)} {random.choice(patronymics_f)}"

def random_date(days_back=120):
    base = datetime.now() - timedelta(days=days_back)
    return base + timedelta(days=random.randint(0, days_back))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

for _ in range(RECORDS):
    discharge_date = random_date()
    status = random.choices(discharge_statuses, weights=[80, 15, 5], k=1)[0]
    date_of_death = discharge_date if status == "Помер" else None

    cur.execute("""
        INSERT INTO records (
            date_of_discharge,
            full_name,
            discharge_department,
            treating_physician,
            history,
            k_days,
            discharge_status,
            date_of_death,
            comment,
            created_by,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        discharge_date.strftime("%Y-%m-%d"),
        random_full_name(),
        random.choice(departments),
        random.choice(doctors),
        random.choice(histories),
        random.randint(1, 30),
        status,
        date_of_death.strftime("%Y-%m-%d") if date_of_death else None,
        random.choice(comments),
        1,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

conn.commit()
conn.close()

print("✔ 3000 українських записів успішно додано в records")
