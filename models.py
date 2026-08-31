from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Schedule(db.Model):
    __tablename__ = "schedule"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    day = db.Column(db.String(20), nullable=False)
    time_start = db.Column(db.String(5), nullable=False)
    time_end = db.Column(db.String(5), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    lesson_type = db.Column(db.String(50), nullable=True)
    teacher = db.Column(db.String(200), nullable=True)
    room = db.Column(db.String(50), nullable=True)

    notes = db.relationship("Note", backref="schedule", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "day": self.day,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "subject": self.subject,
            "lesson_type": self.lesson_type,
            "teacher": self.teacher,
            "room": self.room,
        }


class Note(db.Model):
    __tablename__ = "note"

    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey("schedule.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "text": self.text,
            "created_at": self.created_at.isoformat(),
        }


class Grade(db.Model):
    __tablename__ = "grade"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(200), nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False)
    grade_type = db.Column(db.String(50), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "subject": self.subject,
            "grade": self.grade,
            "date": self.date.isoformat(),
            "grade_type": self.grade_type,
        }


class SemesterAverage(db.Model):
    __tablename__ = "semester_average"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False)
    average = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "average": self.average,
            "created_at": self.created_at.isoformat(),
        }