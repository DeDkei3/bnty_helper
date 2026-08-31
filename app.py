import calendar
from datetime import date, datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request

from models import db, Schedule, Note, Grade, SemesterAverage

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///student.db'
db.init_app(app)

MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


@app.route('/')
def home():
    today = date.today()
    lessons_today = Schedule.query.filter_by(date=today).order_by(Schedule.time_start).all()
    return render_template('home.html', today=today, lessons=lessons_today)


@app.route('/schedule')
def schedule_calendar():
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)

    # calendar.Calendar умеет строить сетку недель месяца сразу с учётом
    # того, с какого дня недели начинается месяц (у нас недели с понедельника)
    cal = calendar.Calendar(firstweekday=0)  # 0 = понедельник
    month_days = cal.monthdatescalendar(year, month)
    # monthdatescalendar возвращает список недель, каждая — список из 7 date(),
    # включая "хвостики" соседних месяцев для заполнения сетки

    # достаём из базы все даты в этом месяце, у которых есть пары —
    # чтобы подсветить в календаре дни, где что-то есть
    days_with_lessons = {
        row.date for row in Schedule.query.filter(
            db.extract('year', Schedule.date) == year,
            db.extract('month', Schedule.date) == month,
        ).all()
    }

    # даты в этом месяце, у которых есть хотя бы одна заметка
    # (заметка привязана к паре через schedule_id, поэтому джойним таблицы)
    notes_dates_query = (
        db.session.query(Schedule.date)
        .join(Note, Note.schedule_id == Schedule.id)
        .filter(
            db.extract('year', Schedule.date) == year,
            db.extract('month', Schedule.date) == month,
        )
        .distinct()
        .all()
    )
    days_with_notes = {row[0] for row in notes_dates_query}

    # для кнопок "предыдущий/следующий месяц"
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    return render_template(
        'schedule_calendar.html',
        month_days=month_days,
        days_with_lessons=days_with_lessons,
        days_with_notes=days_with_notes,
        year=year,
        month=month,
        month_name=MONTH_NAMES_RU[month],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today=date.today(),
    )


@app.route('/schedule/<date_str>', methods=['GET', 'POST'])
def schedule_day(date_str):
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return "Некорректная дата", 400

    if request.method == 'POST':
        schedule_id = request.form.get('schedule_id', type=int)
        text = request.form.get('text', '').strip()
        if schedule_id and text:
            note = Note(schedule_id=schedule_id, text=text)
            db.session.add(note)
            db.session.commit()
        return redirect(url_for('schedule_day', date_str=date_str))

    lessons = Schedule.query.filter_by(date=selected_date).order_by(Schedule.time_start).all()
    return render_template('schedule_day.html', selected_date=selected_date, lessons=lessons)


@app.route('/notes')
def notes_list():
    notes = (
        Note.query.join(Schedule, Note.schedule_id == Schedule.id)
        .order_by(Schedule.date.desc(), Schedule.time_start.desc())
        .all()
    )
    return render_template('notes.html', notes=notes)


@app.route('/notes/<int:note_id>/delete', methods=['POST'])
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    # запомним дату пары, чтобы вернуть пользователя туда же, откуда он пришёл
    schedule_date = note.schedule.date.isoformat()
    db.session.delete(note)
    db.session.commit()
    redirect_to = request.form.get('redirect_to', 'notes')
    if redirect_to == 'day':
        return redirect(url_for('schedule_day', date_str=schedule_date))
    return redirect(url_for('notes_list'))


@app.route('/grades', methods=['GET', 'POST'])
def grades_list():
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        grade_value = request.form.get('grade', type=int)
        grade_date = request.form.get('date', '').strip()
        grade_type = request.form.get('grade_type', '').strip()

        if subject and grade_value and grade_date:
            try:
                parsed_date = datetime.strptime(grade_date, '%Y-%m-%d').date()
            except ValueError:
                parsed_date = date.today()
            entry = Grade(
                subject=subject,
                grade=grade_value,
                date=parsed_date,
                grade_type=grade_type or None,
            )
            db.session.add(entry)
            db.session.commit()
        return redirect(url_for('grades_list'))

    grades = Grade.query.order_by(Grade.date.desc()).all()

    if grades:
        overall_average = round(sum(g.grade for g in grades) / len(grades), 2)
    else:
        overall_average = None

    # средний балл по каждому предмету — для графика
    subject_averages = {}
    subject_counts = {}
    for g in grades:
        subject_averages[g.subject] = subject_averages.get(g.subject, 0) + g.grade
        subject_counts[g.subject] = subject_counts.get(g.subject, 0) + 1
    chart_labels = list(subject_averages.keys())
    chart_values = [
        round(subject_averages[s] / subject_counts[s], 2) for s in chart_labels
    ]

    return render_template(
        'grades.html',
        grades=grades,
        overall_average=overall_average,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )


@app.route('/grades/<int:grade_id>/delete', methods=['POST'])
def delete_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    db.session.delete(grade)
    db.session.commit()
    return redirect(url_for('grades_list'))


@app.route('/calculator', methods=['GET', 'POST'])
def calculator():
    result = None
    error = None

    if request.method == 'POST':
        raw_input = request.form.get('grades_input', '').strip()
        label = request.form.get('label', '').strip()

        # разбираем строку вида "8, 9, 7, 10" в список чисел
        raw_parts = raw_input.replace(';', ',').split(',')
        numbers = []
        for part in raw_parts:
            part = part.strip()
            if not part:
                continue
            try:
                numbers.append(float(part))
            except ValueError:
                error = f'Не удалось распознать значение "{part}" как оценку'
                break

        if not error:
            if not numbers:
                error = 'Введите хотя бы одну оценку'
            else:
                result = round(sum(numbers) / len(numbers), 2)
                if label:
                    entry = SemesterAverage(label=label, average=result)
                    db.session.add(entry)
                    db.session.commit()

    saved_results = SemesterAverage.query.order_by(SemesterAverage.created_at.desc()).all()
    return render_template(
        'calculator.html',
        result=result,
        error=error,
        saved_results=saved_results,
    )


@app.route('/calculator/<int:entry_id>/delete', methods=['POST'])
def delete_saved_average(entry_id):
    entry = SemesterAverage.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('calculator'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)