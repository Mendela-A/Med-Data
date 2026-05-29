import os
import sys
import random
from datetime import date, timedelta

# Ensure python path includes root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from models import AmbulatoryRecord, User

app = create_app()
with app.app_context():
    # Find a valid user to assign as creator
    user = User.query.first()
    if not user:
        print("No users found in database!")
        sys.exit(1)
    
    # Ukrainian Names list
    first_names_m = ["Іван", "Петро", "Василь", "Михайло", "Олександр", "Дмитро", "Сергій", "Андрій", "Володимир", "Ярослав"]
    last_names_m = ["Коваленко", "Мельник", "Шевченко", "Бойко", "Козак", "Мороз", "Лисенко", "Кравченко", "Ткаченко", "Олійник"]
    patronymics_m = ["Петрович", "Іванович", "Васильович", "Михайлович", "Олександрович", "Дмитрович", "Сергійович", "Андрійович", "Володимирович", "Ярославович"]
    
    first_names_f = ["Марія", "Ольга", "Олена", "Ірина", "Наталія", "Тетяна", "Світлана", "Анна", "Галина", "Оксана"]
    last_names_f = ["Коваленко", "Мельник", "Шевченко", "Бойко", "Козак", "Мороз", "Лисенко", "Кравченко", "Ткаченко", "Олійник"]
    patronymics_f = ["Петрівна", "Іванівна", "Василівна", "Михайлівна", "Олександрівна", "Дмитрівна", "Сергіївна", "Андріївна", "Володимирівна", "Ярославівна"]

    doctors = ["Шевченко А. В.", "Петренко В. О.", "Іванова С. М.", "Коваленко О. І.", "Лисенко М. П."]
    diagnoses = [
        "Гіпертонічна хвороба II ст.",
        "Гострий бронхіт",
        "ГРВІ, середньої важкості",
        "Цукровий діабет II типу",
        "Ішемічна хвороба серця",
        "Остеохондроз хребта",
        "Гострий гастрит",
        "Хронічний холецистит",
        "Вегето-судинна дистонія",
        "Пневмонія позалікарняна"
    ]
    statuses = ["Опрацьовується", "Виписаний", "Порушені вимоги"]
    comments = [
        "Направлено на ЕКГ",
        "Рекомендовано домашній режим",
        "Препарати призначено повністю",
        "Повторний огляд через тиждень",
        "Скарги на загальну слабкість",
        "Стан покращився",
        None
    ]

    print("Generating 50 random ambulatory records in database...")
    
    # Get the starting count of records
    initial_count = AmbulatoryRecord.query.count()
    
    for i in range(1, 51):
        # Gender
        is_male = random.choice([True, False])
        if is_male:
            name = f"{random.choice(last_names_m)} {random.choice(first_names_m)} {random.choice(patronymics_m)}"
        else:
            lname = random.choice(last_names_f)
            if not (lname.endswith("ко") or lname.endswith("ак")):
                lname = lname + "а"
            name = f"{lname} {random.choice(first_names_f)} {random.choice(patronymics_f)}"

        # Find unique journal number
        journal_num = f"{initial_count + 100 + i}/А"
        
        # Date within last 30 days
        rec_date = date.today() - timedelta(days=random.randint(0, 28))
        
        # Birth date between 1950 and 2015
        birth_year = random.randint(1950, 2015)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        b_date = date(birth_year, birth_month, birth_day)
        
        doc = random.choice(doctors)
        diag = random.choice(diagnoses)
        status = random.choice(statuses)
        comm = random.choice(comments)
        
        record = AmbulatoryRecord(
            journal_number=journal_num,
            date=rec_date,
            full_name=name,
            birth_date=b_date,
            doctor=doc,
            diagnosis=diag,
            discharge_status=status,
            comment=comm,
            created_by=user.id,
            updated_by=user.id
        )
        db.session.add(record)
        
    db.session.commit()
    new_count = AmbulatoryRecord.query.count()
    print(f"Successfully generated 50 ambulatory records! Total count is now {new_count}.")
