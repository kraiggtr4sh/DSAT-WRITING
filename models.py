from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel
import json

class SessionStats(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    correct: int = 0
    total: int = 0
    streak: int = 0
    best_streak: int = 0

class TopicStats(SQLModel, table=True):
    topic_id: str = Field(primary_key=True)
    correct: int = 0
    total: int = 0

class Mistake(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str
    passage: str
    question: str
    choices_json: str  # Store as JSON string
    correct_index: int
    picked_index: int
    explanation: str
    date: str = Field(default_factory=lambda: datetime.now().strftime("%b %d"))

    @property
    def choices(self) -> List[str]:
        return json.loads(self.choices_json)

    @choices.setter
    def choices(self, value: List[str]):
        self.choices_json = json.dumps(value)

class QuestionPool(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: str = Field(index=True)
    passage: str
    question: str
    choices_json: str
    correct_index: int
    explanation: str
    used_count: int = 0

    @property
    def choices(self) -> List[str]:
        return json.loads(self.choices_json)

    @choices.setter
    def choices(self, value: List[str]):
        self.choices_json = json.dumps(value)

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

def create_db_and_tables(engine):
    SQLModel.metadata.create_all(engine)
