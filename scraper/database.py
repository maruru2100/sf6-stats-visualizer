from sqlalchemy import create_engine, text
from config import DATABASE_URL, ENV_ERROR

# エンジンの作成
engine = create_engine(DATABASE_URL) if not ENV_ERROR else None

def init_db():
    """FlywayがDB管理を行うため、ここでは接続確認のみ実施"""
    if ENV_ERROR or not engine:
        return
    
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection verified.")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")