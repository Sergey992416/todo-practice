from datetime import datetime, timedelta
from typing import Optional, List, Literal

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship


DATABASE_URL = "sqlite:///./dev.db"
JWT_SECRET = "change_me_super_secret"  
JWT_ALG = "HS256"
TOKEN_EXPIRE_DAYS = 7

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class UserDB(Base):
  __tablename__ = "users"
  id = Column(String, primary_key=True)
  email = Column(String, unique=True, nullable=False, index=True)
  password_hash = Column(String, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  tasks = relationship("TaskDB", back_populates="user", cascade="all, delete-orphan")

class TaskDB(Base):
  __tablename__ = "tasks"
  id = Column(String, primary_key=True)
  user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
  title = Column(String, nullable=False)
  status = Column(String, nullable=False, default="backlog")  
  created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
  today_at = Column(DateTime, nullable=True)
  time_spent_sec = Column(Integer, default=0, nullable=False)
  updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

  user = relationship("UserDB", back_populates="tasks")

Base.metadata.create_all(bind=engine)

def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def hash_password(p: str) -> str:
  return pwd_context.hash(p)

def verify_password(p: str, h: str) -> bool:
  return pwd_context.verify(p, h)

def create_token(user_id: str) -> str:
  exp = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
  payload = {"user_id": user_id, "exp": exp}
  return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def get_current_user_id(
  creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> str:
  token = creds.credentials
  try:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    user_id = payload.get("user_id")
    if not user_id:
      raise HTTPException(status_code=401, detail="Invalid token")
    return user_id
  except JWTError:
    raise HTTPException(status_code=401, detail="Invalid token")

Status = Literal["backlog", "today", "done"]

class RegisterIn(BaseModel):
  email: EmailStr
  password: str = Field(min_length=6,max_length=72)

class LoginIn(BaseModel):
  email: EmailStr
  password: str= Field(min_length=6,max_length=72)

class UserOut(BaseModel):
  id: str
  email: EmailStr

class AuthOut(BaseModel):
  token: str
  user: UserOut

class TaskOut(BaseModel):
  id: str
  title: str
  status: Status
  createdAt: int
  todayAt: Optional[int]
  timeSpentSec: int
  updatedAt: int

class TaskCreateIn(BaseModel):
  title: str = Field(min_length=1)
  status: Optional[Status] = None
  todayAt: Optional[int] = None
  timeSpentSec: Optional[int] = None

class TaskUpdateIn(BaseModel):
  title: Optional[str] = None
  status: Optional[Status] = None
  todayAt: Optional[int] = None  
  timeSpentSec: Optional[int] = None

def dt_to_ms(dt: datetime) -> int:
  return int(dt.timestamp() * 1000)

def ms_to_dt(ms: int) -> datetime:
  return datetime.utcfromtimestamp(ms / 1000)

def task_db_to_out(t: TaskDB) -> TaskOut:
  return TaskOut(
    id=t.id,
    title=t.title,
    status=t.status,  
    createdAt=dt_to_ms(t.created_at),
    todayAt=dt_to_ms(t.today_at) if t.today_at else None,
    timeSpentSec=t.time_spent_sec,
    updatedAt=dt_to_ms(t.updated_at),
  )


app = FastAPI(title="Todo Backend (FastAPI)")


app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=False,  
  allow_methods=["*"],
  allow_headers=["*"],
)

@app.get("/health")
def health():
  return {"ok": True}


import uuid

@app.post("/auth/register", response_model=AuthOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
  exists = db.query(UserDB).filter(UserDB.email == body.email).first()
  if exists:
    raise HTTPException(status_code=409, detail="Email already in use")

  user = UserDB(
    id=str(uuid.uuid4()),
    email=body.email,
    password_hash=hash_password(body.password),
  )
  db.add(user)
  db.commit()

  token = create_token(user.id)
  return AuthOut(token=token, user=UserOut(id=user.id, email=user.email))

@app.post("/auth/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
  user = db.query(UserDB).filter(UserDB.email == body.email).first()
  if not user or not verify_password(body.password, user.password_hash):
    raise HTTPException(status_code=401, detail="Invalid credentials")

  token = create_token(user.id)
  return AuthOut(token=token, user=UserOut(id=user.id, email=user.email))


@app.get("/tasks", response_model=List[TaskOut])
def get_tasks(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
  tasks = (
    db.query(TaskDB)
    .filter(TaskDB.user_id == user_id)
    .order_by(TaskDB.created_at.desc())
    .all()
  )
  return [task_db_to_out(t) for t in tasks]

@app.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
  body: TaskCreateIn,
  user_id: str = Depends(get_current_user_id),
  db: Session = Depends(get_db),
):
  now = datetime.utcnow()
  t = TaskDB(
    id=str(uuid.uuid4()),
    user_id=user_id,
    title=body.title,
    status=(body.status or "backlog"),
    created_at=now,
    today_at=ms_to_dt(body.todayAt) if body.todayAt else None,
    time_spent_sec=int(body.timeSpentSec or 0),
    updated_at=now,
  )
  db.add(t)
  db.commit()
  db.refresh(t)
  return task_db_to_out(t)

@app.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(
  task_id: str,
  body: TaskUpdateIn,
  user_id: str = Depends(get_current_user_id),
  db: Session = Depends(get_db),
):
  t = db.query(TaskDB).filter(TaskDB.id == task_id, TaskDB.user_id == user_id).first()
  if not t:
    raise HTTPException(status_code=404, detail="Task not found")

  if body.title is not None:
    if not body.title.strip():
      raise HTTPException(status_code=400, detail="Title cannot be empty")
    t.title = body.title

  if body.status is not None:
    t.status = body.status

  if body.todayAt is not None:
    
    t.today_at = ms_to_dt(body.todayAt)

 

  if body.timeSpentSec is not None:
    if body.timeSpentSec < 0:
      raise HTTPException(status_code=400, detail="timeSpentSec must be >= 0")
    t.time_spent_sec = int(body.timeSpentSec)

  t.updated_at = datetime.utcnow()
  db.commit()
  db.refresh(t)
  return task_db_to_out(t)

@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(
  task_id: str,
  user_id: str = Depends(get_current_user_id),
  db: Session = Depends(get_db),
):
  t = db.query(TaskDB).filter(TaskDB.id == task_id, TaskDB.user_id == user_id).first()
  if not t:
    raise HTTPException(status_code=404, detail="Task not found")

  db.delete(t)
  db.commit()
  return None
