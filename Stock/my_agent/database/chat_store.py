# my_agent/database/chat_store.py
import os
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import DictCursor
import json
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)
load_dotenv()

class ChatStore:
    def __init__(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str = 'localhost',
        port: str = '5432',
        max_messages: int = 12,
        model_name: str = 'all-MiniLM-L6-v2'
    ):
        self.conn_params = {
            'dbname': dbname,
            'user': user,
            'password': password,
            'host': host,
            'port': port
        }
        self.max_messages = max_messages
        self.vector_dimension = 384
        print(f"Khởi tạo Embedder '{model_name}'...")
        self.embedder = SentenceTransformer(model_name)
        print("Embedder đã sẵn sàng.")
        self._init_db()

    def _get_conn(self):
        """
        Tạo, cấu hình (với pgvector) và trả về một kết nối CSDL mới.
        """
        conn = psycopg2.connect(**self.conn_params)
        register_vector(conn)
        return conn

    def _init_db(self):
        """Khởi tạo database và kích hoạt extension 'vector'."""
        # Sử dụng _get_conn() để đảm bảo vector được đăng ký
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # 1. KÍCH HOẠT EXTENSION PGVECTOR
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit() # Commit riêng extension
                print("Extension 'vector' đã được kích hoạt.")

                # 2. Create users table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(100) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 3. Create chat_history table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        message JSONB NOT NULL,
                        embedding VECTOR({self.vector_dimension}),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                print("Database đã được khởi tạo/xác nhận.")

    def add_user(self, username: str) -> int:
        """Add new user and return user id"""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO users (username) VALUES (%s) RETURNING id",
                        (username,)
                    )
                    user_id = cur.fetchone()[0]
                    conn.commit()
                    return user_id
                except psycopg2.IntegrityError:
                    conn.rollback() 
                    cur.execute(
                        "SELECT id FROM users WHERE username = %s",
                        (username,)
                    )
                    return cur.fetchone()[0]

    def add_message(self, user_id_int: int, role: str, content: str) -> str:
        """
        Lưu một tin nhắn vào CSDL. 
        Hàm này tự động tạo timestamp và message dict.
        
        Args:
            user_id_int: ID (dạng số) của user.
            role: Vai trò ('user' hoặc 'model').
            content: Nội dung tin nhắn.
        Returns:
            Một chuỗi xác nhận.
        """
        # 1. Tool tự tạo dict và timestamp
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"Đang tạo embedding cho: {content[:20]}...")
        # 2. Chỉ encode nội dung
        embedding = self.embedder.encode(content)
        print("Đã tạo embedding.")
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_history (user_id, message, embedding)
                    VALUES (%s, %s, %s)
                    """,
                    # 3. Lưu dict đầy đủ và embedding
                    (user_id_int, json.dumps(message), embedding)
                )
                
                # 4. Giữ N tin nhắn gần nhất (Logic này giữ nguyên)
                cur.execute(
                    """
                    DELETE FROM chat_history
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                            FROM chat_history WHERE user_id = %s
                        ) t WHERE rn > %s
                    )
                    """,
                    (user_id_int, self.max_messages)
                )
                
                conn.commit()
                print("Đã lưu tin nhắn vào CSDL.")
        
        # 5. Trả về xác nhận cho LLM
        return f"Message from {role} saved successfully."

    def get_messages(self, user_id_int: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lấy N tin nhắn gần nhất (Short-term / Recent Memory)"""
        limit = limit or self.max_messages
        
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    """
                    SELECT message, created_at
                    FROM chat_history
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id_int, limit)
                )
                messages = [dict(row) for row in cur.fetchall()]
                return messages[::-1]

    def get_relevant_history(self, user_id_int: int, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Lấy 'k' tin nhắn cũ LIÊN QUAN NHẤT (Long-term / Semantic Memory).
        """
        print(f"Đang tìm kiếm bối cảnh liên quan cho: {query[:20]}...")
        query_embedding = self.embedder.encode(query)
        
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    """
                    SELECT message, 1 - (embedding <-> %s) AS similarity
                    FROM chat_history
                    WHERE user_id = %s
                    ORDER BY embedding <-> %s
                    LIMIT %s
                    """,
                    (query_embedding, user_id_int, query_embedding, k)
                )
                results = [dict(row) for row in cur.fetchall()]
                print(f"Đã tìm thấy {len(results)} bối cảnh liên quan.")
                return results
            
print("Đang khởi tạo ChatStore (kết nối CSDL)...")
try:
    chat_store = ChatStore(
        dbname=os.getenv('POSTGRES_DB', 'stockdb'),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', 'Thanhlong@2701'),
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432')
    )
    print("ChatStore đã sẵn sàng.")
except Exception as e:
    print(f"LỖI NGHIÊM TRỌNG: Không thể khởi tạo ChatStore. {e}")
    chat_store = None