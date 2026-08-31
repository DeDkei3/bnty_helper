from flask import Flask
from models import db, Schedule
from parse_schedule import main as parse_main

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///student.db'
db.init_app(app)


def import_schedule():
    lessons = parse_main()

    with app.app_context():
        db.create_all()

        existing_count = Schedule.query.count()
        if existing_count > 0:
            print(f"В базе уже есть {existing_count} записей расписания.")
            confirm = input("Удалить старые и залить заново? (да/нет): ")
            if confirm.strip().lower() != "да":
                print("Отменено.")
                return
            Schedule.query.delete()
            db.session.commit()

        for lesson in lessons:
            entry = Schedule(
                date=lesson["date"],
                day=lesson["day"],
                time_start=lesson["time_start"],
                time_end=lesson["time_end"],
                subject=lesson["subject"],

                lesson_type=lesson["type"],
                teacher=lesson["teacher"],
                room=lesson["room"],
            )
            db.session.add(entry)

        db.session.commit()
        print(f"Загружено {len(lessons)} занятий в базу данных.")


if __name__ == "__main__":
    import_schedule()